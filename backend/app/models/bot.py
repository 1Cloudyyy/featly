"""Bot model — Windows Engine instances."""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class BotStatus(str, enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"


class Bot(Base):
    __tablename__ = "bots"

    bot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    roblox_cookie: Mapped[str] = mapped_column(String(2048), default="")
    status: Mapped[BotStatus] = mapped_column(
        Enum(BotStatus), default=BotStatus.OFFLINE
    )
    ws_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
