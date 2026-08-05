"""Featly Plugin — module for funpay-universal.

Entry point: registers FunPay event handlers and Telegram routers.
"""

from __future__ import annotations

from loguru import logger

from plugin.handlers.funpay import (
    on_deal_confirmed,
    on_deal_rolled_back,
    on_item_paid,
    on_new_deal,
    on_new_message,
)
from plugin.handlers.telegram import router as tg_router
from plugin.meta import NAME, VERSION

# funpay-universal will call these on events
EVENT_HANDLERS = {
    "on_new_deal": on_new_deal,
    "on_new_message": on_new_message,
    "on_item_paid": on_item_paid,
    "on_deal_confirmed": on_deal_confirmed,
    "on_deal_rolled_back": on_deal_rolled_back,
}

# Telegram router for admin commands
TELEGRAM_ROUTERS = [tg_router]


def on_load() -> None:
    """Called by funpay-universal when module is loaded."""
    logger.info(f"{NAME} v{VERSION} loaded")


def on_unload() -> None:
    """Called by funpay-universal when module is unloaded."""
    from plugin.core.backend_client import backend_client

    logger.info(f"{NAME} v{VERSION} unloaded")
    # Cleanup
    import asyncio

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(backend_client.close())
    except RuntimeError:
        pass
