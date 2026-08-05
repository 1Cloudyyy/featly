"""End-to-end test — simulates full trade flow without real Roblox."""

import asyncio
import json

import pytest
import websockets
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_e2e_trade_flow(client):
    """Simulate full trade flow:
    1. Plugin creates order
    2. Plugin creates pending trade
    3. Engine connects via WS
    4. Engine receives waitlist
    5. Engine reports trade completed
    6. Backend updates order status
    7. Plugin verifies completion
    """
    # Step 1: Create order (simulating Plugin)
    order_resp = await client.post("/orders", json={
        "funpay_order_id": "fp_e2e_001",
        "buyer_nickname": "e2e_buyer",
        "buyer_user_id": 999999999,
        "items": ["Ghostblade"],
    })
    assert order_resp.status_code == 201
    order = order_resp.json()

    # Step 2: Create pending trade
    trade_resp = await client.post("/pending_trades", json={
        "order_id": order["id"],
        "bot_id": "e2e_bot",
        "buyer_nickname": "e2e_buyer",
        "buyer_user_id": 999999999,
        "items": ["Ghostblade"],
    })
    assert trade_resp.status_code == 201

    # Step 3-4: Engine connects and gets waitlist
    uri = "ws://localhost:8000/ws/engine"
    try:
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({
                "secret": "change-me-in-production",
                "bot_id": "e2e_bot",
            }))

            # Receive waitlist
            response = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(response)
            assert data["type"] == "waitlist_sync"

            # Verify our trade is in waitlist
            waitlist = data["waitlist"]
            assert any(t["buyer_nickname"] == "e2e_buyer" for t in waitlist)

            # Step 5: Engine reports trade completed
            await ws.send(json.dumps({
                "type": "trade_completed",
                "order_id": order["id"],
                "success": True,
                "bot_id": "e2e_bot",
            }))

            await asyncio.sleep(0.5)

    except (ConnectionRefusedError, OSError):
        pytest.skip("Backend not running — e2e test requires running backend")
        return

    # Step 6: Verify order status updated
    order_resp = await client.get(f"/orders/{order['id']}")
    assert order_resp.status_code == 200
    completed_order = order_resp.json()
    assert completed_order["status"] == "completed"

    # Step 7: Verify pending trade removed
    trades_resp = await client.get("/pending_trades?bot_id=e2e_bot")
    assert trades_resp.status_code == 200
    trades = trades_resp.json()
    assert not any(t["order_id"] == order["id"] for t in trades)
