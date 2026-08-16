"""Runtime data — кэш активных заказов, диалоги.

Логирование операций кэша + threading.Lock (кэш могут трогать несколько хендлеров).
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from loguru import logger

log = logging.getLogger("Featly.data")

DATA_DIR = Path(__file__).parent / "data"
ORDERS_FILE = DATA_DIR / "orders_cache.json"


class OrdersCache:
    """In-memory + disk cache активных заказов (funpay_order_id → hub order)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
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
        with self._lock:
            return self._cache.get(funpay_order_id)

    def find_by_chat(self, chat_id: int) -> tuple[str, dict] | None:
        """Найти запись по chat_id (для !смена). Возвращает (funpay_order_id, entry)."""
        with self._lock:
            for key, entry in self._cache.items():
                if entry.get("chat_id") == chat_id:
                    return key, entry
        return None

    def set(self, funpay_order_id: str, data: dict) -> None:
        with self._lock:
            self._cache[funpay_order_id] = data
            self._save()
        log.debug("Кэш: добавлен заказ %s → %s", funpay_order_id, data.get("order_id"))

    def remove(self, funpay_order_id: str) -> None:
        with self._lock:
            if funpay_order_id in self._cache:
                self._cache.pop(funpay_order_id, None)
                self._save()
                log.info("Кэш: заказ %s удалён", funpay_order_id)

    def all(self) -> dict[str, dict]:
        with self._lock:
            return self._cache.copy()


# Singleton
orders_cache = OrdersCache()

# Файл активных диалогов (персистентность: рестарт плагина не теряет диалоги)
DIALOGS_FILE = DATA_DIR / "dialogs_cache.json"


class DialogCache:
    """Persistent storage активных диалогов (chat_id → state)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._dialogs: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if DIALOGS_FILE.exists():
            try:
                self._dialogs = json.loads(DIALOGS_FILE.read_text(encoding="utf-8"))
                log.info("Восстановлено диалогов из файла: %s", len(self._dialogs))
            except Exception as e:
                log.error("Не удалось прочитать кэш диалогов: %s", e)

    def load_all(self) -> dict[str, dict]:
        with self._lock:
            return dict(self._dialogs)

    def save_all(self, dialogs: dict[int, dict]) -> None:
        with self._lock:
            self._dialogs = {str(k): v for k, v in dialogs.items()}
            DIALOGS_FILE.write_text(
                json.dumps(self._dialogs, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        log.debug("Диалоги сохранены: %s шт", len(self._dialogs))


# Singleton
dialog_cache = DialogCache()