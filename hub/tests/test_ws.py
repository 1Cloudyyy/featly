"""WebSocket integration tests — Engine ↔ Backend communication."""

import asyncio
import json

import pytest
import websockets

from app.config import settings


@pytest.mark.anyio
async def test_ws_auth_success():
    """Test successful WebSocket authentication."""
    uri = f"ws://localhost:8000/ws/engine"
    try:
        async with websockets.connect(uri) as ws:
            # Send auth
            await ws.send(json.dumps({
                "secret": settings.ws_secret,
                "bot_id": "test_bot",
            }))

            # Should receive waitlist sync
            response = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(response)
            assert data["type"] == "waitlist_sync"
            assert "waitlist" in data
    except (ConnectionRefusedError, OSError):
        pytest.skip("Backend not running")


@pytest.mark.anyio
async def test_ws_auth_failure():
    """Test WebSocket authentication with wrong secret."""
    uri = f"ws://localhost:8000/ws/engine"
    try:
        async with websockets.connect(uri) as ws:
            # Send auth with wrong secret
            await ws.send(json.dumps({
                "secret": "wrong-secret",
                "bot_id": "test_bot",
            }))

            # Should be disconnected
            with pytest.raises(websockets.exceptions.ConnectionClosed):
                await asyncio.wait_for(ws.recv(), timeout=5)
    except (ConnectionRefusedError, OSError):
        pytest.skip("Backend not running")


@pytest.mark.anyio
async def test_ws_heartbeat():
    """Test WebSocket heartbeat mechanism."""
    uri = f"ws://localhost:8000/ws/engine"
    try:
        async with websockets.connect(uri) as ws:
            # Auth
            await ws.send(json.dumps({
                "secret": settings.ws_secret,
                "bot_id": "heartbeat_bot",
            }))
            await asyncio.wait_for(ws.recv(), timeout=5)  # waitlist sync

            # Send heartbeat
            await ws.send(json.dumps({
                "type": "heartbeat",
                "bot_id": "heartbeat_bot",
            }))

            # Should receive ack
            response = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(response)
            assert data["type"] == "heartbeat_ack"
    except (ConnectionRefusedError, OSError):
        pytest.skip("Backend not running")
