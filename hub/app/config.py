"""Application configuration via environment variables.

Секреты (WS_SECRET/API_KEY/COOKIE_KEY) при первом запуске генерируются один раз и
сохраняются в корневой `.env` — после рестарта процесса они НЕ меняются (и клиенты
не «отваливаются»). Явные значения из env имеют приоритет.
"""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings

log = logging.getLogger("featly.config")

# Корневой .env репозитория (gitignored)
ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"

_SECRET_NAMES = ("FEATLY_WS_SECRET", "FEATLY_API_KEY", "FEATLY_COOKIE_KEY")


def ensure_env_secrets() -> None:
    """Один раз сгенерировать секреты и записать их в корневой .env."""
    existing: dict[str, str] = {}
    if ENV_FILE.exists():
        try:
            for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith(("#", ";")) and "=" in line:
                    k, v = line.split("=", 1)
                    existing[k.strip()] = v.strip()
        except Exception as e:
            log.warning("Не удалось прочитать %s: %s", ENV_FILE, e)

    missing = [name for name in _SECRET_NAMES if not os.getenv(name) and not existing.get(name)]
    if not missing:
        return

    try:
        ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
        with ENV_FILE.open("a", encoding="utf-8") as fh:
            for name in missing:
                fh.write(f"{name}={secrets.token_urlsafe(32)}\n")
        log.warning(
            "Сгенерированы и сохранены секреты в %s: %s — НЕ коммитьте этот файл!",
            ENV_FILE, ", ".join(missing),
        )
    except Exception as e:
        log.critical(
            "Не удалось сохранить секреты в %s (%s) — при рестарте они будут НОВЫМИ "
            "и все клиенты отвалятся!", ENV_FILE, e,
        )


class Settings(BaseSettings):
    model_config = {"env_prefix": "FEATLY_", "env_file": str(ENV_FILE)}

    # SQLite — по умолчанию (лёгкий деплой на VDS без контейнеров).
    # PostgreSQL: postgresql+asyncpg://featly:featly@localhost:5432/featly
    database_url: str = "sqlite+aiosqlite:///./featly.db"
    ws_secret: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    api_key: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    cors_origins: list[str] = ["http://localhost:3000"]
    upload_dir: str = "uploads"

    # Cookie encryption key (Fernet, см. app/crypto)
    cookie_key: str = Field(default_factory=lambda: secrets.token_urlsafe(32))

    # Telegram
    telegram_bot_token: str = ""
    telegram_alert_chat_id: str = ""

    # Engine
    ws_heartbeat_interval: int = 30
    engine_offline_threshold: int = 2


# Персистентные секреты ДО загрузки Settings (иначе default_factory сгенерит новые)
_ensure_env_secrets()

settings = Settings()