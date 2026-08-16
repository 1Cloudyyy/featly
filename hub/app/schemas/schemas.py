"""Pydantic schemas for API request/response validation."""

from datetime import datetime

from pydantic import BaseModel

from app.models.order import OrderStatus
from app.models.pending_trade import PendingTradeStatus


# --- Order ---

class OrderCreate(BaseModel):
    funpay_order_id: str
    buyer_nickname: str
    buyer_user_id: int
    items: list[str]


class OrderStatusUpdate(BaseModel):
    status: OrderStatus
    proof_url: str | None = None


class OrderNicknameUpdate(BaseModel):
    buyer_nickname: str


class OrderResponse(BaseModel):
    id: int
    funpay_order_id: str
    buyer_nickname: str
    buyer_user_id: int
    items: list[str]
    status: OrderStatus
    proof_url: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


# --- PendingTrade ---

class PendingTradeCreate(BaseModel):
    order_id: int
    bot_id: str
    buyer_nickname: str
    buyer_user_id: int
    items: list[str]


class PendingTradeResponse(BaseModel):
    id: int
    order_id: int
    bot_id: str
    buyer_nickname: str
    buyer_user_id: int
    items: list[str]
    status: PendingTradeStatus
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Inventory ---

class InventoryCreate(BaseModel):
    item_key: str
    name: str
    count: int = 0
    low_stock_threshold: int = 3


class InventoryUpdate(BaseModel):
    count: int | None = None
    low_stock_threshold: int | None = None


class InventoryResponse(BaseModel):
    id: int
    item_key: str
    name: str
    count: int
    low_stock_threshold: int
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Bot ---

class BotCookieUpdate(BaseModel):
    roblox_cookie: str


class BotResponse(BaseModel):
    bot_id: str
    status: str
    ws_connected: bool
    last_seen: datetime | None

    model_config = {"from_attributes": True}


# --- Stats ---

class StatsResponse(BaseModel):
    total_orders: int
    completed: int
    completed_today: int
    cancelled: int
    waitlist_count: int
    inventory_count: int
    online_bots: int
    total_bots: int
