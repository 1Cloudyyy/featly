"""Trade flow — main automation logic for MM2 trades.

Real MM2 trade flow:
1. Trade request notification → click Accept
2. Trade window opens → search item → click to add to YOUR OFFER
3. Click gray ACCEPT → wait for countdown (4 sec)
4. Click green ACCEPT → "ARE YOU SURE?" dialog → click Yes
5. "YOU HAVE ACCEPTED" → proof screenshot
"""

from __future__ import annotations

import asyncio
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
)
from engine.ocr import ocr
from engine.screen_capture import capture_screen
from engine.waitlist_manager import waitlist_manager


class TradeState:
    IDLE = "idle"
    ACCEPTING_REQUEST = "accepting_request"
    WAITING_WINDOW = "waiting_window"
    SEARCHING_ITEM = "searching_item"
    ADDING_TO_OFFER = "adding_to_offer"
    CONFIRMING_GRAY = "confirming_gray"
    WAITING_COUNTDOWN = "waiting_countdown"
    CONFIRMING_GREEN = "confirming_green"
    CONFIRMING_YES = "confirming_yes"
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
        """Step 1: Scan for incoming trade request notification."""
        screenshot = capture_screen()
        regions = self.config.regions

        found, center = detect_template(
            screenshot,
            "trade_request_notification.png",
            threshold=self.config.template_threshold,
        )

        if not found:
            return

        logger.info("Trade request detected!")
        self.state = TradeState.ACCEPTING_REQUEST

        # Click Accept on trade request popup
        if center:
            await async_click(center[0], center[1])
            logger.debug(f"Clicked trade request Accept at {center}")
        else:
            # Fallback: click configured region
            await async_click(*regions.accept_button[:2])

        await asyncio.sleep(2.0)

        # Now wait for trade window to open
        await self._wait_for_trade_window()

    async def _wait_for_trade_window(self) -> None:
        """Step 2: Wait for trade window to appear."""
        self.state = TradeState.WAITING_WINDOW
        logger.info("Waiting for trade window...")

        # Wait for search box to appear (indicates trade window is open)
        found, _ = wait_for_template(
            capture_screen,
            "search_box.png",
            timeout=10.0,
            interval=0.5,
        )

        if not found:
            # Try waiting a bit more
            await asyncio.sleep(2.0)
            screenshot = capture_screen()
            # Check if trade window is visible by looking for "YOUR OFFER" text
            text = ocr.read_text(screenshot, region=self.config.regions.your_offer)
            if "offer" not in text.lower() and "your" not in text.lower():
                logger.warning("Trade window not detected — giving up")
                self.state = TradeState.FAILED
                await self._on_fail(None, "Trade window not opened")
                return

        logger.info("Trade window detected")
        await self._search_and_add_item()

    async def _search_and_add_item(self) -> None:
        """Step 3: Search for item and add to YOUR OFFER."""
        self.state = TradeState.SEARCHING_ITEM
        regions = self.config.regions
        items = self._current_trade.get("items", []) if self._current_trade else []

        if not items:
            logger.warning("No items to trade")
            self.state = TradeState.FAILED
            await self._on_fail(
                self._current_trade.get("order_id") if self._current_trade else None,
                "No items specified",
            )
            return

        item_name = items[0]
        logger.info(f"Searching for item: {item_name}")

        # Click search box
        sx, sy, sw, sh = regions.search_box
        await async_click(sx + sw // 2, sy + sh // 2)
        await asyncio.sleep(0.3)

        # Clear any existing text
        await async_press("ctrl+a")
        await asyncio.sleep(0.1)
        await async_press("backspace")
        await asyncio.sleep(0.2)

        # Type item name (first 3-4 chars for partial match)
        search_term = item_name[:4].lower()
        await async_type(search_term)
        await asyncio.sleep(1.0)

        # Click on the first matching item in the results list
        # Results appear below search box
        await async_click(sx + sw // 2, sy + sh + 40)
        await asyncio.sleep(0.5)

        # Click again to add to YOUR OFFER (click on item in results)
        await async_click(sx + sw // 2, sy + sh + 40)
        await asyncio.sleep(0.5)

        logger.info(f"Item {item_name} added to offer")
        await self._confirm_trade()

    async def _confirm_trade(self) -> None:
        """Step 4: Click gray ACCEPT button."""
        self.state = TradeState.CONFIRMING_GRAY
        regions = self.config.regions

        logger.info("Clicking gray ACCEPT...")
        cx, cy, cw, ch = regions.confirm_button
        await async_click(cx + cw // 2, cy + ch // 2)
        await asyncio.sleep(1.0)

        # Step 5: Wait for countdown (4 seconds in MM2)
        self.state = TradeState.WAITING_COUNTDOWN
        logger.info("Waiting for countdown...")
        await asyncio.sleep(5.0)

        # Step 6: Click green ACCEPT
        self.state = TradeState.CONFIRMING_GREEN
        logger.info("Clicking green ACCEPT...")
        await async_click(cx + cw // 2, cy + ch // 2)
        await asyncio.sleep(1.0)

        # Step 7: Handle "ARE YOU SURE?" dialog
        await self._handle_are_you_sure()

    async def _handle_are_you_sure(self) -> None:
        """Step 7: Click Yes on 'ARE YOU SURE?' dialog."""
        self.state = TradeState.CONFIRMING_YES

        screenshot = capture_screen()

        # Try to find "Yes" button via template
        found, center = detect_template(
            screenshot,
            "yes_button.png",
            threshold=self.config.template_threshold,
        )

        if found and center:
            await async_click(center[0], center[1])
            logger.debug("Clicked Yes on ARE YOU SURE dialog")
        else:
            # Fallback: try OCR to find Yes button
            text = ocr.read_text(screenshot)
            if "sure" in text.lower() or "yes" in text.lower():
                # Click approximate Yes button location (usually center-right)
                w, h = screenshot.shape[:2]
                await async_click(w // 2 + 100, h // 2 + 50)
                logger.debug("Clicked Yes via OCR fallback")
            else:
                logger.info("No ARE YOU SURE dialog — may already be confirmed")

        await asyncio.sleep(2.0)
        await self._verify_completion()

    async def _verify_completion(self) -> None:
        """Step 8: Verify trade completed via template or OCR."""
        if self.config.ocr_enabled:
            # Try template match first
            found, _ = wait_for_template(
                capture_screen,
                "you_have_accepted.png",
                timeout=15.0,
                interval=1.0,
            )

            if not found:
                # Fallback: OCR
                screenshot = capture_screen()
                text = ocr.read_text(screenshot)
                if "accepted" not in text.lower() and "completed" not in text.lower():
                    logger.warning("Trade completion not confirmed")
                    self.state = TradeState.FAILED
                    await self._on_fail(
                        self._current_trade.get("order_id") if self._current_trade else None,
                        "Completion not confirmed",
                    )
                    return

        # Step 9: Take proof screenshot
        proof_path = await self._take_proof_screenshot()

        # Step 10: Report success
        self.state = TradeState.COMPLETED
        order_id = self._current_trade.get("order_id") if self._current_trade else None
        buyer = self._current_trade.get("buyer_nickname", "") if self._current_trade else ""
        logger.info(f"Trade completed for {buyer}, order {order_id}")

        if self._on_trade_completed:
            await self._on_trade_completed(order_id, True, proof_path)

        # Remove from local waitlist
        if buyer:
            waitlist_manager.remove_by_buyer(buyer)

        # Reset state after delay
        await asyncio.sleep(3.0)
        self.state = TradeState.IDLE

    async def _take_proof_screenshot(self) -> str | None:
        """Take proof screenshot and save to disk."""
        try:
            screenshot = capture_screen()
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            order_id = self._current_trade.get("order_id", 0) if self._current_trade else 0
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
        # Reset state
        await asyncio.sleep(3.0)
        self.state = TradeState.IDLE

    def set_current_trade(self, trade: dict) -> None:
        """Set the current trade to process."""
        self._current_trade = trade

    def stop(self) -> None:
        """Stop the scan loop."""
        self._running = False
