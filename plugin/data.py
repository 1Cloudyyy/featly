"""Runtime data — кэш активных заказов, диалоги.

Логирование операций кэша: загрузка/сохранение/удаление, чтобы отлавливать
расхождения между плагином и hub'ом.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from loguru import logger

log = logging.getLogger("Featly.data")

DATA_DIR = Path(__file__).parent / "data"
ORDERS_FILE = DATA_DIR / "orders_cache.json"


class OrdersCache:
    """In-memory + disk cache активных заказов (funpay_order_id → hub order)."""

    def __init__(self) -> None:
        self._cache: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if ORDERS_FILE.exists():
            try:
                self._cache = json.loads(ORDERS_FILE.read_text(encoding="utf-8"))
                log.info("Кэш заказов загружен: %s записей", len(self._cache))
            except Exception as e:
                log.error("Не удалось прочитать кэш заказов: %s", e)

    def _save(self) -> None:
        ORDERS_FILE.write_text(
            json.dumps(self._cache, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def get(self, funpay_order_id: str) -> dict | None:
        return self._cache.get(funpay_order_id)

    def set(self, funpay_order_id: str, data: dict) -> None:
        self._cache[funpay_order_id] = data
        self._save()
        log.debug("Кэш: добавлен заказ %s → %s", funpay_order_id, data.get("order_id"))

    def remove(self, funpay_order_id: str) -> None:
        if funpay_order_id in self._cache:
            self._cache.pop(funpay_order_id, None)
            self._save()
            log.info("Кэш: заказ %s удалён", funpay_order_id)

    def all(self) -> dict[str, dict]:
        return self._cache.copy()


# Singleton
orders_cache = OrdersCache()