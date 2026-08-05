"""Anti-AFK — prevent Roblox from kicking idle players."""

from __future__ import annotations

import asyncio

from loguru import logger

from engine.config import EngineConfig
from engine.input_controller import anti_afk_action


class AntiAFK:
    """Periodically performs random actions to prevent AFK kicks."""

    def __init__(self, config: EngineConfig) -> None:
        self.config = config
        self._running = False

    async def run(self) -> None:
        """Start anti-AFK loop."""
        if not self.config.anti_afk_enabled:
            return

        self._running = True
        logger.info(f"Anti-AFK started (interval: {self.config.anti_afk_interval}s)")

        while self._running:
            await asyncio.sleep(self.config.anti_afk_interval)
            if self._running:
                await anti_afk_action()

    def stop(self) -> None:
        """Stop anti-AFK loop."""
        self._running = False
