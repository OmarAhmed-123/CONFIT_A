from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship

from backend.app.core.database import Base


class Notification(Base):
    """A single in-app notification addressed to exactly ONE recipient user.

    Serverless-safe by design. CONFIT runs on Vercel serverless, which cannot
    hold a persistent WebSocket/SSE connection, so notifications are
    PERSISTED here and read through a polling REST API
    (``/notifications`` + ``/notifications/unread-count``). "Real-time" is
    therefore honest near-real-time (the client polls), never a faked socket.

    Strictly per-recipient: every read/mutate path filters by
    ``recipient_user_id``, so one user can never see or acknowledge another
    user's notifications. Notifications are created SERVER-SIDE only (by event
    producers such as order status changes or a completed catalogue import) —
    there is deliberately no client-facing "create" path, so the feature
    cannot be used to spam another account.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        # The hot query is "unread (and recent) for this recipient".
        Index("ix_notifications_recipient_read", "recipient_user_id", "read_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    recipient_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Coarse event type so the UI can group/icon without parsing the body,
    # e.g. "order_status", "catalog_import", "new_product", "system".
    type = Column(String(50), nullable=False, default="system")
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False, default="")
    # Optional IN-APP deep link, a relative route like "/orders/123". Never an
    # off-site absolute URL the client would open blindly.
    link = Column(String(500), nullable=True)
    # Optional structured payload (JSON string) for the client to render.
    data_json = Column(Text, nullable=True)
    # NULL = unread; set to the acknowledgement timestamp when read.
    read_at = Column(DateTime, nullable=True)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    recipient = relationship("User")
