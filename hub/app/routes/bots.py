"""Bot routes — manage Windows Engine instances."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import verify_api_key
from app.db import get_session
from app.models.bot import Bot
from app.schemas.schemas import BotCookieUpdate, BotResponse

router = APIRouter(prefix="/bots", tags=["bots"], dependencies=[Depends(verify_api_key)])


@router.get("", response_model=list[BotResponse])
async def list_bots(session: AsyncSession = Depends(get_session)) -> list[BotResponse]:
    result = await session.execute(select(Bot))
    bots = list(result.scalars().all())
    return [BotResponse.model_validate(b) for b in bots]


@router.get("/{bot_id}", response_model=BotResponse)
async def get_bot(
    bot_id: str, session: AsyncSession = Depends(get_session)
) -> BotResponse:
    result = await session.execute(select(Bot).where(Bot.bot_id == bot_id))
    bot = result.scalar_one_or_none()
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    return BotResponse.model_validate(bot)


@router.patch("/{bot_id}/cookie", response_model=BotResponse)
async def update_bot_cookie(
    bot_id: str,
    data: BotCookieUpdate,
    session: AsyncSession = Depends(get_session),
) -> BotResponse:
    result = await session.execute(select(Bot).where(Bot.bot_id == bot_id))
    bot = result.scalar_one_or_none()
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    bot.roblox_cookie = data.roblox_cookie
    await session.commit()
    await session.refresh(bot)
    return BotResponse.model_validate(bot)


@router.patch("/{bot_id}/heartbeat")
async def bot_heartbeat(
    bot_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    result = await session.execute(select(Bot).where(Bot.bot_id == bot_id))
    bot = result.scalar_one_or_none()
    if bot is None:
        bot = Bot(bot_id=bot_id)
        session.add(bot)
    bot.last_seen = datetime.now(timezone.utc)
    await session.commit()
    return {"status": "ok"}
