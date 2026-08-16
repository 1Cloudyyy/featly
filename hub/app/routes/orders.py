"""Order routes — REST API for orders."""

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import verify_api_key
from app.db import get_session
from app.models.order import Order, OrderStatus
from app.models.pending_trade import PendingTrade
from app.schemas.schemas import (
    OrderCreate,
    OrderNicknameUpdate,
    OrderResponse,
    OrderStatusUpdate,
    PendingTradeCreate,
    PendingTradeResponse,
)
from app.services.order_service import (
    create_order,
    create_pending_trade,
    delete_pending_trade,
    get_order,
    get_pending_trades_by_bot,
    list_active_orders,
    update_order_status,
)
from app.ws.engine import notify_remove_waitlist, send_to_engine

router = APIRouter(prefix="/orders", tags=["orders"], dependencies=[Depends(verify_api_key)])


@router.post("", response_model=OrderResponse, status_code=201)
async def create_new_order(
    data: OrderCreate, session: AsyncSession = Depends(get_session)
) -> OrderResponse:
    order = await create_order(
        session,
        funpay_order_id=data.funpay_order_id,
        buyer_nickname=data.buyer_nickname,
        buyer_user_id=data.buyer_user_id,
        items=data.items,
    )
    return OrderResponse.model_validate(order)


@router.get("", response_model=list[OrderResponse])
async def list_orders(
    status: OrderStatus | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[OrderResponse]:
    if status:
        from sqlalchemy import select

        from app.models.order import Order

        result = await session.execute(select(Order).where(Order.status == status))
        orders = list(result.scalars().all())
    else:
        orders = await list_active_orders(session)
    return [OrderResponse.model_validate(o) for o in orders]


@router.get("/{order_id}", response_model=OrderResponse)
async def get_single_order(
    order_id: int, session: AsyncSession = Depends(get_session)
) -> OrderResponse:
    order = await get_order(session, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return OrderResponse.model_validate(order)


@router.patch("/{order_id}/status", response_model=OrderResponse)
async def update_order(
    order_id: int,
    data: OrderStatusUpdate,
    session: AsyncSession = Depends(get_session),
) -> OrderResponse:
    order = await update_order_status(
        session, order_id, status=data.status, proof_url=data.proof_url
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return OrderResponse.model_validate(order)


@router.patch("/{order_id}/nickname", response_model=OrderResponse)
async def update_order_nickname(
    order_id: int,
    data: OrderNicknameUpdate,
    session: AsyncSession = Depends(get_session),
) -> OrderResponse:
    """Смена ника покупателя (!смена): обновляет заказ и waitlist — движок подхватит при пулле."""
    nick = data.buyer_nickname.strip()
    if not nick:
        raise HTTPException(status_code=422, detail="buyer_nickname пуст")

    order = await get_order(session, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status in (OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.REFUNDED):
        raise HTTPException(status_code=409, detail=f"Заказ в терминальном статусе {order.status.value}")

    old_nick = order.buyer_nickname
    order.buyer_nickname = nick
    result = await session.execute(
        select(PendingTrade).where(PendingTrade.order_id == order_id)
    )
    for trade in result.scalars().all():
        trade.buyer_nickname = nick
    await session.commit()
    await session.refresh(order)
    logger.info(f"Nickname updated: order {order_id}: {old_nick} → {nick}")
    return OrderResponse.model_validate(order)


@router.post("/{order_id}/force")
async def force_trade(
    order_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    """Принудительная выдача: уведомить движок, чтобы пересканировал и выдал заказ."""
    result = await session.execute(
        select(PendingTrade).where(PendingTrade.order_id == order_id)
    )
    trade = result.scalar_one_or_none()
    if trade is None:
        raise HTTPException(status_code=404, detail="Заказ не в waitlist — выдача невозможна")

    delivered = await send_to_engine(
        trade.bot_id, {"type": "FORCE_TRADE", "order_id": order_id}
    )
    logger.info(f"Force trade order {order_id}: delivered={delivered}")
    return {"ok": delivered, "delivered": delivered}


@router.post("/{order_id}/cancel", response_model=OrderResponse)
async def cancel_order(
    order_id: int, session: AsyncSession = Depends(get_session)
) -> OrderResponse:
    """Отменить заказ: статус CANCELLED, удаление из waitlist и уведомление движка."""
    order = await get_order(session, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status in (OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.REFUNDED):
        raise HTTPException(status_code=409, detail=f"Заказ уже в статусе {order.status.value}")

    order.status = OrderStatus.CANCELLED
    await session.commit()
    await session.refresh(order)
    logger.warning(f"Order {order_id} отменён через панель")

    # Убираем из waitlist и уведомляем движок (быстрый сигнал; poll — основной канал)
    result = await session.execute(
        select(PendingTrade).where(PendingTrade.order_id == order_id)
    )
    for trade in result.scalars().all():
        await notify_remove_waitlist(trade.bot_id, trade.buyer_nickname)
        await session.delete(trade)
    await session.commit()
    logger.info(f"Order {order_id}: pending trades удалены, движок уведомлён")

    return OrderResponse.model_validate(order)


# --- Pending Trades ---

pending_router = APIRouter(prefix="/pending_trades", tags=["pending_trades"], dependencies=[Depends(verify_api_key)])


@pending_router.get("", response_model=list[PendingTradeResponse])
async def list_pending_trades(
    bot_id: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[PendingTradeResponse]:
    if bot_id:
        trades = await get_pending_trades_by_bot(session, bot_id)
    else:
        from sqlalchemy import select

        from app.models.pending_trade import PendingTrade

        result = await session.execute(select(PendingTrade))
        trades = list(result.scalars().all())
    return [PendingTradeResponse.model_validate(t) for t in trades]


@pending_router.post("", response_model=PendingTradeResponse, status_code=201)
async def create_new_pending_trade(
    data: PendingTradeCreate, session: AsyncSession = Depends(get_session)
) -> PendingTradeResponse:
    trade = await create_pending_trade(
        session,
        order_id=data.order_id,
        bot_id=data.bot_id,
        buyer_nickname=data.buyer_nickname,
        buyer_user_id=data.buyer_user_id,
        items=data.items,
    )
    return PendingTradeResponse.model_validate(trade)


@pending_router.delete("/{trade_id}", status_code=204)
async def delete_existing_pending_trade(
    trade_id: int, session: AsyncSession = Depends(get_session)
) -> None:
    result = await session.execute(
        select(PendingTrade).where(PendingTrade.id == trade_id)
    )
    trade = result.scalar_one_or_none()
    if trade is None:
        raise HTTPException(status_code=404, detail="Pending trade not found")

    deleted = await delete_pending_trade(session, trade_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Pending trade not found")
    # Быстрый сигнал движку: убрать покупателя из локального waitlist
    await notify_remove_waitlist(trade.bot_id, trade.buyer_nickname)
