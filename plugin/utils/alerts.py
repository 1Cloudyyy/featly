"""Alert utilities — уведомления через Telegram.

В v3 уведомления уходят в настроенный чат Telegram (telegram_alert_chat_id).
Каждое алерт-событие логируется; если чат не задан — пишем в лог.
"""

from __future__ import annotations

import logging

from ..meta import NAME
from ..settings import load_settings

log = logging.getLogger(f"{NAME}.alerts")


async def send_alert(message: str, level: str = "info") -> bool:
    """Отправить алерт в настроенный чат Telegram."""
    settings = load_settings()
    chat_id = settings.get("telegram_alert_chat_id", "")

    if not chat_id:
        log.warning("Чат для алертов не задан — алерт опущен: %s", message)
        return False

    # TODO(v3-панель): реальная отправка через бота funpay-universal.
    # Текущая заглушка — только лог.
    log.info("Алерт (%s) → чат %s: %s", level, chat_id, message)
    return True


async def alert_low_stock(item_name: str, count: int, threshold: int) -> None:
    """Порог малого остатка."""
    await send_alert(f"🟡 {item_name} осталось {count} шт. Пополни запас.", level="warning")


async def alert_out_of_stock(item_name: str) -> None:
    """Остаток нулевой."""
    await send_alert(f"🔴 {item_name} закончился! Срочно пополни.", level="error")


async def alert_trade_completed(order_id: str, amount: str = "") -> None:
    """Успешная выдача."""
    suffix = f" +{amount}₽" if amount else ""
    await send_alert(f"✅ Заказ #{order_id} выдан.{suffix}", level="info")


async def alert_trade_error(order_id: str, error: str) -> None:
    """Ошибка выдачи."""
    await send_alert(f"🔴 Ошибка #{order_id}: {error}", level="error")


async def alert_roblox_expired() -> None:
    """Roblox-сессия разлогинилась."""
    await send_alert("🔴 Roblox разлогинился. Зайди через браузер.", level="error")


async def alert_cookie_expired() -> None:
    """Cookie Roblox протух."""
    await send_alert("🔴 Roblox API cookie протух. /roblox_cookie", level="error")


async def alert_buyer_help(chat_link: str) -> None:
    """Покупатель просит помощи."""
    await send_alert(f"🆘 Покупатель просит помощь: {chat_link}", level="warning")


async def funpay_session_expired() -> None:
    """FunPay не отвечает."""
    await send_alert("🔴 FunPay не отвечает. Перезайди в funpay-universal.", level="error")