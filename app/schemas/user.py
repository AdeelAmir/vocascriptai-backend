import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator



class OTPVerify(BaseModel):
    email: EmailStr
    otp_code: str

class ForgotPassword(BaseModel):
    email: EmailStr

class ResetPassword(BaseModel):
    email: EmailStr
    otp_code: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

class UserRegister(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    password: str
    confirm_password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("Passwords do not match")
        return v
    

class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserProfileUpdate(BaseModel):
    first_name: str
    last_name: str

    @field_validator("first_name", "last_name")
    @classmethod
    def name_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name fields cannot be empty")
        return value


class UserPasswordChange(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters")
        return value


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    first_name: str
    last_name: str
    email: str
    role: int
    is_verified: bool
    is_active: bool
    subscription_tier: str
    subscription_status: str
    subscription_ends_at: datetime | None = None
    pricing_slug: str = "starter"
    pricing_name: str = "Starter"
    pricing_entitlements: dict = Field(default_factory=dict)
    pricing_quota: dict = Field(default_factory=dict)
    created_at: datetime


class UserSubscriptionSummary(BaseModel):
    id: uuid.UUID
    purchase_count: int = 1
    pricing_id: uuid.UUID | None = None
    pricing_slug: str
    pricing_name: str
    billing_type: str
    status: str
    paddle_subscription_id: str | None = None
    paddle_transaction_id: str | None = None
    price_amount_minor: int | None = None
    currency_code: str | None = None
    billing_interval: str | None = None
    billing_frequency: int | None = None
    entitlements: dict = Field(default_factory=dict)
    quota: dict = Field(default_factory=dict)
    started_at: datetime | None = None
    ends_at: datetime | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserLoginResponse(BaseModel):
    user: UserResponse
    token: TokenResponse


class OTPVerifyResponse(BaseModel):
    message: str
    user: UserResponse
    token: TokenResponse


class RegisterResponse(BaseModel):
    message: str
    user: UserResponse

class CombinedLogin(BaseModel):
    email: EmailStr
    password: str
