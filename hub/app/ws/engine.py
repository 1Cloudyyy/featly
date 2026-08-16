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
from app.models.order import Order, OrderStatus
from app.models.pending_trade import PendingTrade, PendingTradeStatus
from app.services.inventory_service import decrement_item

router = APIRouter()

# Connected engines: bot_id -> WebSocket
connections: dict[str, WebSocket] = {}

# Queued messages for offline engines: bot_id -> asyncio.Queue
message_queue: dict[str, asyncio.Queue] = {}


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
    """Send a message to an engine, queueing it if the engine is offline.

    Queued messages are delivered on the next connection. Returns True if the
    message was sent directly, False if it was queued.
    """
    ws = connections.get(bot_id)
    if ws is None:
        q = message_queue.setdefault(bot_id, asyncio.Queue(maxsize=100))
        try:
            q.put_nowait(message)
            logger.info(f"Engine {bot_id} offline — queued message: {message.get('type')}")
        except asyncio.QueueFull:
            logger.warning(f"Message queue full for {bot_id}, dropping: {message.get('type')}")
        return False
    try:
        await ws.send_json(message)
        return True
    except Exception:
        connections.pop(bot_id, None)
        return False


async def _flush_queued_messages(bot_id: str, ws: WebSocket) -> None:
    """Deliver any messages that were queued while the engine was offline."""
    q = message_queue.pop(bot_id, None)
    if q is None or q.empty():
        return
    delivered = 0
    while not q.empty():
        try:
            msg = q.get_nowait()
        except asyncio.QueueEmpty:
            break
        try:
            await ws.send_json(msg)
            delivered += 1
        except Exception:
            break
    if delivered:
        logger.info(f"Flushed {delivered} queued messages to {bot_id}")


async def queue_pending_trade(trade: PendingTrade, action: str) -> None:
    """Notify an engine about a pending trade change (WAIT_FOR_TRADE/REMOVE_WAITLIST).
    `action` is 'add' or 'remove'. Queues the message if the engine is offline.
    """
    if action == "add":
        message = {
            "type": "WAIT_FOR_TRADE",
            "order_id": trade.order_id,
            "buyer_nickname": trade.buyer_nickname,
            "buyer_user_id": trade.buyer_user_id,
            "items": json.loads(trade.items),
        }
    else:
        message = {
            "type": "REMOVE_WAITLIST",
            "buyer": trade.buyer_nickname,
        }
    await send_to_engine(trade.bot_id, message)


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
                await websocket.send_json({"type": "ping"})
            except Exception:
                break

    keepalive_task = asyncio.create_task(_keepalive())

    # Deliver messages queued while the engine was offline
    await _flush_queued_messages(bot_id, websocket)

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
        # Only pop if this is still the active connection for bot_id
        if connections.get(bot_id) is websocket:
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

        if not success:
            # Failed delivery: keep order + pending_trade so the engine retries.
            # Do not mark CANCELLED while the buyer stays in the waitlist,
            # otherwise the engine would deliver items for a cancelled order.
            logger.warning(f"Trade failed for order {order_id} — keeping for retry")
            return

        logger.info(f"Trade completed: order={order_id}")

        async with async_session() as session:
            result = await session.execute(select(Order).where(Order.id == order_id))
            order = result.scalar_one_or_none()
            if order:
                # Only accept a valid transition (e.g. DELIVERING → COMPLETED)
                valid = {
                    OrderStatus.WAITING_TRADE,
                    OrderStatus.DELIVERING,
                    OrderStatus.DIALOG,
                }
                if order.status in valid:
                    order.status = OrderStatus.COMPLETED
                    order.completed_at = datetime.now(timezone.utc)
                    if proof_path:
                        order.proof_url = proof_path
                    # Decrement inventory for each delivered item
                    try:
                        items: list[str] = json.loads(order.items or "[]")
                    except json.JSONDecodeError:
                        items = []
                    for item in items:
                        item_key = str(item).strip().lower().replace(" ", "_")
                        if item_key:
                            await decrement_item(session, item_key)
                    await session.commit()
                else:
                    logger.warning(
                        f"Ignoring trade_completed for order {order_id}: "
                        f"current status {order.status}"
                    )

            # Remove from pending_trades (success path)
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
