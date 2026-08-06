"""Order routes — REST API for orders."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import verify_api_key
from app.db import get_session
from app.models.order import OrderStatus
from app.schemas.schemas import (
    OrderCreate,
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
    deleted = await delete_pending_trade(session, trade_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Pending trade not found")
