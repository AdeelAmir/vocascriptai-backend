import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator


class AdminUserUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    is_active: bool | None = None
    is_verified: bool | None = None

    @field_validator("first_name", "last_name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr | None) -> str | None:
        return str(value).strip().lower() if value is not None else value


class AdminUserPasswordUpdate(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters")
        return value


class AdminUserListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    first_name: str
    last_name: str
    email: str
    is_active: bool
    is_verified: bool
    created_at: datetime


class SubscriptionSummary(BaseModel):
    id: uuid.UUID | None = None
    plan: str = "free"
    status: str = "free"
    paddle_subscription_id: str | None = None
    paddle_transaction_id: str | None = None
    billing_type: str | None = None
    started_at: datetime | None = None
    ends_at: datetime | None = None
    created_at: datetime | None = None


class AdminUserDetail(AdminUserListItem):
    role: int
    monthly_video_count: int
    usage_reset_date: date
    subscription: SubscriptionSummary | None = None


class PaginatedAdminUsers(BaseModel):
    items: list[AdminUserListItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class AdminSubscriptionListItem(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    user_name: str | None
    email: str
    plan: str
    status: str
    paddle_subscription_id: str | None
    started_at: datetime | None
    ends_at: datetime | None
    created_at: datetime


class PaginatedAdminSubscriptions(BaseModel):
    items: list[AdminSubscriptionListItem]
    page: int
    page_size: int
    total: int
    total_pages: int
