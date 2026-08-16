"""Inventory service — stock management."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import InventoryItem


async def get_inventory(session: AsyncSession) -> list[InventoryItem]:
    result = await session.execute(select(InventoryItem))
    return list(result.scalars().all())


async def get_item(session: AsyncSession, item_key: str) -> InventoryItem | None:
    result = await session.execute(
        select(InventoryItem).where(InventoryItem.item_key == item_key)
    )
    return result.scalar_one_or_none()


async def update_item(
    session: AsyncSession,
    item_key: str,
    count: int | None = None,
    low_stock_threshold: int | None = None,
) -> InventoryItem | None:
    result = await session.execute(
        select(InventoryItem).where(InventoryItem.item_key == item_key)
    )
    item = result.scalar_one_or_none()
    if item is None:
        return None
    if count is not None:
        item.count = count
    if low_stock_threshold is not None:
        item.low_stock_threshold = low_stock_threshold
    await session.commit()
    await session.refresh(item)
    return item


async def decrement_item(session: AsyncSession, item_key: str) -> InventoryItem | None:
    result = await session.execute(
        select(InventoryItem).where(InventoryItem.item_key == item_key)
    )
    item = result.scalar_one_or_none()
    if item is None or item.count <= 0:
        return None
    item.count -= 1
    await session.commit()
    await session.refresh(item)
    return item


async def create_item(
    session: AsyncSession,
    item_key: str,
    name: str,
    count: int = 0,
    low_stock_threshold: int = 3,
) -> InventoryItem:
    item = InventoryItem(
        item_key=item_key,
        name=name,
        count=count,
        low_stock_threshold=low_stock_threshold,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item
