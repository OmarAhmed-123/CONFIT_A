"""In-app notification service — serverless-safe, strictly per-recipient.

Notifications are PERSISTED and read via a polling REST API; there is no
WebSocket/SSE because CONFIT runs on Vercel serverless. Creation is
server-side only (event producers call :meth:`NotificationService.create`);
there is no client-facing create path, so one account cannot push
notifications into another.

Every read/mutate method is scoped by ``recipient_user_id`` and fails closed:
a caller can only ever see or acknowledge their own notifications.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.app.core.exceptions import ResourceNotFoundError, ValidationDomainError
from backend.app.models.notification import Notification

#: Coarse event types the product currently emits. Not an access control —
#: purely a UI grouping hint. An unknown type is clamped to "system" rather
#: than rejected, so a new producer never 500s on an unseen label.
KNOWN_TYPES = {
    "system",
    "order_status",
    "catalog_import",
    "new_product",
    "promotion",
    "return_update",
}

_TITLE_MAX = 200
_BODY_MAX = 4000
_LINK_MAX = 500
_DEFAULT_PAGE = 20
_MAX_PAGE = 100


class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    # ----------------------------------------------------------------- create
    def create(
        self,
        recipient_user_id: int,
        type: str,
        title: str,
        body: str = "",
        link: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        *,
        commit: bool = True,
    ) -> Notification:
        """Create ONE notification for ONE recipient (server-side only).

        Validates and clamps input so a producer can never persist an empty
        title or an unbounded payload. ``link`` must be an in-app relative
        route ("/orders/123") — an absolute/off-site URL is rejected so the
        client never deep-links somewhere unexpected.
        """
        if not recipient_user_id:
            raise ValidationDomainError("notification requires a recipient_user_id")
        clean_title = (title or "").strip()
        if not clean_title:
            raise ValidationDomainError("notification requires a non-empty title")
        ntype = type if type in KNOWN_TYPES else "system"
        if link is not None:
            link = link.strip()
            if link and not link.startswith("/"):
                raise ValidationDomainError(
                    "notification link must be an in-app relative route starting with '/'"
                )
            link = link[:_LINK_MAX] or None
        data_json = None
        if data is not None:
            try:
                data_json = json.dumps(data, ensure_ascii=False, default=str)
            except (TypeError, ValueError) as exc:
                raise ValidationDomainError(f"notification data is not JSON-serialisable: {exc}")

        row = Notification(
            recipient_user_id=recipient_user_id,
            type=ntype,
            title=clean_title[:_TITLE_MAX],
            body=(body or "")[:_BODY_MAX],
            link=link,
            data_json=data_json,
            read_at=None,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(row)
        if commit:
            self.db.commit()
            self.db.refresh(row)
        else:
            self.db.flush()
        return row

    # ------------------------------------------------------------------- reads
    def list_for_user(
        self,
        user_id: int,
        *,
        unread_only: bool = False,
        limit: int = _DEFAULT_PAGE,
        before_id: Optional[int] = None,
    ) -> List[Notification]:
        """Most-recent-first page of the caller's OWN notifications.

        Keyset pagination by id (``before_id``) — stable under concurrent
        inserts, unlike offset paging.
        """
        limit = max(1, min(int(limit or _DEFAULT_PAGE), _MAX_PAGE))
        q = self.db.query(Notification).filter(
            Notification.recipient_user_id == user_id
        )
        if unread_only:
            q = q.filter(Notification.read_at.is_(None))
        if before_id:
            q = q.filter(Notification.id < before_id)
        return q.order_by(Notification.id.desc()).limit(limit).all()

    def unread_count(self, user_id: int) -> int:
        """Number of the caller's OWN unread notifications (the poll target)."""
        return (
            self.db.query(Notification)
            .filter(
                Notification.recipient_user_id == user_id,
                Notification.read_at.is_(None),
            )
            .count()
        )

    # ----------------------------------------------------------------- mutate
    def mark_read(self, user_id: int, notification_id: int) -> Notification:
        """Acknowledge ONE notification the caller owns.

        Fail-closed: the filter requires BOTH the id AND the recipient, so a
        notification that belongs to someone else (or does not exist) raises
        ResourceNotFoundError — the controller returns 404, leaking nothing
        about another user's notifications. Idempotent: re-marking a read row
        is a no-op success.
        """
        row = (
            self.db.query(Notification)
            .filter(
                Notification.id == notification_id,
                Notification.recipient_user_id == user_id,
            )
            .first()
        )
        if row is None:
            raise ResourceNotFoundError("Notification", str(notification_id))
        if row.read_at is None:
            row.read_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(row)
        return row

    def mark_all_read(self, user_id: int) -> int:
        """Acknowledge every unread notification the caller owns. Returns the
        number updated."""
        now = datetime.now(timezone.utc)
        updated = (
            self.db.query(Notification)
            .filter(
                Notification.recipient_user_id == user_id,
                Notification.read_at.is_(None),
            )
            .update({"read_at": now}, synchronize_session=False)
        )
        self.db.commit()
        return int(updated or 0)
