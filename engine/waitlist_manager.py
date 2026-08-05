"""Waitlist manager — local cache of pending trades."""

from __future__ import annotations

from loguru import logger


class WaitlistManager:
    """Manages the local waitlist of pending trades."""

    def __init__(self) -> None:
        self._waitlist: list[dict] = []

    @property
    def waitlist(self) -> list[dict]:
        return self._waitlist.copy()

    def sync(self, trades: list[dict]) -> None:
        """Replace waitlist with fresh data from backend."""
        self._waitlist = trades
        logger.info(f"Waitlist synced: {len(self._waitlist)} trades")

    def add(self, trade: dict) -> None:
        """Add a trade to waitlist."""
        # Avoid duplicates
        existing = [
            w for w in self._waitlist if w.get("order_id") == trade.get("order_id")
        ]
        if not existing:
            self._waitlist.append(trade)
            logger.info(f"Added to waitlist: {trade.get('buyer_nickname')}")

    def remove_by_buyer(self, buyer_nickname: str) -> bool:
        """Remove a trade by buyer nickname."""
        before = len(self._waitlist)
        self._waitlist = [
            w for w in self._waitlist if w.get("buyer_nickname") != buyer_nickname
        ]
        removed = len(self._waitlist) < before
        if removed:
            logger.info(f"Removed from waitlist: {buyer_nickname}")
        return removed

    def remove_by_order(self, order_id: int) -> bool:
        """Remove a trade by order_id."""
        before = len(self._waitlist)
        self._waitlist = [
            w for w in self._waitlist if w.get("order_id") != order_id
        ]
        return len(self._waitlist) < before

    def find_by_buyer(self, buyer_nickname: str) -> dict | None:
        """Find a trade by buyer nickname."""
        for trade in self._waitlist:
            if trade.get("buyer_nickname") == buyer_nickname:
                return trade
        return None

    def is_in_waitlist(self, buyer_nickname: str) -> bool:
        """Check if buyer is in waitlist."""
        return self.find_by_buyer(buyer_nickname) is not None

    def buyer_nicknames(self) -> list[str]:
        """Get list of all buyer nicknames in waitlist."""
        return [w.get("buyer_nickname", "") for w in self._waitlist]

    def clear(self) -> None:
        """Clear waitlist."""
        self._waitlist.clear()
        logger.info("Waitlist cleared")


# Singleton
waitlist_manager = WaitlistManager()
