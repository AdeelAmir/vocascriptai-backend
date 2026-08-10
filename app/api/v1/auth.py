import hashlib
import random
import string
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    create_access_token,
    get_current_admin,
    hash_password,
    verify_password,
    get_current_user,
)
from app.email_sender.SMTP import send_verification_email
# from app.email_sender.email_send import send_verification_email
from app.models.user import User
from app.models.subscription import Subscription
from app.models.email_verification_token import EmailVerificationToken
from app.models.password_reset_token import PasswordResetToken
from app.services.pricing_entitlements import PricingEntitlementService
from app.services.subscriptions import (
    CURRENT_SUBSCRIPTION_STATUSES,
    get_current_subscription,
    reconcile_user_subscriptions,
)
from app.services.user_serialization import build_user_response
from app.schemas.admin import AdminResponse
from app.schemas.user import (
    UserRegister,
    UserLogin,
    UserResponse,
    TokenResponse,
    UserLoginResponse,
    RegisterResponse,
    OTPVerify,
    ForgotPassword,
    ResetPassword,
    UserSubscriptionSummary,
    OTPVerifyResponse,
    UserProfileUpdate,
    UserPasswordChange,
)

router = APIRouter()

def generate_otp() -> str:
    return ''.join(random.choices(string.digits, k=6))

def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


# ==================== ADMIN ====================

from app.schemas.user import CombinedLogin

# ==================== COMBINED LOGIN ====================

@router.post("/login")
async def combined_login(
    body: CombinedLogin,
    db: AsyncSession = Depends(get_db),
) -> dict:

    user_result = await db.execute(select(User).where(
        func.lower(User.email) == body.email.lower()
    ))
    user = user_result.scalar_one_or_none()

    if user:
        if not verify_password(body.password, user.password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")

        if user.role == 1:
            if not user.is_active:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled.")

            token = create_access_token({
                "sub": str(user.id), "email": user.email, "role": 1, "type": "admin"
            })
            return {
                "role": "admin",
                "token": {"access_token": token, "token_type": "bearer"},
                "admin": AdminResponse.model_validate(user),
            }

        if not user.is_verified:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Please verify your email first.")

        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled.")

        token = create_access_token({"sub": str(user.id), "email": user.email, "role": 2, "type": "user"})

        return {
            "role": "user",
            "token": {"access_token": token, "token_type": "bearer"},
            "user": build_user_response(user, await get_current_subscription(db, user.id)),
        }

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")


@router.post("/logout")
async def logout(_: dict = Depends(get_current_admin)) -> dict[str, str]:
    return {"message": "Logged out successfully"}


@router.get("/me/admin", response_model=AdminResponse)
async def get_admin_me(token_payload: dict = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> AdminResponse:
    admin_id = uuid.UUID(token_payload.get("sub"))
    result = await db.execute(select(User).where(User.id == admin_id, User.role == 1))
    admin = result.scalar_one_or_none()

    if admin is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin not found")

    return AdminResponse.model_validate(admin)


# ==================== USER ====================

@router.post("/user/register", response_model=RegisterResponse)
async def user_register(
    body: UserRegister,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:

    # Check if email already exists
    normalized_email = body.email.strip().lower()
    result = await db.execute(select(User).where(func.lower(User.email) == normalized_email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        if not existing_user.is_verified:
            # Resend OTP
            otp = generate_otp()
            otp_hash = hash_otp(otp)
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

            # Delete old tokens
            old_tokens = await db.execute(
                select(EmailVerificationToken).where(EmailVerificationToken.user_id == existing_user.id)
            )
            for token in old_tokens.scalars().all():
                await db.delete(token)

            new_token = EmailVerificationToken(
                user_id=existing_user.id,
                token_hash=otp_hash,
                expires_at=expires_at,
            )
            db.add(new_token)
            await db.commit()

            send_verification_email(body.email, otp)
            return RegisterResponse(
                message="OTP resent to your email.",
                user=build_user_response(existing_user, await get_current_subscription(db, existing_user.id)),
            )

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered.")

    # Create new user
    new_user = User(
        first_name=body.first_name,
        last_name=body.last_name,
        email=normalized_email,
        password=hash_password(body.password),
        is_verified=False,
        is_active=True,
    )
    db.add(new_user)
    await db.flush()

    # Generate OTP
    otp = generate_otp()
    otp_hash = hash_otp(otp)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    verification_token = EmailVerificationToken(
        user_id=new_user.id,
        token_hash=otp_hash,
        expires_at=expires_at,
    )
    db.add(verification_token)
    await db.commit()
    await db.refresh(new_user)

    send_verification_email(body.email, otp)

    return RegisterResponse(
        message="Account created. Please check your email for the OTP.",
        user=build_user_response(new_user, None),
    )


@router.post("/user/verify-otp", response_model=OTPVerifyResponse)
async def verify_otp(
    request: Request,
    body: OTPVerify,
    db: AsyncSession = Depends(get_db),
) -> OTPVerifyResponse:

    result = await db.execute(select(User).where(func.lower(User.email) == body.email.strip().lower()))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if user.is_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account already verified.")

    async def transfer_guest_quota():
        visitor_id = request.headers.get("x-visitor-id") or request.cookies.get("briefroom_visitor_id")
        forwarded = request.headers.get("x-forwarded-for")
        client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
        await PricingEntitlementService.transfer_guest_usage_to_user(visitor_id, client_ip, user, db)

    def build_verified_login_response() -> OTPVerifyResponse:
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled.")
        token = create_access_token({
            "sub": str(user.id),
            "email": user.email,
            "role": 2,
            "type": "user",
        })
        return OTPVerifyResponse(
            message="Email verified successfully. You are now logged in.",
            user=build_user_response(user, None),
            token=TokenResponse(access_token=token),
        )

    # Master OTP for testing
    if body.otp_code == "111111":
        user.is_verified = True
        await transfer_guest_quota()
        await db.commit()
        return build_verified_login_response()

    otp_hash = hash_otp(body.otp_code)
    token_result = await db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.token_hash == otp_hash,
            EmailVerificationToken.used == False,
        )
    )
    token = token_result.scalar_one_or_none()

    if token is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP.")

    if token.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP has expired.")

    token.used = True
    user.is_verified = True
    await transfer_guest_quota()
    await db.commit()

    return build_verified_login_response()


@router.post("/user/login", response_model=UserLoginResponse)
async def user_login(
    body: UserLogin,
    db: AsyncSession = Depends(get_db),
) -> UserLoginResponse:

    result = await db.execute(select(User).where(func.lower(User.email) == body.email.strip().lower()))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")

    if not verify_password(body.password, user.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")

    if not user.is_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Please verify your email first.")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled.")

    token = create_access_token({"sub": str(user.id), "email": user.email, "role": 2, "type": "user"})

    return UserLoginResponse(
        user=build_user_response(user, await get_current_subscription(db, user.id)),
        token=TokenResponse(access_token=token),
    )


@router.get("/user/me", response_model=UserResponse)
async def get_user_me(
    token_payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    user_id = uuid.UUID(token_payload.get("sub"))
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    return build_user_response(user, await get_current_subscription(db, user.id))


@router.put("/user/profile", response_model=UserResponse)
async def update_user_profile(
    body: UserProfileUpdate,
    token_payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    user_id = uuid.UUID(token_payload.get("sub"))
    result = await db.execute(select(User).where(User.id == user_id, User.role == 2))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    user.first_name = body.first_name
    user.last_name = body.last_name
    await db.commit()
    await db.refresh(user)

    return build_user_response(user, await get_current_subscription(db, user.id))


@router.put("/user/change-password")
async def change_user_password(
    body: UserPasswordChange,
    token_payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    user_id = uuid.UUID(token_payload.get("sub"))
    result = await db.execute(select(User).where(User.id == user_id, User.role == 2))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if not verify_password(body.current_password, user.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    user.password = hash_password(body.new_password)
    await db.commit()

    return {"message": "Password updated successfully."}


@router.get("/user/subscriptions", response_model=list[UserSubscriptionSummary])
async def get_user_subscriptions(
    token_payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[UserSubscriptionSummary]:
    user_id = uuid.UUID(token_payload.get("sub"))
    await reconcile_user_subscriptions(db, user_id)
    await db.commit()
    result = await db.execute(
        select(Subscription)
        .where(
            Subscription.user_id == user_id,
            Subscription.status.in_(CURRENT_SUBSCRIPTION_STATUSES),
        )
        .order_by(Subscription.created_at.desc(), Subscription.id.desc())
    )
    rows = result.scalars().all()
    summaries: list[UserSubscriptionSummary] = []
    one_time_by_plan: dict[str, UserSubscriptionSummary] = {}

    def merge_one_time_quota(
        current: dict,
        additional: dict,
    ) -> dict:
        merged = {**current, **additional}
        current_unlimited = bool(current.get("video_quota_unlimited", False))
        additional_unlimited = bool(additional.get("video_quota_unlimited", False))
        current_limit = current.get("video_quota_limit")
        additional_limit = additional.get("video_quota_limit")

        merged["video_quota_period"] = "lifetime"
        if current_unlimited or additional_unlimited:
            merged["video_quota_limit"] = None
            merged["video_quota_unlimited"] = True
        else:
            limits = [limit for limit in (current_limit, additional_limit) if isinstance(limit, (int, float))]
            merged["video_quota_limit"] = sum(limits) if limits else None
            merged["video_quota_unlimited"] = False

        # Daily/monthly reset fields do not apply to one-time purchases.
        merged["daily_video_limit"] = None
        merged["daily_video_quota_unlimited"] = True
        merged["monthly_video_limit"] = None
        merged["monthly_video_quota_unlimited"] = True
        return merged

    for item in rows:
        summary = UserSubscriptionSummary(
            id=item.id,
            purchase_count=1,
            pricing_id=item.pricing_id,
            pricing_slug=item.pricing_slug_snapshot or item.plan,
            pricing_name=item.pricing_name_snapshot or item.plan,
            billing_type=item.billing_type_snapshot or item.billing_type,
            status=item.status,
            paddle_subscription_id=item.paddle_subscription_id,
            paddle_transaction_id=item.paddle_transaction_id,
            price_amount_minor=item.price_amount_minor_snapshot,
            currency_code=item.currency_code_snapshot,
            billing_interval=item.billing_interval_snapshot,
            entitlements=item.entitlements_snapshot or {},
            quota=item.quota_snapshot or {},
            started_at=item.started_at,
            ends_at=item.ends_at,
        )
        if summary.billing_type != "one_time":
            summaries.append(summary)
            continue

        # A one-time checkout is a reusable allowance, not a recurring
        # subscription. Merge repeat purchases of the same package into one
        # profile entry while keeping their limits additive.
        plan_key = str(summary.pricing_id or summary.pricing_slug)
        existing = one_time_by_plan.get(plan_key)
        if existing is None:
            one_time_by_plan[plan_key] = summary
            summaries.append(summary)
        else:
            existing.purchase_count += summary.purchase_count
            existing.price_amount_minor = (existing.price_amount_minor or 0) + (summary.price_amount_minor or 0)
            existing.quota = merge_one_time_quota(existing.quota, summary.quota)
            existing.entitlements = {**existing.entitlements, **summary.entitlements}

    return summaries


@router.post("/user/forgot-password")
async def forgot_password(
    body: ForgotPassword,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:

    result = await db.execute(select(User).where(func.lower(User.email) == body.email.strip().lower()))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email does not exist. Please enter a registered email address.",
        )

    # Delete old reset tokens
    old_tokens = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
    )
    for token in old_tokens.scalars().all():
        await db.delete(token)

    otp = generate_otp()
    otp_hash = hash_otp(otp)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    reset_token = PasswordResetToken(
        user_id=user.id,
        token_hash=otp_hash,
        expires_at=expires_at,
    )
    db.add(reset_token)
    await db.commit()

    send_verification_email(body.email, otp)

    return {"message": "An OTP has been sent to your email."}


@router.post("/user/reset-password")
async def reset_password(
    body: ResetPassword,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:

    result = await db.execute(select(User).where(func.lower(User.email) == body.email.strip().lower()))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    otp_hash = hash_otp(body.otp_code)
    token_result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.token_hash == otp_hash,
            PasswordResetToken.used == False,
        )
    )
    token = token_result.scalar_one_or_none()

    if token is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP.")

    if token.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP has expired.")

    token.used = True
    user.password = hash_password(body.new_password)
    await db.commit()

    return {"message": "Password reset successfully. You can now login."}
