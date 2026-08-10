from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_admin, hash_password, verify_password
from app.core.encryption import encrypt, decrypt
from app.models.user import User
from app.models.settings import Setting
from app.schemas.setting_schema import PasswordChange, SettingsUpdate

router = APIRouter()

SETTINGS_KEYS = [
    "ASSEMBLYAI_API_KEY_1",
    "ASSEMBLYAI_API_KEY_2",
    "ASSEMBLYAI_API_KEY_3",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "SUPADATA_API_KEY_1",
    "SUPADATA_API_KEY_2",
    "SUPADATA_API_KEY_3",
    "SUPADATA_API_KEY_4",
    "SUPADATA_API_KEY_5",
    "GROQ_API_KEY_1",
    "GROQ_API_KEY_2",
    "GROQ_API_KEY_3",
    "MAX_FILE_SIZE_MB",
    "MAX_VIDEO_DURATION_MINUTES",
    "PREMIUM_MAX_FILE_SIZE_MB",
    "PREMIUM_MAX_VIDEO_DURATION_MINUTES",
    "DEEPL_API_KEY",
    "PADDLE_API_KEY",
    "PADDLE_WEBHOOK_SECRET",
    "PADDLE_PRICE_ID",
    "PADDLE_CLIENT_TOKEN",
]

ENCRYPTED_KEYS = [
    k for k in SETTINGS_KEYS
    if k not in (
        "MAX_FILE_SIZE_MB",
        "MAX_VIDEO_DURATION_MINUTES",
        "PREMIUM_MAX_FILE_SIZE_MB",
        "PREMIUM_MAX_VIDEO_DURATION_MINUTES",
        "OPENAI_MODEL",
    )
]


async def _get_setting_value(db: AsyncSession, key: str) -> str:
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    if not setting:
        return ""
    return decrypt(setting.value) if key in ENCRYPTED_KEYS else setting.value


async def _upsert_setting(db: AsyncSession, key: str, value: str) -> None:
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    stored_value = encrypt(value) if key in ENCRYPTED_KEYS else value
    if setting:
        setting.value = stored_value
    else:
        db.add(Setting(key=key, value=stored_value))


async def _replace_key_group(
    db: AsyncSession,
    prefix: str,
    values: list[str],
    max_keys: int,
) -> None:
    """Replace a dynamic API-key group and remove deleted slots.

    Empty inputs are intentionally not persisted.  The previous implementation
    always upserted every slot, including empty strings, so deleted rows were
    recreated by the settings GET response after a refresh.
    """
    compact_values = [value.strip() for value in values if value and value.strip()]
    compact_values = compact_values[:max_keys]

    for index, value in enumerate(compact_values, start=1):
        await _upsert_setting(db, f"{prefix}_{index}", value)

    if len(compact_values) < max_keys:
        await db.execute(
            delete(Setting).where(
                Setting.key.in_(
                    [f"{prefix}_{index}" for index in range(len(compact_values) + 1, max_keys + 1)]
                )
            )
        )


@router.get("/settings")
async def get_settings(
    _: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    values = {key: await _get_setting_value(db, key) for key in SETTINGS_KEYS}

    return {
        "success": True,
        "data": {
            "assemblyai_keys": [value for value in [
                values["ASSEMBLYAI_API_KEY_1"],
                values["ASSEMBLYAI_API_KEY_2"],
                values["ASSEMBLYAI_API_KEY_3"],
            ] if value],
            "openai_api_key": values["OPENAI_API_KEY"],
            "openai_model": values["OPENAI_MODEL"],
            "supadataai_key": [value for value in [
                values["SUPADATA_API_KEY_1"],
                values["SUPADATA_API_KEY_2"],
                values["SUPADATA_API_KEY_3"],
                values["SUPADATA_API_KEY_4"],
                values["SUPADATA_API_KEY_5"],
            ] if value],
            "groq_keys": [value for value in [
                values["GROQ_API_KEY_1"],
                values["GROQ_API_KEY_2"],
                values["GROQ_API_KEY_3"],
            ] if value],
            "max_file_size_mb": values["MAX_FILE_SIZE_MB"],
            "max_video_duration_minutes": values["MAX_VIDEO_DURATION_MINUTES"],
            "premium_max_file_size_mb": values["PREMIUM_MAX_FILE_SIZE_MB"],
            "premium_max_video_duration_minutes": values["PREMIUM_MAX_VIDEO_DURATION_MINUTES"],
            "deepl_api_key": values["DEEPL_API_KEY"],
            "paddle_api_key": values["PADDLE_API_KEY"],
            "paddle_webhook_secret": values["PADDLE_WEBHOOK_SECRET"],
            "paddle_price_id": values["PADDLE_PRICE_ID"],
            "paddle_client_token": values["PADDLE_CLIENT_TOKEN"],
        },
    }


@router.get("/max-file-size")
async def get_max_file_size_public(db: AsyncSession = Depends(get_db)) -> dict[str, int]:
    value = await _get_setting_value(db, "MAX_FILE_SIZE_MB")
    return {"max_file_size_mb": int(value) if value else 200}


@router.get("/max-video-duration")
async def get_max_video_duration_public(db: AsyncSession = Depends(get_db)) -> dict[str, int]:
    value = await _get_setting_value(db, "MAX_VIDEO_DURATION_MINUTES")
    return {"max_video_duration_minutes": int(value) if value else 30}

@router.get("/premium-max-file-size")
async def get_premium_max_file_size_public(db: AsyncSession = Depends(get_db)) -> dict[str, int]:
    value = await _get_setting_value(db, "PREMIUM_MAX_FILE_SIZE_MB")
    return {"premium_max_file_size_mb": int(value) if value else 1000}

@router.get("/premium-max-video-duration")
async def get_premium_max_video_duration_public(db: AsyncSession = Depends(get_db)) -> dict[str, int]:
    value = await _get_setting_value(db, "PREMIUM_MAX_VIDEO_DURATION_MINUTES")
    return {"premium_max_video_duration_minutes": int(value) if value else 120}

@router.get("/paddle-config")
async def get_paddle_config_public(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    from app.core.config import settings
    client_token = await _get_setting_value(db, "PADDLE_CLIENT_TOKEN")
    price_id = await _get_setting_value(db, "PADDLE_PRICE_ID")
    return {
        "client_token": client_token or getattr(settings, "PADDLE_CLIENT_TOKEN", ""),
        "price_id": price_id or getattr(settings, "PADDLE_PRICE_ID", ""),
    }

@router.put("/settings")
async def update_settings(
    body: SettingsUpdate,
    _: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if body.assemblyai_keys is not None:
        await _replace_key_group(db, "ASSEMBLYAI_API_KEY", body.assemblyai_keys, 3)

    if body.supadataai_key is not None:
        await _replace_key_group(db, "SUPADATA_API_KEY", body.supadataai_key, 5)

    if body.groq_keys is not None:
        await _replace_key_group(db, "GROQ_API_KEY", body.groq_keys, 3)

    if body.max_file_size_mb is not None:
        await _upsert_setting(db, "MAX_FILE_SIZE_MB", body.max_file_size_mb)

    if body.max_video_duration_minutes is not None:
        await _upsert_setting(db, "MAX_VIDEO_DURATION_MINUTES", body.max_video_duration_minutes)

    if body.openai_api_key is not None:
        await _upsert_setting(db, "OPENAI_API_KEY", body.openai_api_key)

    if body.openai_model is not None:
        await _upsert_setting(db, "OPENAI_MODEL", body.openai_model)

    if body.premium_max_file_size_mb is not None:
        await _upsert_setting(db, "PREMIUM_MAX_FILE_SIZE_MB", body.premium_max_file_size_mb)

    if body.premium_max_video_duration_minutes is not None:
        await _upsert_setting(db, "PREMIUM_MAX_VIDEO_DURATION_MINUTES", body.premium_max_video_duration_minutes)

    if body.deepl_api_key is not None:
        await _upsert_setting(db, "DEEPL_API_KEY", body.deepl_api_key)

    if body.paddle_api_key is not None:
        await _upsert_setting(db, "PADDLE_API_KEY", body.paddle_api_key)

    if body.paddle_webhook_secret is not None:
        await _upsert_setting(db, "PADDLE_WEBHOOK_SECRET", body.paddle_webhook_secret)

    if body.paddle_price_id is not None:
        await _upsert_setting(db, "PADDLE_PRICE_ID", body.paddle_price_id)

    if body.paddle_client_token is not None:
        await _upsert_setting(db, "PADDLE_CLIENT_TOKEN", body.paddle_client_token)

    await db.commit()

    return {"success": True, "message": "Settings updated successfully"}


@router.put("/change-password")
async def change_password(
    body: PasswordChange,
    token_payload: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    admin_id = token_payload.get("sub")

    result = await db.execute(select(User).where(User.id == admin_id, User.role == 1))
    admin = result.scalar_one_or_none()

    if admin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin not found")

    if not verify_password(body.current_password, admin.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    if len(body.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters",
        )

    admin.password = hash_password(body.new_password)
    await db.commit()

    return {"success": True, "message": "Password updated successfully"}
