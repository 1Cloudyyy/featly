"""WebSocket server — communication with Windows Engine."""

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
from sqlalchemy import select

from app.config import settings
from app.db import async_session
from app.models.bot import Bot, BotStatus
from app.models.pending_trade import PendingTrade, PendingTradeStatus

router = APIRouter()

# Connected engines: bot_id -> WebSocket
connections: dict[str, WebSocket] = {}


async def _update_bot_status(bot_id: str, connected: bool) -> None:
    async with async_session() as session:
        result = await session.execute(select(Bot).where(Bot.bot_id == bot_id))
        bot = result.scalar_one_or_none()
        if bot is None:
            bot = Bot(bot_id=bot_id)
            session.add(bot)
        bot.ws_connected = connected
        bot.status = BotStatus.ONLINE if connected else BotStatus.OFFLINE
        bot.last_seen = datetime.now(timezone.utc)
        await session.commit()


async def _get_waitlist(bot_id: str) -> list[dict]:
    async with async_session() as session:
        result = await session.execute(
            select(PendingTrade).where(
                PendingTrade.bot_id == bot_id,
                PendingTrade.status == PendingTradeStatus.WAITING,
            )
        )
        trades = result.scalars().all()
        return [
            {
                "order_id": t.order_id,
                "buyer_nickname": t.buyer_nickname,
                "buyer_user_id": t.buyer_user_id,
                "items": json.loads(t.items),
            }
            for t in trades
        ]


async def send_to_engine(bot_id: str, message: dict) -> bool:
    ws = connections.get(bot_id)
    if ws is None:
        return False
    try:
        await ws.send_json(message)
        return True
    except Exception:
        return False


@router.websocket("/ws/engine")
async def engine_websocket(websocket: WebSocket) -> None:
    await websocket.accept()

    # Auth
    try:
        auth_msg = await asyncio.wait_for(websocket.receive_json(), timeout=10)
    except (asyncio.TimeoutError, Exception):
        await websocket.close(code=4001, reason="Auth timeout")
        return

    if auth_msg.get("secret") != settings.ws_secret:
        await websocket.close(code=4003, reason="Invalid secret")
        return

    bot_id = auth_msg.get("bot_id", "bot_main")
    connections[bot_id] = websocket
    await _update_bot_status(bot_id, True)
    logger.info(f"Engine connected: {bot_id}")

    # Send waitlist
    waitlist = await _get_waitlist(bot_id)
    await websocket.send_json({"type": "waitlist_sync", "waitlist": waitlist})

    # Message loop with keepalive
    async def _keepalive():
        while True:
            await asyncio.sleep(20)
            try:
                await ws.send_json({"type": "ping"})
            except Exception:
                break

    keepalive_task = asyncio.create_task(_keepalive())

    # Message loop
    try:
        while True:
            data = await asyncio.wait_for(websocket.receive_json(), timeout=60)
            await _handle_engine_message(bot_id, data)
    except asyncio.TimeoutError:
        logger.warning(f"Engine timeout: {bot_id}")
    except WebSocketDisconnect:
        logger.info(f"Engine disconnected: {bot_id}")
    except Exception as e:
        logger.error(f"Engine error {bot_id}: {e}")
    finally:
        keepalive_task.cancel()
        connections.pop(bot_id, None)
        await _update_bot_status(bot_id, False)


async def _handle_engine_message(bot_id: str, data: dict) -> None:
    msg_type = data.get("type")

    if msg_type == "heartbeat":
        async with async_session() as session:
            result = await session.execute(select(Bot).where(Bot.bot_id == bot_id))
            bot = result.scalar_one_or_none()
            if bot:
                bot.last_seen = datetime.now(timezone.utc)
                await session.commit()
        await send_to_engine(bot_id, {"type": "heartbeat_ack"})

    elif msg_type == "request_waitlist":
        waitlist = await _get_waitlist(bot_id)
        await send_to_engine(bot_id, {"type": "waitlist_sync", "waitlist": waitlist})

    elif msg_type == "trade_completed":
        order_id = data.get("order_id")
        success = data.get("success", True)
        proof_path = data.get("proof_path")
        logger.info(f"Trade completed: order={order_id}, success={success}")

        async with async_session() as session:
            from app.models.order import Order, OrderStatus

            result = await session.execute(select(Order).where(Order.id == order_id))
            order = result.scalar_one_or_none()
            if order:
                order.status = OrderStatus.COMPLETED if success else OrderStatus.CANCELLED
                order.completed_at = datetime.now(timezone.utc)
                if proof_path:
                    order.proof_url = proof_path
                await session.commit()

            # Remove from pending_trades
            result = await session.execute(
                select(PendingTrade).where(
                    PendingTrade.order_id == order_id,
                    PendingTrade.bot_id == bot_id,
                )
            )
            trade = result.scalar_one_or_none()
            if trade:
                await session.delete(trade)
                await session.commit()

    elif msg_type == "trade_failed":
        order_id = data.get("order_id")
        error = data.get("error", "unknown")
        logger.error(f"Trade failed: order={order_id}, error={error}")

    else:
        logger.warning(f"Unknown message type from {bot_id}: {msg_type}")
