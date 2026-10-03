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

def render_platform_test_email(recipient_note: str = "") -> tuple[str, str, str]:
    """The operator-triggered deliverability proof.

    Deliberately NOT a marketing template: its job is to be evidence that the
    whole chain works — relay auth, sender acceptance, DKIM/SPF, HTML and
    plain-text parts, RTL Arabic rendering and inbox placement. So it states
    what it is, carries no tracking pixel and asks for nothing.

    Bilingual because the product is EN/AR and a template that renders only
    one of them is half-tested.
    """
    subject = "CONFIT — email delivery verified / تم التحقق من إرسال البريد"
    text = (
        "CONFIT — transactional email is live\n"
        "=====================================\n\n"
        f"{recipient_note}\n\n"
        "This message was sent by the CONFIT platform itself, from production,\n"
        "through its configured SMTP relay. It is the first transactional email\n"
        "the platform has successfully delivered.\n\n"
        "What this proves:\n"
        "  - the relay accepted our credentials and our sending IP\n"
        "  - the sender address was accepted\n"
        "  - HTML and plain-text alternatives both render\n"
        "  - Arabic (RTL) content survives transport\n\n"
        "What it unlocks: password reset, email verification and order\n"
        "notifications, all of which were previously refused with an honest\n"
        "HTTP 501 rather than pretending to send.\n\n"
        "-----------------------------------------------------------------\n"
        "CONFIT — تم تفعيل البريد\n\n"
        "تم إرسال هذه الرسالة من منصة CONFIT نفسها، من بيئة الإنتاج، عبر خادم\n"
        "البريد المهيّأ لها. هذه أول رسالة بريد تعاملية تنجح المنصة في تسليمها.\n\n"
        "ما تثبته: قبول بيانات الاعتماد وعنوان الإرسال، وسلامة المحتوى\n"
        "بالإنجليزية والعربية.\n\n"
        "وما تفتحه: إعادة تعيين كلمة المرور، وتأكيد البريد، وإشعارات الطلبات.\n\n"
        "-----------------------------------------------------------------\n"
        "This is an automated message. No action is required.\n"
        "رسالة آلية — لا يلزم اتخاذ أي إجراء.\n"
    )
    html = (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
        '<body style="margin:0;padding:0;background:#FDF8EE;'
        'font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#FDF8EE;padding:32px 16px;"><tr><td align="center">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:600px;background:#ffffff;border-radius:14px;overflow:hidden;'
        'border:1px solid #EADFC8;">'
        # header
        '<tr><td style="background:#1B1F3B;padding:28px 32px;">'
        '<div style="color:#C9A227;font-size:12px;letter-spacing:3px;'
        'text-transform:uppercase;font-weight:700;">CONFIT</div>'
        '<div style="color:#ffffff;font-size:21px;font-weight:600;margin-top:6px;">'
        'Transactional email is live</div>'
        '<div style="color:#B9BEd6;font-size:13px;margin-top:4px;">'
        'Where Style Meets Your Character in Every Moment</div>'
        '</td></tr>'
        # english body
        '<tr><td style="padding:30px 32px 8px 32px;color:#1B1F3B;">'
        f'<p style="margin:0 0 16px 0;font-size:15px;line-height:1.65;">{recipient_note}</p>'
        '<p style="margin:0 0 16px 0;font-size:15px;line-height:1.65;">'
        'This message was sent by the CONFIT platform itself, from '
        '<strong>production</strong>, through its configured SMTP relay. It is the '
        'first transactional email the platform has successfully delivered.</p>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#FDF8EE;border-left:3px solid #C9A227;border-radius:6px;'
        'margin:18px 0;"><tr><td style="padding:16px 18px;">'
        '<div style="font-size:12px;font-weight:700;letter-spacing:1.5px;'
        'text-transform:uppercase;color:#7A5C28;margin-bottom:10px;">What this proves</div>'
        '<div style="font-size:14px;line-height:1.9;color:#1B1F3B;">'
        '&#10003; the relay accepted our credentials and our sending IP<br>'
        '&#10003; the sender address was accepted<br>'
        '&#10003; HTML and plain-text alternatives both render<br>'
        '&#10003; Arabic (RTL) content survives transport</div>'
        '</td></tr></table>'
        '<p style="margin:0 0 22px 0;font-size:15px;line-height:1.65;">'
        'It unlocks <strong>password reset</strong>, <strong>email verification</strong> '
        'and <strong>order notifications</strong> — all of which were previously refused '
        'with an honest <code style="background:#F2EEE4;padding:1px 5px;border-radius:3px;'
        'font-size:13px;">HTTP 501</code> rather than pretending to send.</p>'
        '</td></tr>'
        # divider
        '<tr><td style="padding:0 32px;"><div style="height:1px;background:#EADFC8;"></div></td></tr>'
        # arabic body
        '<tr><td dir="rtl" lang="ar" style="padding:24px 32px 10px 32px;color:#1B1F3B;'
        'text-align:right;">'
        '<div style="font-size:17px;font-weight:600;margin-bottom:12px;">تم تفعيل البريد</div>'
        '<p style="margin:0 0 14px 0;font-size:15px;line-height:1.9;">'
        'أُرسلت هذه الرسالة من منصة CONFIT نفسها، من بيئة الإنتاج، عبر خادم البريد '
        'المهيّأ لها. وهي أول رسالة بريد تعاملية تنجح المنصة في تسليمها.</p>'
        '<p style="margin:0 0 20px 0;font-size:15px;line-height:1.9;">'
        'تفتح هذه الخطوة: إعادة تعيين كلمة المرور، وتأكيد البريد الإلكتروني، '
        'وإشعارات الطلبات.</p>'
        '</td></tr>'
        # footer
        '<tr><td style="background:#FAF7F0;padding:18px 32px;border-top:1px solid #EADFC8;">'
        '<div style="font-size:12px;color:#7A7E92;line-height:1.7;">'
        'This is an automated message. No action is required.<br>'
        '<span dir="rtl">رسالة آلية — لا يلزم اتخاذ أي إجراء.</span></div>'
        '</td></tr>'
        '</table></td></tr></table></body></html>'
    )
    return subject, html, text


def render_password_reset_email(full_name: str, reset_url: str) -> tuple[str, str, str]:
    """Password reset — bilingual (locale unknown at send time), spec-15 shell
    quality: preheader, one CTA, plain-text parity, no emoji, no images."""
    subject = "Reset your CONFIT password / إعادة تعيين كلمة المرور"
    text = (
        f"Hello {full_name},\n\n"
        f"We received a request to reset your CONFIT password.\n"
        f"This link is valid for 30 minutes and can be used once:\n"
        f"{reset_url}\n\n"
        f"If you did not request this, you can ignore this email — "
        f"your password will not change.\n\n"
        f"-----------------------------------------------------------------\n"
        f"مرحباً {full_name}،\n"
        f"وصلنا طلب لإعادة تعيين كلمة مرور كونفيت. الرابط صالح 30 دقيقة "
        f"وللاستخدام مرة واحدة. إذا لم تطلب ذلك فتجاهل هذه الرسالة — "
        f"لن تتغير كلمة المرور.\n\n— CONFIT"
    )
    html = _auth_shell(
        preheader="Your password reset link — valid 30 minutes, single use.",
        title="Reset your password",
        title_ar="إعادة تعيين كلمة المرور",
        body_en=(
            f"Hello {_h(full_name)}, we received a request to reset your CONFIT "
            "password. The button below is valid for <strong>30 minutes</strong> "
            "and can be used once. If you did not request this, ignore this "
            "email — your password will not change."
        ),
        body_ar=(
            f"مرحباً {_h(full_name)}، وصلنا طلب لإعادة تعيين كلمة مرور كونفيت. "
            "الزر أدناه صالح <strong>30 دقيقة</strong> وللاستخدام مرة واحدة. "
            "إذا لم تطلب ذلك فتجاهل هذه الرسالة — لن تتغير كلمة المرور."
        ),
        cta_label="Reset password / إعادة التعيين",
        cta_url=reset_url,
    )
    return subject, html, text


def render_verification_email(full_name: str, verify_url: str) -> tuple[str, str, str]:
    """Email verification — bilingual, spec-15 shell quality (no emoji §8)."""
    subject = "Verify your CONFIT email / تأكيد بريدك الإلكتروني"
    text = (
        f"Welcome to CONFIT, {full_name}!\n\n"
        f"Confirm your email address to secure your account:\n{verify_url}\n\n"
        f"This link is valid for 24 hours.\n\n"
        f"-----------------------------------------------------------------\n"
        f"أهلاً {full_name} في كونفيت. أكّد بريدك الإلكتروني لتأمين حسابك. "
        f"الرابط صالح 24 ساعة.\n\n— CONFIT"
    )
    html = _auth_shell(
        preheader="Confirm your email address — the link is valid 24 hours.",
        title="Verify your email",
        title_ar="تأكيد بريدك الإلكتروني",
        body_en=(
            f"Welcome to CONFIT, {_h(full_name)}. Confirm your email address to "
            "secure your account. The button below is valid for "
            "<strong>24 hours</strong>."
        ),
        body_ar=(
            f"أهلاً {_h(full_name)} في كونفيت. أكّد بريدك الإلكتروني لتأمين "
            "حسابك. الزر أدناه صالح <strong>24 ساعة</strong>."
        ),
        cta_label="Verify email / تأكيد البريد",
        cta_url=verify_url,
    )
    return subject, html, text


def _h(value) -> str:
    import html as _html_mod
    return _html_mod.escape(str(value), quote=True)


def _auth_shell(*, preheader: str, title: str, title_ar: str, body_en: str,
                body_ar: str, cta_label: str, cta_url: str) -> str:
    """Bilingual auth-mail shell: same visual language as email_templates
    (navy/gold/cream, text wordmark, hidden preheader, ONE bulletproof CTA,
    footer) but EN + AR in one message because the user's locale is unknown
    at password-reset time. Inline CSS, table layout, no images, no emoji."""
    cta_url_safe = _h(cta_url)
    return (
        '<!DOCTYPE html><html lang="en" dir="ltr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light dark">'
        '<meta name="supported-color-schemes" content="light dark">'
        f'<title>{_h(title)}</title></head>'
        '<body style="margin:0;padding:0;background:#FDF8EE;font-family:'
        "-apple-system,BlinkMacSystemFont,'Segoe UI',Tahoma,Helvetica,Arial,sans-serif;\">"
        '<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">'
        f'{_h(preheader)}</div>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#FDF8EE;padding:32px 16px;"><tr><td align="center">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:600px;background:#FFFFFF;border-radius:14px;overflow:hidden;'
        'border:1px solid #EADFC8;">'
        '<tr><td style="background:#1B1F3B;padding:26px 32px;">'
        '<div style="color:#C9A227;font-size:13px;letter-spacing:4px;'
        'text-transform:uppercase;font-weight:700;">CONFIT</div>'
        f'<div style="color:#FFFFFF;font-size:21px;font-weight:600;margin-top:8px;">'
        f'{_h(title)}</div></td></tr>'
        f'<tr><td style="padding:28px 32px 4px 32px;color:#1B1F3B;">'
        f'<p style="margin:0 0 16px 0;font-size:15px;line-height:1.8;">{body_en}</p>'
        '<table role="presentation" cellpadding="0" cellspacing="0" '
        'style="margin:10px 0 22px 0;"><tr>'
        '<td bgcolor="#1B1F3B" style="border-radius:12px;">'
        f'<a href="{cta_url_safe}" style="display:inline-block;padding:14px 30px;'
        'font-size:15px;font-weight:700;color:#FFFFFF;text-decoration:none;">'
        f'{_h(cta_label)}</a></td></tr></table></td></tr>'
        '<tr><td style="padding:0 32px;"><div style="height:1px;background:#EADFC8;">'
        '</div></td></tr>'
        '<tr><td dir="rtl" lang="ar" style="padding:22px 32px 26px 32px;'
        'color:#1B1F3B;text-align:right;">'
        f'<div style="font-size:17px;font-weight:600;margin-bottom:10px;">{_h(title_ar)}</div>'
        f'<p style="margin:0;font-size:15px;line-height:1.9;">{body_ar}</p></td></tr>'
        '<tr><td style="background:#FAF7F0;padding:18px 32px;border-top:1px solid #EADFC8;">'
        '<div style="font-size:12px;color:#7A7E92;line-height:1.7;">'
        'This is a service message about your CONFIT account.<br>'
        '<span dir="rtl">رسالة خدمية تخص حسابك على كونفيت.</span></div>'
        '</td></tr></table></td></tr></table></body></html>'
    )
