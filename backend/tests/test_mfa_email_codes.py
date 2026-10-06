"""MFA email codes — the mailbox alternative for the two-factor step (2026-10-06).

Contract under test:
  · POST /auth/mfa/email-code requires the SAME credentials as login and
    fails with the same non-leaking 401 — the endpoint cannot be used to
    probe account existence or MFA state without the password.
  · "sent" is never claimed unless the transport accepted the message; a
    delivery failure is an honest 502 and the undeliverable code is retired.
  · The emailed code completes login exactly once (atomic claim), expires
    after 10 minutes, dies after 5 wrong guesses, and a new request retires
    every previous live code.
  · TOTP and recovery codes keep working unchanged next to the email path.
  · The Brevo HTTP API transport builds the right request and never
    invents a success.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pyotp
import pytest
from fastapi.testclient import TestClient

from backend.tests.conftest import TestingSessionLocal


PASSWORD = "Password123!"


@pytest.fixture(autouse=True)
def _email_configured():
    """The endpoint honestly refuses with 501 when EMAIL_PROVIDER is unset
    (tested explicitly below); every other test runs as a configured env —
    the transport itself is mocked, configuration is the only thing faked."""
    from backend.app.core.config import settings as _settings

    with patch.object(_settings, "EMAIL_PROVIDER", "smtp"):
        yield

# A FRESH user per fixture (like every other MFA suite here): the TOTP
# replay guard remembers the last accepted time step PER USER, so re-using
# the seeded shopper across tests inside one 30-second window makes the
# second enrollment's verify look like a replay and fail honestly.
_counter = iter(range(1_000_000))


def _login_token(client: TestClient, email: str, mfa_code: str | None = None):
    body = {"email": email, "password": PASSWORD}
    if mfa_code is not None:
        body["mfa_code"] = mfa_code
    return client.post("/api/v1/auth/login", json=body)


@pytest.fixture()
def mfa_user(client: TestClient):
    """Register a fresh user, enable TOTP MFA, yield its identity + secret."""
    import uuid

    email = f"mfa.email.{uuid.uuid4().hex[:10]}@confit-test.io"
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "MFA Email Test"},
    )
    assert reg.status_code == 201, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    setup = client.post("/api/v1/auth/mfa/setup", headers=headers)
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    verify = client.post(
        "/api/v1/auth/mfa/verify",
        json={"code": pyotp.TOTP(secret).now()},
        headers=headers,
    )
    assert verify.status_code == 200, verify.text
    recovery_codes = verify.json()["backup_codes"]

    yield {
        "email": email,
        "secret": secret,
        "recovery_codes": recovery_codes,
        "headers": headers,
    }


def _request_code(client: TestClient, email: str, password: str = PASSWORD):
    return client.post(
        "/api/v1/auth/mfa/email-code",
        json={"email": email, "password": password},
    )


def _latest_sent_code(send_mock) -> str:
    """Extract the 6-digit code from the captured outbound email text."""
    import re

    kwargs = send_mock.call_args.kwargs
    text = kwargs.get("text") or send_mock.call_args.args[-1]
    match = re.search(r"\b(\d{6})\b", text)
    assert match, f"no 6-digit code found in email text: {text[:200]}"
    return match.group(1)


class TestRequestEndpoint:
    def test_wrong_password_same_nonleaking_401_as_login(self, client, mfa_user):
        res = _request_code(client, mfa_user["email"], password="WrongPassword1!")
        assert res.status_code == 401
        assert "Invalid email or password" in res.text
        # and no code row was written
        db = TestingSessionLocal()
        try:
            from backend.app.models.user import MFAEmailCode, User

            uid = db.query(User).filter(User.email == mfa_user["email"]).first().id
            assert (
                db.query(MFAEmailCode)
                .filter(MFAEmailCode.user_id == uid, MFAEmailCode.used_at.is_(None))
                .count()
                == 0
            )
        finally:
            db.close()

    def test_unconfigured_email_is_an_honest_501(self, client, mfa_user):
        from backend.app.core.config import settings as _settings

        with patch.object(_settings, "EMAIL_PROVIDER", None):
            res = _request_code(client, mfa_user["email"])
        assert res.status_code == 501
        assert "FEATURE_NOT_CONFIGURED" in res.text

    def test_mfa_disabled_is_a_422_not_a_send(self, client):
        # the seeded shopper has NO MFA enabled
        with patch("backend.app.services.auth_service.send_email") as send:
            res = _request_code(client, "shopper@confit.io")
        assert res.status_code == 422
        send.assert_not_called()

    def test_sent_only_when_transport_accepts(self, client, mfa_user):
        with patch("backend.app.services.auth_service.send_email") as send:
            send.return_value = {"message_id": "<mfa@test>"}
            res = _request_code(client, mfa_user["email"])
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] == "sent"
        assert body["expires_in_minutes"] == 10
        # masked destination, never the full address
        assert body["sent_to"].startswith("mf***@")
        assert mfa_user["email"] not in body["sent_to"]
        send.assert_called_once()
        # the email is link-free: a sign-in code email with a link is phishing-shaped
        kwargs = send.call_args.kwargs
        assert "http" not in (kwargs.get("text") or "")

    def test_transport_failure_is_an_honest_502_and_code_is_retired(
        self, client, mfa_user
    ):
        from backend.app.services.email_service import EmailDeliveryError

        with patch("backend.app.services.auth_service.send_email") as send:
            send.side_effect = EmailDeliveryError("Brevo API rejected request: HTTP 401")
            res = _request_code(client, mfa_user["email"])
        assert res.status_code == 502
        # the undeliverable code must not be redeemable
        db = TestingSessionLocal()
        try:
            from backend.app.models.user import MFAEmailCode, User

            uid = db.query(User).filter(User.email == mfa_user["email"]).first().id
            assert (
                db.query(MFAEmailCode)
                .filter(MFAEmailCode.user_id == uid, MFAEmailCode.used_at.is_(None))
                .count()
                == 0
            )
        finally:
            db.close()


class TestLoginWithEmailedCode:
    def _get_code(self, client, email: str) -> str:
        with patch("backend.app.services.auth_service.send_email") as send:
            send.return_value = {"message_id": "<mfa@test>"}
            res = _request_code(client, email)
            assert res.status_code == 200, res.text
            return _latest_sent_code(send)

    def test_emailed_code_completes_login_exactly_once(self, client, mfa_user):
        code = self._get_code(client, mfa_user["email"])
        res = _login_token(client, mfa_user["email"], mfa_code=code)
        assert res.status_code == 200, res.text
        assert res.json()["access_token"]
        # single-use: replay is refused
        res2 = _login_token(client, mfa_user["email"], mfa_code=code)
        assert res2.status_code == 401

    def test_new_request_retires_previous_live_code(self, client, mfa_user):
        old_code = self._get_code(client, mfa_user["email"])
        new_code = self._get_code(client, mfa_user["email"])
        assert _login_token(client, mfa_user["email"], mfa_code=old_code).status_code == 401
        assert _login_token(client, mfa_user["email"], mfa_code=new_code).status_code == 200

    def test_expired_code_refused(self, client, mfa_user):
        code = self._get_code(client, mfa_user["email"])
        db = TestingSessionLocal()
        try:
            from backend.app.models.user import MFAEmailCode, User

            uid = db.query(User).filter(User.email == mfa_user["email"]).first().id
            db.query(MFAEmailCode).filter(
                MFAEmailCode.user_id == uid, MFAEmailCode.used_at.is_(None)
            ).update(
                {"expires_at": datetime.now(timezone.utc) - timedelta(minutes=1)},
                synchronize_session=False,
            )
            db.commit()
        finally:
            db.close()
        assert _login_token(client, mfa_user["email"], mfa_code=code).status_code == 401

    def test_five_wrong_guesses_kill_the_live_code(self, client, mfa_user):
        code = self._get_code(client, mfa_user["email"])
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(5):
            assert _login_token(client, mfa_user["email"], mfa_code=wrong).status_code == 401
        # the real code is now dead too — attempts cap reached
        assert _login_token(client, mfa_user["email"], mfa_code=code).status_code == 401

    def test_totp_and_recovery_codes_still_work(self, client, mfa_user):
        import time as _time

        # TOTP next to a live email code. Enrollment already consumed the
        # CURRENT time step (the replay guard is doing its job), so present
        # the NEXT step's code — valid within the server's valid_window=1
        # and strictly newer than the last accepted step.
        self._get_code(client, mfa_user["email"])
        totp_gen = pyotp.TOTP(mfa_user["secret"])
        totp = totp_gen.at(int(_time.time()) + totp_gen.interval)
        assert _login_token(client, mfa_user["email"], mfa_code=totp).status_code == 200
        # recovery code single-use
        rc = mfa_user["recovery_codes"][0]
        assert _login_token(client, mfa_user["email"], mfa_code=rc).status_code == 200
        assert _login_token(client, mfa_user["email"], mfa_code=rc).status_code == 401


class TestBrevoTransport:
    def test_send_builds_the_documented_request_and_returns_message_id(self):
        from backend.app.services import email_service

        captured = {}

        def fake_brevo(url, payload=None):
            captured["url"] = url
            captured["payload"] = payload
            return {"messageId": "<brevo-msg-1>"}

        with patch.object(email_service.settings, "EMAIL_PROVIDER", "brevo_api"), \
             patch.object(email_service.settings, "BREVO_API_KEY", "key-x"), \
             patch.object(email_service.settings, "EMAIL_FROM_ADDRESS", "sender@confit.io"), \
             patch.object(email_service, "_brevo_request", side_effect=fake_brevo):
            result = email_service.send_email(
                "to@confit.io", "Subj", "<p>html</p>", "text body",
                headers={"List-Unsubscribe": "<https://x>", "Subject": "evil"},
            )
        assert result == {"message_id": "<brevo-msg-1>"}
        p = captured["payload"]
        assert captured["url"].endswith("/v3/smtp/email")
        assert p["sender"]["email"] == "sender@confit.io"
        assert p["to"] == [{"email": "to@confit.io"}]
        assert p["textContent"] == "text body"
        assert p["htmlContent"] == "<p>html</p>"
        # override guard: custom headers pass, protected ones never
        assert p["headers"] == {"List-Unsubscribe": "<https://x>"}

    def test_api_rejection_is_an_error_never_a_fake_success(self):
        from backend.app.services import email_service
        from backend.app.services.email_service import EmailDeliveryError

        with patch.object(email_service.settings, "EMAIL_PROVIDER", "brevo_api"), \
             patch.object(email_service.settings, "BREVO_API_KEY", "key-x"), \
             patch.object(email_service.settings, "EMAIL_FROM_ADDRESS", "sender@confit.io"), \
             patch.object(
                 email_service, "_brevo_request",
                 side_effect=EmailDeliveryError("Brevo API rejected request: HTTP 401"),
             ):
            with pytest.raises(EmailDeliveryError):
                email_service.send_email("to@confit.io", "S", "<p>h</p>", "t")

    def test_missing_key_is_a_configuration_error(self):
        from backend.app.services import email_service
        from backend.app.services.email_service import EmailDeliveryError

        with patch.object(email_service.settings, "EMAIL_PROVIDER", "brevo_api"), \
             patch.object(email_service.settings, "BREVO_API_KEY", None), \
             patch.object(email_service.settings, "EMAIL_FROM_ADDRESS", "sender@confit.io"):
            with pytest.raises(EmailDeliveryError, match="BREVO_API_KEY"):
                email_service.send_email("to@confit.io", "S", "<p>h</p>", "t")


class TestRenderer:
    def test_bilingual_link_free_code_email(self):
        from backend.app.services.email_service import render_mfa_code_email

        subject, html, text = render_mfa_code_email("Omar", "042531", 10)
        assert "042531" in html and "042531" in text
        # bilingual
        assert "رمز تسجيل الدخول" in subject
        assert "مرحبًا" in text and "Hello Omar" in text
        # the code block renders LTR inside the RTL-capable shell
        assert 'dir="ltr"' in html and 'dir="rtl"' in html
        # link-free by design
        assert "href" not in html.lower()
        assert "http" not in text
