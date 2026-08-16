"""TradeLog model — delivery audit trail."""

from datetime import datetime

from sqlalchemy import Boolean, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.types import TZDateTime


class TradeLog(Base):
    __tablename__ = "trade_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(Integer, index=True)
    buyer: Mapped[str] = mapped_column(String(128))
    items: Mapped[str] = mapped_column(String(512))
    success: Mapped[bool] = mapped_column(Boolean)
    proof_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime(timezone=True), server_default=func.now()
    )
