from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


BillingType = Literal["free", "recurring", "one_time"]
BillingInterval = Literal["month", "year"]
VideoQuotaPeriod = Literal["daily", "monthly", "yearly", "lifetime"]


class PricingFeatureInput(BaseModel):
    feature_key: str | None = None
    label: str = Field(min_length=1, max_length=250)
    included: bool = True
    sort_order: int = Field(default=0, ge=0)


class PricingUpsert(BaseModel):
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    price_amount_minor: int = Field(default=0, ge=0)
    currency_code: str = Field(default="USD", min_length=3, max_length=3)
    billing_type: BillingType = "free"
    billing_interval: BillingInterval | None = None
    billing_frequency: int = Field(default=1, ge=1)
    video_quota_period: VideoQuotaPeriod = "monthly"
    video_quota_limit: int | None = Field(default=None, ge=1)
    video_quota_unlimited: bool = True
    daily_video_limit: int | None = Field(default=None, ge=1)
    daily_video_quota_unlimited: bool = True
    monthly_video_limit: int | None = Field(default=None, ge=1)
    monthly_video_quota_unlimited: bool = True
    max_file_size_mb: Decimal | None = Field(default=None, gt=0)
    max_file_size_unlimited: bool = True
    max_duration_minutes: Decimal | None = Field(default=None, gt=0)
    max_duration_unlimited: bool = True
    transcript_language_mode: Literal["english", "all"] = "english"
    summary_language_mode: Literal["english", "all"] = "english"
    prompts_enabled: bool = False
    ai_model: Literal["standard", "powerful"] = "standard"
    pdf_download_enabled: bool = True
    priority_support_enabled: bool = False
    youtube_enabled: bool = False
    is_active: bool = False
    is_highlighted: bool = False
    sort_order: int = Field(default=0, ge=0)
    features: list[PricingFeatureInput] = Field(default_factory=list)

    @field_validator("currency_code")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_billing(self) -> "PricingUpsert":
        if self.billing_type in ("free", "one_time") and self.billing_interval is not None:
            raise ValueError("Free and one-time plans must not have a billing interval.")
        if self.billing_type == "one_time":
            self.video_quota_period = "lifetime"
        if self.billing_type == "recurring" and self.billing_interval not in ("month", "year"):
            raise ValueError("Recurring plans must use a month or year billing interval.")
        if self.billing_type == "free" and self.price_amount_minor != 0:
            raise ValueError("Free plans must have a zero price.")
        if self.billing_type != "free" and self.price_amount_minor <= 0:
            raise ValueError("Paid plans must have a positive price.")
        if not self.video_quota_unlimited and self.video_quota_limit is None:
            raise ValueError("Video quota count is required unless unlimited is enabled.")
        if not self.daily_video_quota_unlimited and self.daily_video_limit is None:
            raise ValueError("Daily video limit is required unless unlimited is enabled.")
        if not self.monthly_video_quota_unlimited and self.monthly_video_limit is None:
            raise ValueError("Monthly video limit is required unless unlimited is enabled.")
        if not self.max_file_size_unlimited and self.max_file_size_mb is None:
            raise ValueError("Max file size is required unless unlimited is enabled.")
        if not self.max_duration_unlimited and self.max_duration_minutes is None:
            raise ValueError("Max duration is required unless unlimited is enabled.")
        return self


class PricingFeatureResponse(PricingFeatureInput):
    id: uuid.UUID


class PricingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    description: str
    price_amount_minor: int
    currency_code: str
    billing_type: str
    billing_interval: str | None
    billing_frequency: int
    video_quota_period: str
    video_quota_limit: int | None
    video_quota_unlimited: bool
    daily_video_limit: int | None
    daily_video_quota_unlimited: bool
    monthly_video_limit: int | None
    monthly_video_quota_unlimited: bool
    max_file_size_mb: Decimal | None
    max_file_size_unlimited: bool
    max_duration_minutes: Decimal | None
    max_duration_unlimited: bool
    transcript_language_mode: str
    summary_language_mode: str
    prompts_enabled: bool
    ai_model: str
    pdf_download_enabled: bool
    priority_support_enabled: bool
    youtube_enabled: bool
    paddle_product_id: str | None
    paddle_price_id: str | None
    is_active: bool
    is_highlighted: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime
    features: list[PricingFeatureResponse] = Field(default_factory=list)


class CheckoutRequest(BaseModel):
    pricing_id: uuid.UUID
