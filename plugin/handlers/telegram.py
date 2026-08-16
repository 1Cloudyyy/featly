"""Telegram handlers — aiogram 3 роутеры админ-команд.

Каждая команда логируется (кто вызвал, аргументы, результат).
"""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ..core.backend_client import backend_client
from ..meta import NAME
from ..settings import load_settings, update_settings

log = logging.getLogger(f"{NAME}.telegram")

router = Router()


@router.message(Command("roblox_cookie"))
async def cmd_roblox_cookie(message: Message) -> None:
    """Обновить .ROBLOSECURITY cookie для Roblox API."""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        log.info("/roblox_cookie: без значения (user=%s)", message.from_user.id if message.from_user else "?")
        await message.answer("Использование: /roblox_cookie <значение>")
        return

    cookie = args[1].strip()
    settings = load_settings()
    bot_id = settings.get("bot_id", "bot_main")

    update_settings(roblox_cookie=cookie)
    ok = await backend_client.update_cookie(bot_id, cookie)
    if ok:
        await message.answer("✅ Roblox cookie обновлён")
        log.info("/roblox_cookie: обновлён для bot=%s (user=%s)", bot_id, message.from_user.id if message.from_user else "?")
    else:
        await message.answer("⚠️ Cookie сохранён локально, но hub его не принял")
        log.error("/roblox_cookie: hub отклонил cookie для bot=%s", bot_id)


@router.message(Command("stock"))
async def cmd_stock(message: Message) -> None:
    """Показать текущий инвентарь."""
    log.info("/stock: запрос (user=%s)", message.from_user.id if message.from_user else "?")
    items = await backend_client.get_inventory()
    if not items:
        await message.answer("📦 Инвентарь пуст")
        log.info("/stock: инвентарь пуст")
        return

    lines = ["📦 **Инвентарь:**\n"]
    for item in items:
        name = item.get("name", item.get("item_key", "?"))
        count = item.get("count", 0)
        threshold = item.get("low_stock_threshold", 3)
        warning = " ⚠️" if count <= threshold else ""
        lines.append(f"• {name}: {count}{warning}")

    await message.answer("\n".join(lines))
    log.info("/stock: показано %s предметов", len(items))


@router.message(Command("orders"))
async def cmd_orders(message: Message) -> None:
    """Показать активные заказы (waitlist)."""
    log.info("/orders: запрос (user=%s)", message.from_user.id if message.from_user else "?")
    bot_id = load_settings().get("bot_id", "bot_main")
    trades = await backend_client.get_pending_trades(bot_id)

    if not trades:
        await message.answer("📋 Нет активных заказов")
        return

    lines = ["📋 **Активные заказы:**\n"]
    for t in trades:
        lines.append(f"• #{t['order_id']} | {t['buyer_nickname']} | {t['items']}")
    await message.answer("\n".join(lines))
    log.info("/orders: показано %s заказов", len(trades))


@router.message(Command("force_trade"))
async def cmd_force_trade(message: Message) -> None:
    """Принудительная выдача застрявшего заказа."""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /force_trade <order_id>")
        return

    order_id = args[1].strip()
    log.warning("/force_trade: запрошена принудительная выдача заказа #%s", order_id)
    await message.answer(f"⚡ Принудительная выдача заказа #{order_id}...")
    # TODO: WS-команда движку из hub
    log.warning("/force_trade: TODO — WS-резерв (FORCE_TRADE) не реализован")


@router.message(Command("set_threshold"))
async def cmd_set_threshold(message: Message) -> None:
    """Установить порог малого остатка предмета."""
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

    log.info("/set_threshold: %s = %s", item_key, threshold)
    ok = await backend_client.set_item_threshold(item_key, threshold)
    if ok:
        await message.answer(f"✅ Порог для {item_key} = {threshold}")
    else:
        await message.answer("❌ Предмет не найден или hub недоступен")
        log.error("/set_threshold: hub не принял изменение для %s", item_key)


@router.message(Command("engine_status"))
async def cmd_engine_status(message: Message) -> None:
    """Статус движка."""
    log.info("/engine_status: запрос")
    bot_id = load_settings().get("bot_id", "bot_main")
    bot = await backend_client.get_bot(bot_id)

    if bot is None:
        await message.answer("🔴 Движок: не найден в hub")
        return

    status = "🟢 Online" if bot.get("ws_connected") else "🔴 Offline"
    await message.answer(f"🖥️ Engine (`{bot_id}`): {status}")
    log.info("/engine_status: bot=%s ws_connected=%s", bot_id, bot.get("ws_connected"))