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
* CONSENT: resolved HERE, not by every caller. Pass ``user_id`` and the
  template's category is checked against the user's EmailPreference row:
  an opted-out category records status='unsubscribed' and nothing is
  rendered or sent. For engagement/marketing the signed unsubscribe link
  is minted and injected into the payload automatically, and the send
  carries List-Unsubscribe + List-Unsubscribe-Post (RFC 8058) headers.
  ``suppressed=True`` remains for callers that resolved consent at a
  different boundary (e.g. guest recipients with no user row).

The provider transport (``email_service.send_email``) keeps its own
two-attempt transient retry; this layer never duplicates that.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from backend.app.models.email_outbox import EmailOutbox
from backend.app.services.email_consent import (
    is_allowed,
    unsubscribe_url_for,
)
from backend.app.services.email_service import EmailDeliveryError, send_email
from backend.app.services.email_templates import (
    TEMPLATES,
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
    user_id: int | None = None,
) -> EmailOutbox:
    """Render + send one templated email, exactly once per event_key."""
    if not event_key or len(event_key) > 255:
        raise EmailTemplateError("event_key must be a non-empty string (<=255 chars).")

    spec = TEMPLATES.get(template)
    category = spec.category if spec else "transactional"

    # Consent gate (spec 15 §8): resolved against the preference store when
    # the recipient is a known user. Transactional mail is always allowed.
    if user_id is not None and not is_allowed(db, user_id, category):
        suppressed = True

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

    # Engagement/marketing to a known user: mint the signed, expiring
    # unsubscribe link the templates demand — footers and headers point at
    # the SAME mechanism the account screen shows.
    if user_id is not None and category in ("engagement", "marketing"):
        payload = {**payload, "unsubscribe_url": unsubscribe_url_for(user_id, category)}

    # Render BEFORE touching the transport: a bad payload must fail loudly
    # here and never consume a send attempt.
    content = render_email(template, locale, payload)

    headers: dict[str, str] | None = None
    if content.list_unsubscribe:
        headers = {
            "List-Unsubscribe": content.list_unsubscribe,
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }

    row.attempts = (row.attempts or 0) + 1
    try:
        result = send_email(
            recipient, content.subject, content.html, content.text, headers=headers
        )
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
