"""Alert utilities — send notifications via Telegram."""

from __future__ import annotations

from loguru import logger

from plugin.settings import load_settings


async def send_alert(message: str, level: str = "info") -> bool:
    """Send alert to configured Telegram chat.

    This sends through the funpay-universal TG bot infrastructure.
    In the actual funpay-universal integration, this would use the bot's
    send_message method. For now, it logs the alert.
    """
    settings = load_settings()
    chat_id = settings.get("telegram_alert_chat_id", "")

    if not chat_id:
        logger.warning(f"No alert chat configured, alert dropped: {message}")
        return False

    # In funpay-universal, this would be:
    # await bot.send_message(chat_id, message)
    logger.info(f"Alert ({level}): {message}")
    return True


async def alert_low_stock(item_name: str, count: int, threshold: int) -> None:
    """Low stock alert."""
    await send_alert(f"🟡 {item_name} осталось {count} шт. Пополни запас.", level="warning")


async def alert_out_of_stock(item_name: str) -> None:
    """Out of stock alert."""
    await send_alert(f"🔴 {item_name} закончился! Срочно пополни.", level="error")


async def alert_trade_completed(order_id: str, amount: str = "") -> None:
    """Successful delivery alert."""
    suffix = f" +{amount}₽" if amount else ""
    await send_alert(f"✅ Заказ #{order_id} выдан.{suffix}", level="info")


async def alert_trade_error(order_id: str, error: str) -> None:
    """Trade error alert."""
    await send_alert(f"🔴 Ошибка #{order_id}: {error}", level="error")


async def alert_roblox_expired() -> None:
    """Roblox session expired alert."""
    await send_alert("🔴 Roblox разлогинился. Зайди через браузер.", level="error")


async def alert_cookie_expired() -> None:
    """Roblox cookie expired alert."""
    await send_alert("🔴 Roblox API cookie протух. /roblox_cookie", level="error")


async def alert_buyer_help(chat_link: str) -> None:
    """Buyer requesting help."""
    await send_alert(f"🆘 Покупатель просит помощь: {chat_link}", level="warning")


async def funpay_session_expired() -> None:
    """FunPay session expired alert."""
    await send_alert("🔴 FunPay не отвечает. Перезайди в funpay-universal.", level="error")
