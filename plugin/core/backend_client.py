"""Hub client — REST-вызовы к Featly Hub (центру управления).

Каждый вызов логируется: метод, путь, статус, длительность; ошибки — с текстом,
чтобы сразу было понятно, где именно проблема (недоступен hub, 4xx/5xx, сеть).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import aiohttp

from ..meta import NAME
from ..settings import load_settings

log = logging.getLogger(f"{NAME}.hub")


class BackendClient:
    """Async HTTP client for Featly Hub REST API."""

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            log.debug("Создана новая aiohttp-сессия")
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            log.info("HTTP-сессия к hub закрыта")
        self._session = None

    def _url(self, path: str) -> str:
        settings = load_settings()
        base = settings.get("backend_url", "http://localhost:8000")
        return f"{base.rstrip('/')}{path}"

    async def _request(
        self, method: str, path: str, *, expected: tuple[int, ...] = (200, 201), **kwargs
    ) -> tuple[int | None, Any | None, str | None]:
        """Выполнить запрос. Возвращает (status, json|None, error_text|None)."""
        session = await self._get_session()
        url = self._url(path)
        started = time.perf_counter()
        try:
            async with session.request(method, url, **kwargs) as resp:
                body = await resp.text()
                ms = (time.perf_counter() - started) * 1000
                if resp.status in expected:
                    data = json.loads(body) if body else None
                    log.debug("%s %s → %s (%.1f ms)", method, path, resp.status, ms)
                    return resp.status, data, None
                log.warning(
                    "%s %s → %s (%.1f ms): %s", method, path, resp.status, ms, body[:300]
                )
                return resp.status, None, body[:300]
        except Exception as e:
            ms = (time.perf_counter() - started) * 1000
            log.error("%s %s → исключение (%.1f ms): %r", method, path, ms, e)
            return None, None, repr(e)

    # --- Health ---

    async def health(self) -> bool:
        status, _, err = await self._request("GET", "/health")
        log.info("health → %s", "OK" if status == 200 else f"fail ({err})")
        return status == 200

    # --- Orders ---

    async def create_order(
        self,
        funpay_order_id: str,
        buyer_nickname: str,
        buyer_user_id: int,
        items: list[str],
    ) -> dict | None:
        payload = {
            "funpay_order_id": funpay_order_id,
            "buyer_nickname": buyer_nickname,
            "buyer_user_id": buyer_user_id,
            "items": items,
        }
        status, data, err = await self._request("POST", "/orders", json=payload)
        if status in (200, 201):
            log.info("create_order: funpay=%s → hub_order_id=%s", funpay_order_id, data and data.get("id"))
            return data
        log.error("create_order: funpay=%s не создан (status=%s, err=%s)", funpay_order_id, status, err)
        return None

    async def update_order_status(
        self, order_id: int, status: str, proof_url: str | None = None
    ) -> dict | None:
        payload = {"status": status}
        if proof_url:
            payload["proof_url"] = proof_url
        s, data, err = await self._request("PATCH", f"/orders/{order_id}/status", json=payload)
        if s == 200:
            log.info("update_order_status: order=%s → %s", order_id, status)
            return data
        log.error("update_order_status: order=%s → %s не принят (status=%s, err=%s)", order_id, status, s, err)
        return None

    async def get_order(self, order_id: int) -> dict | None:
        s, data, err = await self._request("GET", f"/orders/{order_id}")
        if s == 200:
            return data
        log.warning("get_order: order=%s → %s (err=%s)", order_id, s, err)
        return None

    async def force_trade(self, order_id: int) -> dict | None:
        """Принудительная выдача: движок пересканирует заказ."""
        s, data, err = await self._request("POST", f"/orders/{order_id}/force")
        if s == 200:
            log.info("force_trade: order=%s → %s", order_id, data)
            return data
        log.error("force_trade: order=%s → %s (err=%s)", order_id, s, err)
        return None

    async def cancel_order(self, order_id: int) -> dict | None:
        """Отмена заказа: CANCELLED + удаление из waitlist + уведомление движка."""
        s, data, err = await self._request("POST", f"/orders/{order_id}/cancel")
        if s == 200:
            log.warning("cancel_order: order=%s отменён", order_id)
            return data
        log.error("cancel_order: order=%s → %s (err=%s)", order_id, s, err)
        return None

    # --- Pending Trades ---

    async def get_pending_trades(self, bot_id: str) -> list[dict]:
        s, data, err = await self._request("GET", f"/pending_trades?bot_id={bot_id}")
        if s == 200:
            log.debug("get_pending_trades: %s записей для bot=%s", len(data or []), bot_id)
            return data or []
        log.error("get_pending_trades: bot=%s → %s (err=%s)", bot_id, s, err)
        return []

    async def create_pending_trade(
        self,
        order_id: int,
        bot_id: str,
        buyer_nickname: str,
        buyer_user_id: int,
        items: list[str],
    ) -> dict | None:
        payload = {
            "order_id": order_id,
            "bot_id": bot_id,
            "buyer_nickname": buyer_nickname,
            "buyer_user_id": buyer_user_id,
            "items": items,
        }
        s, data, err = await self._request("POST", "/pending_trades", json=payload)
        if s in (200, 201):
            log.info("create_pending_trade: order=%s внесён в waitlist (trade_id=%s)", order_id, data and data.get("id"))
            return data
        log.error("create_pending_trade: order=%s → не создан (status=%s, err=%s)", order_id, s, err)
        return None

    async def delete_pending_trade(self, trade_id: int) -> bool:
        s, _, err = await self._request("DELETE", f"/pending_trades/{trade_id}", expected=(204,))
        if s == 204:
            log.info("delete_pending_trade: trade=%s удалён", trade_id)
            return True
        log.error("delete_pending_trade: trade=%s → %s (err=%s)", trade_id, s, err)
        return False

    # --- Inventory ---

    async def get_inventory(self) -> list[dict]:
        s, data, err = await self._request("GET", "/inventory")
        if s == 200:
            log.debug("get_inventory: %s предметов", len(data or []))
            return data or []
        log.error("get_inventory → %s (err=%s)", s, err)
        return []

    async def get_item(self, item_key: str) -> dict | None:
        s, data, err = await self._request("GET", f"/inventory/{item_key}")
        if s == 200:
            return data
        log.warning("get_item: %s → %s (err=%s)", item_key, s, err)
        return None

    async def upsert_item(
        self,
        item_key: str,
        name: str,
        count: int = 0,
        low_stock_threshold: int = 3,
    ) -> bool:
        payload = {
            "item_key": item_key,
            "name": name,
            "count": count,
            "low_stock_threshold": low_stock_threshold,
        }
        s, data, err = await self._request("POST", "/inventory", json=payload, expected=(200, 201))
        if s in (200, 201):
            log.info("upsert_item: %s создан/обновлён (%s шт)", item_key, count)
            return True
        log.error("upsert_item: %s → %s (err=%s)", item_key, s, err)
        return False

    async def update_item_count(self, item_key: str, count: int) -> bool:
        s, _, err = await self._request("PATCH", f"/inventory/{item_key}", json={"count": count})
        if s == 200:
            log.info("update_item_count: %s → %s", item_key, count)
            return True
        log.error("update_item_count: %s → %s (err=%s)", item_key, s, err)
        return False

    async def update_item_threshold(self, item_key: str, threshold: int) -> bool:
        s, _, err = await self._request(
            "PATCH", f"/inventory/{item_key}", json={"low_stock_threshold": threshold}
        )
        if s == 200:
            log.info("update_item_threshold: %s → %s", item_key, threshold)
            return True
        log.error("update_item_threshold: %s → %s (err=%s)", item_key, s, err)
        return False

    async def delete_item(self, item_key: str) -> bool:
        s, _, err = await self._request("DELETE", f"/inventory/{item_key}", expected=(204,))
        if s == 204:
            log.info("delete_item: %s удалён", item_key)
            return True
        log.warning("delete_item: %s → %s (err=%s)", item_key, s, err)
        return False

    # --- Stats ---

    async def get_stats(self) -> dict | None:
        s, data, err = await self._request("GET", "/stats")
        if s == 200:
            return data
        log.error("get_stats → %s (err=%s)", s, err)
        return None

    async def set_item_threshold(self, item_key: str, threshold: int) -> bool:
        s, _, err = await self._request(
            "PATCH", f"/inventory/{item_key}", json={"low_stock_threshold": threshold}
        )
        if s == 200:
            log.info("set_item_threshold: %s = %s", item_key, threshold)
            return True
        log.error("set_item_threshold: %s → %s (err=%s)", item_key, s, err)
        return False

    # --- Bots ---

    async def get_bot(self, bot_id: str) -> dict | None:
        s, data, err = await self._request("GET", f"/bots/{bot_id}")
        if s == 200:
            return data
        log.warning("get_bot: %s → %s (err=%s)", bot_id, s, err)
        return None

    async def update_cookie(self, bot_id: str, cookie: str) -> bool:
        s, _, err = await self._request(
            "PATCH", f"/bots/{bot_id}/cookie", json={"roblox_cookie": cookie}
        )
        if s == 200:
            log.info("update_cookie: bot=%s cookie обновлён", bot_id)
            return True
        log.error("update_cookie: bot=%s → %s (err=%s)", bot_id, s, err)
        return False


# Singleton
backend_client = BackendClient()