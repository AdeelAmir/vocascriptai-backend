import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.subscription import Subscription
from app.models.pricing import Pricing
from app.schemas.pricing import CheckoutRequest
from app.services.pricing_entitlements import pricing_snapshot
from app.email_sender.SMTP import send_subscription_cancelled_email
from app.services.subscriptions import (
    current_subscription_condition,
    reconcile_user_subscriptions,
    webhook_time,
)

router = APIRouter()

def get_paddle_api_url() -> str:
    """
    Returns the appropriate Paddle API URL based on APP_ENV setting.
    """
    env = (getattr(settings, "APP_ENV", "") or "").lower()
    return "https://api.paddle.com" if env == "production" else "https://sandbox-api.paddle.com"


def _get_paddle_auth_header(api_key: str) -> str:
    """
    Sanitizes API Key formatting to guarantee clean 'Bearer <API_KEY>' header,
    stripping extra spaces, quotes, or accidental duplicate 'Bearer ' prefixes.
    """
    clean_key = (api_key or "").strip().strip('"\'')
    if clean_key.lower().startswith("bearer "):
        clean_key = clean_key[7:].strip().strip('"\'')
    return f"Bearer {clean_key}"


async def get_paddle_config(db: AsyncSession) -> dict[str, str]:
    """
    Reads Paddle keys dynamically from database setting table with fallback to config settings (.env).
    """
    from app.api.v1.setting import _get_setting_value

    db_api_key = await _get_setting_value(db, "PADDLE_API_KEY")
    db_webhook_secret = await _get_setting_value(db, "PADDLE_WEBHOOK_SECRET")
    db_price_id = await _get_setting_value(db, "PADDLE_PRICE_ID")
    db_client_token = await _get_setting_value(db, "PADDLE_CLIENT_TOKEN")

    return {
        "api_key": (db_api_key or getattr(settings, "PADDLE_API_KEY", "")).strip().strip('"\''),
        "webhook_secret": (db_webhook_secret or getattr(settings, "PADDLE_WEBHOOK_SECRET", "")).strip().strip('"\''),
        "price_id": (db_price_id or getattr(settings, "PADDLE_PRICE_ID", "")).strip().strip('"\''),
        "client_token": (db_client_token or getattr(settings, "PADDLE_CLIENT_TOKEN", "")).strip().strip('"\''),
    }


def verify_paddle_webhook(payload: bytes, signature_header: str, webhook_secret: str) -> bool:
    """
    Verifies the Paddle-Signature header according to Paddle Billing webhook security standards:
    Header format: ts=<timestamp>;h1=<sha256-hmac>
    Signed payload: <ts>:<raw_body>
    """
    clean_secret = (webhook_secret or "").strip().strip('"\'')
    if not signature_header or not clean_secret:
        return False
    try:
        parts = {}
        for part in signature_header.split(";"):
            if "=" in part:
                key, value = part.split("=", 1)
                parts[key.strip()] = value.strip()

        ts = parts.get("ts")
        h1 = parts.get("h1")

        if not ts or not h1:
            return False

        signed_payload = f"{ts}:{payload.decode('utf-8')}"
        mac = hmac.new(
            clean_secret.encode("utf-8"),
            signed_payload.encode("utf-8"),
            hashlib.sha256,
        )
        expected = mac.hexdigest()

        return hmac.compare_digest(expected, h1)
    except Exception:
        return False


async def _find_user_for_webhook(data: dict, db: AsyncSession) -> User | None:
    """
    Multi-layer user lookup for Paddle Webhooks:
    1. custom_data.user_id
    2. paddle_subscription_id match (data.id or data.subscription_id)
    3. customer.email match
    """
    # 1. Check custom_data
    custom_data = data.get("custom_data") or {}
    user_id_str = custom_data.get("user_id")
    if user_id_str:
        try:
            user_uuid = uuid.UUID(str(user_id_str))
            res = await db.execute(select(User).where(User.id == user_uuid))
            user = res.scalar_one_or_none()
            if user:
                return user
        except ValueError:
            pass

    # 2. Check subscription history by Paddle subscription ID
    sub_id = _subscription_id_from_event("", data)
    if sub_id:
        res = await db.execute(
            select(User)
            .join(Subscription, Subscription.user_id == User.id)
            .where(Subscription.paddle_subscription_id == sub_id)
        )
        if (user := res.scalar_one_or_none()) is not None:
            return user

    # 3. Check customer email
    customer = data.get("customer") or {}
    customer_email = customer.get("email") or data.get("customer_email")
    if customer_email:
        res = await db.execute(select(User).where(User.email.ilike(customer_email.strip())))
        user = res.scalar_one_or_none()
        if user:
            return user

    return None


def _subscription_id_from_event(event_type: str, data: dict) -> str | None:
    """Return Paddle's subscription ID even when the webhook omits data.object.

    Paddle subscription webhooks normally carry the subscription ID in data.id.
    Some payloads do not include data.object, so event type and Paddle's ID
    prefix are also valid signals. Transaction webhooks keep using the nested
    subscription_id field when present.
    """
    data_id = data.get("id")
    if (
        event_type.startswith("subscription.")
        or data.get("object") == "subscription"
        or str(data_id or "").startswith("sub_")
    ):
        return data_id or data.get("subscription_id")
    return data.get("subscription_id")


async def _get_or_create_subscription(
    data: dict,
    user: User,
    db: AsyncSession,
    event_type: str = "",
) -> Subscription | None:
    subscription_id = _subscription_id_from_event(event_type, data)
    transaction_id = data.get("id") if event_type.startswith("transaction.") else None
    if not subscription_id and not transaction_id:
        return None

    subscription = None
    if transaction_id:
        result = await db.execute(
            select(Subscription).where(Subscription.paddle_transaction_id == transaction_id).with_for_update()
        )
        subscription = result.scalar_one_or_none()
    if subscription is None and subscription_id:
        result = await db.execute(
            select(Subscription).where(Subscription.paddle_subscription_id == subscription_id).with_for_update()
        )
        subscription = result.scalar_one_or_none()
    customer_id = data.get("customer_id") or (data.get("customer") or {}).get("id")

    price_id = None
    for item in data.get("items") or data.get("line_items") or []:
        price = item.get("price") or {}
        price_id = price.get("id") or item.get("price_id")
        if price_id:
            break

    custom_data = data.get("custom_data") or {}
    pricing = None
    custom_pricing_id = custom_data.get("pricing_id")
    if custom_pricing_id:
        try:
            pricing = (
                await db.execute(
                    select(Pricing).where(Pricing.id == uuid.UUID(str(custom_pricing_id)))
                )
            ).scalar_one_or_none()
        except ValueError:
            pricing = None
    if pricing is None and custom_data.get("pricing_slug"):
        pricing = (
            await db.execute(select(Pricing).where(Pricing.slug == str(custom_data["pricing_slug"])))
        ).scalar_one_or_none()
    if pricing is None and price_id:
        pricing = (await db.execute(select(Pricing).where(Pricing.paddle_price_id == price_id))).scalar_one_or_none()
    if pricing is None:
        pricing = (await db.execute(select(Pricing).where(Pricing.slug == "pro"))).scalar_one_or_none()
    if pricing is None:
        return None

    # Paddle may send transaction.completed before subscription.activated. If
    # the transaction webhook created an orphan row, attach the real Paddle
    # subscription ID to that row instead of creating a duplicate plan card.
    if subscription is None and subscription_id:
        orphan_result = await db.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user.id,
                Subscription.pricing_id == pricing.id,
                Subscription.billing_type == pricing.billing_type,
                Subscription.paddle_subscription_id.is_(None),
                Subscription.paddle_transaction_id.is_not(None),
                Subscription.status.in_(("pending", "active", "failed")),
            )
            .order_by(Subscription.created_at.desc(), Subscription.id.desc())
            .limit(1)
            .with_for_update()
        )
        subscription = orphan_result.scalar_one_or_none()
        if subscription is not None:
            subscription.paddle_subscription_id = subscription_id

    entitlements, quota = pricing_snapshot(pricing)
    if subscription is None:
        subscription = Subscription(
            user_id=user.id,
            pricing_id=pricing.id,
            email_snapshot=user.email,
            paddle_subscription_id=subscription_id,
            paddle_transaction_id=transaction_id,
            paddle_customer_id=customer_id,
            plan=pricing.slug,
            billing_type=pricing.billing_type,
            pricing_slug_snapshot=pricing.slug,
            pricing_name_snapshot=pricing.name,
            price_amount_minor_snapshot=pricing.price_amount_minor,
            currency_code_snapshot=pricing.currency_code,
            billing_type_snapshot=pricing.billing_type,
            billing_interval_snapshot=pricing.billing_interval,
            paddle_price_id_snapshot=price_id or pricing.paddle_price_id,
            entitlements_snapshot=entitlements,
            quota_snapshot=quota,
            status=(
                "active" if event_type == "transaction.completed"
                else "pending" if event_type.startswith("transaction.")
                else "active" if event_type in ("subscription.activated", "subscription.resumed")
                else "pending"
            ),
        )
        db.add(subscription)
        await db.flush()
    else:
        subscription.user_id = user.id
        subscription.email_snapshot = user.email
        if transaction_id and subscription.paddle_transaction_id is None:
            subscription.paddle_transaction_id = transaction_id
        subscription.pricing_id = pricing.id
        subscription.plan = pricing.slug
        subscription.billing_type = pricing.billing_type
        if subscription.pricing_slug_snapshot is None:
            subscription.pricing_slug_snapshot = pricing.slug
            subscription.pricing_name_snapshot = pricing.name
            subscription.price_amount_minor_snapshot = pricing.price_amount_minor
            subscription.currency_code_snapshot = pricing.currency_code
            subscription.billing_type_snapshot = pricing.billing_type
            subscription.billing_interval_snapshot = pricing.billing_interval
            subscription.paddle_price_id_snapshot = price_id or pricing.paddle_price_id
            subscription.entitlements_snapshot = entitlements
            subscription.quota_snapshot = quota
        if customer_id:
            subscription.paddle_customer_id = customer_id
    return subscription


def _parse_datetime(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return None


@router.post("/create-checkout")
async def create_checkout(
    body: CheckoutRequest,
    token_payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user_id = uuid.UUID(token_payload.get("sub"))
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    pricing = (await db.execute(select(Pricing).where(Pricing.id == body.pricing_id))).scalar_one_or_none()
    if pricing is None:
        raise HTTPException(status_code=404, detail="Pricing plan not found.")
    if pricing.billing_type == "free":
        raise HTTPException(status_code=400, detail="Free plans do not require checkout.")
    if not pricing.is_active:
        raise HTTPException(status_code=400, detail="This pricing plan is not available for checkout.")

    active_statuses = ("active", "cancelling", "past_due")
    now = datetime.now(timezone.utc)
    recurring_conditions = (
        Subscription.user_id == user.id,
        Subscription.billing_type == "recurring",
        Subscription.status.in_(active_statuses),
        or_(Subscription.status != "cancelling", Subscription.ends_at.is_(None), Subscription.ends_at > now),
    )
    if pricing.billing_type == "recurring":
        existing_recurring = (
            await db.execute(
                select(Subscription.id).where(
                    *recurring_conditions,
                ).limit(1)
            )
        ).scalar_one_or_none()
        if existing_recurring is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You already have an active recurring plan.")
    elif pricing.billing_type == "one_time":
        existing_recurring = (
            await db.execute(
                select(Subscription.id).where(
                    *recurring_conditions,
                ).limit(1)
            )
        ).scalar_one_or_none()
        if existing_recurring is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="One-time plans are unavailable while you have an active recurring subscription.")
        # One-time purchases are consumable entitlements, not subscriptions.
        # Every successful checkout must create a separate purchase record so
        # the customer can buy the same package again after (or before) using
        # the previous purchase's allowance.

    paddle_config = await get_paddle_config(db)
    api_key = paddle_config["api_key"]
    price_id = pricing.paddle_price_id or (paddle_config["price_id"] if pricing.slug == "pro" else "")

    # Preserve the existing single-price deployment during the migration. Once
    # a Pro checkout succeeds, the legacy price is also attached to the Pro row.
    if pricing.slug == "pro" and not pricing.paddle_price_id and price_id:
        pricing.paddle_price_id = price_id
        if not pricing.paddle_product_id and api_key:
            async with httpx.AsyncClient(timeout=20) as client:
                price_response = await client.get(
                    f"{get_paddle_api_url()}/prices/{price_id}",
                    params={"include": "product"},
                    headers={"Authorization": _get_paddle_auth_header(api_key)},
                )
            if price_response.status_code == 200:
                pricing.paddle_product_id = price_response.json().get("data", {}).get("product_id")
        await db.commit()

    if not api_key or not price_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Paddle payment configuration is missing.",
        )

    auth_header = _get_paddle_auth_header(api_key)
    api_url = get_paddle_api_url()

    async with httpx.AsyncClient(timeout=30) as client:
        # Paddle defaults catalog prices to a 1-100 quantity range. Lock the
        # existing price to a single unit so overlay checkout cannot offer a
        # quantity selector or allow multiple subscriptions in one checkout.
        quantity_response = await client.patch(
            f"{api_url}/prices/{price_id}",
            headers={
                "Authorization": auth_header,
                "Content-Type": "application/json",
            },
            json={"quantity": {"minimum": 1, "maximum": 1}},
        )
        if quantity_response.status_code not in (200, 201):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to configure the Paddle price for a single subscription.",
            )

        response = await client.post(
            f"{api_url}/transactions",
            headers={
                "Authorization": auth_header,
                "Content-Type": "application/json",
            },
            json={
                "items": [
                    {
                        "price_id": price_id,
                        "quantity": 1,
                    }
                ],
                "customer": {
                    "email": user.email,
                },
                "custom_data": {
                    "user_id": str(user.id),
                    "pricing_id": str(pricing.id),
                    "pricing_slug": pricing.slug,
                },
                "collection_mode": "automatic",
            },
        )

    if response.status_code not in (200, 201):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to create Paddle transaction: {response.text}",
        )

    transaction = response.json()
    transaction_id = transaction.get("data", {}).get("id")

    if not transaction_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Paddle transaction ID not returned.",
        )

    return {
        "transaction_id": transaction_id,
    }


@router.post("/webhook")
async def paddle_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    payload = await request.body()
    signature_header = request.headers.get("paddle-signature", "")

    paddle_config = await get_paddle_config(db)
    webhook_secret = paddle_config["webhook_secret"]

    if not webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Paddle webhook secret is not configured.",
        )
    if not verify_paddle_webhook(payload, signature_header, webhook_secret):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature.")

    try:
        event = json.loads(payload)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload.")

    event_type = event.get("event_type", "")
    data = event.get("data", {})

    user = await _find_user_for_webhook(data, db)
    if user is None:
        return {"status": "ignored", "reason": "user not found"}

    subscription = await _get_or_create_subscription(data, user, db, event_type)
    if subscription is None:
        return {"status": "ignored", "reason": "subscription or pricing identity not found"}

    event_id = event.get("event_id") or event.get("id")
    occurred_at = webhook_time(event.get("occurred_at") or data.get("updated_at"))
    if event_id and subscription.last_webhook_event_id == event_id:
        await db.rollback()
        return {"status": "ignored", "reason": "duplicate event"}
    if (
        occurred_at
        and subscription.last_webhook_occurred_at
        and occurred_at <= subscription.last_webhook_occurred_at
    ):
        await db.rollback()
        return {"status": "ignored", "reason": "out-of-order event"}

    scheduled_change = data.get("scheduled_change") or {}
    current_period = data.get("current_billing_period") or {}
    if subscription.started_at is None:
        subscription.started_at = _parse_datetime(
            data.get("started_at") or current_period.get("starts_at") or data.get("created_at") or event.get("occurred_at")
        )
    scheduled_end = _parse_datetime(
        scheduled_change.get("effective_at") or current_period.get("ends_at")
    )
    incoming_status = data.get("status", "")

    # Terminal states are preserved against delayed ordinary updates. An explicit
    # resumed event is the only event allowed to reopen a terminal subscription.
    if event_type in ("transaction.payment_failed", "transaction.failed") or incoming_status == "failed":
        subscription.status = "failed"
        subscription.ends_at = None
    elif subscription.status in ("canceled", "paused") and event_type != "subscription.resumed":
        pass
    elif event_type in ("subscription.activated", "transaction.completed"):
        if subscription.status != "cancelling" or scheduled_change.get("action") == "cancel":
            subscription.status = "cancelling" if scheduled_change.get("action") == "cancel" else "active"
            # For recurring plans, the current billing period end is the next
            # renewal date. One-time transactions do not have an access end.
            subscription.ends_at = (
                scheduled_end
                if subscription.status == "cancelling" or subscription.billing_type == "recurring"
                else None
            )
    elif event_type == "subscription.updated":
        if incoming_status in ("canceled", "paused"):
            subscription.status = incoming_status
            subscription.ends_at = None
        elif incoming_status == "past_due":
            subscription.status = "past_due"
            if subscription.billing_type == "recurring" and scheduled_end:
                subscription.ends_at = scheduled_end
        elif incoming_status == "active" or scheduled_change.get("action") == "cancel":
            if incoming_status == "active" and subscription.status == "cancelling" and scheduled_change.get("action") != "cancel":
                subscription.last_webhook_event_id = event_id
                subscription.last_webhook_occurred_at = occurred_at
                await db.commit()
                return {"status": "ignored", "reason": "cancellation state preserved"}
            subscription.status = "cancelling" if scheduled_change.get("action") == "cancel" else "active"
            subscription.ends_at = (
                scheduled_end
                if subscription.status == "cancelling" or subscription.billing_type == "recurring"
                else None
            )
    elif event_type == "subscription.canceled":
        subscription.status = "canceled"
        subscription.ends_at = None
    elif event_type == "subscription.paused":
        subscription.status = "paused"
        subscription.ends_at = None
    elif event_type == "subscription.resumed":
        subscription.status = "active"
        subscription.ends_at = scheduled_end if subscription.billing_type == "recurring" else None
    elif event_type == "subscription.past_due":
        subscription.status = "past_due"
        if subscription.billing_type == "recurring" and scheduled_end:
            subscription.ends_at = scheduled_end

    subscription.last_webhook_event_id = event_id
    subscription.last_webhook_occurred_at = occurred_at
    await reconcile_user_subscriptions(db, user.id, preferred=subscription)
    await db.commit()
    return {"status": "ok", "action": f"{event_type} — status is {subscription.status}"}


@router.post("/cancel-subscription")
async def cancel_subscription(
    token_payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user_id = uuid.UUID(token_payload.get("sub"))
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    subscription = (
        await db.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user.id,
                Subscription.billing_type == "recurring",
                current_subscription_condition(),
            )
            .order_by(Subscription.created_at.desc(), Subscription.id.desc())
            .limit(1)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No active recurring subscription to cancel.")

    if not subscription.paddle_subscription_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No subscription ID found.")

    paddle_config = await get_paddle_config(db)
    api_key = paddle_config["api_key"]

    if not api_key:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Paddle API key is missing.")

    auth_header = _get_paddle_auth_header(api_key)
    api_url = get_paddle_api_url()

    # Cancel at end of billing period — user retains premium access until then
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{api_url}/subscriptions/{subscription.paddle_subscription_id}/cancel",
            headers={
                "Authorization": auth_header,
                "Content-Type": "application/json",
            },
            json={
                "effective_from": "next_billing_period"
            },
        )

    if response.status_code not in (200, 201):
        error_data = response.json().get("error", {})
        error_code = error_data.get("code", "")
        if error_code == "subscription_locked_pending_changes":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Your subscription is already scheduled for cancellation.",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to cancel subscription. Please try again.",
        )

    paddle_data = response.json().get("data", {})

    scheduled_change = paddle_data.get("scheduled_change", {})
    ends_at_str = scheduled_change.get("effective_at")

    if ends_at_str:
        ends_at = _parse_datetime(ends_at_str)
    else:
        current_period = paddle_data.get("current_billing_period", {})
        ends_at_str = current_period.get("ends_at")
        ends_at = _parse_datetime(ends_at_str)

    # Mark as cancelling — user RETAINS premium tier until period ends
    subscription.status = "cancelling"
    subscription.ends_at = ends_at
    await db.commit()

    ends_at_display = ends_at.strftime("%B %d, %Y") if ends_at else "end of billing period"
    send_subscription_cancelled_email(
        first_name=user.first_name,
        to_email=user.email,
        ends_at=ends_at_display,
    )

    return {
        "status": "ok",
        "message": "Subscription cancelled successfully.",
        "ends_at": ends_at_display,
    }


@router.post("/portal-session")
async def create_portal_session(
    token_payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user_id = uuid.UUID(token_payload.get("sub"))
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    subscription = (
        await db.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user.id,
                Subscription.billing_type == "recurring",
                current_subscription_condition(),
            )
            .order_by(Subscription.created_at.desc(), Subscription.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if subscription is None or not subscription.paddle_subscription_id:
        raise HTTPException(status_code=404, detail="No active subscription found.")

    paddle_config = await get_paddle_config(db)
    api_key = paddle_config["api_key"]

    if not api_key:
        raise HTTPException(status_code=500, detail="Paddle API key is missing.")

    auth_header = _get_paddle_auth_header(api_key)
    api_url = get_paddle_api_url()
    customer_id = subscription.paddle_customer_id

    # Fallback to query Paddle by email if customer_id not stored yet
    if not customer_id:
        async with httpx.AsyncClient() as client:
            res = await client.get(
                f"{api_url}/customers",
                headers={"Authorization": auth_header},
                params={"email": user.email},
            )

        customers = res.json().get("data", [])
        if not customers:
            raise HTTPException(status_code=404, detail="No Paddle customer found.")

        customer_id = customers[0]["id"]
        subscription.paddle_customer_id = customer_id
        await db.commit()

    async with httpx.AsyncClient() as client:
        res = await client.post(
            f"{api_url}/customers/{customer_id}/portal-sessions",
            headers={
                "Authorization": auth_header,
                "Content-Type": "application/json",
            },
            json={
                "subscription_ids": [subscription.paddle_subscription_id]
            },
        )

    portal = res.json().get("data", {})
    urls = portal.get("urls", {})

    subscription_urls = urls.get("subscriptions", [])
    if subscription_urls:
        url = subscription_urls[0].get("cancel_subscription") or subscription_urls[0].get("update_subscription")
    else:
        url = urls.get("general", {}).get("overview")

    if not url:
        raise HTTPException(status_code=502, detail="Failed to generate portal URL.")

    return {"url": url}
