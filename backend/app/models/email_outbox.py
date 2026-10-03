"""Email outbox — the delivery state contract for templated mail (spec 15).

One row per EMAIL EVENT (not per attempt). ``event_key`` is the caller's
idempotency key ("order:1042:confirmation") and is UNIQUE: wiring the same
business event twice — a replayed webhook, a retried worker — can never
email the user twice. The status column is the spec's state contract:

    pending      row created, send not yet attempted/completed
    sent         the relay accepted the message (message_id recorded)
    failed       transport failed after retries; last_error holds the
                 relay's words — honest, never silently dropped
    bounced      the provider later reported a bounce (webhook-fed)
    unsubscribed the recipient opted out of this category before send;
                 the message was NOT sent and never will be

The table stores recipient + template + locale + outcome only — never the
rendered body and never any credential.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text

from backend.app.core.database import Base


EMAIL_STATUSES = ("pending", "sent", "failed", "bounced", "unsubscribed")


class EmailOutbox(Base):
    __tablename__ = "email_outbox"

    id = Column(Integer, primary_key=True, index=True)
    # Caller-supplied idempotency key, e.g. "order:1042:order_confirmation".
    event_key = Column(String(255), nullable=False, unique=True, index=True)
    template = Column(String(64), nullable=False)
    locale = Column(String(8), nullable=False, default="en")
    recipient = Column(String(320), nullable=False)
    status = Column(String(16), nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    message_id = Column(String(255), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
