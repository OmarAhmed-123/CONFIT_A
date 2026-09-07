"""Cycle 9 — authenticated password change (``POST /auth/change-password``).

Engineering defect this closes: the ONLY password-rotation path was the
email reset flow, which honestly 501s while no email provider is
provisioned — making the admin handover ("sign in once with the temporary
password, then change it") and any user's in-product rotation impossible.

Proves, per the remediation contract:
- re-authentication with the CURRENT password is required;
- MFA-enabled accounts must also pass a TOTP / recovery code;
- the new password must satisfy the Group-1 policy and differ from current;
- success revokes EVERY refresh session, audits ``USER_PASSWORD_CHANGED``,
  and rotates the credential (old fails login, new works);
- failures mutate nothing.
"""
import uuid

import pyotp
import pytest
from fastapi.testclient import TestClient

from backend.app.core.database import get_db
from backend.app.main import app
from backend.app.models.user import AuditLog, RefreshToken


def _db():
    return next(app.dependency_overrides[get_db]())


def _email() -> str:
    return f"cp-{uuid.uuid4().hex[:10]}@confit-test.io"


def _register(client: TestClient, email: str, password: str = "Password123!") -> str:
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Change Pw Test"},
    )
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


def _login(client: TestClient, email: str, password: str, mfa_code: str = None):
    payload = {"email": email, "password": password}
    if mfa_code is not None:
        payload["mfa_code"] = mfa_code
    return client.post("/api/v1/auth/login", json=payload)


def _change(client: TestClient, token: str, current: str, new: str, mfa_code: str = None):
    payload = {"current_password": current, "new_password": new}
    if mfa_code is not None:
        payload["mfa_code"] = mfa_code
    return client.post(
        "/api/v1/auth/change-password",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )


def _enroll_mfa(client: TestClient, token: str) -> str:
    r = client.post("/api/v1/auth/mfa/setup", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    secret = r.json()["secret"]
    r = client.post(
        "/api/v1/auth/mfa/verify",
        json={"code": pyotp.TOTP(secret).now()},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    return secret


def _user_id(email: str) -> int:
    from backend.app.models.user import User

    db = _db()
    try:
        return db.query(User).filter(User.email == email).one().id
    finally:
        db.close()


def test_requires_authentication(client: TestClient):
    r = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "Password123!", "new_password": "NewPassword456!"},
    )
    assert r.status_code == 401


def test_wrong_current_password_changes_nothing(client: TestClient):
    email = _email()
    token = _register(client, email)
    r = _change(client, token, current="WrongCurrent1!", new="NewPassword456!")
    assert r.status_code == 401
    assert "current password" in r.json()["error"]["message"].lower()
    # Nothing mutated: the real password still authenticates.
    assert _login(client, email, "Password123!").status_code == 200


def test_success_revokes_sessions_audits_and_rotates(client: TestClient):
    email = _email()
    token = _register(client, email)
    assert _login(client, email, "Password123!").status_code == 200

    r = _change(client, token, current="Password123!", new="NewPassword456!")
    assert r.status_code == 200, r.text
    assert "sign in again" in r.json()["message"]

    uid = _user_id(email)
    db = _db()
    try:
        live = (
            db.query(RefreshToken)
            .filter(RefreshToken.user_id == uid, RefreshToken.revoked_at.is_(None))
            .count()
        )
        assert live == 0, "every refresh session must be revoked on password change"
        audit = (
            db.query(AuditLog)
            .filter(AuditLog.user_id == uid, AuditLog.action == "USER_PASSWORD_CHANGED")
            .count()
        )
        assert audit == 1, "the change must be audited exactly once"
    finally:
        db.close()

    # Credential truly rotated: old rejected, new accepted.
    assert _login(client, email, "Password123!").status_code == 401
    ok = _login(client, email, "NewPassword456!")
    assert ok.status_code == 200


def test_weak_new_password_rejected(client: TestClient):
    email = _email()
    token = _register(client, email)
    # 9 chars but only one character category -> policy failure (422).
    r = _change(client, token, current="Password123!", new="passwords")
    assert r.status_code == 422
    assert _login(client, email, "Password123!").status_code == 200


def test_same_password_rejected(client: TestClient):
    email = _email()
    token = _register(client, email)
    r = _change(client, token, current="Password123!", new="Password123!")
    assert r.status_code == 422
    assert _login(client, email, "Password123!").status_code == 200


def test_mfa_user_requires_code(client: TestClient):
    email = _email()
    token = _register(client, email)
    _enroll_mfa(client, token)
    r = _change(client, token, current="Password123!", new="NewPassword456!")
    assert r.status_code == 401
    assert "mfa" in r.json()["error"]["message"].lower()


def test_mfa_user_rejects_bad_code(client: TestClient):
    email = _email()
    token = _register(client, email)
    _enroll_mfa(client, token)
    r = _change(client, token, current="Password123!", new="NewPassword456!", mfa_code="000000")
    assert r.status_code == 401
    assert _login(client, email, "Password123!", mfa_code=pyotp.TOTP(_secret_of(email)).now()).status_code == 200


def _secret_of(email: str) -> str:
    from backend.app.models.user import User

    db = _db()
    try:
        return db.query(User).filter(User.email == email).one().mfa_secret
    finally:
        db.close()


def test_mfa_user_with_totp_succeeds(client: TestClient):
    email = _email()
    token = _register(client, email)
    secret = _enroll_mfa(client, token)
    code = pyotp.TOTP(secret).now()
    r = _change(
        client, token, current="Password123!", new="NewPassword456!", mfa_code=code
    )
    assert r.status_code == 200, r.text
    # Old credential dead; new one works WITH a fresh MFA code.
    assert _login(client, email, "Password123!").status_code == 401
    ok = _login(client, email, "NewPassword456!", mfa_code=pyotp.TOTP(secret).now())
    assert ok.status_code == 200


def test_mfa_recovery_code_accepted_for_change(client: TestClient):
    """Recovery codes are a valid second factor for rotation too (login parity)."""
    email = _email()
    token = _register(client, email)
    r = client.post("/api/v1/auth/mfa/setup", headers={"Authorization": f"Bearer {token}"})
    secret = r.json()["secret"]
    r = client.post(
        "/api/v1/auth/mfa/verify",
        json={"code": pyotp.TOTP(secret).now()},
        headers={"Authorization": f"Bearer {token}"},
    )
    recovery = r.json()["backup_codes"][0]
    r = _change(
        client, token, current="Password123!", new="NewPassword456!", mfa_code=recovery
    )
    assert r.status_code == 200, r.text
    # Single-use: the burned recovery code must not work twice.
    token2 = _login(client, email, "NewPassword456!", mfa_code=pyotp.TOTP(secret).now()).json()["access_token"]
    r = _change(client, token2, current="NewPassword456!", new="FinalPassword789!", mfa_code=recovery)
    assert r.status_code == 401
