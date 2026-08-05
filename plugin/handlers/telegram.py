"""Telegram handlers — aiogram 3 routers for admin commands."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from loguru import logger

from plugin.core.backend_client import backend_client
from plugin.settings import load_settings, update_settings

router = Router()


@router.message(Command("roblox_cookie"))
async def cmd_roblox_cookie(message: Message) -> None:
    """Update .ROBLOSECURITY cookie for Roblox API."""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /roblox_cookie <значение>")
        return

    cookie = args[1].strip()
    settings = load_settings()
    bot_id = settings.get("bot_id", "bot_main")

    update_settings(roblox_cookie=cookie)
    await backend_client.update_cookie(bot_id, cookie)
    await message.answer("✅ Roblox cookie обновлён")
    logger.info("Roblox cookie updated via Telegram")


@router.message(Command("stock"))
async def cmd_stock(message: Message) -> None:
    """Show current inventory."""
    items = await backend_client.get_inventory()
    if not items:
        await message.answer("📦 Инвентарь пуст")
        return

    lines = ["📦 **Инвентарь:**\n"]
    for item in items:
        name = item.get("name", item.get("item_key", "?"))
        count = item.get("count", 0)
        threshold = item.get("low_stock_threshold", 3)
        warning = " ⚠️" if count <= threshold else ""
        lines.append(f"• {name}: {count}{warning}")

    await message.answer("\n".join(lines))


@router.message(Command("orders"))
async def cmd_orders(message: Message) -> None:
    """Show active orders."""
    from sqlalchemy import select

    from plugin.core.backend_client import backend_client

    # Get pending trades via backend
    settings = load_settings()
    bot_id = settings.get("bot_id", "bot_main")

    session = await backend_client._get_session()
    base_url = settings.get("backend_url", "http://localhost:8000")

    try:
        async with session.get(f"{base_url}/pending_trades?bot_id={bot_id}") as resp:
            if resp.status == 200:
                trades = await resp.json()
                if not trades:
                    await message.answer("📋 Нет активных заказов")
                    return

                lines = ["📋 **Активные заказы:**\n"]
                for t in trades:
                    lines.append(
                        f"• #{t['order_id']} | {t['buyer_nickname']} | {t['items']}"
                    )
                await message.answer("\n".join(lines))
            else:
                await message.answer("❌ Ошибка получения заказов")
    except Exception as e:
        logger.error(f"Failed to fetch orders: {e}")
        await message.answer("❌ Ошибка подключения к бэкенду")


@router.message(Command("force_trade"))
async def cmd_force_trade(message: Message) -> None:
    """Force delivery for a stuck order."""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /force_trade <order_id>")
        return

    order_id = args[1].strip()
    await message.answer(f"⚡ Принудительная выдача заказа #{order_id}...")
    # TODO: send WS command to Engine
    logger.info(f"Force trade requested for order {order_id}")


@router.message(Command("set_threshold"))
async def cmd_set_threshold(message: Message) -> None:
    """Set low stock threshold for an item."""
    args = message.text.split()
    if len(args) < 3:
        await message.answer("Использование: /set_threshold <item_key> <n>")
        return

    item_key = args[1]
    try:
        threshold = int(args[2])
    except ValueError:
        await message.answer("❌ Порог должен быть числом")
        return

    session = await backend_client._get_session()
    settings = load_settings()
    base_url = settings.get("backend_url", "http://localhost:8000")

    try:
        async with session.patch(
            f"{base_url}/inventory/{item_key}",
            json={"low_stock_threshold": threshold},
        ) as resp:
            if resp.status == 200:
                await message.answer(f"✅ Порог для {item_key} = {threshold}")
            else:
                await message.answer("❌ Предмет не найден")
    except Exception as e:
        logger.error(f"Failed to set threshold: {e}")
        await message.answer("❌ Ошибка подключения к бэкенду")


@router.message(Command("engine_status"))
async def cmd_engine_status(message: Message) -> None:
    """Check Windows Engine status."""
    settings = load_settings()
    base_url = settings.get("backend_url", "http://localhost:8000")
    bot_id = settings.get("bot_id", "bot_main")

    session = await backend_client._get_session()
    try:
        async with session.get(f"{base_url}/bots/{bot_id}") as resp:
            if resp.status == 200:
                bot = await resp.json()
                status = "🟢 Online" if bot.get("ws_connected") else "🔴 Offline"
                await message.answer(f"🖥️ Engine: {status}")
            else:
                await message.answer("🔴 Engine: не найден")
    except Exception as e:
        await message.answer("❌ Ошибка подключения к бэкенду")
