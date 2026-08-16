"""Custom column types.

TZDateTime — время с таймзоной, работающее и на PostgreSQL (timestamptz),
и на SQLite (хранит naive UTC, при чтении возвращает aware UTC).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class TZDateTime(TypeDecorator):
    """DateTime, совместимый с SQLite (naive UTC) и PostgreSQL (timestamptz)."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect):
        if value is None:
            return None
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        if dialect.name == "sqlite":
            return value.replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect: Dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value