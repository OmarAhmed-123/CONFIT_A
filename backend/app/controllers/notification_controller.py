"""In-app notification API — authenticated, strictly per-recipient, polling.

Serverless-safe: clients poll ``GET /notifications/unread-count`` on an
interval and fetch the list when the bell is opened. There is no WebSocket/SSE
(Vercel serverless cannot hold one) and, deliberately, no client-facing
"create" endpoint — notifications are produced server-side by event sources.
Every route is owner-scoped through the authenticated user; a caller can only
ever read or acknowledge their own notifications.
"""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user
from backend.app.core.rate_limit import limiter
from backend.app.models.notification import Notification
from backend.app.models.user import User
from backend.app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])


class NotificationOut(BaseModel):
    id: int
    type: str
    title: str
    body: str
    link: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    read: bool
    created_at: datetime


class NotificationListOut(BaseModel):
    items: List[NotificationOut]
    unread_count: int
    #: Pass back as ``before_id`` to fetch the next (older) page; null when the
    #: returned page is the last one.
    next_before_id: Optional[int] = None


class UnreadCountOut(BaseModel):
    unread_count: int


class MarkAllReadOut(BaseModel):
    updated: int


def _to_out(row: Notification) -> NotificationOut:
    data = None
    if row.data_json:
        try:
            data = json.loads(row.data_json)
        except (TypeError, ValueError):
            data = None
    return NotificationOut(
        id=row.id,
        type=row.type,
        title=row.title,
        body=row.body or "",
        link=row.link,
        data=data,
        read=row.read_at is not None,
        created_at=row.created_at,
    )


@router.get("", response_model=NotificationListOut)
@router.get("/", response_model=NotificationListOut)
def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    before_id: Optional[int] = Query(None, ge=1),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The caller's own notifications, newest first (keyset-paginated)."""
    service = NotificationService(db)
    rows = service.list_for_user(
        user.id, unread_only=unread_only, limit=limit, before_id=before_id
    )
    next_before_id = rows[-1].id if len(rows) == limit else None
    return NotificationListOut(
        items=[_to_out(r) for r in rows],
        unread_count=service.unread_count(user.id),
        next_before_id=next_before_id,
    )


@router.get("/unread-count", response_model=UnreadCountOut)
def unread_count(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lightweight poll target for the notification bell badge."""
    return UnreadCountOut(unread_count=NotificationService(db).unread_count(user.id))


@router.post("/{notification_id}/read", response_model=NotificationOut)
@limiter.limit("120/minute")
def mark_notification_read(
    request: Request,
    notification_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Acknowledge one notification. 404 if it is not the caller's own
    (no existence leakage); idempotent on an already-read row."""
    row = NotificationService(db).mark_read(user.id, notification_id)
    return _to_out(row)


@router.post("/read-all", response_model=MarkAllReadOut, status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")
def mark_all_notifications_read(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Acknowledge every unread notification the caller owns."""
    return MarkAllReadOut(updated=NotificationService(db).mark_all_read(user.id))
