"""Settings service — чтение/запись настроек hub (таблица app_settings)."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_setting import AppSetting

log = logging.getLogger("featly.hub_settings")

# Известные ключи (для панели и валидации)
KNOWN_KEYS = {
    "telegram_bot_token": "🔑 TG bot token (для алертов hub)",
    "telegram_alert_chat_id": "📨 Чат алертов hub",
    "engine_offline_threshold": "⏱ Движок offline > N минут → алерт",
    "ws_heartbeat_interval": "💓 Интервал heartbeat движка (сек, инфо)",
}


async def get_settings_map(session: AsyncSession) -> dict[str, str]:
    result = await session.execute(select(AppSetting))
    return {row.key: row.value for row in result.scalars().all()}


async def update_settings(session: AsyncSession, values: dict[str, str]) -> dict[str, str]:
    """Upsert известных ключей. Возвращает актуальный словарь."""
    current = await get_settings_map(session)
    for key, value in values.items():
        if key not in KNOWN_KEYS:
            log.warning("update_settings: неизвестный ключ %s — пропущен", key)
            continue
        row = await session.get(AppSetting, key)
        if row is None:
            session.add(AppSetting(key=key, value=str(value)))
        else:
            row.value = str(value)
        current[key] = str(value)
    await session.commit()
    log.info("Настройки hub обновлены: %s", ", ".join(values.keys()))
    return current