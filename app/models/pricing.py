import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Pricing(Base):
    __tablename__ = "pricings"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_pricings_slug"),
        Index("ix_pricings_active_order", "is_active", "sort_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    price_amount_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    billing_type: Mapped[str] = mapped_column(String(20), nullable=False, default="free")
    billing_interval: Mapped[str | None] = mapped_column(String(10), nullable=True)
    billing_frequency: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    video_quota_period: Mapped[str] = mapped_column(String(10), nullable=False, default="monthly")
    video_quota_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    video_quota_unlimited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    daily_video_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    daily_video_quota_unlimited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    monthly_video_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_video_quota_unlimited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_file_size_mb: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    max_file_size_unlimited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_duration_minutes: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    max_duration_unlimited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    transcript_language_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="english")
    summary_language_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="english")
    prompts_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ai_model: Mapped[str] = mapped_column(String(20), nullable=False, default="standard")
    pdf_download_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    priority_support_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    youtube_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    paddle_product_id: Mapped[str | None] = mapped_column(String, nullable=True)
    paddle_price_id: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_highlighted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class PricingFeature(Base):
    __tablename__ = "pricing_features"
    __table_args__ = (Index("ix_pricing_features_pricing_order", "pricing_id", "sort_order"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    pricing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pricings.id", ondelete="CASCADE"), nullable=False)
    feature_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    label: Mapped[str] = mapped_column(String(250), nullable=False)
    included: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class UsagePeriod(Base):
    __tablename__ = "usage_periods"
    __table_args__ = (
        UniqueConstraint("user_id", "entitlement_id", "period_type", "period_start", name="uq_usage_periods_key"),
        Index("ix_usage_periods_user_period", "user_id", "period_type", "period_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    entitlement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False)
    period_type: Mapped[str] = mapped_column(String(10), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    video_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class GuestUsagePeriod(Base):
    __tablename__ = "guest_usage_periods"
    __table_args__ = (
        UniqueConstraint("ip_address", "period_start", name="uq_guest_usage_periods_key"),
        Index("ix_guest_usage_periods_ip_period", "ip_address", "period_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ip_address: Mapped[str] = mapped_column(String(255), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    video_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class GuestVisitor(Base):
    __tablename__ = "guest_visitors"
    __table_args__ = (
        UniqueConstraint("visitor_id", name="uq_guest_visitors_visitor_id"),
        Index("ix_guest_visitors_visitor_id", "visitor_id"),
        Index("ix_guest_visitors_ip_address", "ip_address"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    visitor_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    ip_address: Mapped[str] = mapped_column(String(255), nullable=False)
    video_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

