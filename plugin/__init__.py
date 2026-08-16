"""Featly Plugin — модуль funpay-universal (интерфейс 1.17).

Регистрируемые точки входа:
  - BOT_EVENT_HANDLERS     — жизненный цикл модуля
  - FUNPAY_EVENT_HANDLERS  — события FunPay (NEW_MESSAGE / NEW_ORDER / ORDER_STATUS_CHANGED)
  - TELEGRAM_BOT_ROUTERS   — aiogram-роутер админ-команд
"""

from __future__ import annotations

import logging

from FunPayAPI.updater.events import EventTypes

from .core import order_manager
from .core.backend_client import backend_client
from .handlers.funpay import on_new_message, on_new_order, on_order_status_changed
from .handlers.telegram import router as tg_router
from .handlers.telegram_admin import router as admin_router
from .meta import *  # noqa: F401,F403  — метаданные модуля (требование funpay-universal)

log = logging.getLogger(f"{NAME}.module")

_module = None


def get_module():
    """Текущий объект Module (для включения/выключения модуля)."""
    return _module


async def on_module_enabled(module) -> None:
    global _module
    _module = module
    log.info("Модуль %s v%s включён", NAME, VERSION)

    hub_tp = load_settings_url()
    log.info("Целевой hub: %s | bot_id=%s", hub_tp[0], hub_tp[1])

    # Проверка доступности hub при старте
    ok = await backend_client.health()
    if ok:
        log.info("Hub доступен — плагин готов к работе")
    else:
        log.warning("Hub НЕ доступен при старте (проверьте backend_url и сеть)")

    await order_manager.init()


async def on_module_disabled(_) -> None:
    log.info("Модуль %s v%s выключается", NAME, VERSION)
    await backend_client.close()
    await order_manager.shutdown()


async def on_telegram_bot_init(tgbot) -> None:
    """Регистрируем команду /admin (панель появится в v3-этапе)."""
    try:
        from aiogram.types import BotCommand

        cmds = await tgbot.bot.get_my_commands()
        merged = list(cmds) + [BotCommand(command="admin", description="⚙️ FEATLY — админ-панель")]
        await tgbot.bot.set_my_commands(merged)
        log.info("Telegram: команда /admin зарегистрирована")
    except Exception as e:
        log.warning("Не удалось зарегистрировать команды Telegram: %s", e)


def load_settings_url():
    from .settings import load_settings

    s = load_settings()
    return s.get("backend_url", "http://localhost:8000"), s.get("bot_id", "bot_main")


BOT_EVENT_HANDLERS = {
    "ON_MODULE_ENABLED": [on_module_enabled],
    "ON_MODULE_DISABLED": [on_module_disabled],
    "ON_TELEGRAM_BOT_INIT": [on_telegram_bot_init],
}

FUNPAY_EVENT_HANDLERS = {
    EventTypes.NEW_MESSAGE: [on_new_message],
    EventTypes.NEW_ORDER: [on_new_order],
    EventTypes.ORDER_STATUS_CHANGED: [on_order_status_changed],
}

TELEGRAM_BOT_ROUTERS = [tg_router, admin_router]