"""Runtime data — order cache, active dialogs."""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

DATA_DIR = Path(__file__).parent / "data"
ORDERS_FILE = DATA_DIR / "orders_cache.json"


class OrdersCache:
    """In-memory + disk cache of active orders."""

    def __init__(self) -> None:
        self._cache: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if ORDERS_FILE.exists():
            try:
                self._cache = json.loads(ORDERS_FILE.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error(f"Failed to load orders cache: {e}")

    def _save(self) -> None:
        ORDERS_FILE.write_text(
            json.dumps(self._cache, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def get(self, funpay_order_id: str) -> dict | None:
        return self._cache.get(funpay_order_id)

    def set(self, funpay_order_id: str, data: dict) -> None:
        self._cache[funpay_order_id] = data
        self._save()

    def remove(self, funpay_order_id: str) -> None:
        self._cache.pop(funpay_order_id, None)
        self._save()

    def all(self) -> dict[str, dict]:
        return self._cache.copy()


# Singleton
orders_cache = OrdersCache()
