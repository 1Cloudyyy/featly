"""Settings routes — конфигурация hub из Telegram-панели (без рестарта)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import verify_api_key
from app.config import settings as app_settings
from app.db import get_session
from app.services.settings_service import (
    KNOWN_KEYS,
    get_settings_map,
    update_settings,
)

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Depends(verify_api_key)])


@router.get("", response_model=dict[str, Any])
async def list_hub_settings(session: AsyncSession = Depends(get_session)) -> dict:
    current = await get_settings_map(session)
    return {
        "known_keys": KNOWN_KEYS,
        "settings": current,
    }


@router.patch("", response_model=dict[str, Any])
async def patch_hub_settings(
    values: dict[str, str], session: AsyncSession = Depends(get_session)
) -> dict:
    current = await update_settings(session, values)
    logger.info("settings: PATCH %s", ", ".join(values.keys()))
    return {"settings": current}


@router.get("/secrets", response_model=dict[str, str])
async def hub_secrets() -> dict[str, str]:
    """Одноразовое показание секретов для настройки движка (доступ — api-key плагина)."""
    return {
        "ws_secret": app_settings.ws_secret,
        "api_key": app_settings.api_key,
    }