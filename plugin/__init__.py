"""Featly Plugin — module for funpay-universal.

Entry point: registers FunPay event handlers and Telegram routers.
"""

from __future__ import annotations

from loguru import logger

from .handlers.funpay import (
    on_deal_confirmed,
    on_deal_rolled_back,
    on_item_paid,
    on_new_deal,
    on_new_message,
)
from .handlers.telegram import router as tg_router
from .meta import NAME, VERSION

EVENT_HANDLERS = {
    "on_new_deal": on_new_deal,
    "on_new_message": on_new_message,
    "on_item_paid": on_item_paid,
    "on_deal_confirmed": on_deal_confirmed,
    "on_deal_rolled_back": on_deal_rolled_back,
}

TELEGRAM_ROUTERS = [tg_router]


def on_load() -> None:
    logger.info(f"{NAME} v{VERSION} loaded")


def on_unload() -> None:
    from .core.backend_client import backend_client

    logger.info(f"{NAME} v{VERSION} unloaded")
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(backend_client.close())
    except RuntimeError:
        pass
