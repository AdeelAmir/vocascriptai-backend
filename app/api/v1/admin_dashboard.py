from __future__ import annotations

import asyncio
import smtplib
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.payments import _get_paddle_auth_header, get_paddle_api_url, get_paddle_config
from app.api.v1.setting import _get_setting_value
from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_admin
from app.models.meeting import Meeting
from app.models.pricing import UsagePeriod
from app.models.subscription import Subscription
from app.models.user import User
from app.services.pricing_entitlements import PricingEntitlementService
from app.services.subscriptions import current_subscription_condition

router = APIRouter()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _period_start(period_type: str, value: datetime) -> datetime:
    if period_type == "daily":
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    if period_type == "monthly":
        return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if period_type == "yearly":
        return value.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return datetime(1970, 1, 1, tzinfo=timezone.utc)


def _period_reset_at(period_type: str, value: datetime) -> datetime | None:
    if period_type == "daily":
        return _period_start("daily", value) + timedelta(days=1)
    if period_type == "monthly":
        if value.month == 12:
            return value.replace(year=value.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return value.replace(month=value.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
    if period_type == "yearly":
        return value.replace(year=value.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return None


async def _count(db: AsyncSession, model, *conditions) -> int:
    return int((await db.execute(select(func.count(model.id)).where(*conditions))).scalar_one() or 0)


def _add_months(value: datetime, months: int) -> datetime:
    month_index = value.year * 12 + (value.month - 1) + months
    year, month = divmod(month_index, 12)
    return value.replace(year=year, month=month + 1, day=1)


async def _trend_points_with_boundaries(db: AsyncSession, buckets: list[tuple[datetime, datetime, str]]) -> list[dict]:
    points = []
    for start, end, label in buckets:
        result = await db.execute(
            select(
                func.count(Meeting.id),
                func.coalesce(func.sum(case((Meeting.status == "completed", 1), else_=0)), 0),
                func.coalesce(func.sum(case((Meeting.status == "failed", 1), else_=0)), 0),
            ).where(Meeting.created_at >= start, Meeting.created_at < end)
        )
        total, completed, failed = result.one()
        points.append({
            "label": label,
            "period_start": start,
            "total": int(total or 0),
            "completed": int(completed or 0),
            "failed": int(failed or 0),
        })
    return points


async def _trend_points(db: AsyncSession, starts: list[datetime], label_format: str, step: timedelta) -> list[dict]:
    return await _trend_points_with_boundaries(
        db,
        [(start, start + step, start.strftime(label_format)) for start in starts],
    )


HEALTH_TIMEOUT = httpx.Timeout(8.0, connect=4.0)


def _http_failure(response: httpx.Response) -> str:
    if response.status_code in (401, 403):
        return "authentication rejected"
    if response.status_code == 402:
        return "payment or plan required"
    if response.status_code == 429:
        return "rate limit or quota reached"
    if response.status_code >= 500:
        return f"provider error (HTTP {response.status_code})"
    return f"HTTP {response.status_code}"


async def _request_check(client: httpx.AsyncClient, url: str, *, headers: dict[str, str], params: dict[str, str] | None = None) -> str | None:
    try:
        response = await client.get(url, headers=headers, params=params)
        return None if response.is_success else _http_failure(response)
    except httpx.TimeoutException:
        return "request timed out"
    except httpx.ConnectError as error:
        # Include the safe exception type/message so DNS and connection errors
        # can be diagnosed from Service Health without exposing credentials.
        detail = str(error).split(" for ", 1)[0].strip()
        return f"connection/DNS failure ({detail or 'host unavailable'})"
    except httpx.RequestError as error:
        return f"network request failed ({type(error).__name__})"


async def _check_api_keys(
    client: httpx.AsyncClient,
    name: str,
    keys: list[str],
    url: str,
    header_name: str,
    header_prefix: str = "",
    params: dict[str, str] | None = None,
) -> dict[str, str]:
    keys = [str(key).strip() for key in keys if key and str(key).strip()]
    if not keys:
        return {"name": name, "status": "missing", "detail": "No API keys configured"}

    async def check_key(key: str) -> str | None:
        return await _request_check(
            client,
            url,
            headers={header_name: f"{header_prefix}{key}"},
            params=params,
        )

    failures = await asyncio.gather(*(check_key(key) for key in keys))
    working = sum(failure is None for failure in failures)
    failed_details = ", ".join(f"key {index + 1}: {failure}" for index, failure in enumerate(failures) if failure)
    if working == len(keys):
        status_value = "healthy"
        detail = f"Connectivity check passed for all {len(keys)} configured key(s)"
    elif working:
        status_value = "degraded"
        detail = f"{working}/{len(keys)} configured key(s) working; {failed_details}"
    else:
        status_value = "down"
        detail = f"No configured key passed the connectivity check; {failed_details}"
    return {"name": name, "status": status_value, "detail": detail}


async def _check_paddle(client: httpx.AsyncClient, paddle: dict[str, str]) -> dict[str, str]:
    required = ("api_key", "webhook_secret", "client_token")
    missing = [key.replace("_", " ") for key in required if not paddle.get(key)]
    if missing:
        return {"name": "Paddle", "status": "missing", "detail": f"Missing configuration: {', '.join(missing)}"}
    failure = await _request_check(
        client,
        f"{get_paddle_api_url()}/products?per_page=1",
        headers={"Authorization": _get_paddle_auth_header(paddle["api_key"])},
    )
    return {
        "name": "Paddle",
        "status": "healthy" if failure is None else "down",
        "detail": "API connectivity check passed" if failure is None else f"API connectivity check failed: {failure}",
    }


def _check_smtp_credentials(user: str, password: str) -> str | None:
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=8) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(user, password)
        return None
    except smtplib.SMTPAuthenticationError:
        return "SMTP authentication rejected"
    except (smtplib.SMTPException, OSError, TimeoutError):
        return "SMTP connection or authentication failed"


async def _check_smtp(user: str, password: str) -> dict[str, str]:
    if not user or not password:
        return {"name": "Email SMTP", "status": "missing", "detail": "SMTP user and password are required"}
    failure = await asyncio.to_thread(_check_smtp_credentials, user, password)
    return {
        "name": "Email SMTP",
        "status": "healthy" if failure is None else "down",
        "detail": "SMTP connection and login check passed" if failure is None else failure,
    }


@router.get("/dashboard-stats")
async def get_dashboard_stats(
    _: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    now = _utc_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    regular_user = User.role == 2
    current_subscription = current_subscription_condition(now)

    total_users = await _count(db, User, regular_user)
    verified_users = await _count(db, User, regular_user, User.is_verified.is_(True))
    active_users = await _count(db, User, regular_user, User.is_active.is_(True))
    current_subscriptions = await _count(db, Subscription, current_subscription)
    past_due_subscriptions = await _count(db, Subscription, Subscription.status == "past_due")

    total_meetings = await _count(db, Meeting)
    completed_meetings = await _count(db, Meeting, Meeting.status == "completed")
    processing_meetings = await _count(db, Meeting, Meeting.status.in_(("uploading", "transcribing", "processing")))
    failed_meetings = await _count(db, Meeting, Meeting.status == "failed")
    today_meetings = await _count(db, Meeting, Meeting.created_at >= today_start)
    month_meetings = await _count(db, Meeting, Meeting.created_at >= month_start)
    today_completed = await _count(db, Meeting, Meeting.status == "completed", Meeting.updated_at >= today_start)
    today_failed = await _count(db, Meeting, Meeting.status == "failed", Meeting.updated_at >= today_start)

    plan_result = await db.execute(
        select(Subscription.plan, func.count(Subscription.id))
        .where(current_subscription)
        .group_by(Subscription.plan)
        .order_by(func.count(Subscription.id).desc())
    )
    plan_distribution = [{"plan": plan or "unknown", "count": int(count)} for plan, count in plan_result.all()]

    recent_result = await db.execute(
        select(Meeting, User.email)
        .outerjoin(User, User.id == Meeting.user_id)
        .order_by(Meeting.created_at.desc())
        .limit(8)
    )
    recent_meetings = [
        {
            "id": str(meeting.id),
            "title": meeting.title,
            "file_name": meeting.file_name,
            "file_type": meeting.file_type,
            "status": meeting.status,
            "user_email": email,
            "file_duration": meeting.file_duration,
            "created_at": meeting.created_at,
            "updated_at": meeting.updated_at,
            "error_code": meeting.error_code,
            "error_message": meeting.error_message,
        }
        for meeting, email in recent_result.all()
    ]

    day_starts = [today_start + timedelta(hours=index) for index in range(24)]
    week_start = today_start - timedelta(days=today_start.weekday())
    week_starts = [week_start + timedelta(days=index) for index in range(7)]
    month_days = monthrange(now.year, now.month)[1]
    month_day_starts = [month_start + timedelta(days=index) for index in range(month_days)]
    year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    year_month_starts = [_add_months(year_start, index) for index in range(12)]
    trends = {
        "day": await _trend_points(db, day_starts, "%H:00", timedelta(hours=1)),
        "week": await _trend_points(db, week_starts, "%a", timedelta(days=1)),
        "month": await _trend_points(db, month_day_starts, "%d", timedelta(days=1)),
        "year": await _trend_points_with_boundaries(
            db,
            [(start, _add_months(start, 1), start.strftime("%b")) for start in year_month_starts],
        ),
    }

    return {
        "generated_at": now,
        "users": {
            "total": total_users,
            "verified": verified_users,
            "unverified": max(total_users - verified_users, 0),
            "active": active_users,
            "inactive": max(total_users - active_users, 0),
        },
        "subscriptions": {
            "current": current_subscriptions,
            "past_due": past_due_subscriptions,
            "plans": plan_distribution,
        },
        "transcriptions": {
            "total": total_meetings,
            "today": today_meetings,
            "this_month": month_meetings,
            "completed": completed_meetings,
            "processing": processing_meetings,
            "failed": failed_meetings,
            "completed_today": today_completed,
            "failed_today": today_failed,
        },
        "trends": trends,
        "recent_meetings": recent_meetings,
    }


@router.get("/users/{user_id}/usage")
async def get_admin_user_usage(
    user_id: uuid.UUID,
    _: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = (await db.execute(select(User).where(User.id == user_id, User.role == 2))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    now = _utc_now()
    entitlement = await PricingEntitlementService.get_current_entitlement(user, db, ensure_free=False)
    latest_subscription = (
        await db.execute(
            select(Subscription)
            .where(Subscription.user_id == user.id)
            .order_by(Subscription.created_at.desc(), Subscription.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    quota_period = entitlement.video_quota_period
    quota_limit = entitlement.video_quota_limit
    quota_unlimited = entitlement.video_quota_unlimited
    usage_count = 0
    period_started_at = _period_start(quota_period, now) if quota_period else None
    period_reset_at = _period_reset_at(quota_period, now) if quota_period else None

    period_query = select(UsagePeriod).where(UsagePeriod.user_id == user.id).order_by(UsagePeriod.period_start.desc())
    periods = (await db.execute(period_query.limit(24))).scalars().all()
    if entitlement.entitlement_id and quota_period and quota_period != "lifetime":
        current_period = (
            await db.execute(
                select(UsagePeriod).where(
                    UsagePeriod.user_id == user.id,
                    UsagePeriod.entitlement_id == entitlement.entitlement_id,
                    UsagePeriod.period_type == quota_period,
                    UsagePeriod.period_start == period_started_at,
                )
            )
        ).scalar_one_or_none()
        usage_count = current_period.video_count if current_period else 0

    status_counts_result = await db.execute(
        select(Meeting.status, func.count(Meeting.id))
        .where(Meeting.user_id == user.id)
        .group_by(Meeting.status)
    )
    status_counts = {status_name: int(count) for status_name, count in status_counts_result.all()}

    meetings_result = await db.execute(
        select(Meeting)
        .where(Meeting.user_id == user.id)
        .order_by(Meeting.created_at.desc())
        .limit(20)
    )
    recent_processing = [
        {
            "id": str(meeting.id),
            "title": meeting.title,
            "file_name": meeting.file_name,
            "file_type": meeting.file_type,
            "status": meeting.status,
            "file_duration": meeting.file_duration,
            "file_size": meeting.file_size,
            "error_code": meeting.error_code,
            "error_message": meeting.error_message,
            "created_at": meeting.created_at,
            "updated_at": meeting.updated_at,
        }
        for meeting in meetings_result.scalars().all()
    ]

    return {
        "user": {"id": str(user.id), "name": f"{user.first_name} {user.last_name}".strip(), "email": user.email},
        "plan": {
            "name": entitlement.name,
            "slug": entitlement.slug,
            "status": latest_subscription.status if latest_subscription else "free",
            "billing_type": entitlement.billing_type,
            "subscription_id": str(latest_subscription.id) if latest_subscription else None,
        },
        "quota": {
            "period": quota_period,
            "limit": quota_limit,
            "unlimited": quota_unlimited,
            "used": usage_count,
            "remaining": None if quota_unlimited or quota_limit is None else max(quota_limit - usage_count, 0),
            "period_started_at": period_started_at,
            "period_reset_at": period_reset_at,
        },
        "usage_periods": [
            {"period_type": period.period_type, "period_start": period.period_start, "video_count": period.video_count}
            for period in periods
        ],
        "processing": {"counts": status_counts, "recent": recent_processing},
    }


@router.get("/service-health")
async def get_service_health(
    _: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    now = _utc_now()
    services: list[dict[str, str]] = []

    try:
        await db.execute(select(1))
        services.append({"name": "Database", "key": "database", "status": "healthy", "detail": "Connection successful"})
    except Exception:
        services.append({"name": "Database", "key": "database", "status": "down", "detail": "Connection failed"})

    paddle = await get_paddle_config(db)

    openai_keys = [await _get_setting_value(db, "OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", "")]
    openai_model = await _get_setting_value(db, "OPENAI_MODEL") or "gpt-4o-mini"
    openai_model_url = f"https://api.openai.com/v1/models/{quote(openai_model, safe='')}"
    assemblyai_keys = [await _get_setting_value(db, f"ASSEMBLYAI_API_KEY_{index}") or getattr(settings, f"ASSEMBLYAI_API_KEY_{index}", "") for index in range(1, 4)]
    groq_keys = [await _get_setting_value(db, f"GROQ_API_KEY_{index}") or getattr(settings, f"GROQ_API_KEY_{index}", "") for index in range(1, 4)]
    supadata_keys = [await _get_setting_value(db, f"SUPADATA_API_KEY_{index}") or getattr(settings, f"SUPADATA_API_KEY_{index}", "") for index in range(1, 6)]
    deepl_keys = [await _get_setting_value(db, "DEEPL_API_KEY") or ""]

    async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT, follow_redirects=False) as client:
        checked_services = await asyncio.gather(
            _check_api_keys(client, "OpenAI", openai_keys, openai_model_url, "Authorization", "Bearer "),
            _check_api_keys(client, "AssemblyAI", assemblyai_keys, "https://api.assemblyai.com/v2/transcript?limit=1", "Authorization"),
            _check_api_keys(client, "Groq", groq_keys, "https://api.groq.com/openai/v1/models", "Authorization", "Bearer "),
            _check_api_keys(client, "Supadata", supadata_keys, "https://api.supadata.ai/v1/metadata", "x-api-key", params={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}),
            _check_api_keys(client, "DeepL", deepl_keys, "https://api-free.deepl.com/v2/usage", "Authorization", "DeepL-Auth-Key "),
            _check_paddle(client, paddle),
        )
    checked_services.append(await _check_smtp(getattr(settings, "SMTP_USER", ""), getattr(settings, "SMTP_PASSWORD", "")))

    service_names = {
        "OpenAI": "openai",
        "AssemblyAI": "assemblyai",
        "Groq": "groq",
        "Supadata": "supadata",
        "DeepL": "deepl",
        "Email SMTP": "email",
        "Paddle": "paddle",
    }
    for service in checked_services:
        service["key"] = service_names[service["name"]]
        services.append(service)

    return {
        "checked_at": now,
        "environment": getattr(settings, "APP_ENV", "development"),
        "mode": "production" if (getattr(settings, "APP_ENV", "") or "").lower() == "production" else "sandbox/development",
        "services": services,
    }
