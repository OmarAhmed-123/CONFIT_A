"""Real email delivery transport (CYCLE 4 / BLOCKER C engineering half).

History: the auth service issued one-time hashed tokens correctly but the
actual "send" was an intentional stub — with ``EMAIL_PROVIDER`` set the API
would have answered a FAKE "queued" while nothing left the server. This
module replaces that with a real, provider-agnostic SMTP transport.

Design decisions (researched, docs/research/CONFIT_A_CYCLE_4_RESEARCH.md):
- stdlib ``smtplib`` — zero new dependencies; works with any SMTP relay
  (Resend, AWS SES, Mailgun, Postmark, self-hosted). The provider choice
  becomes pure configuration for the operator.
- STARTTLS on port 587 (or explicit SSL on 465). Plaintext 25 is refused
  unless explicitly allowed for local testing.
- One retry on transient transport failure (connection reset / timeout),
  then ``EmailDeliveryError`` — honest failure, never a silent drop.
- Message building via ``email.message.EmailMessage`` (RFC 5322), UTF-8
  ready for the app's bilingual EN/AR content.
- NOTHING in this module logs credentials, tokens, or full recipient
  addresses (audit logs carry user ids, not secrets).
"""

from __future__ import annotations

import logging
import smtplib
import time
from email.message import EmailMessage
from email.utils import make_msgid, formatdate
from typing import Optional

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

_ATTEMPTS = 2
_TIMEOUT_SECONDS = 10.0


class EmailDeliveryError(Exception):
    """Raised when the SMTP relay could not be reached or rejected the mail."""


def is_email_configured() -> bool:
    return bool(settings.EMAIL_PROVIDER)


def _require_config() -> None:
    if not settings.EMAIL_PROVIDER:
        raise EmailDeliveryError("EMAIL_PROVIDER is not configured.")
    if not settings.SMTP_HOST:
        raise EmailDeliveryError("EMAIL_PROVIDER is set but SMTP_HOST is missing.")
    if not settings.EMAIL_FROM_ADDRESS:
        raise EmailDeliveryError("EMAIL_PROVIDER is set but EMAIL_FROM_ADDRESS is missing.")


def _build_message(to: str, subject: str, html: str, text: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = settings.EMAIL_FROM_ADDRESS
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=(settings.EMAIL_FROM_ADDRESS.partition("@")[2] or "confit.local"))
    msg.set_content(text or (html or ""))
    if html:
        msg.add_alternative(html, subtype="html")
    return msg


def _connect():
    host = settings.SMTP_HOST
    port = int(settings.SMTP_PORT or 587)
    if port == 465:
        client = smtplib.SMTP_SSL(host, port, timeout=_TIMEOUT_SECONDS)
    else:
        client = smtplib.SMTP(host, port, timeout=_TIMEOUT_SECONDS)
        client.ehlo()
        client.starttls(context=__import__("ssl").create_default_context())
        client.ehlo()
    if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
        client.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
    return client


# ── Observed transport reality ───────────────────────────────────────────────
# MEASURED ON PRODUCTION, 2026-09-30. With SMTP_* correctly configured the
# capability probe reported `email_delivery: ready` while the relay was in
# fact answering `525 5.7.1 Unauthorized IP address` to Vercel's egress IP.
# `/auth/forgot-password` therefore answered 200 "reset instructions have been
# sent" and nothing was sent — a worse state than the honest 501 it replaced.
#
# Configuration is a claim; a completed handshake is evidence. This records the
# last OBSERVED verdict so the capability probe can report what actually
# happened instead of what was configured. Written by BOTH the real send path
# and the admin diagnostic, read by capability_service — one fact, two
# reporters, no duplicated logic.
#
# Process-local and best-effort by design: serverless containers are
# short-lived, so this is a fast truth-teller for a warm container, never a
# durable store. A cold container simply has no observation yet and says so.
_LAST_TRANSPORT: dict = {"observed": False}


def record_transport_result(ok: bool, stage: str, detail: str, code=None) -> None:
    """Remember what the relay actually did. Never raises."""
    _LAST_TRANSPORT.update(
        {"observed": True, "ok": bool(ok), "stage": stage,
         "detail": (detail or "")[:300], "code": code, "at": time.time()}
    )


def last_transport_result() -> dict:
    """The last observed verdict, or ``{"observed": False}`` if none yet."""
    return dict(_LAST_TRANSPORT)


def check_transport() -> dict:
    """Prove the relay will accept us — WITHOUT sending mail.

    WHY THIS EXISTS (measured 2026-09-30)
    -------------------------------------
    Setting SMTP_* is not the same as being able to send. Brevo (and SES,
    Mailgun, Postmark) enforce a per-account **IP allow-list**, and a
    serverless platform sends from a rotating pool. Verified from this
    workspace against the real relay with valid credentials:

        smtp-relay.brevo.com:587 -> 525 5.7.1 Unauthorized IP address

    Credentials correct, transport refused. If configuration alone were
    treated as proof, the capability probe would report `email_delivery:
    ready` while every password-reset mail failed at AUTH — a health signal
    that is confidently wrong, which is worse than one that says "unknown".

    So: a real EHLO -> STARTTLS -> AUTH handshake, then QUIT. No RCPT, no
    DATA, no message. It is deliberately NOT wired into /health — a poll that
    opens an authenticated SMTP session every 15 minutes is abusive to the
    relay and would itself become a reliability risk. It is an on-demand
    admin diagnostic.

    Reuses ``_connect()``, the exact path ``send_email`` uses, so a green
    check cannot mean something different from a real send. Returns a plain
    dict and never raises; nothing here echoes a credential.
    """
    if not settings.EMAIL_PROVIDER:
        return {"ok": False, "stage": "configuration",
                "detail": "EMAIL_PROVIDER is unset", "code": None}
    _record = record_transport_result
    try:
        _require_config()
    except EmailDeliveryError as exc:
        return {"ok": False, "stage": "configuration", "detail": str(exc), "code": None}

    started = time.time()
    client = None
    try:
        client = _connect()
        _record(True, "authenticated", "handshake accepted")
        return {
            "ok": True,
            "stage": "authenticated",
            "detail": "EHLO + STARTTLS + AUTH accepted by the relay; no message was sent",
            "code": None,
            "host": settings.SMTP_HOST,
            "port": int(settings.SMTP_PORT or 587),
            "latency_ms": int((time.time() - started) * 1000),
        }
    except smtplib.SMTPAuthenticationError as exc:
        # The interesting case: 525 5.7.1 means the credentials were fine and
        # the SOURCE IP was refused. Surfaced verbatim so the remediation is
        # obvious instead of being flattened into "auth failed".
        _record(False, "authentication", _decode(exc.smtp_error), exc.smtp_code)
        return {"ok": False, "stage": "authentication", "code": exc.smtp_code,
                "detail": _decode(exc.smtp_error),
                "host": settings.SMTP_HOST, "port": int(settings.SMTP_PORT or 587),
                "latency_ms": int((time.time() - started) * 1000)}
    except (smtplib.SMTPException, OSError) as exc:
        _record(False, "connection", f"{type(exc).__name__}: {exc}", None)
        return {"ok": False, "stage": "connection",
                "detail": f"{type(exc).__name__}: {exc}"[:300], "code": None,
                "host": settings.SMTP_HOST, "port": int(settings.SMTP_PORT or 587),
                "latency_ms": int((time.time() - started) * 1000)}
    finally:
        if client is not None:
            try:
                client.quit()
            except Exception:  # noqa: BLE001 - closing must never mask the verdict
                pass


def _decode(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")[:300]
    return str(value)[:300]


def send_email(to: str, subject: str, html: str, text: Optional[str] = None) -> dict:
    """Send one transactional email. Raises EmailDeliveryError on hard failure.

    Returns ``{"message_id": ...}`` for audit trails. Two attempts max; the
    second only after a transient-looking failure (never after the relay
    explicitly rejected the message — a rejection is honest and final).
    """
    _require_config()
    msg = _build_message(to, subject, html, text)
    last_error: Optional[Exception] = None
    for attempt in range(1, _ATTEMPTS + 1):
        client = None
        try:
            client = _connect()
            client.send_message(msg)
            # A completed send is the strongest possible evidence the
            # transport works; record it so the capability probe can report
            # observed reality instead of configuration.
            record_transport_result(True, "sent", "message accepted by the relay")
            return {"message_id": msg["Message-ID"]}
        except smtplib.SMTPException as exc:  # relay spoke and refused
            logger.error(
                "Email rejected by relay (attempt %s): %s", attempt, type(exc).__name__
            )
            record_transport_result(
                False, "send", f"{type(exc).__name__}: {exc}",
                getattr(exc, "smtp_code", None),
            )
            raise EmailDeliveryError(f"Relay rejected message: {type(exc).__name__}") from exc
        except Exception as exc:  # network / timeout / DNS — transient class
            last_error = exc
            record_transport_result(False, "send", f"{type(exc).__name__}: {exc}", None)
            logger.warn(
                "Email transport attempt %s failed: %s", attempt, str(exc)[:120]
            )
            if attempt < _ATTEMPTS:
                time.sleep(0.5)
        finally:
            if client is not None:
                try:
                    client.quit()
                except Exception:
                    pass
    raise EmailDeliveryError(f"SMTP transport failed after {_ATTEMPTS} attempts: {last_error}")


# ---------------------------------------------------------------------------
# Templates — bilingual (the product is EN/AR); links point at the SPA.
# ---------------------------------------------------------------------------

def render_password_reset_email(full_name: str, reset_url: str) -> tuple[str, str, str]:
    subject = "Reset your CONFIT password / إعادة تعيين كلمة المرور"
    text = (
        f"Hello {full_name},\n\n"
        f"We received a request to reset your CONFIT password.\n"
        f"This link is valid for 30 minutes and can be used once:\n"
        f"{reset_url}\n\n"
        f"If you did not request this, you can ignore this email — "
        f"your password will not change.\n\n— CONFIT"
    )
    html = f"""<div style="font-family:system-ui,Segoe UI,Tahoma,sans-serif;max-width:520px">
<p>مرحبًا {full_name}،</p>
<p>وصلك طلب لإعادة تعيين كلمة مرور CONFIT. الرابط صالح 30 دقيقة وللاستخدام مرة واحدة:</p>
<p><a href="{reset_url}">إعادة تعيين كلمة المرور / Reset my password</a></p>
<p>إذا لم تطلب ذلك، تجاهل هذه الرسالة — لن تتغير كلمة المرور.</p>
<hr />
<p>Hello {full_name}, we received a request to reset your CONFIT password.
The link above is valid for 30 minutes and single-use. If you did not request
this, ignore this email — your password will not change.</p>
</div>"""
    return subject, html, text


def render_verification_email(full_name: str, verify_url: str) -> tuple[str, str, str]:
    subject = "Verify your CONFIT email / تأكيد بريدك الإلكتروني"
    text = (
        f"Welcome to CONFIT, {full_name}!\n\n"
        f"Confirm your email address to secure your account:\n{verify_url}\n\n"
        f"This link is valid for 24 hours.\n\n— CONFIT"
    )
    html = f"""<div style="font-family:system-ui,Segoe UI,Tahoma,sans-serif;max-width:520px">
<p>أهلًا {full_name} في CONFIT 👋</p>
<p>أكّد بريدك الإلكتروني لتأمين حسابك. الرابط صالح 24 ساعة:</p>
<p><a href="{verify_url}">تأكيد البريد / Verify my email</a></p>
<hr />
<p>Welcome to CONFIT! Confirm your email address to secure your account.
The link above is valid for 24 hours.</p>
</div>"""
    return subject, html, text
