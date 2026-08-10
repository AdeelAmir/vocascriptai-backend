from pydantic import BaseModel


class SettingsUpdate(BaseModel):
    assemblyai_keys: list[str] | None = None
    supadataai_key: list[str] | None = None
    groq_keys: list[str] | None = None
    openai_api_key: str | None = None
    openai_model: str | None = None
    max_file_size_mb: str | None = None
    max_video_duration_minutes: str | None = None
    premium_max_file_size_mb: str | None = None
    premium_max_video_duration_minutes: str | None = None
    deepl_api_key: str | None = None
    paddle_api_key: str | None = None
    paddle_webhook_secret: str | None = None
    paddle_price_id: str | None = None
    paddle_client_token: str | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str

