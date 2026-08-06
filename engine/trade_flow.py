"""Trade flow — main automation logic for MM2 trades.

Real MM2 trade flow:
1. Detect trade request notification
2. Wait for trade window (instant)
3. Search item in Search box
4. Click item(s) to add to YOUR OFFER
5. Wait for countdown 6-7 sec ("Please wait (X) before accepting")
6. Click ACCEPT
7. Click "ARE YOU SURE?"
8. Other side accepts → DONE
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
    DETECTED = "detected"
    WAITING_WINDOW = "waiting_window"
    SEARCHING = "searching"
    ADDING_ITEMS = "adding_items"
    WAITING_COUNTDOWN = "waiting_countdown"
    CLICKING_ACCEPT = "clicking_accept"
    CONFIRMING_YES = "confirming_yes"
    WAITING_OTHER_SIDE = "waiting_other_side"
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

    # ─── Step 1: Detect trade request ─────────────────────────────

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

        # OCR the buyer's nickname BEFORE clicking anything
        buyer_nick = ocr.read_nickname_from_trade(
            screenshot, region=regions.trade_request
        )

        if not buyer_nick:
            # Try full screen OCR as fallback
            buyer_nick = ocr.read_nickname_from_trade(screenshot)

        if not buyer_nick:
            logger.warning("Could not read buyer nickname — ignoring trade request")
            return

        logger.info(f"Trade request from: {buyer_nick}")

        # Check waitlist
        trade_data = waitlist_manager.find_by_buyer(buyer_nick)
        if not trade_data:
            logger.info(f"Buyer {buyer_nick} not in waitlist — declining")
            # Click Decline
            await self._decline_trade()
            return

        # Buyer is in waitlist — accept
        self.state = TradeState.DETECTED
        self._current_trade = trade_data
        logger.info(f"Buyer {buyer_nick} in waitlist — accepting trade")

        if center:
            await async_click(center[0], center[1])
            logger.debug(f"Clicked trade request Accept at {center}")

        await asyncio.sleep(1.0)
        await self._wait_for_trade_window()

    # ─── Step 2: Wait for trade window ────────────────────────────

    async def _wait_for_trade_window(self) -> None:
        """Wait for trade window to open (almost instant)."""
        self.state = TradeState.WAITING_WINDOW

        # Brief wait — window opens fast
        await asyncio.sleep(0.5)

        # Verify window is open by checking for search box or YOUR OFFER
        screenshot = capture_screen()
        found, _ = detect_template(screenshot, "search_box.png", threshold=0.7)

        if not found:
            # Try one more time
            await asyncio.sleep(1.0)
            screenshot = capture_screen()
            found, _ = detect_template(screenshot, "search_box.png", threshold=0.7)

        if not found:
            logger.warning("Trade window not detected")
            self.state = TradeState.FAILED
            await self._on_fail(None, "Trade window not opened")
            return

        logger.info("Trade window open")
        await self._search_and_add_items()

    # ─── Step 3: Search item ──────────────────────────────────────

    async def _search_and_add_items(self) -> None:
        """Search for item and add to YOUR OFFER."""
        self.state = TradeState.SEARCHING
        regions = self.config.regions
        items = self._current_trade.get("items", []) if self._current_trade else []

        if not items:
            logger.warning("No items to trade")
            self.state = TradeState.FAILED
            await self._on_fail(None, "No items specified")
            return

        # Process each item
        for item_name in items:
            await self._search_single_item(item_name)
            await asyncio.sleep(0.5)

        logger.info(f"All items added: {items}")
        await self._wait_for_countdown()

    async def _search_single_item(self, item_name: str) -> None:
        """Search for a single item and add it."""
        regions = self.config.regions
        logger.info(f"Searching for: {item_name}")

        # Click search box
        sx, sy, sw, sh = regions.search_box
        await async_click(sx + sw // 2, sy + sh // 2)
        await asyncio.sleep(0.3)

        # Clear and type FULL item name for exact match
        await async_press("ctrl+a")
        await asyncio.sleep(0.1)
        await async_press("backspace")
        await asyncio.sleep(0.2)

        # Type full item name
        await async_type(item_name.lower())
        await asyncio.sleep(1.0)

        # Click first result in list (below search box)
        await async_click(sx + sw // 2, sy + sh + 40)
        await asyncio.sleep(0.3)

        # Click again to confirm adding to YOUR OFFER
        await async_click(sx + sw // 2, sy + sh + 40)
        await asyncio.sleep(0.3)

        logger.debug(f"Added {item_name} to offer")

    # ─── Step 5: Wait for countdown ───────────────────────────────

    async def _wait_for_countdown(self) -> None:
        """Wait for 'Please wait (X) before accepting' countdown."""
        self.state = TradeState.WAITING_COUNTDOWN
        logger.info("Waiting for countdown (6-7 sec)...")
        await asyncio.sleep(7.0)
        await self._click_accept()

    # ─── Step 6: Click ACCEPT ─────────────────────────────────────

    async def _click_accept(self) -> None:
        """Click the ACCEPT button."""
        self.state = TradeState.CLICKING_ACCEPT
        regions = self.config.regions

        logger.info("Clicking ACCEPT...")
        cx, cy, cw, ch = regions.confirm_button
        await async_click(cx + cw // 2, cy + ch // 2)
        await asyncio.sleep(1.5)

        # Step 7: Handle "ARE YOU SURE?"
        await self._handle_are_you_sure()

    # ─── Step 7: ARE YOU SURE? ────────────────────────────────────

    async def _handle_are_you_sure(self) -> None:
        """Click Yes on 'ARE YOU SURE?' dialog."""
        self.state = TradeState.CONFIRMING_YES

        screenshot = capture_screen()

        # Try template match for Yes button
        found, center = detect_template(
            screenshot,
            "yes_button.png",
            threshold=self.config.template_threshold,
        )

        if found and center:
            await async_click(center[0], center[1])
            logger.debug("Clicked Yes on ARE YOU SURE")
        else:
            # Fallback: try OCR
            text = ocr.read_text(screenshot)
            if "sure" in text.lower() or "yes" in text.lower():
                # Click Yes button (usually center of dialog)
                h, w = screenshot.shape[:2]
                await async_click(w // 2 + 80, h // 2 + 40)
                logger.debug("Clicked Yes via OCR fallback")
            else:
                logger.info("No ARE YOU SURE dialog found")

        await asyncio.sleep(1.0)

        # Step 8: Wait for other side to accept
        await self._wait_for_completion()

    # ─── Step 8: Wait for other side ──────────────────────────────

    async def _wait_for_completion(self) -> None:
        """Wait for other side to accept and trade to complete."""
        self.state = TradeState.WAITING_OTHER_SIDE
        logger.info("Waiting for other side to accept...")

        # Wait for "YOU HAVE ACCEPTED" or trade completion
        if self.config.ocr_enabled:
            found, _ = wait_for_template(
                capture_screen,
                "you_have_accepted.png",
                timeout=30.0,
                interval=1.0,
            )

            if not found:
                # Try OCR
                screenshot = capture_screen()
                text = ocr.read_text(screenshot)
                if "accepted" not in text.lower() and "completed" not in text.lower():
                    logger.warning("Trade completion not confirmed")
                    self.state = TradeState.FAILED
                    await self._on_fail(
                        self._current_trade.get("order_id") if self._current_trade else None,
                        "Other side did not accept",
                    )
                    return
        else:
            # Just wait fixed time
            await asyncio.sleep(15.0)

        # Proof screenshot
        proof_path = await self._take_proof_screenshot()

        # Report success
        self.state = TradeState.COMPLETED
        order_id = self._current_trade.get("order_id") if self._current_trade else None
        buyer = self._current_trade.get("buyer_nickname", "") if self._current_trade else ""
        logger.info(f"Trade completed! Buyer: {buyer}, Order: {order_id}")

        if self._on_trade_completed:
            await self._on_trade_completed(order_id, True, proof_path)

        if buyer:
            waitlist_manager.remove_by_buyer(buyer)

        await asyncio.sleep(3.0)
        self.state = TradeState.IDLE

    # ─── Helpers ───────────────────────────────────────────────────

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
        """Handle trade failure — close window and notify backend."""
        logger.error(f"Trade failed: order={order_id}, error={error}")

        # Close trade window if open
        await self._close_trade_window()

        # Notify backend
        if self._on_trade_failed and order_id:
            await self._on_trade_failed(order_id, error)

        await asyncio.sleep(3.0)
        self.state = TradeState.IDLE

    async def _close_trade_window(self) -> None:
        """Close trade window by pressing Escape."""
        try:
            await async_press("escape")
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.debug(f"Failed to close trade window: {e}")

    def set_current_trade(self, trade: dict) -> None:
        self._current_trade = trade

    def stop(self) -> None:
        self._running = False
