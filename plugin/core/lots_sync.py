"""Автосинхронизация «Наличия» лотов FunPay (шаг 3 концепта v3).

Флоу:
  1) известно item_key и количество (из инвентаря);
  2) если есть привязка item_key → lot_id в settings.lot_map — обновляем напрямую;
  3) иначе авто-поиск лота по названию (FunPayBot.get_lot_by_title → fallback fuzzy по
     своим лотам), сохраняем привязку в lot_map;
  4) меняем amount (и active при нуле) через account.get_lot_fields/save_lot.

ВСЕ шаги логируются; любые ошибки FunPay не роняют панель/диалоги.
"""

from __future__ import annotations

import logging
from typing import Any

from ..meta import NAME
from ..settings import load_settings, save_settings

log = logging.getLogger(f"{NAME}.lots")


def _bot() -> Any | None:
    """Получить синглтон FunPayBot (lazy-импорт, чтобы не ломать импорт модуля)."""
    try:
        from fpbot.funpaybot import get_funpay_bot

        return get_funpay_bot()
    except Exception as e:
        log.error("Не удалось получить FunPayBot: %s", e)
        return None


# ---------------------------------------------------------------- привязки

def get_lot_map() -> dict[str, dict]:
    return load_settings().get("lot_map", {}) or {}


def cache_lot(item_key: str, lot_id: int | str, title: str) -> None:
    """Запомнить связку item_key → лот."""
    mapping = get_lot_map()
    mapping[item_key] = {"lot_id": int(lot_id), "title": title}
    settings = load_settings()
    settings["lot_map"] = mapping
    save_settings(settings)
    log.info("Связка сохранена: %s → лот #%s («%s»)", item_key, lot_id, title)


# ---------------------------------------------------------------- поиск лота

def find_lot(query: str) -> Any | None:
    """Найти свой лот по названию (регистр не важен). None — не найден/ошибка."""
    bot = _bot()
    if bot is None:
        log.warning("find_lot: FunPayBot недоступен — поиск невозможен")
        return None

    # 1) штатный поиск FunPayBot (есть в 1.17)
    try:
        lot = bot.get_lot_by_title(query)
        if lot is not None and getattr(lot, "id", None):
            log.info("find_lot: лот найден через get_lot_by_title: «%s» → #%s", query, lot.id)
            return lot
        log.debug("find_lot: get_lot_by_title('%s') вернул None", query)
    except Exception as e:
        log.warning("find_lot: get_lot_by_title('%s') не сработал: %s", query, e)

    # 2) fallback: свой поиск по списку своих лотов
    try:
        account = bot.account
        profile = account.get_user(account.id)
        lots = profile.get_lots()
        q = query.strip().lower()
        for lot in lots:  # точное совпадение
            if (lot.title or "").strip().lower() == q:
                log.info("find_lot: точное совпадение «%s» → #%s", query, lot.id)
                return lot
        for lot in lots:  # вхождение подстроки
            if q in (lot.title or "").lower():
                log.info("find_lot: совпадение по подстроке «%s» → #%s", query, lot.id)
                return lot
        log.warning("find_lot: лот «%s» не найден (проверено %s лотов)", query, len(lots))
    except Exception as e:
        log.error("find_lot: свой поиск не сработал: %s", e)
    return None


# ---------------------------------------------------------------- наличие

def set_lot_amount(lot_id: int | str, count: int, *, deactivate_on_zero: bool = True) -> bool:
    """Обновить «Наличие» (amount) лота и, при желании, активность по нулю."""
    bot = _bot()
    if bot is None:
        log.error("set_lot_amount: FunPayBot недоступен — лот #%s не обновлён", lot_id)
        return False
    try:
        fields = bot.account.get_lot_fields(int(lot_id))
        fields.amount = count
        if deactivate_on_zero:
            fields.active = count > 0
        bot.account.save_lot(fields)
        log.info("Наличие лота #%s → %s (active=%s)", lot_id, count, fields.active)
        return True
    except Exception as e:
        log.error("set_lot_amount: лот #%s не обновлён: %s", lot_id, e)
        return False


def sync_item(item_key: str, name: str, count: int) -> dict:
    """Автосинк: известно предмет и количество. Возвращает результат для лога/панели.

    result = {"ok": bool, "reason": str, "lot_id": int|None}
    """
    result = {"ok": False, "reason": "", "lot_id": None}

    mapped = get_lot_map().get(item_key)
    if mapped and mapped.get("lot_id"):
        lot_id = mapped["lot_id"]
        ok = set_lot_amount(lot_id, count)
        result.update(
            ok=ok,
            lot_id=lot_id,
            reason=f"обновлён по привязанному лоту #{lot_id}" if ok else f"ошибка привязанного лота #{lot_id}",
        )
        if not ok:
            log.error("sync_item(%s): %s", item_key, result["reason"])
        return result

    lot = find_lot(name)
    if lot is None:
        result["reason"] = "лот по названию не найден"
        log.warning("sync_item(%s, «%s»): %s", item_key, name, result["reason"])
        return result

    ok = set_lot_amount(lot.id, count)
    if ok:
        cache_lot(item_key, lot.id, name)
        result.update(ok=True, lot_id=int(lot.id), reason=f"лот #{lot.id} найден и обновлён")
    else:
        result["reason"] = "не удалось обновить наличие"
    return result