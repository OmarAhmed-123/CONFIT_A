"""Idempotent dispatch for templated email (spec 15 §6.5).

``dispatch()`` is the ONLY way templated mail should leave the platform:

    event ──> outbox row (unique event_key) ──> render ──> transport
                   │                                          │
                   └── already sent? return as-is ────────────┘

Guarantees:
* IDEMPOTENT: one event_key, at most one accepted send — a webhook replay
  or a retried job returns the existing row instead of re-sending.
* HONEST: a transport failure is recorded as status=failed with the relay's
  own words. Nothing pretends to be sent. Retrying a FAILED event with the
  same key IS allowed — failure is the one state a retry may leave.
* CONSENT: the caller resolves opt-out BEFORE dispatch and passes
  ``suppressed=True`` → the row is recorded as 'unsubscribed' and nothing
  is rendered or sent. (There is no user-level preference store in the
  schema today — documented gap; the hook is here so wiring it is a
  one-line change at each call site.)

The provider transport (``email_service.send_email``) keeps its own
two-attempt transient retry; this layer never duplicates that.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from backend.app.models.email_outbox import EmailOutbox
from backend.app.services.email_service import EmailDeliveryError, send_email
from backend.app.services.email_templates import (
    EmailTemplateError,
    render_email,
)

logger = logging.getLogger(__name__)


def dispatch(
    db: Session,
    *,
    event_key: str,
    template: str,
    locale: str,
    recipient: str,
    payload: dict,
    suppressed: bool = False,
) -> EmailOutbox:
    """Render + send one templated email, exactly once per event_key."""
    if not event_key or len(event_key) > 255:
        raise EmailTemplateError("event_key must be a non-empty string (<=255 chars).")

    row = (
        db.query(EmailOutbox).filter(EmailOutbox.event_key == event_key).first()
    )
    if row is not None and row.status in ("sent", "unsubscribed", "bounced"):
        # Terminal states: replaying the event must not send again.
        return row

    if row is None:
        row = EmailOutbox(
            event_key=event_key, template=template, locale=locale,
            recipient=recipient, status="pending",
        )
        db.add(row)
        db.flush()

    if suppressed:
        # Recipient opted out of this category — recorded, never sent.
        row.status = "unsubscribed"
        db.commit()
        return row

    # Render BEFORE touching the transport: a bad payload must fail loudly
    # here and never consume a send attempt.
    content = render_email(template, locale, payload)

    row.attempts = (row.attempts or 0) + 1
    try:
        result = send_email(recipient, content.subject, content.html, content.text)
        row.status = "sent"
        row.message_id = result.get("message_id")
        row.last_error = None
    except EmailDeliveryError as exc:
        row.status = "failed"
        row.last_error = str(exc)[:500]
        logger.error("Outbox send failed for event %s: %s", event_key, str(exc)[:120])
    db.commit()
    return row


def record_bounce(db: Session, *, event_key: str, detail: str = "") -> EmailOutbox | None:
    """Provider webhook hook: mark a previously sent message as bounced."""
    row = db.query(EmailOutbox).filter(EmailOutbox.event_key == event_key).first()
    if row is None:
        return None
    row.status = "bounced"
    if detail:
        row.last_error = detail[:500]
    db.commit()
    return row
