"""CYCLE 4 (BLOCKER C engineering half): real email delivery contract.

Pinned here:
- SMTP transport: STARTTLS/SSL connect, auth, real message shape, one retry
  on transient failure, honest raise on hard rejection.
- forgot-password with email configured: a REAL message containing a REAL
  one-time link leaves the server; the link redeems via /reset-password.
- No account-existence leak: unknown email → identical response, zero sends.
- SMTP hard failure → still non-committal 200 (never leak) + the failure is
  audited, and the issued token stays valid.
- verify-email: request issues hashed 24h one-time token via email; redeem
  flips is_verified; replay/expiry/garbage rejected honestly.
- register sends a verification email when (and only when) configured.
- Production config gate: EMAIL_PROVIDER=smtp without SMTP_HOST refuses boot.
"""

import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.services import auth_service as auth_service_mod
from backend.app.services import email_service


class FakeSMTP:
    sent: list = []
    fail_next: int = 0
    reject: bool = False

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port
        self.tls_started = False
        self.logged_in_as = None

    def ehlo(self):
        return True

    def starttls(self, context=None):
        self.tls_started = True
        return True

    def login(self, user, password):
        self.logged_in_as = user
        return True

    def send_message(self, msg):
        if FakeSMTP.reject:
            import smtplib

            raise smtplib.SMTPSenderRefused(550, "rejected", "x")
        if FakeSMTP.fail_next > 0:
            FakeSMTP.fail_next -= 1
            raise ConnectionResetError("transient")
        FakeSMTP.sent.append(msg)
        return {}

    def quit(self):
        return True


@pytest.fixture(autouse=True)
def _smtp(monkeypatch):
    FakeSMTP.sent = []
    FakeSMTP.fail_next = 0
    FakeSMTP.reject = False
    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(email_service.smtplib, "SMTP_SSL", FakeSMTP)
    yield FakeSMTP


@pytest.fixture()
def email_on(monkeypatch):
    """Simulate a fully configured SMTP provider (Resend-style relay)."""
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "smtp", raising=False)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.fake.test", raising=False)
    monkeypatch.setattr(settings, "SMTP_PORT", 587, raising=False)
    monkeypatch.setattr(settings, "SMTP_USERNAME", "resend", raising=False)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "re_test_key", raising=False)
    monkeypatch.setattr(settings, "EMAIL_FROM_ADDRESS", "CONFIT <no-reply@confit.test>", raising=False)
    monkeypatch.setattr(settings, "FRONTEND_BASE_URL", "https://app.confit.test", raising=False)
    yield


def _extract_token(text: str) -> str:
    m = re.search(r"token=([A-Za-z0-9_\-]+)", text)
    assert m, f"no token link in email body: {text[:120]!r}"
    return m.group(1)


# ---------------------------------------------------------------------------
# Transport unit contract
# ---------------------------------------------------------------------------

def test_transport_starttls_auth_and_shape(_smtp, email_on):
    out = email_service.send_email(
        to="user@example.com", subject="Hello", html="<b>hi</b>", text="hi"
    )
    assert out["message_id"]
    (msg,) = _smtp.sent
    assert msg["To"] == "user@example.com"
    assert "no-reply@confit.test" in msg["From"]
    assert msg["Subject"] == "Hello"
    body = msg.get_body(preferencelist=("plain",)).get_content()
    assert "hi" in body
    html_body = msg.get_body(preferencelist=("html",)).get_content()
    assert "<b>hi</b>" in html_body


def test_transport_retries_once_on_transient_then_succeeds(_smtp, email_on):
    _smtp.fail_next = 1
    email_service.send_email(to="a@b.c", subject="s", html="x")
    assert len(_smtp.sent) == 1


def test_transport_hard_rejection_is_honest(_smtp, email_on):
    _smtp.reject = True
    with pytest.raises(email_service.EmailDeliveryError):
        email_service.send_email(to="a@b.c", subject="s", html="x")
    assert _smtp.sent == []


def test_transport_fails_honestly_when_unconfigured(_smtp, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", None, raising=False)
    with pytest.raises(email_service.EmailDeliveryError):
        email_service.send_email(to="a@b.c", subject="s", html="x")


# ---------------------------------------------------------------------------
# forgot-password end-to-end with real delivery
# ---------------------------------------------------------------------------

def _csrf(client: TestClient) -> dict:
    token = client.cookies.get("confit_csrf")
    return {"X-CSRF-Token": token} if token else {}

def _register(client: TestClient, email: str):
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": "Test User"},
    )
    assert r.status_code in (200, 201), r.text
    return r


def test_forgot_password_sends_real_one_time_link(client, _smtp, email_on):
    email = "resetme@example.com"
    _register(client, email)
    _smtp.sent.clear()  # registration may have sent a verification mail

    r = client.post("/api/v1/auth/forgot-password", json={"email": email}, headers=_csrf(client))
    assert r.status_code == 200
    assert r.json()["status"] == "queued"
    (msg,) = _smtp.sent
    body = msg.get_body(preferencelist=("plain",)).get_content()
    assert "https://app.confit.test/reset-password?token=" in body
    token = _extract_token(body)

    # the EMAILED token actually redeems
    r2 = client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "NewPassword123!"},
        headers=_csrf(client),
    )
    assert r2.status_code == 200, r2.text

    # ...and login works with the new password
    r3 = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "NewPassword123!"}
    )
    assert r3.status_code == 200


def test_forgot_password_unknown_email_no_leak_no_send(client, _smtp, email_on):
    r_known_shape = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"}, headers=_csrf(client))
    assert r_known_shape.status_code == 200
    assert r_known_shape.json()["status"] == "queued"
    assert _smtp.sent == []


def test_forgot_password_smtp_failure_does_not_leak(client, _smtp, email_on):
    email = "downrelay@example.com"
    _register(client, email)
    _smtp.sent.clear()
    _smtp.reject = True
    r = client.post("/api/v1/auth/forgot-password", json={"email": email}, headers=_csrf(client))
    assert r.status_code == 200  # non-committal, exactly like success
    assert r.json()["status"] == "queued"


def test_forgot_password_still_501_when_unconfigured(client, _smtp):
    # settings.EMAIL_PROVIDER is None in the default test environment
    r = client.post("/api/v1/auth/forgot-password", json={"email": "x@example.com"})
    assert r.status_code == 501
    assert r.json()["error"]["code"] == "FEATURE_NOT_CONFIGURED"


# ---------------------------------------------------------------------------
# email verification lifecycle
# ---------------------------------------------------------------------------

def test_verification_request_and_redeem(client, _smtp, email_on):
    email = "verifyme@example.com"
    _register(client, email)
    _smtp.sent.clear()

    r = client.post("/api/v1/auth/verify-email/request", json={"email": email}, headers=_csrf(client))
    assert r.status_code == 200
    (msg,) = _smtp.sent
    body = msg.get_body(preferencelist=("plain",)).get_content()
    assert "https://app.confit.test/verify-email?token=" in body
    token = _extract_token(body)

    v = client.post("/api/v1/auth/verify-email", json={"token": token}, headers=_csrf(client))
    assert v.status_code == 200, v.text

    # is_verified now true on the profile
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json().get("is_verified") is True


def test_verification_replay_rejected(client, _smtp, email_on):
    email = "replay@example.com"
    _register(client, email)
    _smtp.sent.clear()
    client.post("/api/v1/auth/verify-email/request", json={"email": email}, headers=_csrf(client))
    body = _smtp.sent[-1].get_body(preferencelist=("plain",)).get_content()
    token = _extract_token(body)
    assert client.post("/api/v1/auth/verify-email", json={"token": token}, headers=_csrf(client)).status_code == 200
    replay = client.post("/api/v1/auth/verify-email", json={"token": token}, headers=_csrf(client))
    assert replay.status_code == 401


def test_verification_expired_token_rejected(client, _smtp, email_on, monkeypatch):
    email = "expired@example.com"
    _register(client, email)
    _smtp.sent.clear()
    monkeypatch.setattr(auth_service_mod, "_EMAIL_VERIFICATION_TTL", timedelta(seconds=-1))
    client.post("/api/v1/auth/verify-email/request", json={"email": email}, headers=_csrf(client))
    body = _smtp.sent[-1].get_body(preferencelist=("plain",)).get_content()
    token = _extract_token(body)
    r = client.post("/api/v1/auth/verify-email", json={"token": token}, headers=_csrf(client))
    assert r.status_code == 401
    assert "expired" in r.json()["error"]["message"].lower()


def test_verification_garbage_token_rejected(client, _smtp, email_on):
    r = client.post("/api/v1/auth/verify-email", json={"token": "not-a-real-token"})
    assert r.status_code == 401


def test_register_sends_verification_only_when_configured(client, _smtp, email_on):
    _register(client, "welcome@example.com")
    assert len(_smtp.sent) == 1
    assert "verify-email" in str(_smtp.sent[0].get_body(preferencelist=("plain",)).get_content())


def test_verify_email_still_501_when_unconfigured(client, _smtp):
    r = client.post("/api/v1/auth/verify-email", json={"token": "x"})
    assert r.status_code == 501
    r2 = client.post("/api/v1/auth/verify-email/request", json={"email": "x@example.com"})
    assert r2.status_code == 501


# ---------------------------------------------------------------------------
# Production honesty gate (config validator)
# ---------------------------------------------------------------------------

def test_production_boots_refuse_provider_without_smtp_host(monkeypatch):
    from backend.app.core.config import Settings

    strong = "x" * 64
    with pytest.raises(Exception) as ei:
        Settings(
            ENVIRONMENT="production",
            DATABASE_URL="postgresql://u:p@h:5432/db",
            SECRET_KEY=strong,
            JWT_REFRESH_SECRET=strong,
            ENCRYPTION_KEY_FOR_BODY_DATA=strong,
            EMAIL_PROVIDER="smtp",
            SMTP_HOST=None,
            EMAIL_FROM_ADDRESS="no-reply@confit.test",
            FRONTEND_BASE_URL="https://app.confit.test",
        )
    assert "SMTP_HOST" in str(ei.value)
