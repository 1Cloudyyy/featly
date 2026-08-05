"""Windows Engine — entry point.

Connects to Featly Backend via WebSocket and automates MM2 trades.
"""

from __future__ import annotations

import asyncio
import signal
import sys

from loguru import logger

from engine.anti_afk import AntiAFK
from engine.config import load_config
from engine.reconnect import ReconnectHandler
from engine.screen_capture import screen
from engine.trade_flow import TradeFlow
from engine.waitlist_manager import waitlist_manager
from engine.ws_client import WSClient


async def main() -> None:
    """Main entry point."""
    logger.info("Starting Featly Windows Engine...")

    # Load config
    config = load_config("mm2")
    logger.info(f"Config loaded: ws_url={config.ws_url}, bot_id={config.bot_id}")

    # Initialize components
    ws_client = WSClient(config)
    trade_flow = TradeFlow(config)
    anti_afk = AntiAFK(config)
    reconnect = ReconnectHandler(config, ws_client)

    # Wire up waitlist sync
    async def on_waitlist_update(trades: list[dict]) -> None:
        waitlist_manager.sync(trades)

    ws_client.on_waitlist_update(on_waitlist_update)

    # Handle shutdown
    def shutdown_handler():
        logger.info("Shutdown signal received")
        trade_flow.stop()
        anti_afk.stop()
        reconnect.stop()
        asyncio.create_task(ws_client.disconnect())

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, shutdown_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    # Run everything concurrently
    try:
        await asyncio.gather(
            ws_client.connect(),
            trade_flow.run_scan_loop(),
            anti_afk.run(),
            reconnect.run(),
        )
    except KeyboardInterrupt:
        logger.info("Engine stopped by user")
    finally:
        screen.close()
        logger.info("Engine shutdown complete")


if __name__ == "__main__":
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        level="INFO",
    )
    logger.add("logs/engine_{time:YYYY-MM-DD}.log", rotation="1 day", level="DEBUG")

    asyncio.run(main())
