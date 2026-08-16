"""Plugin configuration — stored in JSON.

Файл `data/settings.json`. Логируем чтение/сохранение, чтобы сразу видеть,
откуда берутся значения (и почему изменились).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from loguru import logger

log = logging.getLogger("Featly.settings")

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
    "admin_tg_id": "",
}


def _ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict:
    _ensure_dir()
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            log.debug("Настройки загружены из %s", SETTINGS_FILE)
            return data
        except Exception as e:
            log.error("Не удалось прочитать настройки: %s — использую defaults", e)
    log.warning("Файла настроек нет — создаю по умолчанию")
    return DEFAULT_SETTINGS.copy()


def save_settings(settings: dict) -> None:
    _ensure_dir()
    SETTINGS_FILE.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log.info("Настройки сохранены (%s ключей)", len(settings))


def update_settings(**kwargs) -> dict:
    settings = load_settings()
    settings.update(kwargs)
    save_settings(settings)
    log.info("Настройки обновлены: %s", ", ".join(kwargs.keys()))
    return settings
