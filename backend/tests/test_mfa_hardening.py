"""MFA hardening regression suite — identity/MFA/data-rights audit remediation.

Closes the audit gaps in the MFA end-to-end path (audit 2026-09-21:
"لم أتحقق من نجاح MFA end-to-end") with executable proof:

1. TOTP secret is stored ENCRYPTED at rest (Fernet envelope ``enc:v1:``) —
   a stolen DB dump can no longer mint codes for every enrolled account.
   Legacy plaintext rows keep working (transparent fallback).
2. An accepted TOTP code cannot be REPLAYED inside its validity window —
   the accepted time-step is persisted and any code from a step <= it is
   rejected (OWASP MFA guidance).
3. Disabling MFA requires password AND a current TOTP/recovery code —
   password alone (the thing MFA exists to survive being stolen) is no
   longer sufficient.
4. ``/mfa/setup`` refuses to restart enrollment while MFA is enabled — a
   hijacked session can no longer silently rotate the secret and wipe the
   real owner's backup codes.
5. Full E2E: enroll -> verify -> wrong code rejected -> right code accepted
   (login) -> disable -> login without code works again.

Every test hits the real FastAPI app; nothing is mocked in the MFA path.
"""
from __future__ import annotations

import uuid

import pyotp
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.user import AuditLog, MFABackupCode, User
from backend.app.services.auth_service import AuthService
from backend.tests.conftest import TestingSessionLocal

client = TestClient(app)

PASSWORD = "Password123!"


def _email() -> str:
    return f"mfah-{uuid.uuid4().hex[:10]}@confit-testing.example.com"


def _register(email: str) -> str:
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "MFA Hardening Test"},
    )
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


def _login(email: str, mfa_code: str | None = None):
    payload = {"email": email, "password": PASSWORD}
    if mfa_code is not None:
        payload["mfa_code"] = mfa_code
    return client.post("/api/v1/auth/login", json=payload)


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _enroll(token: str) -> tuple[str, list[str]]:
    r = client.post("/api/v1/auth/mfa/setup", headers=_hdr(token))
    assert r.status_code == 200, r.text
    secret = r.json()["secret"]
    r = client.post(
        "/api/v1/auth/mfa/verify",
        json={"code": pyotp.TOTP(secret).now()},
        headers=_hdr(token),
    )
    assert r.status_code == 200, r.text
    return secret, r.json()["backup_codes"]


def _advance_totp_window(email: str) -> None:
    """Equivalent to waiting 30 s for the next TOTP period (see docstring in
    test_auth_change_password). The replay test does NOT use this."""
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == email).one()
        db.query(AuditLog).filter(
            AuditLog.user_id == user.id,
            AuditLog.action == AuthService._MFA_STEP_ACTION,
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


# =============================================================================
# 1. Secret encrypted at rest
# =============================================================================
def test_totp_secret_stored_encrypted_at_rest():
    email = _email()
    token = _register(email)
    r = client.post("/api/v1/auth/mfa/setup", headers=_hdr(token))
    assert r.status_code == 200
    plaintext_secret = r.json()["secret"]

    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == email).one()
        stored = user.mfa_secret
        # Envelope format, never the raw base32 secret.
        assert stored.startswith("enc:v1:"), f"secret not enveloped: {stored[:20]}"
        assert plaintext_secret not in stored
        # The service accessor round-trips back to the real secret.
        assert AuthService(db)._load_mfa_secret(user) == plaintext_secret
    finally:
        db.close()


def test_legacy_plaintext_secret_still_verifies():
    """Rows written before the encryption change (raw base32) keep working."""
    email = _email()
    token = _register(email)
    secret = pyotp.random_base32()

    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == email).one()
        user.mfa_secret = secret  # legacy: plaintext, no envelope
        user.mfa_enabled = True
        db.commit()
    finally:
        db.close()

    r = _login(email, mfa_code=pyotp.TOTP(secret).now())
    assert r.status_code == 200, r.text


# =============================================================================
# 2. TOTP replay protection
# =============================================================================
def test_totp_code_cannot_be_replayed_within_window():
    email = _email()
    token = _register(email)
    secret, _codes = _enroll(token)
    _advance_totp_window(email)

    code = pyotp.TOTP(secret).now()
    first = _login(email, mfa_code=code)
    assert first.status_code == 200, first.text

    # Same code, same window — MUST be rejected (replay).
    second = _login(email, mfa_code=code)
    assert second.status_code == 401, (
        "replayed TOTP code was accepted — replay guard is not effective"
    )


def test_enrollment_code_cannot_be_replayed_at_login():
    """The code consumed by /mfa/verify must not immediately re-authenticate."""
    email = _email()
    token = _register(email)
    r = client.post("/api/v1/auth/mfa/setup", headers=_hdr(token))
    secret = r.json()["secret"]
    code = pyotp.TOTP(secret).now()
    r = client.post("/api/v1/auth/mfa/verify", json={"code": code}, headers=_hdr(token))
    assert r.status_code == 200
    # Same code replayed on the login surface.
    r = _login(email, mfa_code=code)
    assert r.status_code == 401


# =============================================================================
# 3. Disable requires password AND a current code
# =============================================================================
def test_disable_mfa_password_alone_is_rejected():
    email = _email()
    token = _register(email)
    _enroll(token)

    r = client.post(
        "/api/v1/auth/mfa/disable",
        json={"password": PASSWORD},
        headers=_hdr(token),
    )
    assert r.status_code == 401
    assert r.json()["error"]["details"].get("reason") == "MFA_CODE_REQUIRED"

    # MFA must still be enabled after the refused attempt.
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == email).one()
        assert user.mfa_enabled is True
        assert user.mfa_secret is not None
    finally:
        db.close()


def test_disable_mfa_with_wrong_code_rejected_with_totp_succeeds():
    email = _email()
    token = _register(email)
    secret, _ = _enroll(token)

    r = client.post(
        "/api/v1/auth/mfa/disable",
        json={"password": PASSWORD, "mfa_code": "000000"},
        headers=_hdr(token),
    )
    assert r.status_code == 401

    _advance_totp_window(email)
    r = client.post(
        "/api/v1/auth/mfa/disable",
        json={"password": PASSWORD, "mfa_code": pyotp.TOTP(secret).now()},
        headers=_hdr(token),
    )
    assert r.status_code == 200, r.text

    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == email).one()
        assert user.mfa_enabled is False
        assert user.mfa_secret is None  # purged
        remaining = db.query(MFABackupCode).filter(MFABackupCode.user_id == user.id).count()
        assert remaining == 0  # backup codes purged
    finally:
        db.close()


def test_disable_mfa_accepts_recovery_code():
    email = _email()
    token = _register(email)
    _secret, codes = _enroll(token)

    r = client.post(
        "/api/v1/auth/mfa/disable",
        json={"password": PASSWORD, "mfa_code": codes[0]},
        headers=_hdr(token),
    )
    assert r.status_code == 200, r.text


# =============================================================================
# 4. Setup refuses to restart enrollment while enabled
# =============================================================================
def test_setup_refused_while_mfa_enabled_secret_not_rotated():
    email = _email()
    token = _register(email)
    secret, codes = _enroll(token)

    r = client.post("/api/v1/auth/mfa/setup", headers=_hdr(token))
    assert r.status_code == 422, (
        "setup restarted while MFA was enabled — hijacked-session secret "
        "rotation is possible again"
    )

    # Secret unchanged and backup codes untouched.
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == email).one()
        assert AuthService(db)._load_mfa_secret(user) == secret
        remaining = (
            db.query(MFABackupCode)
            .filter(MFABackupCode.user_id == user.id, MFABackupCode.used_at.is_(None))
            .count()
        )
        assert remaining == len(codes)
    finally:
        db.close()


# =============================================================================
# 5. Full E2E lifecycle
# =============================================================================
def test_mfa_full_lifecycle_end_to_end():
    email = _email()
    token = _register(email)

    # Enroll + verify.
    secret, backup_codes = _enroll(token)
    assert len(backup_codes) == 10

    # Login without a code -> explicit MFA_REQUIRED challenge.
    r = _login(email)
    assert r.status_code == 401
    assert r.json()["error"]["details"].get("reason") == "MFA_REQUIRED"

    # Wrong code -> rejected.
    r = _login(email, mfa_code="000000")
    assert r.status_code == 401

    # Correct code -> session established.
    _advance_totp_window(email)
    r = _login(email, mfa_code=pyotp.TOTP(secret).now())
    assert r.status_code == 200, r.text
    fresh_token = r.json()["access_token"]

    # Disable (password + fresh code) -> login works without a code again.
    _advance_totp_window(email)
    r = client.post(
        "/api/v1/auth/mfa/disable",
        json={"password": PASSWORD, "mfa_code": pyotp.TOTP(secret).now()},
        headers=_hdr(fresh_token),
    )
    assert r.status_code == 200, r.text
    r = _login(email)
    assert r.status_code == 200

    # Audit trail: MFA_ENABLED and MFA_DISABLED both recorded, and the
    # step-acceptance rows never contain the secret or a code.
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == email).one()
        actions = {
            a.action
            for a in db.query(AuditLog).filter(AuditLog.user_id == user.id).all()
        }
        assert "MFA_ENABLED" in actions
        assert "MFA_DISABLED" in actions
        for row in db.query(AuditLog).filter(
            AuditLog.user_id == user.id,
            AuditLog.action == AuthService._MFA_STEP_ACTION,
        ):
            assert secret not in (row.resource_id or "")
            assert row.resource_id.isdigit()  # a time-step counter, nothing else
    finally:
        db.close()
