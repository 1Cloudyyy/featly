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
        """Find a trade by buyer nickname (fuzzy match)."""
        buyer_lower = buyer_nickname.lower().strip()
        for trade in self._waitlist:
            nick = trade.get("buyer_nickname", "").lower().strip()
            # Exact match
            if buyer_lower == nick:
                return trade
            # Partial match (OCR might read partial name)
            if buyer_lower in nick or nick in buyer_lower:
                return trade
            # Fuzzy match (Levenshtein-like: allow 2 char difference)
            if len(buyer_lower) >= 3 and len(nick) >= 3:
                if self._levenshtein(buyer_lower, nick) <= 2:
                    return trade
        return None

    @staticmethod
    def _levenshtein(a: str, b: str) -> int:
        """Simple Levenshtein distance."""
        if len(a) < len(b):
            return WaitlistManager._levenshtein(b, a)
        if len(b) == 0:
            return len(a)
        prev = range(len(b) + 1)
        for i, ca in enumerate(a):
            curr = [i + 1]
            for j, cb in enumerate(b):
                insertions = prev[j + 1] + 1
                deletions = curr[j] + 1
                substitutions = prev[j] + (ca != cb)
                curr.append(min(insertions, deletions, substitutions))
            prev = curr
        return prev[-1]

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
