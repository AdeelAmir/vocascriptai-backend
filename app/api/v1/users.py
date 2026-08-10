from app.core.security import hash_refresh_token as hash_token  # reuse same hashing
from datetime import datetime, timedelta, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    create_refresh_token,
    hash_password,
    hash_refresh_token,
)
from app.core.config import settings
from app.models.user import User
from app.models.email_verification_token import EmailVerificationToken
from app.schemas.user import UserRegister, RegisterResponse, UserResponse
from app.email_sender.SMTP import send_verification_email
# from app.email_sender.email_send import send_verification_email
from fastapi import Request, Response
from app.schemas.user import UserLogin, UserLoginResponse, TokenResponse
from app.core.security import create_access_token, verify_password
from app.models.user_refresh_token import UserRefreshToken
from app.core.security import get_current_user
from app.services.subscriptions import get_current_subscription
from app.services.user_serialization import build_user_response

router = APIRouter()

@router.post("/login", response_model=UserLoginResponse)
async def login(
    body: UserLogin,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserLoginResponse:
    normalized_email = body.email.strip().lower()
    result = await db.execute(select(User).where(func.lower(User.email) == normalized_email))
    user = result.scalar_one_or_none()

    if user is None or user.role != 2 or not verify_password(body.password, user.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    if not user.is_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Please verify your email before logging in")

    access_token = create_access_token({"sub": str(user.id), "email": user.email, "role": 2, "type": "user"})

    raw_refresh_token = create_refresh_token()
    refresh_expires = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)

    db.add(UserRefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_refresh_token),
        expires_at=refresh_expires,
    ))
    await db.commit()

    response.set_cookie(
        key="user_refresh_token",
        value=raw_refresh_token,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="none" if settings.ENVIRONMENT == "production" else "lax",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/",
    )

    return UserLoginResponse(
        user=build_user_response(user, await get_current_subscription(db, user.id)),
        token=TokenResponse(access_token=access_token),
    )


@router.post("/register", response_model=RegisterResponse)
async def register(
    body: UserRegister,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    normalized_email = body.email.strip().lower()
    result = await db.execute(select(User).where(func.lower(User.email) == normalized_email))
    existing = result.scalar_one_or_none()

    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=normalized_email,
        first_name=body.first_name,
        last_name=body.last_name,
        password=hash_password(body.password),
        is_verified=False,
        is_active=True,
        role=2,
    )
    db.add(user)
    await db.flush()  # get user.id before commit

    raw_token = create_refresh_token()
    expires = datetime.now(timezone.utc) + timedelta(hours=24)

    db.add(EmailVerificationToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_token),
        expires_at=expires,
    ))
    await db.commit()

    verify_link = f"{settings.FRONTEND_URL}/verify-email?token={raw_token}"
    send_verification_email(body.email, verify_link)

    return RegisterResponse(
        message="Registration successful. Please check your email to verify your account.",
        user=build_user_response(user, await get_current_subscription(db, user.id)),
    )

@router.post("/verify-email")
async def verify_email(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    token_hash = hash_refresh_token(token)
    result = await db.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.token_hash == token_hash)
    )
    stored_token = result.scalar_one_or_none()

    if stored_token is None or stored_token.used:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or already used token")

    if stored_token.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification link expired")

    result = await db.execute(select(User).where(User.id == stored_token.user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_verified = True
    stored_token.used = True
    await db.commit()

    return {"message": "Email verified successfully"}



@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    raw_token = request.cookies.get("user_refresh_token")
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token provided")

    token_hash = hash_refresh_token(raw_token)
    result = await db.execute(select(UserRefreshToken).where(UserRefreshToken.token_hash == token_hash))
    stored_token = result.scalar_one_or_none()

    if stored_token is None or stored_token.revoked:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    if stored_token.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    stored_token.revoked = True

    result = await db.execute(select(User).where(User.id == stored_token.user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or disabled")

    new_raw_refresh_token = create_refresh_token()
    new_refresh_expires = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)

    db.add(UserRefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(new_raw_refresh_token),
        expires_at=new_refresh_expires,
    ))
    await db.commit()

    new_access_token = create_access_token({"sub": str(user.id), "email": user.email, "role": 2, "type": "user"})

    response.set_cookie(
        key="user_refresh_token",
        value=new_raw_refresh_token,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="none" if settings.ENVIRONMENT == "production" else "lax",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/",
    )

    return TokenResponse(access_token=new_access_token)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
) -> dict[str, str]:
    raw_token = request.cookies.get("user_refresh_token")
    if raw_token:
        token_hash = hash_refresh_token(raw_token)
        result = await db.execute(select(UserRefreshToken).where(UserRefreshToken.token_hash == token_hash))
        stored_token = result.scalar_one_or_none()
        if stored_token:
            stored_token.revoked = True
            await db.commit()

    response.delete_cookie(key="user_refresh_token", path="/")

    return {"message": "Logged out successfully"}
