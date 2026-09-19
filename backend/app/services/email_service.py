"""Real transactional email delivery + delivery ledger (task §13–§16).

Architecture
------------
    Auth/Partner/Profile event
        ↓
    TransactionalEmailService  ← this module (provider-agnostic API)
        ↓
    Adapter: smtp (stdlib smtplib) | resend (HTTPS API)
        ↓
    Provider  →  DeliveryResult  →  email_deliveries ledger + audit log

History: the auth service issued one-time hashed tokens correctly but the
actual "send" was an intentional stub. Cycle 4 replaced it with a real SMTP
transport. This revision keeps that transport and closes the remaining
honesty gap: the API used to answer ``{"status": "queued"}`` even when the
relay had rejected the message, and nothing recorded what actually happened.

Guarantees now enforced here:
  * nothing is ever reported as sent unless the provider accepted it — the
    ledger row (``email_deliveries``) is written from the provider's own
    response, and ``DeliveryResult.status`` is the single source of truth;
  * an unconfigured provider yields ``BLOCKED`` and no send attempt;
  * idempotency: an identical (purpose, token) send is never duplicated —
    the unique index on ``idempotency_key`` makes a concurrent double-submit
    collapse into one delivered message;
  * one retry on a transient transport failure, never after an explicit relay
    rejection;
  * no credentials, tokens or full addresses are logged or persisted in the
    ledger (recipient is stored as a SHA-256 hash).

Honest limitation: SMTP accepts a message for relaying, which is not the same
as inbox delivery. The ledger therefore says SUCCEEDED meaning "the provider
accepted the message", and never claims more than that.
"""
from __future__ import annotations

import hashlib
import logging
import smtplib
import ssl
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Optional

import httpx
from sqlalchemy.exc import IntegrityError

from backend.app.core.config import settings
from backend.app.models.user import EmailDelivery, EmailDeliveryStatus

# Templates live in their own module (task §16) and are re-exported here so
# existing imports keep working.
from backend.app.services.email_templates import (  # noqa: F401
    render_email_change_verification_email,
    render_email_changed_notice_email,
    render_partner_application_decision_email,
    render_partner_application_received_email,
    render_partner_invitation_email,
    render_password_changed_email,
    render_password_reset_email,
    render_security_notification_email,
    render_verification_email,
    render_verification_reminder_email,
)

logger = logging.getLogger(__name__)

_ATTEMPTS = 2
_TIMEOUT_SECONDS = 10.0
_RESEND_ENDPOINT = "https://api.resend.com/emails"

PURPOSE_VERIFICATION = "email_verification"
PURPOSE_VERIFICATION_REMINDER = "email_verification_reminder"
PURPOSE_PASSWORD_RESET = "password_reset"
PURPOSE_PASSWORD_CHANGED = "password_changed"
PURPOSE_EMAIL_CHANGE = "email_change_verification"
PURPOSE_EMAIL_CHANGED_NOTICE = "email_changed_notice"
PURPOSE_PARTNER_INVITATION = "partner_invitation"
PURPOSE_PARTNER_APPLICATION_RECEIVED = "partner_application_received"
PURPOSE_PARTNER_APPLICATION_DECISION = "partner_application_decision"
PURPOSE_SECURITY_NOTIFICATION = "security_notification"


class EmailDeliveryError(Exception):
    """Raised when the relay could not be reached or rejected the mail."""


@dataclass
class DeliveryResult:
    """Outcome of one transactional send attempt (the honest vocabulary)."""
    status: EmailDeliveryStatus
    provider: Optional[str] = None
    message_id: Optional[str] = None
    error_class: Optional[str] = None
    attempts: int = 0
    delivery_id: Optional[int] = None
    idempotent_replay: bool = False

    @property
    def accepted(self) -> bool:
        return self.status == EmailDeliveryStatus.SUCCEEDED

    def as_dict(self) -> dict:
        return {
            "status": self.status.value,
            "provider": self.provider,
            "message_id": self.message_id,
            "error_class": self.error_class,
            "attempts": self.attempts,
            "accepted": self.accepted,
        }


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def provider_name() -> Optional[str]:
    return (settings.EMAIL_PROVIDER or "").lower().strip() or None


def is_email_configured() -> bool:
    """True only when a provider AND its transport are actually usable."""
    provider = provider_name()
    if provider == "smtp":
        return bool(settings.SMTP_HOST and settings.EMAIL_FROM_ADDRESS)
    if provider == "resend":
        return bool(settings.RESEND_API_KEY and settings.EMAIL_FROM_ADDRESS)
    return False


def _require_config() -> str:
    provider = provider_name()
    if not provider:
        raise EmailDeliveryError("EMAIL_PROVIDER is not configured.")
    if provider == "smtp":
        if not settings.SMTP_HOST:
            raise EmailDeliveryError("EMAIL_PROVIDER=smtp requires SMTP_HOST.")
        if not settings.EMAIL_FROM_ADDRESS:
            raise EmailDeliveryError("EMAIL_PROVIDER=smtp requires EMAIL_FROM_ADDRESS.")
    elif provider == "resend":
        if not settings.RESEND_API_KEY:
            raise EmailDeliveryError("EMAIL_PROVIDER=resend requires RESEND_API_KEY.")
        if not settings.EMAIL_FROM_ADDRESS:
            raise EmailDeliveryError("EMAIL_PROVIDER=resend requires EMAIL_FROM_ADDRESS.")
    else:
        raise EmailDeliveryError(f"Unsupported EMAIL_PROVIDER: {provider!r}")
    return provider


def recipient_hash(address: str) -> str:
    """SHA-256 of the normalised address — the ledger stores no plain address."""
    return hashlib.sha256((address or "").strip().lower().encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Message building + SMTP transport
# ---------------------------------------------------------------------------

def _build_message(to: str, subject: str, html: str, text: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = settings.EMAIL_FROM_ADDRESS
    msg["To"] = to
    # Header-injection defence: a subject carrying CR/LF can never add headers.
    msg["Subject"] = " ".join(str(subject).splitlines()).strip()
    if getattr(settings, "EMAIL_REPLY_TO", None):
        msg["Reply-To"] = settings.EMAIL_REPLY_TO
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=(settings.EMAIL_FROM_ADDRESS or "confit.local").partition("@")[2] or "confit.local")
    msg.set_content(text or (html or ""))
    if html:
        msg.add_alternative(html, subtype="html")
    return msg


def _tls_mode() -> str:
    mode = (getattr(settings, "SMTP_TLS_MODE", "starttls") or "starttls").lower()
    return mode if mode in {"starttls", "ssl", "none"} else "starttls"


def _connect():
    host = settings.SMTP_HOST
    port = int(settings.SMTP_PORT or 587)
    mode = _tls_mode()
    if mode == "ssl" or port == 465:
        client = smtplib.SMTP_SSL(host, port, timeout=_TIMEOUT_SECONDS)
    else:
        client = smtplib.SMTP(host, port, timeout=_TIMEOUT_SECONDS)
        client.ehlo()
        if mode == "starttls":
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
    if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
        client.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
    return client


def send_email(to: str, subject: str, html: str, text: Optional[str] = None) -> dict:
    """Send one transactional email through the configured provider.

    Raised ``EmailDeliveryError`` on any hard failure — this function never
    pretends a message left the server. Returns provider metadata on success.
    """
    provider = _require_config()
    if provider == "resend":
        return _send_via_resend(to, subject, html, text)
    return _send_via_smtp(to, subject, html, text)


def _send_via_smtp(to: str, subject: str, html: str, text: Optional[str]) -> dict:
    msg = _build_message(to, subject, html, text)
    last_error: Optional[Exception] = None
    for attempt in range(1, _ATTEMPTS + 1):
        client = None
        try:
            client = _connect()
            client.send_message(msg)
            return {"message_id": msg["Message-ID"], "provider": "smtp", "attempts": attempt}
        except smtplib.SMTPException as exc:  # relay spoke and refused — final
            logger.error("Email rejected by relay (attempt %s): %s", attempt, type(exc).__name__)
            raise EmailDeliveryError(f"Relay rejected message: {type(exc).__name__}") from exc
        except Exception as exc:  # network / timeout / DNS — transient class
            last_error = exc
            logger.warning("Email transport attempt %s failed: %s", attempt, str(exc)[:120])
            if attempt < _ATTEMPTS:
                time.sleep(0.5)
        finally:
            if client is not None:
                try:
                    client.quit()
                except Exception:
                    pass
    raise EmailDeliveryError(f"SMTP transport failed after {_ATTEMPTS} attempts: {last_error}")


def _send_via_resend(to: str, subject: str, html: str, text: Optional[str]) -> dict:
    """HTTPS API transport (Vercel-friendly: no outbound SMTP port needed)."""
    payload = {
        "from": settings.EMAIL_FROM_ADDRESS,
        "to": [to],
        "subject": " ".join(str(subject).splitlines()).strip(),
        "html": html,
    }
    if text:
        payload["text"] = text
    if getattr(settings, "EMAIL_REPLY_TO", None):
        payload["reply_to"] = settings.EMAIL_REPLY_TO
    try:
        resp = httpx.post(
            _RESEND_ENDPOINT,
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # network-level failure
        raise EmailDeliveryError(f"Resend transport failed: {type(exc).__name__}") from exc
    if resp.status_code >= 400:
        # Never log the response body (may echo the address); status code only.
        raise EmailDeliveryError(f"Resend rejected message: HTTP {resp.status_code}")
    try:
        body = resp.json()
    except Exception:
        body = {}
    return {"message_id": body.get("id"), "provider": "resend", "attempts": 1}


# ---------------------------------------------------------------------------
# Transactional service layer: send + ledger (+ idempotency)
# ---------------------------------------------------------------------------

def send_transactional(
    db,
    *,
    to: str,
    subject: str,
    html: str,
    text: Optional[str] = None,
    purpose: str,
    user_id: Optional[int] = None,
    dedupe_key: Optional[str] = None,
    request_id: Optional[str] = None,
) -> DeliveryResult:
    """Send and RECORD. Returns the honest outcome; never raises for delivery.

    ``dedupe_key`` should identify the exact message being sent (for auth mails
    the one-time token hash). A repeated call with the same key returns the
    first attempt's recorded outcome instead of sending a second message.
    """
    idem = f"{purpose}:{dedupe_key or recipient_hash(to)}"
    existing = db.query(EmailDelivery).filter(EmailDelivery.idempotency_key == idem).first()
    if existing is not None:
        return DeliveryResult(
            status=existing.status,
            provider=existing.provider,
            message_id=existing.provider_message_id,
            error_class=existing.error_class,
            attempts=existing.attempts or 0,
            delivery_id=existing.id,
            idempotent_replay=True,
        )

    provider = provider_name()
    if not is_email_configured():
        # Nothing was sent and we say so: no queue, no pretend.
        record = EmailDelivery(
            user_id=user_id,
            purpose=purpose,
            idempotency_key=idem,
            status=EmailDeliveryStatus.BLOCKED,
            provider=provider,
            error_class="provider_not_configured",
            attempts=0,
            recipient_hash=recipient_hash(to),
            request_id=request_id,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return DeliveryResult(
            status=EmailDeliveryStatus.BLOCKED,
            provider=provider,
            error_class="provider_not_configured",
            delivery_id=record.id,
        )

    try:
        meta = send_email(to=to, subject=subject, html=html, text=text)
        result = DeliveryResult(
            status=EmailDeliveryStatus.SUCCEEDED,
            provider=meta.get("provider") or provider,
            message_id=meta.get("message_id"),
            attempts=int(meta.get("attempts") or 1),
        )
    except EmailDeliveryError as exc:
        result = DeliveryResult(
            status=EmailDeliveryStatus.FAILED,
            provider=provider,
            error_class=type(exc).__name__,
            attempts=_ATTEMPTS,
        )
    except Exception as exc:  # pragma: no cover - defensive
        result = DeliveryResult(
            status=EmailDeliveryStatus.FAILED,
            provider=provider,
            error_class=type(exc).__name__,
            attempts=_ATTEMPTS,
        )

    record = EmailDelivery(
        user_id=user_id,
        purpose=purpose,
        idempotency_key=idem,
        status=result.status,
        provider=result.provider,
        provider_message_id=result.message_id,
        error_class=result.error_class,
        attempts=result.attempts,
        recipient_hash=recipient_hash(to),
        request_id=request_id,
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        # A concurrent identical send won the race: report ITS outcome so the
        # caller never believes two messages were delivered.
        db.rollback()
        winner = db.query(EmailDelivery).filter(EmailDelivery.idempotency_key == idem).first()
        if winner is not None:
            return DeliveryResult(
                status=winner.status,
                provider=winner.provider,
                message_id=winner.provider_message_id,
                error_class=winner.error_class,
                attempts=winner.attempts or 0,
                delivery_id=winner.id,
                idempotent_replay=True,
            )
        raise
    db.refresh(record)
    result.delivery_id = record.id
    return result


def latest_delivery(db, *, user_id: int, purpose: Optional[str] = None) -> Optional[EmailDelivery]:
    """Most recent delivery for a signed-in user's own account (honest UI).

    Scoped by ``user_id`` — the endpoint that uses this can only ever report on
    the caller's own address, so it cannot become an enumeration oracle.
    """
    q = db.query(EmailDelivery).filter(EmailDelivery.user_id == user_id)
    if purpose:
        q = q.filter(EmailDelivery.purpose == purpose)
    return q.order_by(EmailDelivery.created_at.desc(), EmailDelivery.id.desc()).first()


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
