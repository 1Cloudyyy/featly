"""Backend HTTP client — REST calls to Featly Backend."""

from __future__ import annotations

import aiohttp
from loguru import logger

from ..settings import load_settings


class BackendClient:
    """Async HTTP client for Featly Backend REST API."""

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _url(self, path: str) -> str:
        settings = load_settings()
        base = settings.get("backend_url", "http://localhost:8000")
        return f"{base.rstrip('/')}{path}"

    # --- Orders ---

    async def create_order(
        self,
        funpay_order_id: str,
        buyer_nickname: str,
        buyer_user_id: int,
        items: list[str],
    ) -> dict | None:
        session = await self._get_session()
        payload = {
            "funpay_order_id": funpay_order_id,
            "buyer_nickname": buyer_nickname,
            "buyer_user_id": buyer_user_id,
            "items": items,
        }
        try:
            async with session.post(self._url("/orders"), json=payload) as resp:
                if resp.status in (200, 201):
                    return await resp.json()
                logger.error(f"create_order failed: {resp.status} {await resp.text()}")
                return None
        except Exception as e:
            logger.error(f"create_order error: {e}")
            return None

    async def update_order_status(
        self, order_id: int, status: str, proof_url: str | None = None
    ) -> dict | None:
        session = await self._get_session()
        payload = {"status": status}
        if proof_url:
            payload["proof_url"] = proof_url
        try:
            async with session.patch(
                self._url(f"/orders/{order_id}/status"), json=payload
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                logger.error(f"update_order_status failed: {resp.status}")
                return None
        except Exception as e:
            logger.error(f"update_order_status error: {e}")
            return None

    async def get_order(self, order_id: int) -> dict | None:
        session = await self._get_session()
        try:
            async with session.get(self._url(f"/orders/{order_id}")) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
        except Exception as e:
            logger.error(f"get_order error: {e}")
            return None

    # --- Pending Trades ---

    async def create_pending_trade(
        self,
        order_id: int,
        bot_id: str,
        buyer_nickname: str,
        buyer_user_id: int,
        items: list[str],
    ) -> dict | None:
        session = await self._get_session()
        payload = {
            "order_id": order_id,
            "bot_id": bot_id,
            "buyer_nickname": buyer_nickname,
            "buyer_user_id": buyer_user_id,
            "items": items,
        }
        try:
            async with session.post(self._url("/pending_trades"), json=payload) as resp:
                if resp.status in (200, 201):
                    return await resp.json()
                logger.error(f"create_pending_trade failed: {resp.status}")
                return None
        except Exception as e:
            logger.error(f"create_pending_trade error: {e}")
            return None

    async def delete_pending_trade(self, trade_id: int) -> bool:
        session = await self._get_session()
        try:
            async with session.delete(self._url(f"/pending_trades/{trade_id}")) as resp:
                return resp.status == 204
        except Exception as e:
            logger.error(f"delete_pending_trade error: {e}")
            return False

    # --- Inventory ---

    async def get_inventory(self) -> list[dict]:
        session = await self._get_session()
        try:
            async with session.get(self._url("/inventory")) as resp:
                if resp.status == 200:
                    return await resp.json()
                return []
        except Exception as e:
            logger.error(f"get_inventory error: {e}")
            return []

    async def get_item(self, item_key: str) -> dict | None:
        session = await self._get_session()
        try:
            async with session.get(self._url(f"/inventory/{item_key}")) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
        except Exception as e:
            logger.error(f"get_item error: {e}")
            return None

    # --- Bot ---

    async def update_cookie(self, bot_id: str, cookie: str) -> bool:
        session = await self._get_session()
        payload = {"roblox_cookie": cookie}
        try:
            async with session.patch(
                self._url(f"/bots/{bot_id}/cookie"), json=payload
            ) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"update_cookie error: {e}")
            return False


# Singleton
backend_client = BackendClient()
