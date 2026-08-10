from __future__ import annotations

import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.payments import _get_paddle_auth_header, get_paddle_api_url, get_paddle_config
from app.core.database import get_db
from app.core.security import get_current_admin
from app.models.pricing import Pricing, PricingFeature
from app.schemas.pricing import PricingFeatureResponse, PricingResponse, PricingUpsert

public_router = APIRouter()
admin_router = APIRouter()


SUPPORTED_FEATURE_KEYS = {
    "transcript_english", "summary_english", "pdf_download", "standard_processing",
    "video_quota", "unlimited_videos", "unlimited_duration_size", "transcript_languages",
    "summary_languages", "actionable_prompts", "powerful_ai", "priority_support", "youtube",
}

FEATURE_REQUIREMENTS = {
    "transcript_english": lambda body: body.transcript_language_mode in ("english", "all"),
    "summary_english": lambda body: body.summary_language_mode in ("english", "all"),
    "summary_languages": lambda body: body.summary_language_mode == "all",
    "actionable_prompts": lambda body: body.prompts_enabled,
    "powerful_ai": lambda body: body.ai_model == "powerful",
    "pdf_download": lambda body: body.pdf_download_enabled,
    "priority_support": lambda body: body.priority_support_enabled,
    "youtube": lambda body: body.youtube_enabled,
}


def _validate_display_features(body: PricingUpsert) -> None:
    for feature in body.features:
        if feature.feature_key not in SUPPORTED_FEATURE_KEYS:
            raise HTTPException(
                status_code=400,
                detail="Each display feature must use a supported entitlement key.",
            )
        requirement = FEATURE_REQUIREMENTS.get(feature.feature_key or "")
        if feature.included and requirement is not None and not requirement(body):
            raise HTTPException(
                status_code=400,
                detail=f"Feature '{feature.feature_key}' is marked included but its entitlement is disabled.",
            )


def _clean_plan_values(body: PricingUpsert) -> dict[str, Any]:
    _validate_display_features(body)
    values = body.model_dump(exclude={"features"})
    # A one-time payment grants a fixed allowance once. It must never turn
    # into a daily/monthly/yearly reset simply because the admin selected a
    # periodic quota in the form.
    if values["billing_type"] == "one_time":
        values["video_quota_period"] = "lifetime"
    quota_period = values["video_quota_period"]
    quota_limit = values["video_quota_limit"]
    quota_unlimited = values["video_quota_unlimited"]
    values["daily_video_limit"] = quota_limit if quota_period == "daily" and not quota_unlimited else None
    values["daily_video_quota_unlimited"] = quota_unlimited or quota_period != "daily"
    values["monthly_video_limit"] = quota_limit if quota_period == "monthly" and not quota_unlimited else None
    values["monthly_video_quota_unlimited"] = quota_unlimited or quota_period != "monthly"
    for key in ("max_file_size_mb", "max_duration_minutes"):
        if values[key] is not None:
            values[key] = str(values[key])
    if values["daily_video_quota_unlimited"]:
        values["daily_video_limit"] = None
    if values["monthly_video_quota_unlimited"]:
        values["monthly_video_limit"] = None
    if values["max_file_size_unlimited"]:
        values["max_file_size_mb"] = None
    if values["max_duration_unlimited"]:
        values["max_duration_minutes"] = None
    return values


def _feature_payload(plan: Pricing) -> list[PricingFeatureResponse]:
    return [
        PricingFeatureResponse(
            id=feature.id,
            feature_key=feature.feature_key,
            label=feature.label,
            included=feature.included,
            sort_order=feature.sort_order,
        )
        for feature in getattr(plan, "_features", [])
    ]


async def _get_plan(plan_id: uuid.UUID, db: AsyncSession) -> Pricing:
    plan = (await db.execute(select(Pricing).where(Pricing.id == plan_id))).scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="Pricing plan not found.")
    return plan


async def _load_features(plan: Pricing, db: AsyncSession) -> None:
    plan._features = (
        await db.execute(select(PricingFeature).where(PricingFeature.pricing_id == plan.id).order_by(PricingFeature.sort_order, PricingFeature.id))
    ).scalars().all()


def _response(plan: Pricing) -> PricingResponse:
    return PricingResponse(
        **{column.name: getattr(plan, column.name) for column in Pricing.__table__.columns},
        features=_feature_payload(plan),
    )


async def _paddle_call(config: dict[str, str], method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if not config["api_key"]:
        raise HTTPException(status_code=500, detail="Paddle API key is missing.")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.request(
            method,
            f"{get_paddle_api_url()}{path}",
            headers={"Authorization": _get_paddle_auth_header(config["api_key"]), "Content-Type": "application/json"},
            json=payload,
        )
    if response.status_code not in (200, 201):
        try:
            detail = response.json().get("error", {}).get("detail") or response.json().get("error", {}).get("code")
        except Exception:
            detail = None
        raise HTTPException(status_code=502, detail=f"Paddle request failed: {detail or response.text[:200]}")
    return response.json().get("data", {})


async def _create_paddle_catalog(plan: Pricing, config: dict[str, str]) -> tuple[str, str]:
    product = await _paddle_call(
        config,
        "POST",
        "/products",
        {"name": plan.name, "description": plan.description or plan.name, "tax_category": "saas"},
    )
    product_id = product.get("id")
    if not product_id:
        raise HTTPException(status_code=502, detail="Paddle did not return a product ID.")
    price = await _paddle_call(
        config,
        "POST",
        "/prices",
        {
            "product_id": product_id,
            "description": f"{plan.name} price",
            "name": plan.name,
            "billing_cycle": ({"interval": plan.billing_interval, "frequency": plan.billing_frequency} if plan.billing_type == "recurring" else None),
            "unit_price": {"amount": str(plan.price_amount_minor), "currency_code": plan.currency_code},
            # These plans represent one BriefRoom subscription/purchase only.
            # Without this, Paddle defaults to a 1-100 quantity range and
            # renders the quantity selector in overlay checkout.
            "quantity": {"minimum": 1, "maximum": 1},
        },
    )
    price_id = price.get("id")
    if not price_id:
        raise HTTPException(status_code=502, detail="Paddle did not return a price ID.")
    return product_id, price_id


async def _sync_paddle_plan(plan: Pricing, old: Pricing | None, config: dict[str, str]) -> None:
    if plan.billing_type == "free":
        if old and old.paddle_price_id:
            await _paddle_call(config, "PATCH", f"/prices/{old.paddle_price_id}", {"status": "archived"})
        plan.paddle_product_id = None
        plan.paddle_price_id = None
        return

    price_changed = old is None or any(
        getattr(old, key) != getattr(plan, key)
        for key in ("price_amount_minor", "currency_code", "billing_type", "billing_interval", "billing_frequency")
    )
    product_id = old.paddle_product_id if old else plan.paddle_product_id
    old_price_id = old.paddle_price_id if old else plan.paddle_price_id

    if not product_id:
        product_id, price_id = await _create_paddle_catalog(plan, config)
        plan.paddle_product_id = product_id
        plan.paddle_price_id = price_id
        return

    if old is not None and (old.name != plan.name or old.description != plan.description):
        await _paddle_call(config, "PATCH", f"/products/{product_id}", {"name": plan.name, "description": plan.description or plan.name})

    if price_changed or not old_price_id:
        price = await _paddle_call(
            config,
            "POST",
            "/prices",
            {
                "product_id": product_id,
                "description": f"{plan.name} price",
                "name": plan.name,
                "billing_cycle": ({"interval": plan.billing_interval, "frequency": plan.billing_frequency} if plan.billing_type == "recurring" else None),
                "unit_price": {"amount": str(plan.price_amount_minor), "currency_code": plan.currency_code},
                "quantity": {"minimum": 1, "maximum": 1},
            },
        )
        new_price_id = price.get("id")
        if not new_price_id:
            raise HTTPException(status_code=502, detail="Paddle did not return a replacement price ID.")
        if old_price_id:
            await _paddle_call(config, "PATCH", f"/prices/{old_price_id}", {"status": "archived"})
        plan.paddle_price_id = new_price_id
    elif old_price_id:
        # Existing catalog prices were created before quantity was explicitly
        # configured. Lock them to one unit as well.
        await _paddle_call(
            config,
            "PATCH",
            f"/prices/{old_price_id}",
            {"quantity": {"minimum": 1, "maximum": 1}},
        )
    plan.paddle_product_id = product_id


async def _hydrate_legacy_pro(plan: Pricing, db: AsyncSession) -> None:
    if plan.slug != "pro" or plan.paddle_price_id:
        return
    config = await get_paddle_config(db)
    if not config["price_id"]:
        return
    plan.paddle_price_id = config["price_id"]
    if config["api_key"]:
        try:
            data = await _paddle_call(config, "GET", f"/prices/{plan.paddle_price_id}?include=product")
            plan.paddle_product_id = data.get("product_id")
        except HTTPException:
            # The legacy price is still valid for checkout; product discovery
            # can be retried on a later admin sync.
            pass
    await db.commit()


async def _save_features(plan: Pricing, features: list[Any], db: AsyncSession) -> None:
    await db.execute(delete(PricingFeature).where(PricingFeature.pricing_id == plan.id))
    for index, feature in enumerate(features):
        item = feature.model_dump() if hasattr(feature, "model_dump") else feature
        item["sort_order"] = index
        db.add(PricingFeature(pricing_id=plan.id, **item))


@public_router.get("", response_model=list[PricingResponse])
async def list_public_pricing(db: AsyncSession = Depends(get_db)) -> list[PricingResponse]:
    result = await db.execute(
        select(Pricing)
        .where(Pricing.is_active.is_(True))
        .order_by(Pricing.sort_order, Pricing.created_at, Pricing.id)
    )
    plans = result.scalars().all()
    for plan in plans:
        await _load_features(plan, db)
    return [_response(plan) for plan in plans]


@admin_router.get("", response_model=list[PricingResponse])
async def list_admin_pricing(_: dict = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> list[PricingResponse]:
    plans = (await db.execute(select(Pricing).order_by(Pricing.sort_order, Pricing.created_at, Pricing.id))).scalars().all()
    for plan in plans:
        await _hydrate_legacy_pro(plan, db)
    for plan in plans:
        await _load_features(plan, db)
    return [_response(plan) for plan in plans]


@admin_router.post("", response_model=PricingResponse, status_code=status.HTTP_201_CREATED)
async def create_pricing(body: PricingUpsert, _: dict = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> PricingResponse:
    duplicate = (await db.execute(select(Pricing.id).where(Pricing.slug == body.slug))).scalar_one_or_none()
    if duplicate:
        raise HTTPException(status_code=409, detail="A pricing plan with this slug already exists.")
    plan = Pricing(**_clean_plan_values(body))
    db.add(plan)
    await db.flush()
    config = await get_paddle_config(db)
    await _sync_paddle_plan(plan, None, config)
    await _save_features(plan, body.features, db)
    await db.commit()
    await db.refresh(plan)
    await _load_features(plan, db)
    return _response(plan)


@admin_router.get("/{plan_id}", response_model=PricingResponse)
async def get_admin_pricing(plan_id: uuid.UUID, _: dict = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> PricingResponse:
    plan = await _get_plan(plan_id, db)
    await _hydrate_legacy_pro(plan, db)
    await _load_features(plan, db)
    return _response(plan)


@admin_router.put("/{plan_id}", response_model=PricingResponse)
async def update_pricing(plan_id: uuid.UUID, body: PricingUpsert, _: dict = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> PricingResponse:
    plan = await _get_plan(plan_id, db)
    duplicate = (await db.execute(select(Pricing.id).where(Pricing.slug == body.slug, Pricing.id != plan.id))).scalar_one_or_none()
    if duplicate:
        raise HTTPException(status_code=409, detail="A pricing plan with this slug already exists.")
    old = Pricing()
    for column in Pricing.__table__.columns:
        if column.name not in ("id", "created_at", "updated_at"):
            setattr(old, column.name, getattr(plan, column.name))
    for key, value in _clean_plan_values(body).items():
        setattr(plan, key, value)
    config = await get_paddle_config(db)
    await _sync_paddle_plan(plan, old, config)
    await _save_features(plan, body.features, db)
    await db.commit()
    await db.refresh(plan)
    await _load_features(plan, db)
    return _response(plan)


@admin_router.post("/{plan_id}/publish", response_model=PricingResponse)
async def publish_pricing(plan_id: uuid.UUID, _: dict = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> PricingResponse:
    plan = await _get_plan(plan_id, db)
    feature_count = (await db.execute(select(PricingFeature.id).where(PricingFeature.pricing_id == plan.id))).scalars().all()
    if not feature_count:
        raise HTTPException(status_code=400, detail="Add at least one display feature before publishing this plan.")
    if plan.billing_type != "free" and not plan.paddle_price_id:
        config = await get_paddle_config(db)
        await _sync_paddle_plan(plan, None, config)
    if not plan.video_quota_unlimited and plan.video_quota_limit is None:
        raise HTTPException(status_code=400, detail="Configure the video quota count or enable unlimited.")
    if not plan.max_file_size_unlimited and plan.max_file_size_mb is None:
        raise HTTPException(status_code=400, detail="Configure max file size or enable unlimited.")
    if not plan.max_duration_unlimited and plan.max_duration_minutes is None:
        raise HTTPException(status_code=400, detail="Configure max duration or enable unlimited.")
    plan.is_active = True
    await db.commit()
    await db.refresh(plan)
    await _load_features(plan, db)
    return _response(plan)


@admin_router.post("/{plan_id}/archive", response_model=PricingResponse)
async def archive_pricing(plan_id: uuid.UUID, _: dict = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> PricingResponse:
    plan = await _get_plan(plan_id, db)
    if plan.paddle_price_id:
        config = await get_paddle_config(db)
        await _paddle_call(config, "PATCH", f"/prices/{plan.paddle_price_id}", {"status": "archived"})
    plan.is_active = False
    await db.commit()
    await db.refresh(plan)
    await _load_features(plan, db)
    return _response(plan)
