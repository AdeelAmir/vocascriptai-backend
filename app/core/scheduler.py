import asyncio
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.subscription import Subscription
from app.models.user import User
from app.email_sender.SMTP import send_subscription_reminder


async def process_expired_subscriptions() -> None:
    """
    Failsafe cleanup task: marks subscriptions whose cancellation period has ended
    as terminal while preserving their history.
    """
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(Subscription).where(
                Subscription.status == "cancelling",
                Subscription.ends_at != None,
                Subscription.ends_at <= now,
            )
        )
        subscriptions = result.scalars().all()

        for subscription in subscriptions:
            subscription.status = "canceled"
            print(f"Subscription expired for {subscription.email_snapshot} — marked as canceled.")

        if subscriptions:
            await db.commit()


async def check_expiring_subscriptions() -> None:
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        two_days_later = now + timedelta(days=2)

        # Find cancelling users whose subscription ends within the next 2 days
        result = await db.execute(
            select(Subscription, User).join(User, User.id == Subscription.user_id).where(
                Subscription.status == "cancelling",
                Subscription.ends_at != None,
                Subscription.ends_at <= two_days_later,
                Subscription.ends_at > now,
                Subscription.billing_type == "recurring",
            )
        )
        rows = result.all()

        for subscription, user in rows:
            ends_at_str = subscription.ends_at.strftime("%B %d, %Y")
            send_subscription_reminder(
                first_name=user.first_name,
                to_email=user.email,
                ends_at=ends_at_str,
            )
            print(f"Reminder sent to {user.email}, subscription ends {ends_at_str}")


async def run_scheduler() -> None:
    while True:
        try:
            await process_expired_subscriptions()
            await check_expiring_subscriptions()
        except Exception as e:
            print(f"Scheduler error: {e}")
        # Run every 24 hours
        await asyncio.sleep(86400)
