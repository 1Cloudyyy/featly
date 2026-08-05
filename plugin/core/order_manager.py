"""Order manager — orchestrates order lifecycle and dialogs."""

from __future__ import annotations

import json

from loguru import logger

from ..core.backend_client import backend_client
from ..core.roblox_api import RobloxAuthError, request_friendship, validate_username
from ..data import orders_cache
from ..settings import load_settings

# Conversation states per chat_id
_dialog_states: dict[int, dict] = {}


async def handle_new_deal(deal, acc) -> None:
    """Called on FunPay NEW_DEAL event."""
    chat_id = deal.chat_id
    order_id = deal.order_id
    items_raw = deal.items

    # Parse items — could be list of objects or strings
    if isinstance(items_raw, list):
        items = []
        for item in items_raw:
            if isinstance(item, dict):
                items.append(item.get("title", str(item)))
            else:
                items.append(str(item))
    else:
        items = [str(items_raw)]

    item_name = items[0] if items else "unknown"

    # Check inventory
    inventory = await backend_client.get_item(item_name.lower().replace(" ", "_"))
    if inventory and inventory.get("count", 0) <= 0:
        await acc.send_message(chat_id, "❌ Предмет закончился. Оформляю возврат...")
        logger.warning(f"Item out of stock: {item_name}")
        return

    # Start dialog
    _dialog_states[chat_id] = {
        "step": "waiting_nickname",
        "order_id": order_id,
        "items": items,
        "item_name": item_name,
    }
    await acc.send_message(chat_id, "Привет! Напиши свой ник в Roblox:")
    logger.info(f"New deal {order_id}, dialog started in chat {chat_id}")


async def handle_new_message(message, acc) -> None:
    """Called on FunPay NEW_MESSAGE event."""
    chat_id = message.chat_id
    text = message.text.strip()

    if not text.startswith("!"):
        # Check dialog state
        state = _dialog_states.get(chat_id)
        if state:
            await _handle_dialog_step(chat_id, text, acc, state)
        return

    # Command handling
    parts = text.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd == "!смена":
        await _cmd_change_nick(chat_id, arg, acc)
    elif cmd == "!фото":
        await _cmd_screenshot(chat_id, acc)
    elif cmd == "!помощь":
        await _cmd_help(chat_id, acc)
    elif cmd == "!отмена":
        await _cmd_cancel(chat_id, acc)
    elif cmd == "!статус":
        await _cmd_status(chat_id, acc)


async def _handle_dialog_step(chat_id: int, text: str, acc, state: dict) -> None:
    """Process a step in the nickname dialog."""
    step = state["step"]

    if step == "waiting_nickname":
        nick = text.strip()
        user_id = await validate_username(nick)
        if user_id is None:
            await acc.send_message(chat_id, f"❌ Ник '{nick}' не найден в Roblox. Попробуй ещё раз:")
            return

        state["buyer_nickname"] = nick
        state["buyer_user_id"] = user_id
        state["step"] = "confirming"
        await acc.send_message(
            chat_id, f"Ник: {nick}. Верно? Ответь Да"
        )

    elif step == "confirming":
        if text.lower() not in ("да", "yes", "y"):
            await acc.send_message(chat_id, "Ок, напиши правильный ник:")
            state["step"] = "waiting_nickname"
            return

        nick = state["buyer_nickname"]
        user_id = state["buyer_user_id"]
        items = state["items"]
        order_id_str = state["order_id"]

        # Send friend request
        try:
            sent = await request_friendship(user_id)
            if not sent:
                await acc.send_message(
                    chat_id,
                    "⚠️ Не удалось отправить заявку. Попробуй добавить меня сам: migufim",
                )
        except RobloxAuthError:
            await acc.send_message(
                chat_id,
                "⚠️ Техническая пауза, скоро продолжим...",
            )
            logger.error("Roblox auth error — cookie expired")
            _dialog_states.pop(chat_id, None)
            return

        settings = load_settings()
        bot_id = settings.get("bot_id", "bot_main")

        # Create order in backend
        order = await backend_client.create_order(
            funpay_order_id=order_id_str,
            buyer_nickname=nick,
            buyer_user_id=user_id,
            items=items,
        )
        if order:
            # Create pending trade
            await backend_client.create_pending_trade(
                order_id=order["id"],
                bot_id=bot_id,
                buyer_nickname=nick,
                buyer_user_id=user_id,
                items=items,
            )
            orders_cache.set(order_id_str, {
                "order_id": order["id"],
                "buyer_nickname": nick,
                "items": items,
            })

        server_link = settings.get("static_server_link", "")
        await acc.send_message(chat_id, "✅ Добавил тебя в друзья. Заходи в игру!")
        if server_link:
            await acc.send_message(chat_id, f"Сервер: {server_link}")
        await acc.send_message(chat_id, "Кинь мне трейд через TAB → Trade.")

        _dialog_states.pop(chat_id, None)
        logger.info(f"Dialog completed: {nick} ({user_id}), order {order_id_str}")


async def _cmd_change_nick(chat_id: int, new_nick: str, acc) -> None:
    """Handle !смена command."""
    if not new_nick:
        await acc.send_message(chat_id, "Использование: !смена НовыйНик")
        return

    user_id = await validate_username(new_nick)
    if user_id is None:
        await acc.send_message(chat_id, f"❌ Ник '{new_nick}' не найден в Roblox")
        return

    await acc.send_message(chat_id, f"✅ Ник изменён на {new_nick}. Верно? Ответь Да")
    # TODO: update order in backend and waitlist
    logger.info(f"!смена: new nick {new_nick} ({user_id}) in chat {chat_id}")


async def _cmd_screenshot(chat_id: int, acc) -> None:
    """Handle !фото command — request screenshot from Engine."""
    # TODO: send WS command to Engine, wait for proof
    await acc.send_message(chat_id, "📸 Запрос скриншота отправлен...")


async def _cmd_help(chat_id: int, acc) -> None:
    """Handle !помощь command — alert admin."""
    await acc.send_message(chat_id, "🆘 Продавец вызван. Ожидай.")
    logger.info(f"!помощь requested in chat {chat_id}")


async def _cmd_cancel(chat_id: int, acc) -> None:
    """Handle !отмена command."""
    await acc.send_message(chat_id, "Подтверди: Да/Нет")
    # TODO: implement cancel confirmation flow


async def _cmd_status(chat_id: int, acc) -> None:
    """Handle !статус command."""
    await acc.send_message(chat_id, "📊 Проверяю статус заказа...")
    # TODO: get order status from backend and reply
