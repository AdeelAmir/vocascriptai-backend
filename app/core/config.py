from pathlib import Path
from typing import ClassVar
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    DATABASE_URL: str

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # AssemblyAI
    ASSEMBLYAI_API_KEY_1: str | None = None
    ASSEMBLYAI_API_KEY_2: str | None = None
    ASSEMBLYAI_API_KEY_3: str | None = None

    # Groq
    GROQ_API_KEY_1: str | None = None
    GROQ_API_KEY_2: str | None = None
    GROQ_API_KEY_3: str | None = None

    # GPT
    OPENAI_API_KEY: str | None = None

    # GPT Model
    MODEL: ClassVar[str] = 'gpt-4o-mini'

    YOUTUBE_API_KEY: str = ""

    RESEND_API_KEY: str | None = None
    ENCRYPTION_KEY: str

    SMTP_USER: str
    SMTP_PASSWORD: str

    SUPADATA_API_KEY_1: str | None = None
    SUPADATA_API_KEY_2: str | None = None
    SUPADATA_API_KEY_3: str | None = None
    SUPADATA_API_KEY_4: str | None = None
    SUPADATA_API_KEY_5: str | None = None

    APP_ENV: str = "development"
    FRONTEND_URL: str = "http://localhost:3000"

    PADDLE_API_KEY: str
    PADDLE_WEBHOOK_SECRET: str
    PADDLE_PRICE_ID: str

settings = Settings()
