"""FunPay event handlers — интерфейс funpay-universal 1.17.

События, доступные в бандле EventTypes 1.17:
  - NEW_MESSAGE      — новое сообщение/системное сообщение в чате
  - NEW_ORDER        — появился новый (оплаченный) заказ
  - ORDER_STATUS_CHANGED — статус заказа изменился (CLOSED/REFUNDED/...)
"""

from __future__ import annotations

import logging

from FunPayAPI.common.enums import MessageTypes

from ..core import order_manager
from ..meta import NAME

log = logging.getLogger(f"{NAME}.funpay")

# Системные сообщения чата FunPay, влияющие на жизненный цикл заказа
_SYSTEM_FLOW_TYPES = {
    MessageTypes.ORDER_PURCHASED: "покупка оформлена (оплата)",
    MessageTypes.ORDER_CONFIRMED: "заказ подтверждён покупателем",
    MessageTypes.REFUND: "возврат оформлен",
    MessageTypes.PARTIAL_REFUND: "частичный возврат",
    MessageTypes.ORDER_REOPENED: "заказ переоткрыт",
}


async def on_new_message(bot, event) -> None:
    """NEW_MESSAGE: пользовательское или системное сообщение."""
    msg = event.message
    try:
        if msg is None:
            log.debug("NEW_MESSAGE без объекта message — игнорирую")
            return

        chat_id = getattr(msg, "chat_id", None)
        if msg.text is None:
            log.debug("NEW_MESSAGE chat=%s без текста (игнорирую)", chat_id)
            return

        # Свои сообщения (от аккаунта продавца) не обрабатываем
        if msg.author and bot.account and msg.author == bot.account.username:
            log.debug("NEW_MESSAGE chat=%s — своё сообщение, пропускаю", chat_id)
            return

        msg_type = getattr(msg, "type", None)
        if msg_type in _SYSTEM_FLOW_TYPES:
            log.info(
                "Системное сообщение (%s): chat=%s type=%s",
                _SYSTEM_FLOW_TYPES[msg_type], chat_id, msg_type,
            )
            await order_manager.handle_system_message(bot, msg)
            return

        # Системные тексты FunPay (автор «FunPay») с обычным типом — НЕ обрабатываем:
        # сюда попадают блоки «Вы можете перейти в Discord…», уведомления об отзыве и т.п.
        if msg.author == "FunPay":
            log.debug(
                "NEW_MESSAGE chat=%s — системный текст FunPay (text=%r), пропускаю",
                chat_id, (msg.text or "")[:60],
            )
            return

        log.info(
            "NEW_MESSAGE: chat=%s author=%s text=%r",
            chat_id, msg.author, (msg.text or "")[:80],
        )
        await order_manager.handle_new_message(bot, msg)
    except Exception as e:
        log.exception("on_new_message: ошибка при обработке: %s", e)


async def on_new_order(bot, event) -> None:
    """NEW_ORDER: покупатель оплатил товар — запускаем диалог."""
    order = event.order
    try:
        log.info(
            "NEW_ORDER: order=%s buyer=%s price=%s",
            getattr(order, "id", "?"),
            getattr(order, "buyer_username", "?"),
            getattr(order, "price", "?"),
        )
        await order_manager.handle_new_order(bot, order)
    except Exception as e:
        log.exception("on_new_order: ошибка при обработке: %s", e)


async def on_order_status_changed(bot, event) -> None:
    """ORDER_STATUS_CHANGED: статус заказа изменился."""
    order = event.order
    try:
        log.info(
            "ORDER_STATUS_CHANGED: order=%s status=%s",
            getattr(order, "id", "?"),
            getattr(order, "status", "?"),
        )
        await order_manager.handle_order_status(bot, order)
    except Exception as e:
        log.exception("on_order_status_changed: ошибка при обработке: %s", e)