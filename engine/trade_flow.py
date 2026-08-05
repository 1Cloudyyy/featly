"""Trade flow — main automation logic for MM2 trades."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
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
from engine.ocr import ocr
from engine.screen_capture import capture_screen
from engine.waitlist_manager import waitlist_manager


class TradeState:
    IDLE = "idle"
    SCANNING = "scanning"
    ACCEPTING = "accepting"
    PUTTING_ITEMS = "putting_items"
    CONFIRMING = "confirming"
    WAITING_GREEN = "waiting_green"
    COMPLETED = "completed"
    FAILED = "failed"


PROOFS_DIR = Path(__file__).parent / "proofs"
PROOFS_DIR.mkdir(parents=True, exist_ok=True)


class TradeFlow:
    """Manages the trade flow for MM2."""

    def __init__(self, config: EngineConfig) -> None:
        self.config = config
        self.state = TradeState.IDLE
        self._running = False
        self._current_trade: dict | None = None
        self._on_trade_completed: callable = None
        self._on_trade_failed: callable = None

    def on_trade_completed(self, callback) -> None:
        self._on_trade_completed = callback

    def on_trade_failed(self, callback) -> None:
        self._on_trade_failed = callback

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
            await asyncio.sleep(1.5)

        # Read buyer nickname from trade window
        await asyncio.sleep(0.5)
        screenshot = capture_screen()
        buyer_nick = ocr.read_nickname_from_trade(
            screenshot, region=regions.trade_request
        )

        if not buyer_nick:
            logger.warning("Could not read buyer nickname — declining trade")
            await self._decline_trade()
            self.state = TradeState.IDLE
            return

        logger.info(f"Trade request from: {buyer_nick}")

        # Check waitlist
        trade_data = waitlist_manager.find_by_buyer(buyer_nick)
        if not trade_data:
            logger.warning(f"Buyer {buyer_nick} not in waitlist — declining")
            await self._decline_trade()
            self.state = TradeState.IDLE
            return

        self._current_trade = trade_data
        await self._process_trade(trade_data)

    async def _process_trade(self, trade_data: dict) -> None:
        """Process an accepted trade — put items and confirm."""
        buyer = trade_data.get("buyer_nickname", "")
        items = trade_data.get("items", [])
        order_id = trade_data.get("order_id")

        logger.info(f"Processing trade for {buyer}: {items}")

        try:
            # Step 1: Search for item
            self.state = TradeState.PUTTING_ITEMS
            if items:
                await self._search_and_select_item(items[0])

            # Step 2: Click "Add to offer" / move to YOUR OFFER
            await asyncio.sleep(0.5)
            await self._add_to_offer()

            # Step 3: First confirm (gray button)
            self.state = TradeState.CONFIRMING
            await self._click_confirm()
            logger.debug("Clicked first Accept (gray)")

            # Step 4: Wait for green accept
            self.state = TradeState.WAITING_GREEN
            await asyncio.sleep(self.config.trade_confirm_delay)

            # Step 5: Second confirm (green button)
            await self._click_confirm()
            logger.debug("Clicked second Accept (green)")

            # Step 6: Wait for "YOU HAVE ACCEPTED"
            if self.config.ocr_enabled:
                found, _ = wait_for_template(
                    capture_screen,
                    "you_have_accepted.png",
                    timeout=15.0,
                    region=self.config.regions.you_have_accepted,
                )
                if not found:
                    # Fallback: try OCR
                    screenshot = capture_screen()
                    text = ocr.read_text(
                        screenshot,
                        region=self.config.regions.you_have_accepted,
                    )
                    if "accepted" not in text.lower():
                        logger.warning("Trade confirmation not detected")
                        self.state = TradeState.FAILED
                        await self._on_fail(order_id, "Confirmation not detected")
                        return

            # Step 7: Screenshot proof
            proof_path = await self._take_proof_screenshot(order_id)

            # Step 8: Report success
            self.state = TradeState.COMPLETED
            logger.info(f"Trade completed for {buyer}, order {order_id}")

            if self._on_trade_completed:
                await self._on_trade_completed(order_id, True, proof_path)

            # Remove from local waitlist
            waitlist_manager.remove_by_buyer(buyer)

        except Exception as e:
            logger.exception(f"Trade processing error: {e}")
            self.state = TradeState.FAILED
            await self._on_fail(order_id, str(e))

    async def _search_and_select_item(self, item_name: str) -> None:
        """Search for item in trade window and select it."""
        regions = self.config.regions

        # Click search box
        await async_click(*regions.search_box[:2])
        await asyncio.sleep(0.3)

        # Clear existing search
        await async_press("backspace")
        await asyncio.sleep(0.1)

        # Type item name (partial match)
        search_term = item_name[:4].lower() if item_name else ""
        await async_type(search_term)
        await asyncio.sleep(0.8)

        # Click first result in the list
        # Adjust Y offset for first result
        sx, sy, sw, sh = regions.search_box
        await async_click(sx + sw // 2, sy + sh + 30)
        await asyncio.sleep(0.3)

    async def _add_to_offer(self) -> None:
        """Move selected item to YOUR OFFER."""
        regions = self.config.regions
        # Click on the item in "Their Items" to move to "Your Offer"
        ox, oy, ow, oh = regions.your_offer
        await async_click(ox + ow // 2, oy + oh // 2)
        await asyncio.sleep(0.3)

    async def _click_confirm(self) -> None:
        """Click the confirm/accept button."""
        regions = self.config.regions
        await async_click(*regions.confirm_button[:2])

    async def _decline_trade(self) -> None:
        """Decline a trade (not in waitlist)."""
        # Press Escape or click decline
        await async_press("escape")
        await asyncio.sleep(0.5)

    async def _take_proof_screenshot(self, order_id: int | None) -> str | None:
        """Take proof screenshot and save to disk."""
        try:
            screenshot = capture_screen()
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"proof_{order_id}_{timestamp}.png"
            filepath = PROOFS_DIR / filename
            cv2.imwrite(str(filepath), screenshot)
            logger.info(f"Proof saved: {filepath}")
            return str(filepath)
        except Exception as e:
            logger.error(f"Failed to take proof screenshot: {e}")
            return None

    async def _on_fail(self, order_id: int | None, error: str) -> None:
        """Handle trade failure."""
        logger.error(f"Trade failed: order={order_id}, error={error}")
        if self._on_trade_failed and order_id:
            await self._on_trade_failed(order_id, error)

    def set_current_trade(self, trade: dict) -> None:
        """Set the current trade to process."""
        self._current_trade = trade

    def stop(self) -> None:
        """Stop the scan loop."""
        self._running = False
