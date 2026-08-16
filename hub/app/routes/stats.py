"""Stats routes — сводные счётчики для Telegram-панели."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import verify_api_key
from app.db import get_session
from app.models.bot import Bot
from app.models.inventory import InventoryItem
from app.models.order import Order, OrderStatus
from app.models.pending_trade import PendingTrade
from app.schemas.schemas import StatsResponse

router = APIRouter(prefix="/stats", tags=["stats"], dependencies=[Depends(verify_api_key)])


@router.get("", response_model=StatsResponse)
async def get_stats(session: AsyncSession = Depends(get_session)) -> StatsResponse:
    total_orders = (await session.execute(select(func.count(Order.id)))).scalar_one()
    completed = (
        await session.execute(
            select(func.count(Order.id)).where(Order.status == OrderStatus.COMPLETED)
        )
    ).scalar_one()
    cancelled = (
        await session.execute(
            select(func.count(Order.id)).where(
                Order.status.in_([OrderStatus.CANCELLED, OrderStatus.REFUNDED])
            )
        )
    ).scalar_one()

    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    completed_today = (
        await session.execute(
            select(func.count(Order.id)).where(
                Order.status == OrderStatus.COMPLETED,
                Order.completed_at >= today_start,
            )
        )
    ).scalar_one()

    waitlist_count = (await session.execute(select(func.count(PendingTrade.id)))).scalar_one()
    inventory_count = (await session.execute(select(func.count(InventoryItem.id)))).scalar_one()
    online_bots = (
        await session.execute(
            select(func.count(Bot.bot_id)).where(Bot.ws_connected.is_(True))
        )
    ).scalar_one()
    total_bots = (await session.execute(select(func.count(Bot.bot_id)))).scalar_one()

    return StatsResponse(
        total_orders=total_orders,
        completed=completed,
        completed_today=completed_today,
        cancelled=cancelled,
        waitlist_count=waitlist_count,
        inventory_count=inventory_count,
        online_bots=online_bots,
        total_bots=total_bots,
    )