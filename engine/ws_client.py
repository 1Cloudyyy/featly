"""WebSocket client — connects to Featly Backend."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

import websockets
from loguru import logger

from engine.config import EngineConfig
from engine.waitlist_manager import waitlist_manager


class WSClient:
    """WebSocket client for Engine ↔ Backend communication."""

    def __init__(self, config: EngineConfig) -> None:
        self.config = config
        self._ws = None
        self._running = False
        self._waitlist: list[dict] = []
        self._on_waitlist_update: Callable | None = None
        self._on_force_trade: Callable | None = None

    @property
    def waitlist(self) -> list[dict]:
        return self._waitlist.copy()

    def on_waitlist_update(self, callback) -> None:
        """Register callback for waitlist sync events."""
        self._on_waitlist_update = callback

    def on_force_trade(self, callback) -> None:
        """Register callback for FORCE_TRADE commands (trade_flow.kick_scan)."""
        self._on_force_trade = callback

    async def connect(self) -> None:
        """Connect to WebSocket server with retry."""
        self._running = True
        while self._running:
            try:
                async with websockets.connect(
                    self.config.ws_url,
                    ping_interval=None,
                    close_timeout=5,
                ) as ws:
                    self._ws = ws
                    logger.info(f"Connected to {self.config.ws_url}")

                    # Auth
                    await ws.send(json.dumps({
                        "secret": self.config.ws_secret,
                        "bot_id": self.config.bot_id,
                    }))

                    # Start heartbeat
                    heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                    try:
                        await self._message_loop(ws)
                    finally:
                        heartbeat_task.cancel()

            except websockets.ConnectionClosed as e:
                logger.warning(f"Connection closed: {e}")
            except Exception as e:
                logger.error(f"WebSocket error: {e}")

            if self._running:
                logger.info("Reconnecting in 5 seconds...")
                await asyncio.sleep(5)

    async def _message_loop(self, ws) -> None:
        """Process incoming messages."""
        async for raw in ws:
            try:
                data = json.loads(raw)
                await self._handle_message(data)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received: {raw[:100]}")

    async def _handle_message(self, data: dict) -> None:
        msg_type = data.get("type")

        if msg_type == "waitlist_sync":
            self._waitlist = data.get("waitlist", [])
            logger.info(f"Waitlist synced: {len(self._waitlist)} trades")
            if self._on_waitlist_update:
                await self._on_waitlist_update(self._waitlist)

        elif msg_type == "heartbeat_ack":
            pass  # OK

        elif msg_type == "WAIT_FOR_TRADE":
            trade = {
                "order_id": data.get("order_id"),
                "buyer_nickname": data.get("buyer_nickname"),
                "buyer_user_id": data.get("buyer_user_id"),
                "items": data.get("items", []),
            }
            waitlist_manager.add(trade)
            logger.info(f"New pending trade queued: {trade.get('buyer_nickname')}")

        elif msg_type == "REMOVE_WAITLIST":
            buyer = data.get("buyer", "")
            waitlist_manager.remove_by_buyer(buyer)
            logger.info(f"Removed from waitlist: {buyer}")

        elif msg_type == "FORCE_TRADE":
            order_id = data.get("order_id")
            trade = waitlist_manager.find_by_order_id(order_id)
            if trade is None:
                logger.warning(
                    f"FORCE_TRADE: заказ {order_id} не в локальном waitlist — запрашиваю синхронизацию"
                )
                await self.request_waitlist()
                trade = waitlist_manager.find_by_order_id(order_id)
            if trade is None:
                logger.error(f"FORCE_TRADE: заказ {order_id} не найден даже после синхронизации")
            elif self._on_force_trade:
                await self._on_force_trade(trade)
            else:
                logger.warning(
                    f"FORCE_TRADE: заказ {order_id} в waitlist, но обработчик не подключён"
                )

        elif msg_type == "SCREENSHOT":
            # Trigger screenshot
            from engine.screen_capture import capture_screen
            screenshot = capture_screen()
            await self.send({
                "type": "screenshot_taken",
                "bot_id": self.config.bot_id,
            })

        else:
            logger.warning(f"Unknown message type: {msg_type}")

    async def _heartbeat_loop(self) -> None:
        """Send heartbeat at configured interval."""
        while self._running:
            await asyncio.sleep(self.config.ws_heartbeat_interval)
            await self.send({"type": "heartbeat", "bot_id": self.config.bot_id})

    async def send(self, data: dict) -> None:
        """Send JSON message to backend."""
        if self._ws:
            try:
                await self._ws.send(json.dumps(data))
            except Exception as e:
                logger.error(f"Failed to send: {e}")

    async def request_waitlist(self) -> None:
        """Request fresh waitlist from backend."""
        await self.send({"type": "request_waitlist", "bot_id": self.config.bot_id})

    async def report_trade_completed(
        self, order_id: int, success: bool, proof_path: str | None = None
    ) -> None:
        """Report trade completion to backend."""
        msg = {
            "type": "trade_completed",
            "order_id": order_id,
            "success": success,
            "bot_id": self.config.bot_id,
        }
        if proof_path:
            msg["proof_path"] = proof_path
        await self.send(msg)

    async def report_trade_failed(self, order_id: int, error: str) -> None:
        """Report trade failure to backend."""
        await self.send({
            "type": "trade_failed",
            "order_id": order_id,
            "error": error,
            "bot_id": self.config.bot_id,
        })

    async def disconnect(self) -> None:
        """Gracefully disconnect."""
        self._running = False
        if self._ws:
            await self._ws.close()
