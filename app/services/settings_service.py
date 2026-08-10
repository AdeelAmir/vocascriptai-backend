from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.core.config import settings
from app.core.encryption import decrypt
from app.models.settings import Setting

PLAIN_KEYS = (
    "MAX_FILE_SIZE_MB",
    "MAX_VIDEO_DURATION_MINUTES",
    "PREMIUM_MAX_FILE_SIZE_MB",
    "PREMIUM_MAX_VIDEO_DURATION_MINUTES",
    "GEMINI_MODEL",
    "OPENAI_MODEL",
)

async def get_setting(key: str) -> str | None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()
        if not setting:
            # Keep runtime configuration consistent with the admin service-health
            # checks: database settings take priority, then environment settings.
            return getattr(settings, key, None)
        value = setting.value if key in PLAIN_KEYS else decrypt(setting.value)
        return value

async def get_keys(prefix: str) -> list[str]:
    keys = []
    for i in range(1, 4):
        value = await get_setting(f"{prefix}_{i}")
        if value:
            keys.append(value)
    return keys
