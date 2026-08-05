"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "FEATLY_"}

    database_url: str = "postgresql+asyncpg://featly:featly@localhost:5432/featly"
    ws_secret: str = "change-me-in-production"
    cors_origins: list[str] = ["http://localhost:3000"]
    upload_dir: str = "uploads"

    # Roblox
    roblox_cookie: str = ""

    # Telegram
    telegram_bot_token: str = ""
    telegram_alert_chat_id: str = ""

    # Engine
    ws_heartbeat_interval: int = 30
    engine_offline_threshold: int = 2  # missed heartbeats


settings = Settings()
