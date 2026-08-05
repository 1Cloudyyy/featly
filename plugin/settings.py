"""Plugin configuration — stored in JSON, editable via Telegram."""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

DATA_DIR = Path(__file__).parent / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "backend_url": "http://localhost:8000",
    "backend_ws_url": "ws://localhost:8000/ws/engine",
    "roblox_cookie": "",
    "low_stock_threshold": 3,
    "telegram_alert_chat_id": "",
    "alert_on_zero": True,
    "bot_id": "bot_main",
    "static_server_link": "",
}


def _ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict:
    _ensure_dir()
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Failed to load settings: {e}")
    return DEFAULT_SETTINGS.copy()


def save_settings(settings: dict) -> None:
    _ensure_dir()
    SETTINGS_FILE.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def update_settings(**kwargs) -> dict:
    settings = load_settings()
    settings.update(kwargs)
    save_settings(settings)
    return settings
