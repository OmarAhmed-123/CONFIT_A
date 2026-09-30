"""SMTP transport self-test: configured is not the same as deliverable.

MEASURED 2026-09-30, real relay, valid credentials:
    smtp-relay.brevo.com:587 -> 525 5.7.1 Unauthorized IP address

Brevo (like SES, Mailgun, Postmark) enforces a per-account IP allow-list, and
a serverless platform dials out from a rotating pool. If configuration alone
were treated as proof, `email_delivery` would report `ready` while every
password-reset mail failed at AUTH — a health signal that is confidently
wrong, which is worse than one that says "unknown".

These tests pin the four things that make the diagnostic trustworthy:
it reuses the real send path, it never sends a message, it never leaks a
credential, and it reports the relay's own verdict verbatim.
"""
from __future__ import annotations

import smtplib

import pytest

from backend.app.services import email_service


def _set(monkeypatch, **kw):
    for key, value in kw.items():
        monkeypatch.setattr(f"backend.app.core.config.settings.{key}", value, raising=False)


def _configure(monkeypatch):
    _set(monkeypatch, EMAIL_PROVIDER="smtp", SMTP_HOST="smtp-relay.example.test",
         SMTP_PORT=587, SMTP_USERNAME="user@example.test",
         SMTP_PASSWORD="secret-value-must-never-appear",
         EMAIL_FROM_ADDRESS="no-reply@example.test")


class _FakeClient:
    def __init__(self): self.quit_called = False
    def quit(self): self.quit_called = True


def test_unconfigured_reports_configuration_stage(monkeypatch):
    _set(monkeypatch, EMAIL_PROVIDER=None)
    r = email_service.check_transport()
    assert r["ok"] is False and r["stage"] == "configuration"


def test_half_configured_reports_configuration_stage(monkeypatch):
    _configure(monkeypatch)
    _set(monkeypatch, SMTP_HOST=None)
    r = email_service.check_transport()
    assert r["ok"] is False and r["stage"] == "configuration"


def test_successful_handshake_is_reported_and_the_session_is_closed(monkeypatch):
    _configure(monkeypatch)
    client = _FakeClient()
    monkeypatch.setattr(email_service, "_connect", lambda: client)
    r = email_service.check_transport()
    assert r["ok"] is True and r["stage"] == "authenticated"
    assert "no message was sent" in r["detail"]
    assert client.quit_called, "an opened SMTP session must always be closed"


def test_unauthorized_ip_is_surfaced_verbatim_not_flattened(monkeypatch):
    """The exact production failure mode. Flattening this into "auth failed"
    would hide the one fact that tells an operator what to fix."""
    _configure(monkeypatch)

    def _boom():
        raise smtplib.SMTPAuthenticationError(525, b"5.7.1 Unauthorized IP address")

    monkeypatch.setattr(email_service, "_connect", _boom)
    r = email_service.check_transport()
    assert r["ok"] is False
    assert r["stage"] == "authentication"
    assert r["code"] == 525
    assert "Unauthorized IP address" in r["detail"]


def test_connection_failure_is_reported_not_raised(monkeypatch):
    _configure(monkeypatch)

    def _boom():
        raise OSError("connection timed out")

    monkeypatch.setattr(email_service, "_connect", _boom)
    r = email_service.check_transport()
    assert r["ok"] is False and r["stage"] == "connection"
    assert "connection timed out" in r["detail"]


def test_no_credential_ever_appears_in_the_result(monkeypatch):
    """A diagnostic that leaks the password it just used is a vulnerability."""
    _configure(monkeypatch)

    def _boom():
        raise smtplib.SMTPAuthenticationError(535, b"5.7.8 Authentication failed")

    monkeypatch.setattr(email_service, "_connect", _boom)
    blob = repr(email_service.check_transport())
    assert "secret-value-must-never-appear" not in blob
    assert "user@example.test" not in blob


def test_it_reuses_the_real_send_path(monkeypatch):
    """A green check computed through a different transport than send_email
    uses would be meaningless."""
    _configure(monkeypatch)
    called = []
    monkeypatch.setattr(email_service, "_connect", lambda: called.append(1) or _FakeClient())
    email_service.check_transport()
    assert called == [1], "check_transport must go through _connect(), the send path"


def test_the_diagnostic_never_sends_a_message(monkeypatch):
    """EHLO -> STARTTLS -> AUTH -> QUIT. No RCPT, no DATA, no recipient."""
    _configure(monkeypatch)

    class _Strict(_FakeClient):
        def sendmail(self, *a, **k): raise AssertionError("must not send")
        def send_message(self, *a, **k): raise AssertionError("must not send")

    monkeypatch.setattr(email_service, "_connect", _Strict)
    assert email_service.check_transport()["ok"] is True


# ── authorization on the endpoint ────────────────────────────────────────────

def test_diagnostic_endpoint_requires_admin(client):
    assert client.get("/api/v1/admin/diagnostics/email").status_code in (401, 403)


# ── observed reality must beat configuration ────────────────────────────────

# The observation recorder is reset suite-wide by an autouse fixture in
# conftest.py — it is process-global, so containing it per-file is not enough.


def test_capability_is_blocked_after_an_observed_failure(monkeypatch):
    """THE PRODUCTION DEFECT, 2026-09-30: with SMTP_* correctly set the probe
    said `ready` while the relay answered 525 Unauthorized IP, so
    /auth/forgot-password returned 200 "instructions have been sent" and
    nothing was sent — worse than the honest 501 it replaced."""
    from backend.app.core.readiness import STATE_BLOCKED
    from backend.app.services.capability_service import _email_delivery_capability

    _configure(monkeypatch)

    def _boom():
        raise smtplib.SMTPAuthenticationError(525, b"5.7.1 Unauthorized IP address")

    monkeypatch.setattr(email_service, "_connect", _boom)
    email_service.check_transport()

    cap = _email_delivery_capability()
    assert cap.state == STATE_BLOCKED
    assert "Unauthorized IP address" in cap.detail
    assert "525" in cap.detail
    assert "not being" in cap.detail and "delivered" in cap.detail


def test_capability_is_delivery_verified_after_an_observed_success(monkeypatch):
    from backend.app.core.readiness import STATE_READY
    from backend.app.services.capability_service import _email_delivery_capability

    _configure(monkeypatch)
    monkeypatch.setattr(email_service, "_connect", _FakeClient)
    email_service.check_transport()

    cap = _email_delivery_capability()
    assert cap.state == STATE_READY
    assert "DELIVERY-VERIFIED" in cap.detail


def test_with_no_observation_yet_it_says_so_instead_of_claiming_delivery(monkeypatch):
    from backend.app.services.capability_service import _email_delivery_capability

    _configure(monkeypatch)
    detail = _email_delivery_capability().detail
    assert "not delivery-verified" in detail
    assert "no send or handshake observed yet" in detail


def test_a_real_send_failure_also_updates_the_observation(monkeypatch):
    """The admin diagnostic is not the only reporter — production traffic
    teaches the capability too."""
    _configure(monkeypatch)

    def _boom():
        raise smtplib.SMTPRecipientsRefused({"a@b.test": (550, b"nope")})

    monkeypatch.setattr(email_service, "_connect", _boom)
    with pytest.raises(email_service.EmailDeliveryError):
        email_service.send_email("a@b.test", "s", "<p>h</p>", "t")

    observed = email_service.last_transport_result()
    assert observed["observed"] is True and observed["ok"] is False
    assert observed["stage"] == "send"


# ── the admin send-test endpoint ─────────────────────────────────────────────

def test_send_test_endpoint_requires_admin(client):
    r = client.post("/api/v1/admin/diagnostics/email/test",
                    json={"to": "someone@example.test"})
    assert r.status_code in (401, 403)


def test_send_test_rejects_a_caller_chosen_subject_or_body(client):
    """An admin endpoint that lets the caller pick subject+HTML is an open
    relay wearing an auth check. extra='forbid' makes that impossible."""
    from backend.app.controllers.admin_controller import EmailTestRequest
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        EmailTestRequest(to="a@b.test", subject="Free money", html="<p>spam</p>")


def test_send_test_validates_the_recipient():
    from backend.app.controllers.admin_controller import EmailTestRequest
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        EmailTestRequest(to="not-an-email")


def test_launch_template_is_bilingual_and_has_both_parts():
    from backend.app.services.email_service import render_platform_test_email

    subject, html, text = render_platform_test_email("note here")
    assert subject and html and text
    # Arabic present in both alternatives — a template that renders only one
    # language is half-tested in an EN/AR product.
    assert any("\u0600" <= ch <= "\u06FF" for ch in html)
    assert any("\u0600" <= ch <= "\u06FF" for ch in text)
    assert 'dir="rtl"' in html
    assert "note here" in html and "note here" in text
    # No tracking pixel in an operational proof email.
    assert "<img" not in html.lower()
