"""Time helpers shared by the query layer.

``to_naive_utc`` exists because the ORM writes aware UTC timestamps while SQLite
persists them without an offset: comparing an aware bound against that column
matches nothing on the dev/test backend and works on PostgreSQL, which is the
worst kind of bug — a filter that silently returns zero rows in one environment
only. Normalising at the boundary makes the same predicate correct on both.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional


def to_naive_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Convert an aware datetime to naive UTC; pass naive values through."""
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def days_ago_utc(days: int) -> datetime:
    return to_naive_utc(datetime.now(timezone.utc) - timedelta(days=days))  # type: ignore[return-value]
