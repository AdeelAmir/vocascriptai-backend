from __future__ import annotations

import math
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.payments import (
    _get_paddle_auth_header,
    _parse_datetime,
    get_paddle_api_url,
    get_paddle_config,
)
from app.core.database import get_db
from app.core.security import get_current_admin, hash_password
from app.email_sender.SMTP import send_subscription_cancelled_email
from app.models.subscription import Subscription
from app.models.user import User
from app.models.user_refresh_token import UserRefreshToken
from app.schemas.admin_management import (
    AdminSubscriptionListItem,
    AdminUserDetail,
    AdminUserListItem,
    AdminUserPasswordUpdate,
    AdminUserUpdate,
    PaginatedAdminSubscriptions,
    PaginatedAdminUsers,
    SubscriptionSummary,
)
from app.services.subscriptions import CURRENT_SUBSCRIPTION_STATUSES, get_current_subscription

router = APIRouter()

SUBSCRIPTION_STATUS_GROUPS = {
    "pending": ("pending",),
    "active": ("active",),
    "cancelled": ("cancelling", "canceled", "paused"),
    "failed": ("past_due", "failed"),
}


async def _get_regular_user(user_id: uuid.UUID, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.id == user_id, User.role == 2))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _page_values(page: int, page_size: int, total: int) -> tuple[int, int]:
    return page, math.ceil(total / page_size) if total else 0


@router.get("/users", response_model=PaginatedAdminUsers)
async def list_admin_users(
    search: str | None = None,
    is_active: bool | None = None,
    is_verified: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> PaginatedAdminUsers:
    filters = [User.role == 2]
    if search and search.strip():
        needle = f"%{search.strip().lower()}%"
        filters.append(
            or_(
                func.lower(User.first_name).like(needle),
                func.lower(User.last_name).like(needle),
                func.lower(User.email).like(needle),
            )
        )
    if is_active is not None:
        filters.append(User.is_active == is_active)
    if is_verified is not None:
        filters.append(User.is_verified == is_verified)

    total = (await db.execute(select(func.count(User.id)).where(*filters))).scalar_one()
    result = await db.execute(
        select(User)
        .where(*filters)
        .order_by(User.created_at.desc(), User.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    current_page, total_pages = _page_values(page, page_size, total)
    return PaginatedAdminUsers(
        items=[AdminUserListItem.model_validate(user) for user in result.scalars().all()],
        page=current_page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.get("/users/{user_id}", response_model=AdminUserDetail)
async def get_admin_user(
    user_id: uuid.UUID,
    _: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUserDetail:
    user = await _get_regular_user(user_id, db)
    # Show the latest billing record, including cancelled/failed and one-time
    # purchases, so the detail page matches the subscriptions table history.
    subscription = (
        await db.execute(
            select(Subscription)
            .where(Subscription.user_id == user.id)
            .order_by(Subscription.created_at.desc(), Subscription.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    summary = None
    if subscription:
        summary = SubscriptionSummary(
            id=subscription.id,
            plan=subscription.plan,
            status=subscription.status,
            paddle_subscription_id=subscription.paddle_subscription_id,
            paddle_transaction_id=subscription.paddle_transaction_id,
            billing_type=subscription.billing_type,
            started_at=subscription.started_at,
            ends_at=subscription.ends_at,
            created_at=subscription.created_at,
        )
    return AdminUserDetail(
        **AdminUserListItem.model_validate(user).model_dump(),
        role=user.role,
        monthly_video_count=user.monthly_video_count,
        usage_reset_date=user.usage_reset_date,
        subscription=summary,
    )


@router.put("/users/{user_id}", response_model=AdminUserListItem)
async def update_admin_user(
    user_id: uuid.UUID,
    body: AdminUserUpdate,
    _: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUserListItem:
    user = await _get_regular_user(user_id, db)
    updates = body.model_dump(exclude_unset=True)
    if "email" in updates:
        email = updates["email"]
        duplicate = await db.execute(
            select(User.id).where(func.lower(User.email) == email.lower(), User.id != user.id)
        )
        if duplicate.scalar_one_or_none() is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
        updates["email"] = email.lower()
    for key, value in updates.items():
        setattr(user, key, value)
    await db.commit()
    await db.refresh(user)
    return AdminUserListItem.model_validate(user)


@router.put("/users/{user_id}/password")
async def update_admin_user_password(
    user_id: uuid.UUID,
    body: AdminUserPasswordUpdate,
    _: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    user = await _get_regular_user(user_id, db)
    user.password = hash_password(body.new_password)
    await db.execute(delete(UserRefreshToken).where(UserRefreshToken.user_id == user.id))
    await db.commit()
    return {"message": "User password updated successfully"}


@router.delete("/users/{user_id}")
async def delete_admin_user(
    user_id: uuid.UUID,
    _: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    user = await _get_regular_user(user_id, db)
    active_subscription = await db.execute(
        select(Subscription.id).where(
            Subscription.user_id == user.id,
            Subscription.status.in_(CURRENT_SUBSCRIPTION_STATUSES),
        ).limit(1)
    )
    if active_subscription.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cancel the user's active subscription before deleting the user.",
        )
    await db.delete(user)
    await db.commit()
    return {"message": "User deleted successfully"}


@router.get("/subscriptions", response_model=PaginatedAdminSubscriptions)
async def list_admin_subscriptions(
    search: str | None = None,
    subscription_status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> PaginatedAdminSubscriptions:
    filters = []
    if subscription_status:
        normalized_status = subscription_status.strip().lower()
        filters.append(Subscription.status.in_(SUBSCRIPTION_STATUS_GROUPS.get(normalized_status, (normalized_status,))))
    if search and search.strip():
        needle = f"%{search.strip().lower()}%"
        filters.append(
            or_(
                func.lower(Subscription.email_snapshot).like(needle),
                func.lower(User.email).like(needle),
                func.lower(User.first_name).like(needle),
                func.lower(User.last_name).like(needle),
            )
        )

    total = (
        await db.execute(
            select(func.count(Subscription.id)).select_from(Subscription).outerjoin(User, User.id == Subscription.user_id).where(*filters)
        )
    ).scalar_one()
    result = await db.execute(
        select(Subscription, User)
        .outerjoin(User, User.id == Subscription.user_id)
        .where(*filters)
        .order_by(Subscription.created_at.desc(), Subscription.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    current_page, total_pages = _page_values(page, page_size, total)
    items = []
    for subscription, user in result.all():
        items.append(
            AdminSubscriptionListItem(
                id=subscription.id,
                user_id=subscription.user_id,
                user_name=(f"{user.first_name} {user.last_name}".strip() if user else None),
                email=user.email if user else subscription.email_snapshot,
                plan=subscription.plan,
                status=subscription.status,
                paddle_subscription_id=subscription.paddle_subscription_id,
                started_at=subscription.started_at,
                ends_at=subscription.ends_at,
                created_at=subscription.created_at,
            )
        )
    return PaginatedAdminSubscriptions(
        items=items,
        page=current_page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.post("/subscriptions/{subscription_id}/cancel")
async def cancel_admin_subscription(
    subscription_id: uuid.UUID,
    _: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    result = await db.execute(
        select(Subscription).where(Subscription.id == subscription_id).with_for_update()
    )
    subscription = result.scalar_one_or_none()
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
    if subscription.status not in ("active", "past_due"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Subscription cannot be cancelled in its current state")
    if not subscription.paddle_subscription_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No Paddle subscription ID found")

    config = await get_paddle_config(db)
    if not config["api_key"]:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Paddle API key is missing")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{get_paddle_api_url()}/subscriptions/{subscription.paddle_subscription_id}/cancel",
            headers={
                "Authorization": _get_paddle_auth_header(config["api_key"]),
                "Content-Type": "application/json",
            },
            json={"effective_from": "next_billing_period"},
        )

    if response.status_code not in (200, 201):
        try:
            error_code = response.json().get("error", {}).get("code", "")
        except Exception:
            error_code = ""
        detail = "Subscription is already scheduled for cancellation." if error_code == "subscription_locked_pending_changes" else "Failed to cancel subscription in Paddle."
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)

    paddle_data = response.json().get("data", {})
    scheduled_change = paddle_data.get("scheduled_change") or {}
    period = paddle_data.get("current_billing_period") or {}
    subscription.ends_at = _parse_datetime(scheduled_change.get("effective_at") or period.get("ends_at"))
    subscription.status = "cancelling"
    await db.commit()

    if subscription.user_id:
        user = (await db.execute(select(User).where(User.id == subscription.user_id))).scalar_one_or_none()
        if user:
            ends_at = subscription.ends_at.strftime("%B %d, %Y") if subscription.ends_at else "end of billing period"
            send_subscription_cancelled_email(user.first_name, user.email, ends_at)

    return {
        "message": "Subscription cancellation scheduled successfully",
        "ends_at": subscription.ends_at.isoformat() if subscription.ends_at else "",
    }
