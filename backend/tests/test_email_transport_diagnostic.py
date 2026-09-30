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
