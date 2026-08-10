import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("paddle_subscription_id", name="uq_subscriptions_paddle_subscription_id"),
        UniqueConstraint("paddle_transaction_id", name="uq_subscriptions_paddle_transaction_id"),
        Index("ix_subscriptions_user_id", "user_id"),
        Index("ix_subscriptions_status", "status"),
        Index("ix_subscriptions_created_at", "created_at"),
        Index("uq_subscriptions_free_user", "user_id", unique=True, postgresql_where=text("billing_type = 'free'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    pricing_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("pricings.id", ondelete="SET NULL"), nullable=True
    )
    email_snapshot: Mapped[str] = mapped_column(String, nullable=False)
    paddle_subscription_id: Mapped[str | None] = mapped_column(String, nullable=True)
    paddle_transaction_id: Mapped[str | None] = mapped_column(String, nullable=True)
    paddle_customer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    plan: Mapped[str] = mapped_column(String, default="premium", nullable=False)
    billing_type: Mapped[str] = mapped_column(String, default="recurring", nullable=False)
    pricing_slug_snapshot: Mapped[str | None] = mapped_column(String, nullable=True)
    pricing_name_snapshot: Mapped[str | None] = mapped_column(String, nullable=True)
    price_amount_minor_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency_code_snapshot: Mapped[str | None] = mapped_column(String(3), nullable=True)
    billing_type_snapshot: Mapped[str | None] = mapped_column(String, nullable=True)
    billing_interval_snapshot: Mapped[str | None] = mapped_column(String, nullable=True)
    paddle_price_id_snapshot: Mapped[str | None] = mapped_column(String, nullable=True)
    entitlements_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    quota_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_webhook_occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_webhook_event_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
