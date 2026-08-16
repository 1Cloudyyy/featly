"""Order service — business logic for orders and pending trades."""

import json
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderStatus
from app.models.pending_trade import PendingTrade, PendingTradeStatus

# Valid status transitions for state machine
VALID_TRANSITIONS: dict[OrderStatus, list[OrderStatus]] = {
    OrderStatus.NEW: [OrderStatus.DIALOG, OrderStatus.CANCELLED],
    OrderStatus.DIALOG: [OrderStatus.WAITING_TRADE, OrderStatus.CANCELLED, OrderStatus.COMPLETED],
    OrderStatus.WAITING_TRADE: [OrderStatus.DELIVERING, OrderStatus.CANCELLED, OrderStatus.COMPLETED],
    OrderStatus.DELIVERING: [OrderStatus.COMPLETED, OrderStatus.CANCELLED],
    OrderStatus.COMPLETED: [],
    OrderStatus.CANCELLED: [],
    OrderStatus.REFUNDED: [],
}


def validate_transition(current: OrderStatus, new: OrderStatus) -> bool:
    """Единая проверка корректности перехода статусов заказа."""
    return new in VALID_TRANSITIONS.get(current, [])


async def create_order(
    session: AsyncSession,
    funpay_order_id: str,
    buyer_nickname: str,
    buyer_user_id: int,
    items: list[str],
) -> Order:
    # Check for duplicate
    existing = await get_order_by_funpay_id(session, funpay_order_id)
    if existing:
        logger.info(f"Order {funpay_order_id} already exists, returning existing")
        return existing

    order = Order(
        funpay_order_id=funpay_order_id,
        buyer_nickname=buyer_nickname,
        buyer_user_id=buyer_user_id,
        items=json.dumps(items),
        status=OrderStatus.NEW,
    )
    session.add(order)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await get_order_by_funpay_id(session, funpay_order_id)
        if existing:
            return existing
        raise
    await session.refresh(order)
    return order


async def update_order_status(
    session: AsyncSession,
    order_id: int,
    status: OrderStatus,
    proof_url: str | None = None,
) -> Order | None:
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if order is None:
        return None

    # State machine validation (единый переход)
    if not validate_transition(order.status, status):
        logger.warning(f"Invalid transition: {order.status} → {status} for order {order_id}")
        raise ValueError(f"Cannot transition from {order.status} to {status}")

    order.status = status
    if proof_url:
        order.proof_url = proof_url
    if status == OrderStatus.COMPLETED:
        order.completed_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(order)
    return order


async def get_order(session: AsyncSession, order_id: int) -> Order | None:
    result = await session.execute(select(Order).where(Order.id == order_id))
    return result.scalar_one_or_none()


async def get_order_by_funpay_id(
    session: AsyncSession, funpay_order_id: str
) -> Order | None:
    result = await session.execute(
        select(Order).where(Order.funpay_order_id == funpay_order_id)
    )
    return result.scalar_one_or_none()


async def list_active_orders(session: AsyncSession) -> list[Order]:
    result = await session.execute(
        select(Order).where(
            Order.status.in_(
                [OrderStatus.WAITING_TRADE, OrderStatus.DELIVERING, OrderStatus.DIALOG]
            )
        )
    )
    return list(result.scalars().all())


async def create_pending_trade(
    session: AsyncSession,
    order_id: int,
    bot_id: str,
    buyer_nickname: str,
    buyer_user_id: int,
    items: list[str],
) -> PendingTrade:
    trade = PendingTrade(
        order_id=order_id,
        bot_id=bot_id,
        buyer_nickname=buyer_nickname,
        buyer_user_id=buyer_user_id,
        items=json.dumps(items),
        status=PendingTradeStatus.WAITING,
    )
    session.add(trade)
    await session.commit()
    await session.refresh(trade)
    return trade


async def delete_pending_trade(session: AsyncSession, trade_id: int) -> bool:
    result = await session.execute(
        select(PendingTrade).where(PendingTrade.id == trade_id)
    )
    trade = result.scalar_one_or_none()
    if trade is None:
        return False
    await session.delete(trade)
    await session.commit()
    return True


async def get_pending_trades_by_bot(
    session: AsyncSession, bot_id: str
) -> list[PendingTrade]:
    result = await session.execute(
        select(PendingTrade).where(
            PendingTrade.bot_id == bot_id,
            PendingTrade.status == PendingTradeStatus.WAITING,
        )
    )
    return list(result.scalars().all())
