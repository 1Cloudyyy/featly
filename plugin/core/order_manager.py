"""Order manager — оркестрация диалогов и жизненного цикла заказа.

Работает с объектами funpay-universal 1.17:
  - bot:  FunPayBot (send_message, account)
  - order: FunPayAPI.types.order заказа (id, buyer_username, status, ...)
  - msg:   FunPayAPI.types.Message
"""

from __future__ import annotations

import logging

from FunPayAPI.common.enums import MessageTypes, OrderStatuses

from ..data import dialog_cache, orders_cache
from ..meta import NAME
from ..settings import load_settings
from .backend_client import backend_client
from .roblox_api import RobloxAuthError, request_friendship, validate_username

log = logging.getLogger(f"{NAME}.orders")

# Ник продавца в Roblox (fallback-текст в диалоге)
OWNER_ROBLOX_NICK = "migufim"

# Состояния диалогов: chat_id -> dict
_dialog_states: dict = {}

# Ожидание подтверждения смены ника (!смена): chat_id -> {"nick", "user_id", "funpay_order_id"}
_nick_change: dict = {}


# ---------------------------------------------------------------- lifecycle

async def init() -> None:
    _dialog_states.clear()
    _nick_change.clear()
    # Восстановление активных диалогов после рестарта плагина
    restored = dialog_cache.load_all()
    for chat_id_str, state in restored.items():
        _dialog_states[int(chat_id_str)] = state
    if restored:
        log.warning("Восстановлено %s активных диалогов из файла", len(restored))
    log.info("order_manager инициализирован")


async def shutdown() -> None:
    _dialog_states.clear()
    _nick_change.clear()
    dialog_cache.save_all(_dialog_states)
    log.info("order_manager остановлен")


async def _persist_dialogs() -> None:
    dialog_cache.save_all(_dialog_states)


# ---------------------------------------------------------------- helpers

def _chat(bot, nickname: str):
    """Найти чат FunPay по нику покупателя."""
    try:
        return bot.account.get_chat_by_name(nickname, True)
    except Exception as e:
        log.warning("Не удалось найти чат по нику '%s': %r", nickname, e)
        return None


def _parse_items(order) -> list[str]:
    """Названия предметов из заказа (title или short_description через запятую)."""
    title = getattr(order, "title", None) or getattr(order, "short_description", None)
    if not title:
        log.warning("Заказ %s без title/short_description — items=[order_id]", getattr(order, "id", "?"))
        return [str(getattr(order, "id", "?"))]
    items = [t.strip() for t in str(title).split(",") if t.strip()]
    return items or [str(getattr(order, "id", "?"))]


def _send(bot, chat_id: int, text: str) -> None:
    """Отправить сообщение через FunPayBot с логированием результата."""
    try:
        bot.send_message(chat_id, text)
        log.debug("Сообщение отправлено в чат %s: %r", chat_id, text[:60])
    except Exception as e:
        log.exception("Не удалось отправить сообщение в чат %s: %s", chat_id, e)


# ---------------------------------------------------------------- события

async def handle_new_order(bot, order) -> None:
    """NEW_ORDER: оплаченный заказ — старт диалога."""
    order_id_str = str(getattr(order, "id", ""))
    buyer = getattr(order, "buyer_username", "") or "?"

    chat = _chat(bot, buyer)
    if chat is None:
        log.error("NEW_ORDER %s: чат покупателя '%s' не найден — диалог невозможен", order_id_str, buyer)
        return
    chat_id = chat.id

    if chat_id in _dialog_states:
        log.info("NEW_ORDER %s: диалог в чате %s уже активен — пропускаю", order_id_str, chat_id)
        return

    items = _parse_items(order)
    item_name = items[0]
    log.info("NEW_ORDER %s: предметы=%s", order_id_str, items)

    # Остаток на складе
    inv = await backend_client.get_item(item_name.lower().replace(" ", "_"))
    if inv and inv.get("count", 0) <= 0:
        log.warning("NEW_ORDER %s: предмет '%s' закончился — отказ в выдаче", order_id_str, item_name)
        _send(bot, chat_id, "❌ Предмет закончился. Оформляю возврат...")
        return

    settings = load_settings()
    nickname_source = settings.get("nickname_source", "auto")

    # Ник из обязательного поля заказа «Имя персонажа» (Order.player)
    player_nick = None
    if nickname_source != "ask":
        try:
            full_order = bot.account.get_order(getattr(order, "id", 0))
            player_nick = (getattr(full_order, "player", None) or "").strip() or None
        except Exception as e:
            log.warning("NEW_ORDER %s: не удалось получить полный заказ (player): %s", order_id_str, e)
        if player_nick:
            log.info("NEW_ORDER %s: ник из «Имя персонажа»: %s", order_id_str, player_nick)

    # Режим auto_trusted: ник найден в Roblox 1-в-1 — финализируем без подтверждения
    if player_nick and nickname_source == "auto_trusted":
        user_id = await validate_username(player_nick)
        if user_id is not None:
            log.info(
                "NEW_ORDER %s: auto_trusted — ник '%s' найден 1-в-1, пропускаем подтверждение",
                order_id_str, player_nick,
            )
            state = {
                "step": "confirm_nick",
                "order_id": order_id_str,
                "items": items,
                "item_name": item_name,
                "buyer_nickname": player_nick,
                "buyer_user_id": user_id,
            }
            _dialog_states[chat_id] = state
            await _finish_dialog(bot, chat_id, state)
            return
        log.info(
            "NEW_ORDER %s: auto_trusted — ник '%s' не найден 1-в-1, потребуем подтверждение",
            order_id_str, player_nick,
        )

    # Обычный старт диалога
    _dialog_states[chat_id] = {
        "step": "confirm_nick" if player_nick else "waiting_nickname",
        "order_id": order_id_str,
        "items": items,
        "item_name": item_name,
        **({"buyer_nickname": player_nick} if player_nick else {}),
    }
    if player_nick:
        log.info("Диалог запущен (подтверждение ника): chat=%s order=%s ник=%s", chat_id, order_id_str, player_nick)
        _send(bot, chat_id, f"Твой ник для выдачи: {player_nick}. Верно? Ответь Да")
        await _persist_dialogs()
    else:
        log.info("Диалог запущен (запрос ника): chat=%s order=%s", chat_id, order_id_str)
        _send(bot, chat_id, "Привет! Напиши свой ник в Roblox:")
        await _persist_dialogs()


async def handle_system_message(bot, msg) -> None:
    """Системные сообщения чата (оплата / подтверждение / возврат)."""
    chat_id = msg.chat_id
    state = _dialog_states.get(chat_id)
    if not state:
        log.debug("Системное сообщение chat=%s, но активного диалога нет", chat_id)
        return

    order_id_str = state.get("order_id")
    if msg.type == MessageTypes.ORDER_CONFIRMED:
        log.info("Покупатель подтвердил заказ %s (по системному сообщению)", order_id_str)
        await _finalize_order(bot, chat_id, order_id_str, completed=True)
    elif msg.type in (MessageTypes.REFUND, MessageTypes.PARTIAL_REFUND):
        log.warning("По заказу %s оформлен возврат (по системному сообщению)", order_id_str)
        await _finalize_order(bot, chat_id, order_id_str, completed=False)


async def handle_new_message(bot, msg) -> None:
    """Пользовательское сообщение: команда или шаг диалога."""
    chat_id = msg.chat_id
    text = (msg.text or "").strip()
    if not text:
        return

    # Ожидание подтверждения смены ника
    if chat_id in _nick_change:
        await _handle_nick_confirm(bot, chat_id, text)
        return

    if text.startswith("!"):
        await _handle_command(bot, chat_id, text)
        return

    state = _dialog_states.get(chat_id)
    if state:
        await _handle_dialog_step(bot, chat_id, text, state)
    else:
        log.debug("Сообщение в чате %s без активного диалога: %r", chat_id, text[:60])


async def handle_order_status(bot, order) -> None:
    """ORDER_STATUS_CHANGED: CLOSED→completed, REFUNDED→cancelled."""
    order_id_str = str(getattr(order, "id", ""))
    status = getattr(order, "status", None)
    log.info("Статус заказа %s → %s", order_id_str, status)

    cached = orders_cache.get(order_id_str)
    if cached is None:
        log.warning("Заказ %s не найден в orders_cache (появился до рестарта?)", order_id_str)
        return

    if status == OrderStatuses.CLOSED:
        await _finalize_order(bot, None, order_id_str, completed=True)
    elif status in (OrderStatuses.REFUNDED, OrderStatuses.PARTIALLY_REFUNDED):
        await _finalize_order(bot, None, order_id_str, completed=False)
    else:
        log.debug("Заказ %s: статус %s пока не терминальный — пропускаю", order_id_str, status)


# ---------------------------------------------------------------- финализация

async def _finalize_order(bot, chat_id, funpay_order_id: str, *, completed: bool) -> None:
    """Отметить заказ в hub как completed/cancelled, почистить кэш и waitlist."""
    cached = orders_cache.get(funpay_order_id)
    hub_order_id = cached.get("order_id") if cached else None
    if not hub_order_id:
        log.error("Финализация %s: нет hub_order_id в orders_cache", funpay_order_id)
        return

    new_status = "completed" if completed else "cancelled"
    res = await backend_client.update_order_status(hub_order_id, new_status)
    if res is None:
        log.error("Финализация %s: hub не принял статус '%s'", funpay_order_id, new_status)
    else:
        log.info("Финализация %s: статус '%s' принят hub'ом (order_id=%s)", funpay_order_id, new_status, hub_order_id)

    orders_cache.remove(funpay_order_id)
    log.info("Финализация %s: orders_cache очищен", funpay_order_id)

    if chat_id is not None:
        _send(bot, chat_id, "✅ Спасибо за покупку!" if completed else "❌ Возврат оформлен.")


# ---------------------------------------------------------------- диалог

async def _finish_dialog(bot, chat_id: int, state: dict) -> None:
    """Финализация диалога: (опц.) заявка в друзья → запись в hub → waitlist → сообщения."""
    nick = state["buyer_nickname"]
    user_id = state.get("buyer_user_id")
    items = state["items"]
    order_id_str = state["order_id"]
    settings = load_settings()
    bot_id = settings.get("bot_id", "bot_main")

    # 1) Заявка в друзья (настройка add_friends)
    if settings.get("add_friends", True):
        if not user_id:
            log.warning("[диалог %s] заявка пропущена: ник '%s' не найден в Roblox (userId нет)", chat_id, nick)
            _send(bot, chat_id, f"⚠️ Не удалось отправить заявку. Добавь меня сам: {OWNER_ROBLOX_NICK}")
        else:
            try:
                sent = await request_friendship(user_id)
                if not sent:
                    log.warning("[диалог %s] заявка не отправлена (userId=%s)", chat_id, user_id)
                    _send(bot, chat_id, f"⚠️ Не удалось отправить заявку. Добавь меня сам: {OWNER_ROBLOX_NICK}")
            except RobloxAuthError as e:
                # Cookie невалиден: диалог НЕ сбрасываем — после обновления cookie
                # покупатель напишет «Да» и всё продолжится с той же точки
                log.error("[диалог %s] Roblox-ошибка (cookie): %s — диалог сохранён", chat_id, e)
                _send(bot, chat_id, "⚠️ Техническая минутка — напиши «Да» через 2 минуты, продолжим с этого места.")
                return
    else:
        log.info("[диалог %s] заявка в друзья пропущена (add_friends=false)", chat_id)

    # 2) Создание заказа в hub
    order = await backend_client.create_order(
        funpay_order_id=order_id_str,
        buyer_nickname=nick,
        buyer_user_id=user_id,
        items=items,
    )
    if not order:
        log.error("[диалог %s] hub не создал заказ (funpay=%s) — возвращаем диалог назад", chat_id, order_id_str)
        _send(bot, chat_id, "⚠️ Не удалось зарегистрировать заказ. Напиши ник ещё раз:")
        state["step"] = "waiting_nickname"
        return

    hub_order_id = order["id"]
    log.info("[диалог %s] заказ создан: funpay=%s → hub=%s", chat_id, order_id_str, hub_order_id)

    # 3) Внесение в waitlist движка
    trade = await backend_client.create_pending_trade(
        order_id=hub_order_id,
        bot_id=bot_id,
        buyer_nickname=nick,
        buyer_user_id=user_id,
        items=items,
    )
    if not trade:
        log.error("[диалог %s] pending_trade НЕ создан — движок может не выдать заказ %s!", chat_id, hub_order_id)
    else:
        log.info("[диалог %s] заказ %s в waitlist (trade_id=%s)", chat_id, hub_order_id, trade.get("id"))

    orders_cache.set(order_id_str, {
        "order_id": hub_order_id,
        "buyer_nickname": nick,
        "items": items,
        "chat_id": chat_id,
    })

    # 4) Финальные сообщения покупателю
    if settings.get("add_friends", True):
        _send(bot, chat_id, "✅ Добавил тебя в друзья. Заходи в игру!")
    else:
        _send(bot, chat_id, "✅ Заказ принят. Заходи в игру!")
    server_link = settings.get("static_server_link", "")
    if server_link:
        _send(bot, chat_id, f"Сервер: {server_link}")
    _send(bot, chat_id, "Кинь мне трейд через TAB → Trade.")

    _dialog_states.pop(chat_id, None)
    await _persist_dialogs()
    log.info("Диалог завершён: %s (%s), заказ %s", nick, user_id, order_id_str)


async def _handle_dialog_step(bot, chat_id: int, text: str, state: dict) -> None:
    step = state["step"]
    log.debug("[диалог %s] шаг=%s текст=%r", chat_id, step, text[:60])

    if step == "waiting_nickname":
        nick = text.strip()
        log.info("[диалог %s] покупатель указал ник: %s", chat_id, nick)

        user_id = await validate_username(nick)
        if user_id is None:
            log.warning("[диалог %s] ник '%s' не найден в Roblox", chat_id, nick)
            _send(bot, chat_id, f"❌ Ник '{nick}' не найден в Roblox. Попробуй ещё раз:")
            return

        log.info("[диалог %s] ник валиден: %s → userId=%s", chat_id, nick, user_id)
        state["buyer_nickname"] = nick
        state["buyer_user_id"] = user_id
        state["step"] = "confirming"
        _send(bot, chat_id, f"Ник: {nick}. Верно? Ответь Да")
        await _persist_dialogs()

    elif step in ("confirming", "confirm_nick"):
        if text.lower() not in ("да", "yes", "y"):
            log.info("[диалог %s] подтверждение отклонено («%s») — просим исправить ник", chat_id, text)
            _send(bot, chat_id, "Ок, напиши правильный ник:")
            state["step"] = "waiting_nickname"
            await _persist_dialogs()
            return

        nick = state.get("buyer_nickname")
        if not nick:
            log.error("[диалог %s] подтверждение без ника — возвращаем к запросу", chat_id)
            state["step"] = "waiting_nickname"
            _send(bot, chat_id, "Напиши свой ник в Roblox:")
            return

        # Мягкая проверка ника в Roblox (не блокируем при подтверждении покупателя)
        if not state.get("buyer_user_id"):
            user_id = await validate_username(nick)
            if user_id is None:
                log.warning("[диалог %s] ник '%s' не найден в Roblox, но продолжено (покупатель подтвердил)", chat_id, nick)
            else:
                log.info("[диалог %s] ник '%s' подтверждён в Roblox → userId=%s", chat_id, nick, user_id)
            state["buyer_user_id"] = user_id

        await _finish_dialog(bot, chat_id, state)

    elif step == "cancel_confirm":
        if text.lower() in ("да", "yes", "y"):
            log.info("[диалог %s] отмена подтверждена — отменяем заказ %s", chat_id, state.get("order_id"))
            await _finalize_order(bot, chat_id, state.get("order_id"), completed=False)
            _dialog_states.pop(chat_id, None)
            await _persist_dialogs()
        else:
            log.info("[диалог %s] покупатель отменил отмену", chat_id)
            _send(bot, chat_id, "Ок, продолжаем! Напиши ник в Roblox:")
            state["step"] = "waiting_nickname"
            await _persist_dialogs()


# ---------------------------------------------------------------- команды чата

async def _handle_command(bot, chat_id: int, text: str) -> None:
    parts = text.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""
    log.info("[команда] чат=%s cmd=%s arg=%r", chat_id, cmd, arg[:40])

    if cmd == "!смена":
        await _cmd_change_nick(bot, chat_id, arg)
    elif cmd == "!фото":
        await _cmd_screenshot(bot, chat_id)
    elif cmd == "!помощь":
        await _cmd_help(bot, chat_id)
    elif cmd == "!отмена":
        await _cmd_cancel(bot, chat_id)
    elif cmd == "!статус":
        await _cmd_status(bot, chat_id)
    else:
        log.warning("[команда] неизвестная команда %s в чате %s", cmd, chat_id)
        _send(bot, chat_id, "Команды: !смена <ник>, !фото, !статус, !отмена, !помощь")


async def _cmd_change_nick(bot, chat_id: int, new_nick: str) -> None:
    """!смена — смена ника покупателя: валидация → подтверждение → обновление в hub."""
    if not new_nick:
        _send(bot, chat_id, "Использование: !смена НовыйНик")
        return

    user_id = await validate_username(new_nick)
    if user_id is None:
        _send(bot, chat_id, f"❌ Ник '{new_nick}' не найден в Roblox")
        return

    # Ищем заказ этого чата в кэше
    found = orders_cache.find_by_chat(chat_id)
    if found is None:
        log.warning("!смена: в чате %s нет активного заказа (кэш пуст)", chat_id)
        _send(bot, chat_id, "⚠️ Не найден активный заказ для смены ника. Напиши поддержке.")
        return

    funpay_order_id, entry = found
    _nick_change[chat_id] = {
        "nick": new_nick,
        "user_id": user_id,
        "funpay_order_id": funpay_order_id,
    }
    log.info(
        "!смена: чат %s, заказ funpay=%s, новый ник %s (%s) — жду подтверждения",
        chat_id, funpay_order_id, new_nick, user_id,
    )
    _send(bot, chat_id, f"Ник: {new_nick}. Верно? Ответь Да")


async def _handle_nick_confirm(bot, chat_id: int, text: str) -> None:
    pending = _nick_change.pop(chat_id, None)
    if pending is None:
        return

    if text.lower() not in ("да", "yes", "y"):
        log.info("!смена: подтверждение отклонено (чат %s)", chat_id)
        _send(bot, chat_id, "Ок, напиши правильный ник через !смена Ник")
        return

    found = orders_cache.find_by_chat(chat_id)
    if found is None:
        log.error("!смена: заказ чата %s исчез из кэша к моменту подтверждения", chat_id)
        _send(bot, chat_id, "⚠️ Ошибка: заказ не найден. Напиши поддержке.")
        return

    funpay_order_id, entry = found
    hub_order_id = entry.get("order_id")
    res = await backend_client.update_buyer_nickname(hub_order_id, pending["nick"])
    if res is None:
        log.error("!смена: hub не принял новый ник для заказа %s", hub_order_id)
        _send(bot, chat_id, "❌ Не удалось обновить ник. Попробуй позже!")
        return

    orders_cache.set(funpay_order_id, {**entry, "buyer_nickname": pending["nick"]})
    log.warning(
        "!смена: заказ %s: ник обновлён на %s — движок учтёт при следующей синхронизации",
        hub_order_id, pending["nick"],
    )
    _send(bot, chat_id, f"✅ Ник обновлён: {pending['nick']}. Движок учтёт при выдаче.")


async def _cmd_screenshot(bot, chat_id: int) -> None:
    _send(bot, chat_id, "📸 Запрос скриншота отправлен...")
    log.info("!фото: запрошен скриншот движка из чата %s", chat_id)
    log.warning("!фото: TODO — WS-команда SCREENSHOT → движок → proof")


async def _cmd_help(bot, chat_id: int) -> None:
    _send(bot, chat_id, "🆘 Продавец вызван. Ожидай.")
    log.warning("!помощь: покупатель в чате %s просит помощи — вмешаться вручную!", chat_id)


async def _cmd_cancel(bot, chat_id: int) -> None:
    state = _dialog_states.get(chat_id)
    if not state:
        _send(bot, chat_id, "Сейчас нет активного заказа для отмены.")
        log.info("!отмена: отмена запрошена, но диалога нет (чать %s)", chat_id)
        return

    state["step"] = "cancel_confirm"
    _send(bot, chat_id, "Подтверди отмену: Да")
    await _persist_dialogs()
    log.info("!отмена: диалог %s переведён в подтверждение отмены", chat_id)


async def _cmd_status(bot, chat_id: int) -> None:
    state = _dialog_states.get(chat_id)
    if state:
        _send(bot, chat_id, f"📊 Заказ {state.get('order_id')}: ожидает оформления.")
    else:
        _send(bot, chat_id, "📊 Активных заказов в этом чате нет.")
    log.info("!статус: запрос статуса в чате %s", chat_id)