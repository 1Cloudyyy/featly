"""Monitor — фоновый ватчер состояния движков.

Раз в 60 секунд проверяет ws_connected/last_seen ботов и, если движок offline дольше
порога (настройка engine_offline_threshold), шлёт Telegram-алерт (telegram_bot_token +
telegram_alert_chat_id). Настройки читаются из app_settings каждую итерацию —
применяются БЕЗ рестарта hub. Throttle: не чаще раза в 10 минут на движок.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import aiohttp
from sqlalchemy import select

from app.db import async_session
from app.models.bot import Bot
from app.services.settings_service import get_settings_map

log = logging.getLogger("featly.monitor")

ALERT_PERIOD_SEC = 600  # не спамить чаще, чем раз в 10 минут на движок
_LAST_ALERTED: dict[str, float] = {}


async def _send_telegram(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"chat_id": chat_id, "text": text}) as resp:
                if resp.status != 200:
                    log.warning("TG-алерт не ушёл: %s %s", resp.status, (await resp.text())[:200])
                else:
                    log.info("TG-алерт отправлен: %s", text[:80])
    except Exception as e:
        log.error("TG-алерт: ошибка сети: %s", e)


async def engine_offline_watcher() -> None:
    while True:
        try:
            await _check_once()
        except Exception as e:
            log.warning("engine_offline_watcher: %s", e)
        await asyncio.sleep(60)


async def _check_once() -> None:
    async with async_session() as session:
        settings = await get_settings_map(session)
        token = (settings.get("telegram_bot_token") or "").strip()
        chat_id = (settings.get("telegram_alert_chat_id") or "").strip()
        if not token or not chat_id:
            return  # канал алертов не настроен — панель «🏠 Hub» покажет подсказку

        try:
            threshold_min = int((settings.get("engine_offline_threshold") or "10"))
        except ValueError:
            threshold_min = 10
        threshold_sec = threshold_min * 60

        bots = (await session.execute(select(Bot))).scalars().all()
        now = datetime.now(timezone.utc)
        for bot in bots:
            if bot.ws_connected:
                continue
            last_seen = bot.last_seen
            offline_for = None
            if last_seen is not None:
                offline_for = (now - last_seen).total_seconds()
            if offline_for is None or offline_for < threshold_sec:
                continue

            last_alert = _LAST_ALERTED.get(bot.bot_id, 0)
            if now.timestamp() - last_alert < ALERT_PERIOD_SEC:
                continue
            _LAST_ALERTED[bot.bot_id] = now.timestamp()

            text = (
                f"🔴 Движок `{bot.bot_id}` оффлайн {threshold_min} мин и больше "
                f"(последний контакт: {last_seen or 'никогда'}). Проверь машину выдачи!"
            )
            log.warning("ALERT: %s", text)
            await _send_telegram(token, chat_id, text)