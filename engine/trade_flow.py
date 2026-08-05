"""Trade flow — main automation logic for MM2 trades."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from loguru import logger

from engine.config import EngineConfig
from engine.cv_matcher import detect_template, wait_for_template
from engine.input_controller import (
    async_click,
    async_press,
    async_type,
    click,
    key_down,
    key_up,
    type_text,
)
from engine.screen_capture import capture_screen
from engine.waitlist_manager import waitlist_manager


class TradeState:
    IDLE = "idle"
    SCANNING = "scanning"
    ACCEPTING = "accepting"
    PUTTING_ITEMS = "putting_items"
    CONFIRMING = "confirming"
    COMPLETED = "completed"
    FAILED = "failed"


class TradeFlow:
    """Manages the trade flow for MM2."""

    def __init__(self, config: EngineConfig) -> None:
        self.config = config
        self.state = TradeState.IDLE
        self._running = False
        self._current_trade: dict | None = None

    async def run_scan_loop(self) -> None:
        """Main loop — scan screen for trade requests."""
        self._running = True
        logger.info("Trade scan loop started")

        while self._running:
            try:
                if self.state == TradeState.IDLE:
                    await self._scan_for_trade_request()
                await asyncio.sleep(self.config.scan_interval)
            except Exception as e:
                logger.exception(f"Trade loop error: {e}")
                self.state = TradeState.IDLE
                await asyncio.sleep(5)

    async def _scan_for_trade_request(self) -> None:
        """Scan screen for incoming trade request."""
        screenshot = capture_screen()
        regions = self.config.regions

        found, center = detect_template(
            screenshot,
            "trade_request_notification.png",
            threshold=self.config.template_threshold,
            region=regions.trade_request,
        )

        if not found:
            return

        logger.info("Trade request detected!")
        self.state = TradeState.ACCEPTING

        # Click accept
        if center:
            await async_click(center[0], center[1])
            await asyncio.sleep(1.0)

        # Check if buyer is in waitlist
        # TODO: OCR the buyer's nickname from the trade window
        # For now, accept all trades and check later
        await self._process_trade()

    async def _process_trade(self) -> None:
        """Process an accepted trade — put items and confirm."""
        if not self._current_trade:
            # Try to find a matching trade from waitlist
            # TODO: OCR nickname from trade window
            logger.warning("No trade data — waiting for OCR integration")
            self.state = TradeState.IDLE
            return

        buyer = self._current_trade.get("buyer_nickname", "")
        items = self._current_trade.get("items", [])

        logger.info(f"Processing trade for {buyer}: {items}")

        try:
            # Step 1: Search for item
            self.state = TradeState.PUTTING_ITEMS
            await self._search_and_select_item(items[0] if items else "")

            # Step 2: Confirm trade
            self.state = TradeState.CONFIRMING
            await self._confirm_trade()

            # Step 3: Wait for "YOU HAVE ACCEPTED"
            if self.config.ocr_enabled:
                found, _ = wait_for_template(
                    capture_screen,
                    "you_have_accepted.png",
                    timeout=15.0,
                    region=self.config.regions.you_have_accepted,
                )
                if found:
                    logger.info("Trade completed — YOU HAVE ACCEPTED detected")
                    self.state = TradeState.COMPLETED
                else:
                    logger.warning("YOU HAVE ACCEPTED not detected")
                    self.state = TradeState.FAILED
            else:
                # Just wait fixed time
                await asyncio.sleep(10.0)
                self.state = TradeState.COMPLETED

        except Exception as e:
            logger.exception(f"Trade processing error: {e}")
            self.state = TradeState.FAILED

    async def _search_and_select_item(self, item_name: str) -> None:
        """Search for item in trade window and select it."""
        regions = self.config.regions

        # Click search box
        await async_click(*regions.search_box[:2])
        await asyncio.sleep(0.3)

        # Type item name (partial match)
        search_term = item_name[:3].lower() if item_name else ""
        await async_type(search_term)
        await asyncio.sleep(0.5)

        # Click first result
        # TODO: detect first result position
        await async_click(*regions.your_offer[:2])
        await asyncio.sleep(0.3)

    async def _confirm_trade(self) -> None:
        """Click accept buttons (gray → wait → green)."""
        regions = self.config.regions

        # First accept (gray button)
        await async_click(*regions.confirm_button[:2])
        logger.debug("Clicked first Accept")

        # Wait for green accept
        await asyncio.sleep(self.config.trade_confirm_delay)

        # Second accept (green button)
        await async_click(*regions.confirm_button[:2])
        logger.debug("Clicked second Accept")

    def set_current_trade(self, trade: dict) -> None:
        """Set the current trade to process."""
        self._current_trade = trade

    def stop(self) -> None:
        """Stop the scan loop."""
        self._running = False
