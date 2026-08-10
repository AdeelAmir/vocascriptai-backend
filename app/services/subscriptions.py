from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from sqlalchemy import and_, case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subscription import Subscription

CURRENT_SUBSCRIPTION_STATUSES = ("active", "cancelling", "past_due")
TERMINAL_SUBSCRIPTION_STATUSES = ("canceled", "paused")
STALE_PAYMENT_STATUSES = ("pending", "failed")


def current_subscription_condition(now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    return and_(
        Subscription.status.in_(CURRENT_SUBSCRIPTION_STATUSES),
        or_(
            Subscription.status != "cancelling",
            Subscription.ends_at.is_(None),
            Subscription.ends_at > now,
        ),
    )


def _status_priority(status: Any):
    return case(
        (status == "active", 0),
        (status == "cancelling", 1),
        (status == "past_due", 2),
        else_=99,
    )


def _subscription_preference_key(subscription: Subscription, preferred_id: uuid.UUID | None = None):
    """Prefer the paid current record that represents the real Paddle subscription."""
    created_at = subscription.created_at.timestamp() if subscription.created_at else 0
    return (
        0 if preferred_id and subscription.id == preferred_id else 1,
        {"active": 0, "cancelling": 1, "past_due": 2}.get(subscription.status, 99),
        0 if subscription.paddle_subscription_id else 1,
        -created_at,
    )


async def reconcile_user_subscriptions(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    preferred: Subscription | None = None,
) -> bool:
    """Remove stale payment attempts and collapse duplicate recurring records.

    Paddle can emit a successful transaction event before the subscription event.
    Older records may therefore exist once for the transaction and once for the
    actual subscription. Only one paid recurring record should remain usable.
    """
    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .with_for_update()
    )
    rows = list(result.scalars().all())
    changed = False

    for row in rows:
        if row.status in STALE_PAYMENT_STATUSES:
            await db.delete(row)
            changed = True

    paid_recurring = [
        row for row in rows
        if row.status in CURRENT_SUBSCRIPTION_STATUSES
        and row.billing_type == "recurring"
    ]
    if paid_recurring:
        preferred_id = preferred.id if preferred and preferred in paid_recurring else None
        keep = min(
            paid_recurring,
            key=lambda row: _subscription_preference_key(row, preferred_id),
        )
        for row in paid_recurring:
            if row.id != keep.id:
                await db.delete(row)
                changed = True

    return changed


async def get_current_subscription(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> Subscription | None:
    query = (
        select(Subscription)
        .where(
            Subscription.user_id == user_id,
            current_subscription_condition(),
        )
        .order_by(
            Subscription.created_at.desc(),
            Subscription.id.desc(),
            _status_priority(Subscription.status),
        )
        .limit(1)
    )
    if for_update:
        query = query.with_for_update()
    result = await db.execute(query)
    return result.scalar_one_or_none()


def subscription_values(subscription: Subscription | None) -> dict[str, Any]:
    if subscription is None:
        return {
            "subscription_tier": "starter",
            "subscription_status": "free",
            "subscription_ends_at": None,
            "pricing_slug": "starter",
            "pricing_name": "Starter",
            "pricing_entitlements": {
                "transcript_language_mode": "english",
                "summary_language_mode": "english",
                "prompts_enabled": False,
                "ai_model": "standard",
                "pdf_download_enabled": True,
                "priority_support_enabled": False,
            },
            "pricing_quota": {
                "max_file_size_mb": 200,
                "max_file_size_unlimited": False,
                "max_duration_minutes": 30,
                "max_duration_unlimited": False,
            },
        }
    slug = subscription.pricing_slug_snapshot or subscription.plan
    entitlements = {
        **(subscription.entitlements_snapshot or {}),
        "youtube_enabled": (subscription.entitlements_snapshot or {}).get(
            "youtube_enabled",
            subscription.billing_type_snapshot != "free" and subscription.billing_type != "free",
        ),
    }
    return {
        "subscription_tier": slug,
        "subscription_status": subscription.status,
        "subscription_ends_at": subscription.ends_at,
        "pricing_slug": slug,
        "pricing_name": subscription.pricing_name_snapshot or slug,
        "pricing_entitlements": entitlements,
        "pricing_quota": subscription.quota_snapshot or {},
    }


def webhook_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
