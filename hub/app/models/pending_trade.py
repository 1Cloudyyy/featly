"""PendingTrade model — persistent waitlist for Windows Engine."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PendingTradeStatus(str, enum.Enum):
    WAITING = "waiting"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PendingTrade(Base):
    __tablename__ = "pending_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id"), index=True)
    bot_id: Mapped[str] = mapped_column(String(64), index=True)
    buyer_nickname: Mapped[str] = mapped_column(String(128))
    buyer_user_id: Mapped[int] = mapped_column(Integer)
    items: Mapped[str] = mapped_column(String(512))
    status: Mapped[PendingTradeStatus] = mapped_column(
        Enum(PendingTradeStatus), default=PendingTradeStatus.WAITING, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_pending_trades_bot_status", "bot_id", "status"),
    )
