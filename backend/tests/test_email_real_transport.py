"""Real delivery over a real socket + the delivery-ledger honesty contract.

Why this file exists (task §24): asserting "send_email() was called" proves
nothing. These tests start an actual SMTP server on a loopback port, let the
application speak the real protocol to it (connect → EHLO → MAIL FROM →
RCPT TO → DATA → QUIT), and then assert that:

  * the message reached the server as bytes,
  * it carries a one-time verification/reset link for the real production-style
    base URL configured via settings (never a hardcoded localhost),
  * the token that arrived BY EMAIL actually redeems through the API,
  * the `email_deliveries` ledger records what the provider did (SUCCEEDED /
    FAILED / BLOCKED) — never a fabricated success,
  * an identical (purpose, token) send is not duplicated (idempotency),
  * an anonymous request endpoint answers with the non-committal vocabulary
    ("requested") and does not leak account existence.

Scope note: a loopback MTA is a *controlled environment*, not a third-party
provider. Third-party delivery requires real provider credentials
(EMAIL_PROVIDER + SMTP_HOST/SMTP_USERNAME/SMTP_PASSWORD or RESEND_API_KEY) and
is reported as BLOCKED/UNVERIFIED until those exist — see the final report.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import settings

# Shared practice sink + message helpers (kept out of a test-named module so
# other suites can import them without tripping the dependency-manifest gate).
from backend.tests.smtp_test_support import (  # noqa: F401
    LocalSMTPSink,
    _csrf,
    _plain_text,
    _token_from,
    smtp_sink,
)
from backend.app.models.user import EmailDelivery, EmailDeliveryStatus
from backend.app.services import email_service


# ---------------------------------------------------------------------------
# 1. A REAL message reaches a REAL server and its token redeems
# ---------------------------------------------------------------------------

def test_verification_email_is_really_delivered_and_redeems(client: TestClient, smtp_sink):
    email_addr = "wire-proof@example.com"
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email_addr, "password": "Password123!", "full_name": "Wire Proof"},
    )
    assert r.status_code == 201, r.text
    assert len(smtp_sink.messages) == 1, "registration must send exactly one verification email"

    raw = smtp_sink.messages[0]
    text = _plain_text(raw)
    assert "https://confit-a.vercel.app/verify-email?token=" in text, text[:400]
    assert b"no-reply@confit.test" in raw
    token = _token_from(text)

    # The token that travelled over the wire is the one that redeems.
    v = client.post("/api/v1/auth/verify-email", json={"token": token}, headers=_csrf(client))
    assert v.status_code == 200, v.text
    me = client.get("/api/v1/auth/me")
    assert me.json()["is_verified"] is True


def test_password_reset_email_is_really_delivered_and_rotates_password(client: TestClient, smtp_sink):
    email_addr = "wire-reset@example.com"
    client.post(
        "/api/v1/auth/register",
        json={"email": email_addr, "password": "Password123!", "full_name": "Reset Wire"},
    )
    smtp_sink.messages.clear()

    r = client.post("/api/v1/auth/forgot-password", json={"email": email_addr}, headers=_csrf(client))
    assert r.status_code == 200
    assert r.json()["status"] == "requested"
    assert len(smtp_sink.messages) == 1

    token = _token_from(_plain_text(smtp_sink.messages[0]))
    reset = client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "BrandNewPass123!"},
        headers=_csrf(client),
    )
    assert reset.status_code == 200, reset.text
    login = client.post("/api/v1/auth/login", json={"email": email_addr, "password": "BrandNewPass123!"})
    assert login.status_code == 200


# ---------------------------------------------------------------------------
# 2. The ledger records the truth (no fabricated success)
# ---------------------------------------------------------------------------

def test_ledger_records_success_only_when_the_server_accepted(client: TestClient, smtp_sink):
    from backend.app.core.database import get_db
    from backend.app.main import app

    email_addr = "ledger-ok@example.com"
    client.post("/api/v1/auth/register", json={"email": email_addr, "password": "Password123!", "full_name": "Ledger"})
    user_id = client.get("/api/v1/auth/me").json()["id"]
    db = next(app.dependency_overrides[get_db]())
    try:
        rows = (
            db.query(EmailDelivery)
            .filter(EmailDelivery.purpose == email_service.PURPOSE_VERIFICATION, EmailDelivery.user_id == user_id)
            .all()
        )
        assert rows, "successful send must be recorded in the ledger"
        assert all(r.status == EmailDeliveryStatus.SUCCEEDED for r in rows)
        assert all(r.provider_message_id for r in rows), "provider receipt must be captured"
        assert all(r.recipient_hash and "ledger-ok@" not in (r.recipient_hash or "") for r in rows), "no plaintext address in the ledger"
    finally:
        db.close()


def test_ledger_records_failure_and_never_raises_to_the_caller(client: TestClient, monkeypatch):
    """A dead relay must not produce a SUCCEEDED row, and registration must
    still work (the account exists either way) — but the failure is recorded."""
    from backend.app.core.database import get_db
    from backend.app.main import app

    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "smtp", raising=False)
    monkeypatch.setattr(settings, "SMTP_HOST", "127.0.0.1", raising=False)
    monkeypatch.setattr(settings, "SMTP_PORT", 9, raising=False)  # discard port: nothing listens
    monkeypatch.setattr(settings, "SMTP_USERNAME", None, raising=False)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", None, raising=False)
    monkeypatch.setattr(settings, "SMTP_TLS_MODE", "none", raising=False)
    monkeypatch.setattr(settings, "EMAIL_FROM_ADDRESS", "CONFIT <no-reply@confit.test>", raising=False)

    email_addr = "ledger-fail@example.com"
    r = client.post("/api/v1/auth/register", json={"email": email_addr, "password": "Password123!", "full_name": "Dead Relay"})
    assert r.status_code == 201, "registration survives email failure"
    user_id = r.json()["user"]["id"]

    db = next(app.dependency_overrides[get_db]())
    try:
        rows = (
            db.query(EmailDelivery)
            .filter(EmailDelivery.purpose == email_service.PURPOSE_VERIFICATION, EmailDelivery.user_id == user_id)
            .all()
        )
        assert rows and all(r.status == EmailDeliveryStatus.FAILED for r in rows)
        assert all(r.error_class for r in rows)
    finally:
        db.close()


def test_unconfigured_provider_records_blocked_and_the_api_says_501(client: TestClient, monkeypatch):
    from backend.app.core.database import get_db
    from backend.app.main import app

    monkeypatch.setattr(settings, "EMAIL_PROVIDER", None, raising=False)
    r = client.post("/api/v1/auth/forgot-password", json={"email": "blocked@example.com"})
    assert r.status_code == 501
    assert r.json()["error"]["code"] == "FEATURE_NOT_CONFIGURED"

    # Direct service-level call records BLOCKED instead of pretending.
    db = next(app.dependency_overrides[get_db]())
    try:
        result = email_service.send_transactional(
            db, to="someone@example.com", subject="s", html="<b>x</b>", text="x",
            purpose="unit_probe", dedupe_key="unit-probe-blocked",
        )
        assert result.status == EmailDeliveryStatus.BLOCKED
        assert result.accepted is False
    finally:
        db.close()


def test_identical_send_is_not_duplicated(client: TestClient, smtp_sink):
    """Idempotency: the same (purpose, token) never produces two messages."""
    from backend.app.core.database import get_db
    from backend.app.main import app

    db = next(app.dependency_overrides[get_db]())
    try:
        first = email_service.send_transactional(
            db, to="idem@example.com", subject="Hello", html="<b>hi</b>", text="hi",
            purpose="unit_idem", dedupe_key="same-key",
        )
        second = email_service.send_transactional(
            db, to="idem@example.com", subject="Hello", html="<b>hi</b>", text="hi",
            purpose="unit_idem", dedupe_key="same-key",
        )
        assert first.accepted and second.idempotent_replay
        assert len(smtp_sink.messages) == 1, "the provider must see exactly one message"
    finally:
        db.close()


def test_anonymous_request_never_leaks_existence_and_uses_conditional_copy(client: TestClient, smtp_sink):
    known = client.post(
        "/api/v1/auth/register",
        json={"email": "known@example.com", "password": "Password123!", "full_name": "Known"},
    )
    assert known.status_code == 201
    smtp_sink.messages.clear()

    r_known = client.post("/api/v1/auth/forgot-password", json={"email": "known@example.com"}, headers=_csrf(client))
    r_unknown = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"}, headers=_csrf(client))
    assert r_known.status_code == r_unknown.status_code == 200
    assert r_known.json() == r_unknown.json()
    assert "if" in r_known.json()["message"].lower(), "copy must stay conditional"
    assert len(smtp_sink.messages) == 1, "only the existing account triggers a send"


def test_email_status_endpoint_reports_own_delivery_truth(client: TestClient, smtp_sink):
    email_addr = "status-owner@example.com"
    client.post("/api/v1/auth/register", json={"email": email_addr, "password": "Password123!", "full_name": "Status"})
    r = client.get("/api/v1/auth/email-status?purpose=email_verification")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "succeeded"
    assert body["accepted"] is True
    assert body["provider"] == "smtp"


def test_streaming_resend_invalidates_the_previous_link(client: TestClient, smtp_sink):
    email_addr = "resend@example.com"
    client.post("/api/v1/auth/register", json={"email": email_addr, "password": "Password123!", "full_name": "Resend"})
    first_token = _token_from(_plain_text(smtp_sink.messages[-1]))

    r = client.post("/api/v1/auth/verify-email/request", json={"email": email_addr}, headers=_csrf(client))
    assert r.status_code == 200 and r.json()["status"] == "requested"
    second_token = _token_from(_plain_text(smtp_sink.messages[-1]))
    assert first_token != second_token

    # The superseded link is dead; only one live token exists per account.
    stale = client.post("/api/v1/auth/verify-email", json={"token": first_token}, headers=_csrf(client))
    assert stale.status_code == 401
    fresh = client.post("/api/v1/auth/verify-email", json={"token": second_token}, headers=_csrf(client))
    assert fresh.status_code == 200
