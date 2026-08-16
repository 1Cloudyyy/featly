"""Telegram admin panel — панель управления в Telegram (v3, шаг 1).

Экраны: /admin → главное меню → движок / инвентарь (CRUD через FSM) /
заказы (waitlist) / статистика / настройки / диагностика.
Каркас: aiogram Router + StatesGroup + inline-кнопки с текущими значениями +
редактирование одного и того же сообщения (паттерн из playerok-плагина).
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..core.backend_client import backend_client
from ..core.lots_sync import cache_lot, set_lot_amount, sync_item
from ..meta import NAME
from ..settings import load_settings, update_settings

log = logging.getLogger(f"{NAME}.admin")

router = Router()

# Поля настроек, редактируемые из панели (кнопка показывает текущее значение)
SETTING_FIELDS: dict[str, str] = {
    "backend_url": "📡 Hub URL",
    "backend_ws_url": "🌐 WS URL движка",
    "bot_id": "🤖 bot_id",
    "roblox_cookie": "🔑 Roblox cookie",
    "api_key": "🔐 Hub API-key",
    "low_stock_threshold": "📉 Порог остатка",
    "telegram_alert_chat_id": "🔔 Чат алертов",
    "alert_on_zero": "🔕 Алерт при нуле",
    "admin_tg_id": "🆔 Admin TG ID",
    "static_server_link": "🔗 Ссылка сервера",
    "autosync_lots": "🛍 Авто-синк лотов",
}

# Ключи hub-настроек, редактируемые с экрана «🏠 Hub»
HUB_SETTING_FIELDS: dict[str, str] = {
    "telegram_bot_token": "🔑 TG bot token",
    "telegram_alert_chat_id": "📨 Чат алертов hub",
    "engine_offline_threshold": "⏱ Offline-порог, мин",
}

# Режимы источника ника для выдачи (нормирование в @delivery)
NICKNAME_MODES = ("auto", "auto_trusted", "ask")
NICKNAME_LABELS = {
    "auto": "🎮 Ник: подтверждение (из заказа)",
    "auto_trusted": "🎮 Ник: авто-доверие (без вопросов)",
    "ask": "🎮 Ник: всегда спрашивать",
}

# Примеры значений для полей настроек (подсказка при невалидном URL)
DEFAULT_EXAMPLES = {
    "backend_url": "http://localhost:8000",
    "backend_ws_url": "ws://localhost:8000/ws/engine",
}


class PanelStates(StatesGroup):
    """FSM-состояния панели (по одному стейту на поле ввода)."""

    item_key = State()
    item_name = State()
    item_count = State()
    item_threshold = State()
    setting_value = State()
    lot_id = State()
    confirm_order = State()
    hub_value = State()


# ---------------------------------------------------------------- helpers

def _is_admin(chat_id: int) -> bool:
    admin_id = str(load_settings().get("admin_tg_id", "")).strip()
    if not admin_id:
        log.warning("admin_tg_id не задан — панель недоступна (chat_id=%s)", chat_id)
        return False
    if str(chat_id) != admin_id:
        log.warning("Доступ к панели запрещён: chat_id=%s (admin=%s)", chat_id, admin_id)
        return False
    return True


def _kb(rows: list[list[tuple[str, str]]]):
    """Сборка inline-клавиатуры из строк [(label, callback_data)]."""
    b = InlineKeyboardBuilder()
    for row in rows:
        for label, cb in row:
            b.button(text=label, callback_data=cb)
    b.adjust(*[len(r) for r in rows])
    return b.as_markup()


_BACK = [("⬅️ Назад", "cb:main")]


async def _screen(obj: Message | CallbackQuery, text: str, kb) -> None:
    """Показать/обновить экран: edit, если это callback; иначе answer."""
    if isinstance(obj, CallbackQuery):
        if obj.message is None:
            return
        try:
            await obj.message.edit_text(text, reply_markup=kb)
        except Exception as e:
            log.warning("edit_text не удался (%s) — отвечаю новым сообщением", e)
            await obj.message.answer(text, reply_markup=kb)
        await obj.answer()
    else:
        await obj.answer(text, reply_markup=kb)


# ---------------------------------------------------------------- тексты

async def _main_text() -> str:
    lines = ["⚙️ Featly — админ\n"]
    try:
        stats = await backend_client.get_stats()
        if stats:
            lines.append(f"🤖 Движки: {stats.get('online_bots', 0)}/{stats.get('total_bots', 0)} online")
            lines.append(f"📦 Инвентарь: {stats.get('inventory_count', 0)} предметов")
            lines.append(f"📋 В waitlist: {stats.get('waitlist_count', 0)}")
            lines.append(f"✅ Выдано сегодня: {stats.get('completed_today', 0)}")
        else:
            lines.append("❌ Hub не отвечает — сводка недоступна")
    except Exception as e:
        log.error("Главное меню: ошибка сводки: %s", e)
        lines.append("❌ Hub недоступен (см. лог)")
    return "\n".join(lines)


async def _inv_text() -> str:
    items = await backend_client.get_inventory()
    if not items:
        return "📦 Инвентарь пуст\nНажми «➕ Предмет», чтобы добавить."
    threshold_default = int(load_settings().get("low_stock_threshold", 3))
    lines = ["📦 Инвентарь:\n"]
    for it in items:
        thr = it.get("low_stock_threshold", threshold_default)
        warn = " ⚠️" if it.get("count", 0) <= thr else ""
        name = it.get("name") or it.get("item_key")
        lines.append(f"• {name}: {it.get('count')}{warn}")
    return "\n".join(lines)


def _kb_main():
    return _kb(
        [
            [("🤖 Движок", "cb:engine"), ("📦 Инвентарь", "cb:inv")],
            [("📋 Заказы", "cb:orders"), ("📊 Статистика", "cb:stats")],
            [("🚀 Автовыдача", "cb:delivery"), ("🧪 Диагностика", "cb:diag")],
            [("🏠 Hub", "cb:hub"), ("🔑 Подключения", "cb:con")],
            [("⚙️ Настройки", "cb:settings")],
        ]
    )


def _kb_hub(current: dict[str, str]):
    rows = []
    for key, label in HUB_SETTING_FIELDS.items():
        value = current.get(key, "")
        if key == "telegram_bot_token":
            shown = "🟢 задан" if value else "🔴 пусто"
        else:
            shown = str(value)[:30] if value else "—"
        rows.append([(f"✏️ {label}: {shown}", f"cb:hub_edit:{key}")])
    rows.append([("🔄 Обновить", "cb:hub"), ("⬅️ Назад", "cb:main")])
    return _kb(rows)


def _kb_delivery(add_friends: bool, nickname_source: str):
    friend_label = f"🔑 Запрос в друзья: {'вкл' if add_friends else 'выкл'}"
    nick_label = NICKNAME_LABELS.get(nickname_source, NICKNAME_LABELS["auto"])
    return _kb(
        [
            [(friend_label, "cb:del_toggle_friends")],
            [(nick_label, "cb:del_cycle_nick")],
            [("⬅️ Назад", "cb:main")],
        ]
    )


def _kb_inv(items: list[dict]):
    rows = [[("➕ Предмет", "cb:inv_add")]]
    for it in items:
        name = it.get("name") or it.get("item_key")
        rows.append([(f"✏️ {name}", f"cb:inv_edit:{it['item_key']}")])
    rows.append([("⬅️ Назад", "cb:main")])
    return _kb(rows)


def _kb_inv_item(key: str):
    return _kb(
        [
            [("🔢 Количество", f"cb:inv_count:{key}")],
            [("📉 Порог", f"cb:inv_thr:{key}")],
            [("🛍 Синхронизировать лот", f"cb:inv_lot_sync:{key}")],
            [("📎 Привязать лот вручную", f"cb:inv_lot_bind:{key}")],
            [("🗑 Удалить", f"cb:inv_del:{key}")],
            [("⬅️ К списку", "cb:inv")],
        ]
    )


async def _item_text(key: str) -> str:
    it = await backend_client.get_item(key)
    if it is None:
        return f"❌ Предмет `{key}` не найден"
    thr = it.get("low_stock_threshold", 3)
    warn = " ⚠️" if it.get("count", 0) <= thr else ""
    return (
        f"📦 {it.get('name')} (`{it['item_key']}`)\n"
        f"Количество: {it.get('count')}{warn}\nПорог: {thr}"
    )


def _kb_orders(trades: list[dict]):
    rows = []
    for t in trades:
        rows.append(
            [
                (f"⚡ Выдать #{t['order_id']}", f"cb:order_force:{t['order_id']}"),
                (f"❌ Отменить #{t['order_id']}", f"cb:order_cancel:{t['order_id']}"),
                (f"🗑 Из waitlist #{t['order_id']}", f"cb:trade_del:{t['id']}"),
            ]
        )
    rows.append([("🔄 Обновить", "cb:orders"), ("⬅️ Назад", "cb:main")])
    return _kb(rows)


def _kb_settings():
    rows = [[(f"✏️ {label}", f"cb:set:{field}")] for field, label in SETTING_FIELDS.items()]
    rows.append([("⬅️ Назад", "cb:main")])
    return _kb(rows)


# ---------------------------------------------------------------- главное меню

@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if message.from_user is None:
        return
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа. Задай admin_tg_id в настройках модуля (settings.json).")
        return
    log.info("/admin: панель открыта (user_id=%s)", message.from_user.id)
    await _screen(message, await _main_text(), _kb_main())


@router.callback_query(F.data == "cb:main")
async def cb_main(cb: CallbackQuery) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return
    log.info("Панель: главное меню")
    await _screen(cb, await _main_text(), _kb_main())


# ---------------------------------------------------------------- движок

@router.callback_query(F.data == "cb:engine")
async def cb_engine(cb: CallbackQuery) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return
    bot_id = load_settings().get("bot_id", "bot_main")
    bot = await backend_client.get_bot(bot_id)
    if bot is None:
        text = f"🤖 Движок `{bot_id}`: не зарегистрирован в hub"
        log.warning("Панель: движок %s не найден в hub", bot_id)
    else:
        status = "🟢 online" if bot.get("ws_connected") else "🔴 offline"
        text = f"🤖 Движок `{bot_id}`: {status}\nПоследний контакт: {bot.get('last_seen') or '—'}"
        log.info("Панель: статус движка %s = %s", bot_id, status)
    await _screen(cb, text, _kb([[("🔄 Обновить", "cb:engine")], _BACK]))


# ---------------------------------------------------------------- инвентарь

@router.callback_query(F.data == "cb:inv")
async def cb_inventory(cb: CallbackQuery) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return
    items = await backend_client.get_inventory()
    log.info("Панель: инвентарь (%s предметов)", len(items))
    await _screen(cb, await _inv_text(), _kb_inv(items))


@router.callback_query(F.data == "cb:inv_add")
async def cb_inv_add(cb: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return
    await state.clear()
    await state.set_state(PanelStates.item_key)
    log.info("Панель: добавление предмета — запрашиваю item_key")
    await _screen(cb, "➕ Новый предмет\n\nВведи item_key (например, chroma_luger):", None)


@router.callback_query(F.data.startswith("cb:inv_edit:"))
async def cb_inv_edit(cb: CallbackQuery) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return
    key = cb.data.split(":", 2)[2]
    log.info("Панель: редактирование %s", key)
    await _screen(cb, await _item_text(key), _kb_inv_item(key))


@router.callback_query(F.data.startswith("cb:inv_count:"))
async def cb_inv_count(cb: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return
    key = cb.data.split(":", 2)[2]
    await state.clear()
    await state.set_state(PanelStates.item_count)
    await state.update_data(edit_key=key)
    log.info("Панель: изменение количества %s", key)
    await _screen(cb, f"🔢 Новое количество для `{key}` (число):", None)


@router.callback_query(F.data.startswith("cb:inv_thr:"))
async def cb_inv_thr(cb: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return
    key = cb.data.split(":", 2)[2]
    await state.clear()
    await state.set_state(PanelStates.item_threshold)
    await state.update_data(edit_key=key)
    log.info("Панель: изменение порога %s", key)
    await _screen(cb, f"📉 Новый порог для `{key}` (число):", None)


@router.callback_query(F.data.startswith("cb:inv_del:"))
async def cb_inv_del(cb: CallbackQuery) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return
    key = cb.data.split(":", 2)[2]
    ok = await backend_client.delete_item(key)
    if ok:
        log.warning("Панель: предмет удалён %s", key)
        await cb.answer(f"🗑 «{key}» удалён", show_alert=True)
    else:
        log.error("Панель: не удалось удалить %s", key)
        await cb.answer("❌ Не удалось удалить", show_alert=True)
    items = await backend_client.get_inventory()
    await _screen(cb, await _inv_text(), _kb_inv(items))


# --- синхронизация «Наличия» лота ---

async def _item_for_sync(key: str) -> dict | None:
    item = await backend_client.get_item(key)
    if item is None:
        log.error("Панель: синк лота — предмет %s не найден в hub", key)
    return item


async def _maybe_autosync(item_key: str, name: str, count: int) -> str:
    """Автосинхронизация «Наличия» лота при изменении инвентаря (по настройке)."""
    if not load_settings().get("autosync_lots", True):
        return ""
    result = await sync_item(item_key, name, count)
    log.info("Автосинк лота после изменения инвентаря %s → %s", item_key, result)
    return f"\n🛍 <b>Лот:</b> {result.get('reason')}" if result.get("reason") else ""


@router.callback_query(F.data.startswith("cb:inv_lot_sync:"))
async def cb_inv_lot_sync(cb: CallbackQuery) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return
    key = cb.data.split(":", 2)[2]
    item = await _item_for_sync(key)
    if item is None:
        await cb.answer("❌ Предмет не найден в hub", show_alert=True)
        return
    await cb.answer("⏳ Синхронизирую лот...")
    result = await sync_item(key, item.get("name") or key, item.get("count", 0))
    log.info("Панель: синк лота %s → %s", key, result)
    emoji = "✅" if result.get("ok") else "❌"
    await _screen(cb, f"{emoji} Синк лота для `{key}`:\n{result.get('reason')}", _kb_inv_item(key))


@router.callback_query(F.data.startswith("cb:inv_lot_bind:"))
async def cb_inv_lot_bind(cb: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return
    key = cb.data.split(":", 2)[2]
    await state.clear()
    await state.set_state(PanelStates.lot_id)
    await state.update_data(bind_key=key)
    log.info("Панель: ручная привязка лота для %s — запрашиваю lot_id", key)
    await _screen(cb, f"📎 Введи ID лота FunPay для «{key}» (число из URL лота):", None)


@router.message(PanelStates.lot_id)
async def fsm_lot_id(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    if not _is_admin(message.from_user.id):
        return
    data = await state.get_data()
    key = data.get("bind_key")
    if key is None:
        await state.clear()
        return
    try:
        lot_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ lot_id должен быть числом. Попробуй ещё раз:")
        return
    await state.clear()

    cache_lot(key, lot_id, key)
    log.info("Панель: лот #%s привязан к %s", lot_id, key)
    item = await _item_for_sync(key)
    if item is None:
        await message.answer(f"✅ Лот #{lot_id} привязан к «{key}»")
        await _screen(message, await _main_text(), _kb_main())
        return

    ok = set_lot_amount(lot_id, item.get("count", 0))
    if ok:
        log.info("Панель: наличие лота #%s → %s", lot_id, item.get("count", 0))
        await message.answer(f"✅ Лот #{lot_id} привязан, наличие обновлено: {item.get('count', 0)}")
    else:
        await message.answer(f"⚠️ Лот #{lot_id} привязан, но наличие обновить не удалось (см. лог)")
    await _screen(message, await _main_text(), _kb_main())


# --- FSM: добавление предмета (item_key → name → count → threshold) ---

@router.message(PanelStates.item_key)
async def fsm_item_key(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    if not _is_admin(message.from_user.id):
        return
    key = message.text.strip().lower().replace(" ", "_")
    if not key:
        await message.answer("❌ Пустой key. Попробуй ещё раз:")
        return
    await state.update_data(item_key=key)
    await state.set_state(PanelStates.item_name)
    log.info("Панель: item_key=%s → запрашиваю name", key)
    await message.answer("Название (как в лоте FunPay):")


@router.message(PanelStates.item_name)
async def fsm_item_name(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    if not _is_admin(message.from_user.id):
        return
    name = message.text.strip()
    if not name:
        await message.answer("❌ Пустое название. Попробуй ещё раз:")
        return
    await state.update_data(item_name=name)
    await state.set_state(PanelStates.item_count)
    log.info("Панель: name=%s → запрашиваю количество", name)
    await message.answer("Количество (число):")


@router.message(PanelStates.item_count)
async def fsm_item_count(message: Message, state: FSMContext) -> None:
    """Количество: режим добавления или редактирования (edit_key)."""
    if message.from_user is None:
        return
    if not _is_admin(message.from_user.id):
        return
    try:
        count = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Должно быть число. Попробуй ещё раз:")
        return
    if count < 0:
        await message.answer("❌ Количество не может быть отрицательным. Попробуй ещё раз:")
        return

    data = await state.get_data()
    if data.get("edit_key"):
        key = data["edit_key"]
        await state.clear()
        ok = await backend_client.update_item_count(key, count)
        item = await backend_client.get_item(key)
        name = item.get("name") if item else key
        extra = await _maybe_autosync(key, name, count)
        if ok:
            log.info("Панель: количество %s → %s", key, count)
            await message.answer(f"✅ Количество `{key}` = {count}{extra}")
        else:
            log.error("Панель: не обновилось количество %s", key)
            await message.answer(f"❌ Не удалось обновить `{key}`")
        await _screen(message, await _main_text(), _kb_main())
        return

    await state.update_data(item_count=count)
    await state.set_state(PanelStates.item_threshold)
    log.info("Панель: count=%s → запрашиваю порог", count)
    await message.answer("Порог малого остатка (число, по умолчанию 3):")


@router.message(PanelStates.item_threshold)
async def fsm_item_threshold(message: Message, state: FSMContext) -> None:
    """Порог: финал добавления или редактирование порога (edit_key)."""
    if message.from_user is None:
        return
    if not _is_admin(message.from_user.id):
        return
    try:
        threshold = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Должно быть число. Попробуй ещё раз:")
        return
    if threshold < 0:
        await message.answer("❌ Порог не может быть отрицательным. Попробуй ещё раз:")
        return

    data = await state.get_data()
    if data.get("edit_key"):
        key = data["edit_key"]
        await state.clear()
        ok = await backend_client.update_item_threshold(key, threshold)
        if ok:
            log.info("Панель: порог %s → %s", key, threshold)
            await message.answer(f"✅ Порог `{key}` = {threshold}")
        else:
            log.error("Панель: не обновился порог %s", key)
            await message.answer(f"❌ Не удалось обновить порог `{key}`")
        await _screen(message, await _main_text(), _kb_main())
        return

    if not data.get("item_key"):
        await state.clear()
        log.warning("Панель: FSM-порог без item_key (сбой состояния)")
        await message.answer("❌ Сбой состояния — попробуй ещё раз (/admin)")
        return

    created = await backend_client.upsert_item(
        item_key=data["item_key"],
        name=data.get("item_name", data["item_key"]),
        count=data.get("item_count", 0),
        low_stock_threshold=threshold,
    )
    await state.clear()
    if created:
        extra = await _maybe_autosync(
            data["item_key"], data.get("item_name", data["item_key"]), data.get("item_count", 0)
        )
        log.info("Панель: предмет добавлен %s (%s шт)", data["item_key"], data.get("item_count", 0))
        await message.answer(f"✅ «{data.get('item_name', data['item_key'])}» добавлен{extra}")
    else:
        log.error("Панель: upsert_item не удался (key=%s)", data["item_key"])
        await message.answer("❌ Не удалось сохранить предмет")
    await _screen(message, await _main_text(), _kb_main())


# ---------------------------------------------------------------- заказы

@router.callback_query(F.data == "cb:orders")
async def cb_orders(cb: CallbackQuery) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return
    bot_id = load_settings().get("bot_id", "bot_main")
    trades = await backend_client.get_pending_trades(bot_id)
    log.info("Панель: заказы (%s в waitlist)", len(trades))

    if not trades:
        text = "📋 Нет активных заказов"
        kb = _kb([[("🔄 Обновить", "cb:orders")], _BACK])
    else:
        lines = ["📋 Активные заказы:\n"]
        for t in trades:
            lines.append(f"• #{t['order_id']} | {t['buyer_nickname']} | {t['items']}")
        text = "\n".join(lines)
        kb = _kb_orders(trades)

    await _screen(cb, text, kb)


@router.callback_query(F.data.startswith("cb:trade_del:"))
async def cb_trade_del(cb: CallbackQuery) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return
    trade_id = int(cb.data.split(":", 2)[2])
    ok = await backend_client.delete_pending_trade(trade_id)
    if ok:
        log.warning("Панель: заказ убран из waitlist (trade_id=%s)", trade_id)
        await cb.answer("✅ Убран из waitlist", show_alert=True)
    else:
        log.error("Панель: не удалось убрать trade_id=%s", trade_id)
        await cb.answer("❌ Ошибка удаления", show_alert=True)
    await cb_orders(cb)


# --- принудительная выдача заказа ---

@router.callback_query(F.data.startswith("cb:order_force:"))
async def cb_order_force(cb: CallbackQuery) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return
    order_id = int(cb.data.split(":", 2)[2])
    log.warning("Панель: принудительная выдача заказа #%s", order_id)
    res = await backend_client.force_trade(order_id)
    if res is None:
        await cb.answer("❌ Не удалось — заказ не в waitlist или hub недоступен", show_alert=True)
    elif res.get("delivered"):
        await cb.answer(f"⚡ Заказ #{order_id}: команда отправлена движку", show_alert=True)
    else:
        await cb.answer(f"⚡ Заказ #{order_id}: движок офлайн — повтори, когда подключится", show_alert=True)
    await cb_orders(cb)


# --- отмена заказа (с подтверждением) ---

@router.callback_query(F.data.startswith("cb:order_cancel:"))
async def cb_order_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return
    order_id = int(cb.data.split(":", 2)[2])
    await state.clear()
    await state.set_state(PanelStates.confirm_order)
    await state.update_data(cancel_order_id=order_id)
    log.warning("Панель: запрошена отмена заказа #%s — жду подтверждения", order_id)
    await _screen(cb, f"⚠️ Отменить заказ #{order_id}?\n\nНапиши «да» или «нет»:", None)


@router.message(PanelStates.confirm_order)
async def fsm_confirm_order(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    if not _is_admin(message.from_user.id):
        return
    data = await state.get_data()
    order_id = data.get("cancel_order_id")
    await state.clear()
    if order_id is None:
        return

    if message.text.strip().lower() in ("да", "yes", "y"):
        log.warning("Панель: отмена заказа #%s подтверждена", order_id)
        res = await backend_client.cancel_order(order_id)
        if res is None:
            await message.answer(f"❌ Не удалось отменить заказ #{order_id} (возможно, уже завершён)")
        else:
            await message.answer(f"✅ Заказ #{order_id} отменён, убран из waitlist")
    else:
        log.info("Панель: отмена заказа #%s отклонена", order_id)
        await message.answer("Отмена отменена.")
    await _screen(message, await _main_text(), _kb_main())


# ---------------------------------------------------------------- статистика

@router.callback_query(F.data == "cb:stats")
async def cb_stats(cb: CallbackQuery) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return
    stats = await backend_client.get_stats()
    if stats is None:
        await cb.answer("❌ Hub недоступен", show_alert=True)
        return
    log.info("Панель: статистика → %s", stats)
    text = (
        "📊 Статистика\n\n"
        f"Всего заказов: {stats.get('total_orders', 0)}\n"
        f"✅ Выполнено: {stats.get('completed', 0)} (сегодня: {stats.get('completed_today', 0)})\n"
        f"❌ Отменено/возвраты: {stats.get('cancelled', 0)}\n"
        f"📋 В waitlist: {stats.get('waitlist_count', 0)}\n"
        f"📦 Предметов: {stats.get('inventory_count', 0)}\n"
        f"🤖 Движки: {stats.get('online_bots', 0)}/{stats.get('total_bots', 0)} online"
    )
    await _screen(cb, text, _kb([[("🔄 Обновить", "cb:stats")], _BACK]))


# ---------------------------------------------------------------- автовыдача

@router.callback_query(F.data == "cb:delivery")
async def cb_delivery(cb: CallbackQuery) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return
    settings = load_settings()
    log.info("Панель: экран автовыдачи (add_friends=%s, nick=%s)",
             settings.get("add_friends"), settings.get("nickname_source"))
    text = (
        "🚀 Настройки выдачи\n\n"
        f"{'🟢' if settings.get('add_friends', True) else '🔴'} Запрос в друзья — "
        f"{'включён' if settings.get('add_friends', True) else 'выключен'}\n"
        f"🎮 Ник покупателя: {NICKNAME_LABELS.get(settings.get('nickname_source'), 'auto')}\n\n"
        "Подсказка: выход — «⬅️ Назад»."
    )
    await _screen(cb, text, _kb_delivery(settings.get("add_friends", True), settings.get("nickname_source", "auto")))


@router.callback_query(F.data == "cb:del_toggle_friends")
async def cb_del_toggle_friends(cb: CallbackQuery) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return
    current = load_settings().get("add_friends", True)
    update_settings(add_friends=not current)
    log.info("Панель: add_friends → %s", not current)
    await cb_delivery(cb)


@router.callback_query(F.data == "cb:del_cycle_nick")
async def cb_del_cycle_nick(cb: CallbackQuery) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return
    current = load_settings().get("nickname_source", "auto")
    if current not in NICKNAME_MODES:
        current = "auto"
    nxt = NICKNAME_MODES[(NICKNAME_MODES.index(current) + 1) % len(NICKNAME_MODES)]
    update_settings(nickname_source=nxt)
    log.info("Панель: nickname_source → %s", nxt)
    await cb_delivery(cb)


# ---------------------------------------------------------------- hub

@router.callback_query(F.data == "cb:hub")
async def cb_hub(cb: CallbackQuery) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return
    data = await backend_client.get_hub_settings()
    if data is None:
        await cb.answer("❌ Hub недоступен", show_alert=True)
        return
    current = data.get("settings", {})
    log.info("Панель: экран Hub (%s настроек)", len(current))
    text = ["🏠 Hub — настройки сервера:\n"]
    for key, label in HUB_SETTING_FIELDS.items():
        value = current.get(key, "")
        if key == "telegram_bot_token":
            shown = "🟢 задан" if value else "🔴 пусто"
        else:
            shown = str(value)[:40] if value else "—"
        text.append(f"{label}: {shown}")
    if not current.get("telegram_bot_token") or not current.get("telegram_alert_chat_id"):
        text.append("\n⚠️ Настрой канал алертов — движки будут молчать об офлайне!")
    await _screen(cb, "\n".join(text), _kb_hub(current))


@router.callback_query(F.data.startswith("cb:hub_edit:"))
async def cb_hub_edit(cb: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return
    key = cb.data.split(":", 2)[2]
    if key not in HUB_SETTING_FIELDS:
        await cb.answer("Неизвестная настройка", show_alert=True)
        return
    await state.clear()
    await state.set_state(PanelStates.hub_value)
    await state.update_data(hub_field=key)
    log.info("Панель: редактирование hub-настройки %s", key)
    await _screen(cb, f"✏️ {HUB_SETTING_FIELDS[key]}\nВведи новое значение:", None)


@router.message(PanelStates.hub_value)
async def fsm_hub_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    if not _is_admin(message.from_user.id):
        return
    data = await state.get_data()
    key = data.get("hub_field")
    await state.clear()
    if key is None or key not in HUB_SETTING_FIELDS:
        return

    value = message.text.strip()
    if key == "engine_offline_threshold":
        try:
            value = str(int(value))
        except ValueError:
            await message.answer("❌ Порог должен быть числом (минуты). Попробуй снова (/admin → Hub)")
            return

    res = await backend_client.update_hub_settings({key: value})
    if res is None:
        await message.answer("❌ Hub не принял настройку (проверь api_key и сеть)")
        log.error("Панель: hub-настройка %s не применена", key)
    else:
        log.info("Панель: hub-настройка %s → %s", key, value)
        await message.answer(f"✅ {HUB_SETTING_FIELDS[key]} обновлён")
    await _screen(message, await _main_text(), _kb_main())


# ---------------------------------------------------------------- подключения

@router.callback_query(F.data == "cb:con")
async def cb_connections(cb: CallbackQuery) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return
    secrets = await backend_client.get_secrets()
    if secrets is None:
        await cb.answer("❌ Hub недоступен", show_alert=True)
        return

    settings = load_settings()
    bot_id = settings.get("bot_id", "bot_main")
    backend_url = str(settings.get("backend_url", "")).rstrip("/")
    ws_host = backend_url.replace("http://", "").replace("https://", "")
    ws_url = f"ws://{ws_host}/ws/engine" if secrets.get("ws_secret") else "?"

    text = (
        "🔑 Подключения\n\n"
        f"<b>Env-блок для движка (Mini-ПК):</b>\n"
        f"<code>FEATLY_WS_URL={ws_url}\n"
        f"FEATLY_BOT_ID={bot_id}\n"
        f"FEATLY_WS_SECRET={secrets.get('ws_secret')}</code>\n\n"
        f"Hub API-key: <code>{secrets.get('api_key')}</code>\n"
        "⚠️ Секреты видны только через панель. Храни их в безопасном месте."
    )
    log.info("Панель: экран подключений (env-блок для движка показан)")
    await _screen(cb, text, _kb([[("⬅️ Назад", "cb:main")]]))


# ---------------------------------------------------------------- настройки

@router.callback_query(F.data == "cb:settings")
async def cb_settings(cb: CallbackQuery) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return
    settings = load_settings()
    log.info("Панель: экран настроек")
    lines = ["⚙️ Настройки:\n"]
    for field, label in SETTING_FIELDS.items():
        value = settings.get(field, "")
        if field in ("roblox_cookie", "api_key"):
            value = "🟢 задан" if value else "🔴 пусто"
        elif field == "low_stock_threshold":
            value = str(value)
        elif field in ("autosync_lots", "alert_on_zero"):
            value = "вкл" if value else "выкл"
        else:
            value = str(value)[:50] if value else "—"
        lines.append(f"{label}: {value}")
    await _screen(cb, "\n".join(lines), _kb_settings())


@router.callback_query(F.data.startswith("cb:set:"))
async def cb_set_field(cb: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return
    field = cb.data.split(":", 2)[2]
    if field not in SETTING_FIELDS:
        await cb.answer("Неизвестное поле", show_alert=True)
        return
    await state.clear()
    await state.set_state(PanelStates.setting_value)
    await state.update_data(setting_field=field)
    current = load_settings().get(field, "")
    log.info("Панель: редактирование настройки %s (текущее=%r)", field, current)
    await _screen(cb, f"✏️ {SETTING_FIELDS[field]}\nТекущее: {current or '—'}\nВведи новое значение:", None)


@router.message(PanelStates.setting_value)
async def fsm_setting_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    if not _is_admin(message.from_user.id):
        return
    data = await state.get_data()
    field = data.get("setting_field")
    if field is None:
        await state.clear()
        return
    value = message.text.strip()
    await state.clear()

    if field == "low_stock_threshold":
        try:
            value = int(value)
        except ValueError:
            await message.answer("❌ Порог должен быть числом. Попробуй снова (/admin → Настройки)")
            return
        if value < 0:
            await message.answer("❌ Порог не может быть отрицательным. Попробуй снова")
            return
    if field in ("backend_url", "backend_ws_url"):
        parsed = urlparse(value)
        allowed = {"http", "https", "ws", "wss"}
        if parsed.scheme not in allowed or not parsed.netloc:
            await message.answer(
                f"❌ Непохоже на URL: `{value}`. Пример: {DEFAULT_EXAMPLES.get(field, 'https://…')}"
            )
            return
    if field == "admin_tg_id":
        value = value.replace("@", "").strip()
    if field in ("autosync_lots", "alert_on_zero"):
        value = str(value).strip().lower() in ("1", "да", "yes", "y", "true", "вкл", "on")

    update_settings(**{field: value})
    log.info("Панель: настройка %s → %r", field, value)
    await message.answer(f"✅ {SETTING_FIELDS[field]} обновлён")
    await _screen(message, await _main_text(), _kb_main())


# ---------------------------------------------------------------- диагностика

@router.callback_query(F.data == "cb:diag")
async def cb_diag(cb: CallbackQuery) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return
    lines = ["🧪 Диагностика:\n"]

    try:
        health = await backend_client.health()
        lines.append(f"1. Hub: {'🟢 доступен' if health else '🔴 недоступен'}")
    except Exception as e:
        lines.append(f"1. Hub: 🔴 ошибка ({e})")

    cookie = load_settings().get("roblox_cookie", "")
    lines.append(f"2. Roblox cookie: {'🟢 задан' if cookie else '🔴 не задан'}")

    bot_id = load_settings().get("bot_id", "bot_main")
    try:
        bot = await backend_client.get_bot(bot_id)
        lines.append(f"3. Движок `{bot_id}`: {'🟢 online' if bot and bot.get('ws_connected') else '🔴 offline'}")
    except Exception as e:
        lines.append(f"3. Движок: 🔴 ошибка ({e})")

    log.info("Панель: диагностика — %s", " | ".join(lines))
    await _screen(cb, "\n".join(lines), _kb([_BACK]))