"""Application configuration via environment variables."""

import secrets

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "FEATLY_"}

    # SQLite — по умолчанию (лёгкий деплой на VDS без контейнеров).
    # PostgreSQL: postgresql+asyncpg://featly:featly@localhost:5432/featly
    database_url: str = "sqlite+aiosqlite:///./featly.db"
    ws_secret: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    api_key: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    cors_origins: list[str] = ["http://localhost:3000"]
    upload_dir: str = "uploads"

    # Cookie encryption key (32 bytes base64)
    cookie_key: str = Field(default_factory=lambda: secrets.token_urlsafe(32))

    # Telegram
    telegram_bot_token: str = ""
    telegram_alert_chat_id: str = ""

    # Engine
    ws_heartbeat_interval: int = 30
    engine_offline_threshold: int = 2


settings = Settings()
