"""FunPay event handlers — integrates with funpay-universal Runner."""

from __future__ import annotations

from loguru import logger

from ..core.order_manager import handle_new_deal, handle_new_message


async def on_new_deal(deal, acc) -> None:
    """Handle NEW_DEAL event from funpay-universal."""
    try:
        await handle_new_deal(deal, acc)
    except Exception as e:
        logger.exception(f"Error handling NEW_DEAL: {e}")


async def on_new_message(message, acc) -> None:
    """Handle NEW_MESSAGE event from funpay-universal."""
    try:
        await handle_new_message(message, acc)
    except Exception as e:
        logger.exception(f"Error handling NEW_MESSAGE: {e}")


async def on_item_paid(deal, acc) -> None:
    """Handle ITEM_PAID event — item confirmed paid."""
    logger.info(f"ITEM_PAID: deal {deal.order_id}")
    # Order already created in on_new_deal, update status
    from ..core.backend_client import backend_client
    from ..data import orders_cache

    cached = orders_cache.get(deal.order_id)
    if cached:
        await backend_client.update_order_status(cached["order_id"], "waiting_trade")


async def on_deal_confirmed(deal, acc) -> None:
    """Handle DEAL_CONFIRMED event — delivery confirmed."""
    logger.info(f"DEAL_CONFIRMED: deal {deal.order_id}")
    from ..core.backend_client import backend_client
    from ..data import orders_cache

    cached = orders_cache.get(deal.order_id)
    if cached:
        await backend_client.update_order_status(cached["order_id"], "completed")
        orders_cache.remove(deal.order_id)
        await acc.send_message(deal.chat_id, "✅ Спасибо за покупку!")


async def on_deal_rolled_back(deal, acc) -> None:
    """Handle DEAL_ROLLED_BACK event — deal cancelled/refunded."""
    logger.info(f"DEAL_ROLLED_BACK: deal {deal.order_id}")
    from ..core.backend_client import backend_client
    from ..data import orders_cache

    cached = orders_cache.get(deal.order_id)
    if cached:
        await backend_client.update_order_status(cached["order_id"], "cancelled")
        orders_cache.remove(deal.order_id)
