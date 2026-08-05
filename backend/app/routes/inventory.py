"""Inventory routes — REST API for stock management."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.schemas import InventoryResponse, InventoryUpdate
from app.services.inventory_service import (
    get_inventory,
    get_item,
    update_item,
)

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("", response_model=list[InventoryResponse])
async def list_inventory(
    session: AsyncSession = Depends(get_session),
) -> list[InventoryResponse]:
    items = await get_inventory(session)
    return [InventoryResponse.model_validate(i) for i in items]


@router.get("/{item_key}", response_model=InventoryResponse)
async def get_single_item(
    item_key: str, session: AsyncSession = Depends(get_session)
) -> InventoryResponse:
    item = await get_item(session, item_key)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return InventoryResponse.model_validate(item)


@router.patch("/{item_key}", response_model=InventoryResponse)
async def update_single_item(
    item_key: str,
    data: InventoryUpdate,
    session: AsyncSession = Depends(get_session),
) -> InventoryResponse:
    item = await update_item(
        session, item_key, count=data.count, low_stock_threshold=data.low_stock_threshold
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return InventoryResponse.model_validate(item)
