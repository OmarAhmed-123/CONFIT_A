"""Time helpers shared by the query layer.

``to_naive_utc`` exists because the ORM writes aware UTC timestamps while SQLite
persists them without an offset: comparing an aware bound against that column
matches nothing on the dev/test backend and works on PostgreSQL, which is the
worst kind of bug — a filter that silently returns zero rows in one environment
only. Normalising at the boundary makes the same predicate correct on both.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


def to_naive_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Convert an aware datetime to naive UTC; pass naive values through."""
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def days_ago_utc(days: int) -> datetime:
    return to_naive_utc(datetime.now(timezone.utc) - timedelta(days=days))  # type: ignore[return-value]


class TimeRangeError(ValueError):
    """Raised for a time window the API must reject rather than silently widen."""


@dataclass(frozen=True)
class TimeRange:
    """A resolved ``[date_from, date_to]`` window in naive UTC.

    G-15: admin analytics accepted no time dimension at all, so every figure
    was lifetime-only and the dashboard could not answer "this month". A query
    parameter that is accepted and then ignored is worse than no parameter, so
    the window is resolved once here and pushed into every aggregate's SQL
    predicate — never applied in Python after the rows are loaded.

    Bounds are half-open because that is what makes adjacent ranges tile
    without double counting a row whose timestamp lands exactly on a boundary.
    ``date_to`` is therefore *exclusive*; a caller passing a calendar day gets
    that day only if it passes the following midnight.
    """

    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    source: str = "all_time"

    @classmethod
    def resolve(
        cls,
        days: Optional[int] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> "TimeRange":
        """Build a window from the API's parameters, validating as it goes.

        ``days`` and an explicit range are mutually exclusive — accepting both
        would leave the reader unable to tell which one produced the numbers.
        """
        if days is not None and (date_from is not None or date_to is not None):
            raise TimeRangeError("pass either 'days' or 'date_from'/'date_to', not both")
        if days is not None:
            if days < 1:
                raise TimeRangeError("'days' must be >= 1")
            return cls(date_from=days_ago_utc(days), date_to=None, source=f"last_{days}_days")

        lo, hi = to_naive_utc(date_from), to_naive_utc(date_to)
        if lo is None and hi is None:
            return cls(source="all_time")
        if lo is not None and hi is not None and hi < lo:
            raise TimeRangeError("'date_to' must not be before 'date_from'")
        return cls(date_from=lo, date_to=hi, source="explicit")

    @property
    def is_all_time(self) -> bool:
        return self.date_from is None and self.date_to is None

    def bound(self, column) -> List[Any]:
        """SQL predicates that restrict ``column`` to this window."""
        clauses = []
        if self.date_from is not None:
            clauses.append(column >= self.date_from)
        if self.date_to is not None:
            clauses.append(column <= self.date_to)
        return clauses

    def describe(self) -> Dict[str, Any]:
        """The window as reported in the payload, so a reader can audit it."""
        return {
            "source": self.source,
            "date_from": self.date_from.isoformat() if self.date_from else None,
            "date_to": self.date_to.isoformat() if self.date_to else None,
            "date_to_inclusive": True,
            "is_all_time": self.is_all_time,
        }
