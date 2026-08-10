from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
import uuid

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.pricing import GuestUsagePeriod, GuestVisitor, Pricing, UsagePeriod
from app.models.subscription import Subscription
from app.models.user import User
from app.services.subscriptions import get_current_subscription


@dataclass(frozen=True)
class PricingEntitlement:
    pricing_id: uuid.UUID | None
    entitlement_id: uuid.UUID | None
    slug: str
    name: str
    billing_type: str
    video_quota_period: str | None
    video_quota_limit: int | None
    video_quota_unlimited: bool
    daily_limit: int | None
    daily_unlimited: bool
    monthly_limit: int | None
    monthly_unlimited: bool
    max_file_size_mb: float | None
    max_file_size_unlimited: bool
    max_duration_minutes: float | None
    max_duration_unlimited: bool
    capabilities: dict[str, Any]


def _number(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _capabilities_from_pricing(pricing: Pricing) -> dict[str, Any]:
    return {
        "transcript_language_mode": pricing.transcript_language_mode,
        "summary_language_mode": pricing.summary_language_mode,
        "prompts_enabled": pricing.prompts_enabled,
        "ai_model": pricing.ai_model,
        "pdf_download_enabled": pricing.pdf_download_enabled,
        "priority_support_enabled": pricing.priority_support_enabled,
        "youtube_enabled": pricing.youtube_enabled,
    }


def pricing_snapshot(pricing: Pricing) -> tuple[dict[str, Any], dict[str, Any]]:
    entitlements = _capabilities_from_pricing(pricing)
    quota = {
        "video_quota_period": pricing.video_quota_period,
        "video_quota_limit": pricing.video_quota_limit,
        "video_quota_unlimited": pricing.video_quota_unlimited,
        "daily_video_limit": pricing.daily_video_limit,
        "daily_video_quota_unlimited": pricing.daily_video_quota_unlimited,
        "monthly_video_limit": pricing.monthly_video_limit,
        "monthly_video_quota_unlimited": pricing.monthly_video_quota_unlimited,
        "max_file_size_mb": _number(pricing.max_file_size_mb),
        "max_file_size_unlimited": pricing.max_file_size_unlimited,
        "max_duration_minutes": _number(pricing.max_duration_minutes),
        "max_duration_unlimited": pricing.max_duration_unlimited,
    }
    return entitlements, quota


def entitlement_from_pricing(pricing: Pricing, entitlement_id: uuid.UUID | None = None) -> PricingEntitlement:
    return PricingEntitlement(
        pricing_id=pricing.id,
        entitlement_id=entitlement_id,
        slug=pricing.slug,
        name=pricing.name,
        billing_type=pricing.billing_type,
        video_quota_period=pricing.video_quota_period,
        video_quota_limit=pricing.video_quota_limit,
        video_quota_unlimited=pricing.video_quota_unlimited,
        daily_limit=pricing.daily_video_limit,
        daily_unlimited=pricing.daily_video_quota_unlimited,
        monthly_limit=pricing.monthly_video_limit,
        monthly_unlimited=pricing.monthly_video_quota_unlimited,
        max_file_size_mb=_number(pricing.max_file_size_mb),
        max_file_size_unlimited=pricing.max_file_size_unlimited,
        max_duration_minutes=_number(pricing.max_duration_minutes),
        max_duration_unlimited=pricing.max_duration_unlimited,
        capabilities=_capabilities_from_pricing(pricing),
    )


def entitlement_from_subscription(subscription: Subscription) -> PricingEntitlement:
    quota = subscription.quota_snapshot or {}
    has_unified_quota = "video_quota_period" in quota
    billing_type = subscription.billing_type_snapshot or subscription.billing_type
    legacy_one_time_limit = None
    legacy_one_time_unlimited = True
    if billing_type == "one_time" and not has_unified_quota:
        # Convert purchase snapshots written before the unified quota fields
        # existed into a single lifetime allowance as well.
        for period in ("monthly", "daily"):
            if not quota.get(f"{period}_video_quota_unlimited", True):
                legacy_one_time_limit = quota.get(f"{period}_video_limit")
                legacy_one_time_unlimited = False
                break
    return PricingEntitlement(
        pricing_id=subscription.pricing_id,
        entitlement_id=subscription.id,
        slug=subscription.pricing_slug_snapshot or subscription.plan,
        name=subscription.pricing_name_snapshot or subscription.plan,
        billing_type=billing_type,
        video_quota_period=quota.get("video_quota_period") if has_unified_quota else ("lifetime" if billing_type == "one_time" else None),
        video_quota_limit=quota.get("video_quota_limit") if has_unified_quota else legacy_one_time_limit,
        video_quota_unlimited=bool(quota.get("video_quota_unlimited", True)) if has_unified_quota else legacy_one_time_unlimited,
        daily_limit=quota.get("daily_video_limit"),
        daily_unlimited=bool(quota.get("daily_video_quota_unlimited", True)),
        monthly_limit=quota.get("monthly_video_limit"),
        monthly_unlimited=bool(quota.get("monthly_video_quota_unlimited", True)),
        max_file_size_mb=quota.get("max_file_size_mb"),
        max_file_size_unlimited=bool(quota.get("max_file_size_unlimited", False)),
        max_duration_minutes=quota.get("max_duration_minutes"),
        max_duration_unlimited=bool(quota.get("max_duration_unlimited", False)),
        capabilities={
            **(subscription.entitlements_snapshot or {}),
            "youtube_enabled": (subscription.entitlements_snapshot or {}).get(
                "youtube_enabled",
                subscription.billing_type != "free",
            ),
        },
    )


class PricingEntitlementService:
    @staticmethod
    async def _starter(db: AsyncSession) -> Pricing:
        result = await db.execute(select(Pricing).where(Pricing.slug == "starter"))
        pricing = result.scalar_one_or_none()
        if pricing is None:
            raise HTTPException(status_code=500, detail="Starter pricing plan is not configured.")
        return pricing

    @staticmethod
    async def _free_entitlement(user: User, pricing: Pricing, db: AsyncSession) -> Subscription:
        result = await db.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user.id,
                Subscription.billing_type == "free",
                Subscription.plan == pricing.slug,
            )
            .limit(1)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        entitlements, quota = pricing_snapshot(pricing)
        free_entitlement = Subscription(
            user_id=user.id,
            pricing_id=pricing.id,
            email_snapshot=user.email,
            plan=pricing.slug,
            status="free",
            billing_type="free",
            pricing_slug_snapshot=pricing.slug,
            pricing_name_snapshot=pricing.name,
            price_amount_minor_snapshot=pricing.price_amount_minor,
            currency_code_snapshot=pricing.currency_code,
            billing_type_snapshot=pricing.billing_type,
            billing_interval_snapshot=pricing.billing_interval,
            paddle_price_id_snapshot=pricing.paddle_price_id,
            entitlements_snapshot=entitlements,
            quota_snapshot=quota,
        )
        try:
            async with db.begin_nested():
                db.add(free_entitlement)
                await db.flush()
        except IntegrityError:
            result = await db.execute(
                select(Subscription)
                .where(
                    Subscription.user_id == user.id,
                    Subscription.billing_type == "free",
                    Subscription.plan == pricing.slug,
                )
                .limit(1)
            )
            existing = result.scalar_one_or_none()
            if existing:
                return existing
            raise
        return free_entitlement

    @staticmethod
    async def get_current_entitlement(user: User, db: AsyncSession, ensure_free: bool = False) -> PricingEntitlement:
        if user.role == 1:
            return PricingEntitlement(
                pricing_id=None,
                entitlement_id=None,
                slug="admin",
                name="Administrator",
                billing_type="free",
                video_quota_period="lifetime",
                video_quota_limit=None,
                video_quota_unlimited=True,
                daily_limit=None,
                daily_unlimited=True,
                monthly_limit=None,
                monthly_unlimited=True,
                max_file_size_mb=None,
                max_file_size_unlimited=True,
                max_duration_minutes=None,
                max_duration_unlimited=True,
                capabilities={
                    "transcript_language_mode": "all",
                    "summary_language_mode": "all",
                    "prompts_enabled": True,
                    "ai_model": "powerful",
                    "pdf_download_enabled": True,
                    "priority_support_enabled": True,
                },
            )

        subscription = await get_current_subscription(db, user.id)
        if subscription:
            if subscription.quota_snapshot is not None:
                return entitlement_from_subscription(subscription)
            if subscription.pricing_id:
                pricing = (await db.execute(select(Pricing).where(Pricing.id == subscription.pricing_id))).scalar_one_or_none()
                if pricing:
                    return entitlement_from_pricing(pricing, subscription.id)

        pricing = await PricingEntitlementService._starter(db)
        if ensure_free:
            free_entitlement = await PricingEntitlementService._free_entitlement(user, pricing, db)
            return entitlement_from_subscription(free_entitlement)
        return entitlement_from_pricing(pricing)

    @staticmethod
    async def can_process_video(
        user: User,
        metadata: dict[str, Any],
        db: AsyncSession,
    ) -> PricingEntitlement:
        entitlement = await PricingEntitlementService.get_current_entitlement(user, db, ensure_free=True)
        file_size_mb = metadata.get("file_size_mb")
        duration_minutes = metadata.get("duration_minutes")

        if (
            file_size_mb is not None
            and not entitlement.max_file_size_unlimited
            and entitlement.max_file_size_mb is not None
            and file_size_mb > entitlement.max_file_size_mb
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File size exceeds maximum allowed size of {entitlement.max_file_size_mb:g}MB.",
            )
        if (
            duration_minutes is not None
            and not entitlement.max_duration_unlimited
            and entitlement.max_duration_minutes is not None
            and duration_minutes > entitlement.max_duration_minutes
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Video duration exceeds the {entitlement.max_duration_minutes:g} minute limit.",
            )
        return entitlement

    @staticmethod
    def _period_start(period_type: str, now: datetime) -> datetime:
        if period_type == "daily":
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        if period_type == "monthly":
            return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if period_type == "yearly":
            return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return datetime(1970, 1, 1, tzinfo=timezone.utc)

    @staticmethod
    async def reserve_usage(user: User, entitlement: PricingEntitlement, db: AsyncSession) -> None:
        if user.role == 1 or entitlement.entitlement_id is None:
            return

        if entitlement.billing_type == "one_time":
            await PricingEntitlementService._reserve_one_time_usage(user, db)
            return

        now = datetime.now(timezone.utc)
        if entitlement.video_quota_period is not None:
            limits = ((entitlement.video_quota_period, entitlement.video_quota_limit, entitlement.video_quota_unlimited),)
        else:
            # Preserve purchase-time snapshots created before the unified quota
            # fields were introduced.
            limits = (("daily", entitlement.daily_limit, entitlement.daily_unlimited), ("monthly", entitlement.monthly_limit, entitlement.monthly_unlimited))
        for period_type, limit, unlimited in limits:
            if unlimited or limit is None:
                continue
            period_start = PricingEntitlementService._period_start(period_type, now)
            await db.execute(
                insert(UsagePeriod)
                .values(
                    user_id=user.id,
                    entitlement_id=entitlement.entitlement_id,
                    period_type=period_type,
                    period_start=period_start,
                    video_count=0,
                )
                .on_conflict_do_nothing(
                    index_elements=["user_id", "entitlement_id", "period_type", "period_start"]
                )
            )
            result = await db.execute(
                select(UsagePeriod)
                .where(
                    UsagePeriod.user_id == user.id,
                    UsagePeriod.entitlement_id == entitlement.entitlement_id,
                    UsagePeriod.period_type == period_type,
                    UsagePeriod.period_start == period_start,
                )
                .with_for_update()
            )
            period = result.scalar_one()
            if period.video_count >= limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"You have reached your {period_type} limit of {limit} videos for the {entitlement.name} plan.",
                )
            period.video_count += 1

    @staticmethod
    async def _reserve_one_time_usage(user: User, db: AsyncSession) -> None:
        """Consume one video from any still-available one-time purchase.

        Each purchase owns its own lifetime usage bucket. Looking through all
        active purchases makes repeat buys additive instead of replacing the
        previous purchase when the newest one is selected as the current plan.
        """
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user.id,
                Subscription.billing_type == "one_time",
                Subscription.status.in_(("active", "cancelling", "past_due")),
                or_(
                    Subscription.status != "cancelling",
                    Subscription.ends_at.is_(None),
                    Subscription.ends_at > now,
                ),
            )
            .order_by(Subscription.created_at.desc(), Subscription.id.desc())
            .with_for_update()
        )
        purchases = result.scalars().all()
        period_start = datetime(1970, 1, 1, tzinfo=timezone.utc)

        for purchase in purchases:
            entitlement = entitlement_from_subscription(purchase)
            limit = entitlement.video_quota_limit
            unlimited = entitlement.video_quota_unlimited

            # One-time purchase snapshots created by older versions may still
            # carry a periodic label. Their count is nevertheless a purchase
            # allowance, so always consume it from the lifetime bucket.
            if unlimited or limit is None:
                return

            await db.execute(
                insert(UsagePeriod)
                .values(
                    user_id=user.id,
                    entitlement_id=purchase.id,
                    period_type="lifetime",
                    period_start=period_start,
                    video_count=0,
                )
                .on_conflict_do_nothing(
                    index_elements=["user_id", "entitlement_id", "period_type", "period_start"]
                )
            )
            usage_result = await db.execute(
                select(UsagePeriod)
                .where(
                    UsagePeriod.user_id == user.id,
                    UsagePeriod.entitlement_id == purchase.id,
                    UsagePeriod.period_type == "lifetime",
                    UsagePeriod.period_start == period_start,
                )
                .with_for_update()
            )
            period = usage_result.scalar_one()
            if period.video_count < limit:
                period.video_count += 1
                return

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="You have used all videos included in your one-time purchase. Please buy the plan again to continue.",
        )

    @staticmethod
    async def reserve_guest_usage(
        visitor_id: str | uuid.UUID | None,
        ip_address: str,
        entitlement: PricingEntitlement | None,
        db: AsyncSession,
    ) -> uuid.UUID:
        limit = 5
        if entitlement and not entitlement.monthly_unlimited and entitlement.monthly_limit is not None:
            limit = entitlement.monthly_limit

        parsed_visitor_id: uuid.UUID | None = None
        if visitor_id:
            try:
                if isinstance(visitor_id, uuid.UUID):
                    parsed_visitor_id = visitor_id
                else:
                    parsed_visitor_id = uuid.UUID(str(visitor_id))
            except (ValueError, TypeError):
                parsed_visitor_id = None

        if not parsed_visitor_id:
            parsed_visitor_id = uuid.uuid4()

        now = datetime.now(timezone.utc)
        period_start = PricingEntitlementService._period_start("monthly", now)

        visitor_stmt = select(GuestVisitor).where(
            or_(
                GuestVisitor.visitor_id == parsed_visitor_id,
                GuestVisitor.ip_address == ip_address,
            )
        ).with_for_update()
        visitor_result = await db.execute(visitor_stmt)
        matched_visitors = visitor_result.scalars().all()

        max_visitor_count = 0
        target_visitor: GuestVisitor | None = None
        for v in matched_visitors:
            if v.visitor_id == parsed_visitor_id:
                target_visitor = v
            if v.video_count > max_visitor_count:
                max_visitor_count = v.video_count

        await db.execute(
            insert(GuestUsagePeriod)
            .values(ip_address=ip_address, period_start=period_start, video_count=0)
            .on_conflict_do_nothing(index_elements=["ip_address", "period_start"])
        )
        period_res = await db.execute(
            select(GuestUsagePeriod)
            .where(GuestUsagePeriod.ip_address == ip_address, GuestUsagePeriod.period_start == period_start)
            .with_for_update()
        )
        ip_period = period_res.scalar_one_or_none()
        ip_count = ip_period.video_count if ip_period else 0

        effective_count = max(max_visitor_count, ip_count)

        if effective_count >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"You have used all {limit} free summaries. Please upgrade to Pro plan to continue.",
            )

        new_count = effective_count + 1

        if target_visitor:
            target_visitor.video_count = new_count
            target_visitor.ip_address = ip_address
            target_visitor.updated_at = now
        else:
            target_visitor = GuestVisitor(
                visitor_id=parsed_visitor_id,
                ip_address=ip_address,
                video_count=new_count,
                created_at=now,
                updated_at=now,
            )
            db.add(target_visitor)

        if ip_period:
            ip_period.video_count = max(ip_period.video_count, new_count)

        return parsed_visitor_id

    @staticmethod
    async def transfer_guest_usage_to_user(
        visitor_id: str | uuid.UUID | None,
        ip_address: str | None,
        user: User,
        db: AsyncSession,
    ) -> None:
        """Transfer only this browser's unclaimed guest usage to the user.

        IP addresses are deliberately not used for ownership transfer. An IP
        can be shared by multiple people (office, school, VPN, or mobile
        carrier), so using it here could make a brand-new account inherit
        another visitor's exhausted quota. The IP is still used by
        ``reserve_guest_usage`` while the visitor is anonymous to limit abuse;
        it must not establish ownership of that usage after registration.
        """
        if user.role == 1:
            return

        parsed_visitor_id: uuid.UUID | None = None
        if visitor_id:
            try:
                parsed_visitor_id = uuid.UUID(str(visitor_id)) if isinstance(visitor_id, str) else visitor_id
            except (ValueError, TypeError):
                parsed_visitor_id = None

        # A missing/invalid visitor cookie means there is no safe way to prove
        # that anonymous usage belongs to this newly verified account. Never
        # fall back to the request IP for this transfer.
        if not parsed_visitor_id:
            return

        result = await db.execute(
            select(GuestVisitor).where(
                GuestVisitor.visitor_id == parsed_visitor_id,
                GuestVisitor.user_id.is_(None),
            )
        )
        matched_visitors = result.scalars().all()
        if not matched_visitors:
            return

        max_guest_count = max(v.video_count for v in matched_visitors)
        if max_guest_count <= 0:
            return

        pricing = await PricingEntitlementService._starter(db)
        free_sub = await PricingEntitlementService._free_entitlement(user, pricing, db)

        now = datetime.now(timezone.utc)
        period_start = PricingEntitlementService._period_start("monthly", now)

        await db.execute(
            insert(UsagePeriod)
            .values(
                user_id=user.id,
                entitlement_id=free_sub.id,
                period_type="monthly",
                period_start=period_start,
                video_count=0,
            )
            .on_conflict_do_nothing(index_elements=["user_id", "entitlement_id", "period_type", "period_start"])
        )
        usage_res = await db.execute(
            select(UsagePeriod)
            .where(
                UsagePeriod.user_id == user.id,
                UsagePeriod.entitlement_id == free_sub.id,
                UsagePeriod.period_type == "monthly",
                UsagePeriod.period_start == period_start,
            )
            .with_for_update()
        )
        usage_period = usage_res.scalar_one_or_none()
        if usage_period:
            if usage_period.video_count < max_guest_count:
                usage_period.video_count = max_guest_count

        for v in matched_visitors:
            v.user_id = user.id

    @staticmethod
    async def release_usage(*_: Any, **__: Any) -> None:
        return None
