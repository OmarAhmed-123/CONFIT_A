"""Data access for the platform audit trail (G-05).

Kept as a repository so the controller stays thin and the same query builder is
reused by the trail, the facets and the stats endpoints (DRY). Everything here
is a real ``SELECT`` against ``audit_logs`` — no sampling, no synthesis.

Actor enrichment is done as **one** additional query for the whole page, not one
per row: the N+1 pattern this replaces is documented in the gap register (G-14).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.app.models.user import AuditLog, User


def to_naive_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Normalise a filter bound to naive UTC.

    ``AuditLog.timestamp`` is written as an aware UTC datetime but SQLite
    persists it without an offset, so an aware bound compares against a naive
    column and silently matches nothing on the dev/test backend. Converting
    here keeps the same predicate correct on both SQLite and PostgreSQL.
    """
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


@dataclass
class AuditQuery:
    """Validated filter set for the audit trail."""

    action: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    actor_id: Optional[int] = None
    search: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    only_admin_actions: bool = False

    def as_public_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "actor_id": self.actor_id,
            "search": self.search,
            "date_from": to_naive_utc(self.date_from).isoformat() if self.date_from else None,
            "date_to": to_naive_utc(self.date_to).isoformat() if self.date_to else None,
            "only_admin_actions": self.only_admin_actions or None,
        }


class AuditRepository:
    def __init__(self, db: Session):
        self.db = db

    # --- query building -------------------------------------------------
    def _apply(self, query, q: AuditQuery):
        if q.action:
            query = query.filter(AuditLog.action == q.action)
        if q.resource_type:
            query = query.filter(AuditLog.resource_type == q.resource_type)
        if q.resource_id:
            query = query.filter(AuditLog.resource_id == str(q.resource_id))
        if q.actor_id is not None:
            query = query.filter(AuditLog.user_id == q.actor_id)
        if q.only_admin_actions:
            query = query.filter(AuditLog.action.like("ADMIN\\_%", escape="\\"))
        lower_from = to_naive_utc(q.date_from)
        lower_to = to_naive_utc(q.date_to)
        if lower_from:
            query = query.filter(AuditLog.timestamp >= lower_from)
        if lower_to:
            query = query.filter(AuditLog.timestamp <= lower_to)
        if q.search:
            like = f"%{q.search}%"
            query = query.filter(
                or_(
                    AuditLog.action.ilike(like),
                    AuditLog.resource_type.ilike(like),
                    AuditLog.resource_id.ilike(like),
                    AuditLog.details_json.ilike(like),
                )
            )
        return query

    # --- reads ----------------------------------------------------------
    def count(self, q: AuditQuery) -> int:
        return int(self._apply(self.db.query(func.count(AuditLog.id)), q).scalar() or 0)

    def page(self, q: AuditQuery, page: int, page_size: int) -> Tuple[List[AuditLog], int]:
        total = self.count(q)
        rows = (
            self._apply(self.db.query(AuditLog), q)
            .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return rows, total

    def recent(self, limit: int, window_days: Optional[int] = None) -> List[AuditLog]:
        query = self.db.query(AuditLog)
        if window_days:
            since = to_naive_utc(datetime.now(timezone.utc) - timedelta(days=window_days))
            query = query.filter(AuditLog.timestamp >= since)
        return query.order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).limit(limit).all()

    def facets(self, q: AuditQuery, limit: int = 25) -> Dict[str, Any]:
        base = self._apply(self.db.query(AuditLog), q)

        def grouped(column) -> List[Dict[str, Any]]:
            rows = (
                base.with_entities(column, func.count(AuditLog.id))
                .group_by(column)
                .order_by(func.count(AuditLog.id).desc())
                .limit(limit)
                .all()
            )
            return [{"value": str(value), "count": int(count)} for value, count in rows if value is not None]

        oldest = base.with_entities(func.min(AuditLog.timestamp)).scalar()
        newest = base.with_entities(func.max(AuditLog.timestamp)).scalar()
        return {
            "actions": grouped(AuditLog.action),
            "resource_types": grouped(AuditLog.resource_type),
            "oldest": oldest,
            "newest": newest,
        }

    def actors(self, q: AuditQuery, limit: int = 25) -> List[Dict[str, Any]]:
        """Actor rollup with an identity, joined once."""
        rows = (
            self._apply(
                self.db.query(AuditLog.user_id, func.count(AuditLog.id))
                .filter(AuditLog.user_id.isnot(None)),
                q,
            )
            .group_by(AuditLog.user_id)
            .order_by(func.count(AuditLog.id).desc())
            .limit(limit)
            .all()
        )
        out: List[Dict[str, Any]] = []
        identities = self.actor_identities([uid for uid, _ in rows])
        for uid, count in rows:
            ident = identities.get(uid, {})
            out.append(
                {
                    "value": ident.get("email") or f"user:{uid}",
                    "count": int(count),
                    "actor_id": uid,
                    "role": ident.get("role"),
                }
            )
        return out

    def by_day(self, q: AuditQuery, limit: int = 90) -> List[Dict[str, Any]]:
        day = func.date(AuditLog.timestamp).label("day")
        rows = (
            self._apply(self.db.query(day, func.count(AuditLog.id)), q)
            .group_by(day)
            .order_by(day.desc())
            .limit(limit)
            .all()
        )
        return [{"day": str(value), "count": int(count)} for value, count in rows]

    def actor_identities(self, user_ids: Sequence[Optional[int]]) -> Dict[int, Dict[str, Any]]:
        """One query for every actor on the page — replaces per-row lookups."""
        ids = sorted({int(uid) for uid in user_ids if uid is not None})
        if not ids:
            return {}
        rows = self.db.query(User.id, User.email, User.role).filter(User.id.in_(ids)).all()
        return {
            int(uid): {
                "email": email,
                "role": getattr(role, "value", role) if role is not None else None,
            }
            for uid, email, role in rows
        }

    def bounds(self, window_days: int) -> Tuple[int, int, int, int, int]:
        """Structural counters for the integrity self-check."""
        since = to_naive_utc(datetime.now(timezone.utc) - timedelta(days=window_days))
        scope = self.db.query(AuditLog).filter(AuditLog.timestamp >= since)
        checked = scope.count()
        with_before_after = (
            scope.filter(or_(AuditLog.before_json.isnot(None), AuditLog.after_json.isnot(None))).count()
        )
        with_request_id = scope.filter(AuditLog.request_id.isnot(None)).count()
        with_ip = scope.filter(AuditLog.ip_address.isnot(None)).count()
        distinct_actors = scope.filter(AuditLog.user_id.isnot(None)).with_entities(
            func.count(func.distinct(AuditLog.user_id))
        ).scalar() or 0
        return int(checked), int(with_before_after), int(with_request_id), int(with_ip), int(distinct_actors)

    def admin_action_count(self, window_days: int) -> int:
        since = to_naive_utc(datetime.now(timezone.utc) - timedelta(days=window_days))
        return int(
            self.db.query(func.count(AuditLog.id))
            .filter(AuditLog.timestamp >= since, AuditLog.action.like("ADMIN\\_%", escape="\\"))
            .scalar()
            or 0
        )
