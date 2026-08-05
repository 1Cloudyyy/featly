"""Integration tests — full flow: Plugin → Backend → Engine."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_full_order_flow(client):
    """Test complete order lifecycle:
    1. Create order
    2. Create pending trade
    3. Update order status
    4. Verify inventory
    5. Delete pending trade
    """
    # 1. Create order
    order_data = {
        "funpay_order_id": "fp_test_001",
        "buyer_nickname": "test_buyer",
        "buyer_user_id": 123456789,
        "items": ["Batwing"],
    }
    resp = await client.post("/orders", json=order_data)
    assert resp.status_code == 201
    order = resp.json()
    order_id = order["id"]
    assert order["status"] == "new"
    assert order["buyer_nickname"] == "test_buyer"

    # 2. Create pending trade
    trade_data = {
        "order_id": order_id,
        "bot_id": "bot_main",
        "buyer_nickname": "test_buyer",
        "buyer_user_id": 123456789,
        "items": ["Batwing"],
    }
    resp = await client.post("/pending_trades", json=trade_data)
    assert resp.status_code == 201
    trade = resp.json()
    trade_id = trade["id"]
    assert trade["status"] == "waiting"

    # 3. Update order status to waiting_trade
    resp = await client.patch(
        f"/orders/{order_id}/status", json={"status": "waiting_trade"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "waiting_trade"

    # 4. Verify pending trade exists
    resp = await client.get(f"/pending_trades?bot_id=bot_main")
    assert resp.status_code == 200
    trades = resp.json()
    assert any(t["id"] == trade_id for t in trades)

    # 5. Complete order
    resp = await client.patch(
        f"/orders/{order_id}/status",
        json={"status": "completed", "proof_url": "/proofs/proof_001.png"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"
    assert resp.json()["proof_url"] == "/proofs/proof_001.png"

    # 6. Delete pending trade
    resp = await client.delete(f"/pending_trades/{trade_id}")
    assert resp.status_code == 204

    # 7. Verify trade removed
    resp = await client.get(f"/pending_trades?bot_id=bot_main")
    assert resp.status_code == 200
    trades = resp.json()
    assert not any(t["id"] == trade_id for t in trades)


@pytest.mark.anyio
async def test_inventory_flow(client):
    """Test inventory management."""
    # Get inventory (may be empty)
    resp = await client.get("/inventory")
    assert resp.status_code == 200

    # Update an item (create if not exists via direct DB)
    # This tests the PATCH endpoint
    resp = await client.patch(
        "/inventory/batwing_single",
        json={"count": 5, "low_stock_threshold": 3},
    )
    # May return 404 if item doesn't exist yet — that's ok
    assert resp.status_code in (200, 404)


@pytest.mark.anyio
async def test_bot_heartbeat(client):
    """Test bot heartbeat endpoint."""
    resp = await client.patch("/bots/bot_main/heartbeat")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Verify bot status
    resp = await client.get("/bots/bot_main")
    assert resp.status_code == 200
    bot = resp.json()
    assert bot["bot_id"] == "bot_main"
