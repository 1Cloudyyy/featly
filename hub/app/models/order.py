"""Order model — main trade order."""

import enum
from datetime import datetime

from sqlalchemy import Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.types import TZDateTime


class OrderStatus(str, enum.Enum):
    NEW = "new"
    DIALOG = "dialog"
    WAITING_TRADE = "waiting_trade"
    DELIVERING = "delivering"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    funpay_order_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    buyer_nickname: Mapped[str] = mapped_column(String(128))
    buyer_user_id: Mapped[int] = mapped_column(Integer)
    items: Mapped[str] = mapped_column(String(512))  # JSON array as string
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus), default=OrderStatus.NEW, index=True
    )
    proof_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        TZDateTime(timezone=True), nullable=True
    )
