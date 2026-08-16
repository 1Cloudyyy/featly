"""Reconnect handler — detect and recover from Roblox disconnects."""

from __future__ import annotations

import asyncio

from loguru import logger

from engine.config import EngineConfig
from engine.cv_matcher import detect_template, wait_for_template_async
from engine.input_controller import async_click
from engine.screen_capture import capture_screen
from engine.ws_client import WSClient


class ReconnectHandler:
    """Detects disconnect screen and clicks Reconnect."""

    def __init__(self, config: EngineConfig, ws_client: WSClient) -> None:
        self.config = config
        self.ws_client = ws_client
        self._running = False

    async def run(self) -> None:
        """Monitor for disconnect and reconnect."""
        self._running = True
        logger.info("Reconnect handler started")

        while self._running:
            try:
                await asyncio.sleep(5.0)
                await self._check_reconnect()
            except Exception as e:
                logger.error(f"Reconnect check error: {e}")

    async def _check_reconnect(self) -> None:
        """Check if reconnect button is visible."""
        screenshot = capture_screen()
        found, center = detect_template(
            screenshot,
            "reconnect_button.png",
            threshold=self.config.template_threshold,
            region=self.config.regions.reconnect_button,
        )

        if found and center:
            logger.warning("Disconnect detected — clicking Reconnect")
            await async_click(center[0], center[1])

            # Wait for HUD to appear (async — не блокирует event loop)
            found_hud, _ = await wait_for_template_async(
                capture_screen,
                "mm2_hud.png",
                timeout=30.0,
            )

            if found_hud:
                logger.info("Reconnected successfully")
                # Request fresh waitlist
                await self.ws_client.request_waitlist()
            else:
                logger.error("Reconnect failed — HUD not found after 30s")

    def stop(self) -> None:
        self._running = False
