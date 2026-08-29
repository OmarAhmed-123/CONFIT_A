"""Group 1 (User Identity & Profile Management) — end-to-end integration tests.

Every test hits the real FastAPI app against a real SQLite test DB.
External OAuth providers are mocked ONLY at the httpx boundary — the
Group 1 code path itself is executed real.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import httpx
import pytest
import pyotp
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.database import get_db
from backend.app.core.security import (
    encrypt_sensitive_data,
    decrypt_sensitive_data,
    validate_password_policy,
)
from backend.app.core.exceptions import EncryptionError, ValidationDomainError
from backend.app.models.profile import UserStyleProfile
from backend.app.models.user import (
    User,
    RefreshToken,
    MFABackupCode,
    PasswordResetToken,
)
from backend.tests.conftest import TestingSessionLocal


client = TestClient(app)


def _unique_email() -> str:
    return f"g1_{uuid.uuid4().hex[:8]}@confit-testing.example.com"


def _fresh_client() -> TestClient:
    """A TestClient with no cookies — auth endpoints then bypass the CSRF
    middleware, which only fires when a session cookie is present."""
    return TestClient(app)


def _register(email: str, password: str = "StrongPassw0rd!") -> dict:
    c = _fresh_client()
    r = c.post("/api/v1/auth/register", json={
        "email": email,
        "password": password,
        "full_name": "G1 Test User",
    })
    assert r.status_code == 201, r.text
    return r.json()


def _login(email: str, password: str = "StrongPassw0rd!", mfa_code: str | None = None):
    c = _fresh_client()
    body = {"email": email, "password": password}
    if mfa_code is not None:
        body["mfa_code"] = mfa_code
    return c.post("/api/v1/auth/login", json=body)


# =============================================================================
# 1. Authentication BLOCKING fixes
# =============================================================================
def test_profile_me_requires_auth_no_anonymous_fallback_to_user_1():
    """Regression for G1.SEC-01. Anonymous /profile/me MUST 401, not silently
    return user #1's USP with decrypted body attributes."""
    # No auth headers, fresh cookie jar
    fresh = TestClient(app)
    res = fresh.get("/api/v1/profile/me")
    assert res.status_code == 401
    # And onboarding-quiz POST must also 401 for guests
    res2 = fresh.post("/api/v1/profile/onboarding-quiz", json={"style_archetypes": ["Minimalist"]})
    assert res2.status_code in (401, 422)  # 422 if body fails validation before auth check


def test_profile_me_cross_user_isolation():
    """User A must never see User B's USP."""
    email_a = _unique_email()
    email_b = _unique_email()
    _register(email_a)
    _register(email_b)

    login_a = _login(email_a).json()
    login_b = _login(email_b).json()

    # A submits an onboarding profile
    client.post(
        "/api/v1/profile/onboarding-quiz",
        headers={"Authorization": f"Bearer {login_a['access_token']}"},
        json={"style_archetypes": ["Minimalist"], "preferred_colors": ["Navy"]},
    )
    # B fetches /profile/me — must be their OWN state (not_completed), not A's
    r = client.get(
        "/api/v1/profile/me",
        headers={"Authorization": f"Bearer {login_b['access_token']}"},
    )
    assert r.status_code == 200
    data = r.json()
    # Either the not_completed stub or an empty USP with B's user_id — but
    # NEVER A's archetypes.
    if "state" in data:
        assert data["state"] == "not_completed"
    else:
        assert "Minimalist" not in data.get("style_archetypes", [])


def test_password_policy_enforced_server_side():
    weak_passwords = ["short", "alllowercase", "ALLUPPERCASE", "12345678", "Password"]
    for pw in weak_passwords:
        r = client.post("/api/v1/auth/register", json={
            "email": _unique_email(),
            "password": pw,
            "full_name": "Weak PW",
        })
        assert r.status_code == 422, f"expected 422 for {pw!r}, got {r.status_code} {r.text}"


def test_get_profile_me_returns_not_completed_for_fresh_user_no_write():
    """G1.STY-05 regression: GET /profile/me must NOT silently create a
    fabricated USP row on a missing profile."""
    email = _unique_email()
    _register(email)
    token = _login(email).json()["access_token"]

    r = client.get("/api/v1/profile/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("state") == "not_completed"

    # Confirm no USP row was created — a second GET must still return the stub.
    r2 = client.get("/api/v1/profile/me", headers={"Authorization": f"Bearer {token}"})
    assert r2.json().get("state") == "not_completed"


# =============================================================================
# 2. Decrypt failure never leaks ciphertext
# =============================================================================
def test_decrypt_wrong_key_raises_encryption_error_not_returns_ciphertext():
    """G1.BODY-02: the previous implementation silently returned the
    ciphertext on failure. The new one raises."""
    # Structurally invalid ciphertext — Fernet must reject and we must NOT
    # get the input string back.
    junk = "not-a-real-fernet-ciphertext-XXXXXX"
    with pytest.raises(EncryptionError):
        decrypt_sensitive_data(junk)


def test_body_attributes_roundtrip_encrypted():
    email = _unique_email()
    _register(email)
    token = _login(email).json()["access_token"]

    r = client.post(
        "/api/v1/profile/onboarding-quiz",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "style_archetypes": ["Minimalist"],
            "body_attributes": {"height_cm": 180.0, "weight_kg": 75.0, "body_shape": "Athletic"},
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["body_attributes"]["height_cm"] == 180.0
    assert data["body_attributes"]["is_encrypted"] is True

    # And on disk it really IS encrypted (raw column is not the plaintext)
    db = TestingSessionLocal()
    usp = db.query(UserStyleProfile).join(User, User.id == UserStyleProfile.user_id).filter(User.email == email).first()
    assert usp is not None
    assert usp.encrypted_body_data is not None
    assert "180" not in usp.encrypted_body_data  # ciphertext must not contain the plaintext number
    db.close()


def test_body_attributes_delete_flow():
    email = _unique_email()
    _register(email)
    token = _login(email).json()["access_token"]
    hdr = {"Authorization": f"Bearer {token}"}

    client.post("/api/v1/profile/onboarding-quiz", headers=hdr, json={
        "body_attributes": {"height_cm": 175.0, "body_shape": "Rectangle"},
    })
    r = client.delete("/api/v1/me/body-profile", headers=hdr)
    assert r.status_code == 200
    r = client.get("/api/v1/profile/me", headers=hdr)
    assert r.status_code == 200
    assert r.json().get("body_attributes") is None


def test_body_step_optional_no_fabricated_defaults():
    """G1.BODY-01: a user who skips the body step must NOT have body
    measurements written to their profile."""
    email = _unique_email()
    _register(email)
    token = _login(email).json()["access_token"]
    client.post(
        "/api/v1/profile/onboarding-quiz",
        headers={"Authorization": f"Bearer {token}"},
        json={"style_archetypes": ["Minimalist"], "preferred_colors": ["Navy"]},
    )
    r = client.get("/api/v1/profile/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json().get("body_attributes") is None


# =============================================================================
# 3. Real consent persistence
# =============================================================================
def test_consent_get_and_patch_persist_to_db():
    email = _unique_email()
    _register(email)
    token = _login(email).json()["access_token"]
    hdr = {"Authorization": f"Bearer {token}"}

    r = client.get("/api/v1/me/consents", headers=hdr)
    assert r.status_code == 200
    initial = r.json()
    # Default share_with_brands should be False (privacy-first)
    assert initial["share_with_brands"] is False

    r = client.patch("/api/v1/me/consents", headers=hdr, json={
        "share_with_brands": True,
        "marketing_analytics": True,
    })
    assert r.status_code == 200
    updated = r.json()
    assert updated["share_with_brands"] is True
    assert updated["marketing_analytics"] is True

    # New client, same auth — must read the persisted value back
    r2 = client.get("/api/v1/me/consents", headers=hdr)
    assert r2.json()["share_with_brands"] is True


# =============================================================================
# 4. Social login refuses client-supplied identity, verifies real tokens
# =============================================================================
def test_social_login_google_not_configured_501():
    """Without GOOGLE_OAUTH_CLIENT_ID configured, the endpoint must 501,
    NEVER accept a client-supplied identity as valid."""
    with patch.object(app.state, "limiter", app.state.limiter):
        pass
    r = client.post("/api/v1/auth/social-login", json={
        "provider": "google",
        "provider_token": "fake_id_token",
    })
    assert r.status_code == 501
    assert r.json()["error"]["code"] == "FEATURE_NOT_CONFIGURED"


def test_social_login_google_success_with_mocked_provider():
    from backend.app.core.config import settings as _settings
    _settings.GOOGLE_OAUTH_CLIENT_ID = "test-google-client-id"
    try:
        google_sub = f"google-sub-{uuid.uuid4().hex[:8]}"
        exp_ts = int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp())
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "aud": "test-google-client-id",
            "iss": "accounts.google.com",
            "exp": exp_ts,
            "sub": google_sub,
            "email": f"g1social_{google_sub[:6]}@confit-testing.example.com",
            "email_verified": "true",
            "name": "Google Tester",
        }
        with patch("backend.app.services.auth_service.httpx.get", return_value=mock_resp):
            r = client.post("/api/v1/auth/social-login", json={
                "provider": "google",
                "provider_token": "any-token-we-mocked",
            })
        assert r.status_code == 200, r.text
        assert "access_token" in r.json()
        assert r.json()["user"]["email"].endswith("@confit-testing.example.com")
    finally:
        _settings.GOOGLE_OAUTH_CLIENT_ID = None


def test_social_login_ignores_client_supplied_email():
    """A client that sends email/full_name alongside provider_token gets
    the identity from the PROVIDER (mocked), never from the request body."""
    from backend.app.core.config import settings as _settings
    _settings.GOOGLE_OAUTH_CLIENT_ID = "test-google-client-id"
    try:
        google_sub = f"google-sub-{uuid.uuid4().hex[:8]}"
        exp_ts = int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp())
        provider_email = f"real_{google_sub[:6]}@confit-testing.example.com"
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "aud": "test-google-client-id",
            "iss": "accounts.google.com",
            "exp": exp_ts,
            "sub": google_sub,
            "email": provider_email,
            "email_verified": "true",
        }
        with patch("backend.app.services.auth_service.httpx.get", return_value=mock_resp):
            c = _fresh_client()
            # Attacker-shaped body: try to inject admin@confit.io
            r = c.post("/api/v1/auth/social-login", json={
                "provider": "google",
                "provider_token": "any-mocked-token-long-enough",
                # These extra fields were the bug — they must be IGNORED
                "email": "admin@confit.io",
                "full_name": "Admin Attacker",
            })
        assert r.status_code == 200
        assert r.json()["user"]["email"] == provider_email
        assert r.json()["user"]["email"] != "admin@confit.io"
    finally:
        _settings.GOOGLE_OAUTH_CLIENT_ID = None


# =============================================================================
# 5. Refresh token rotation + reuse detection
# =============================================================================
def test_refresh_token_rotation_and_reuse_detection():
    email = _unique_email()
    login = _register(email)  # returns tokens
    c = _fresh_client()

    old_refresh = login["refresh_token"]
    r = c.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert r.status_code == 200, r.text
    new_refresh = r.json()["refresh_token"]
    assert new_refresh != old_refresh

    # Reuse the OLD refresh token — must be rejected and revoke the family.
    c2 = _fresh_client()
    r_reuse = c2.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert r_reuse.status_code == 401

    # The NEW refresh token was in the same family, so it too is now revoked.
    c3 = _fresh_client()
    r_new = c3.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh})
    assert r_new.status_code == 401


def test_logout_revokes_refresh_token():
    email = _unique_email()
    login = _register(email)
    hdr = {"Authorization": f"Bearer {login['access_token']}"}
    c = _fresh_client()
    r_out = c.post("/api/v1/auth/logout", headers=hdr, json={"refresh_token": login["refresh_token"]})
    assert r_out.status_code == 200
    # That refresh token must now fail
    c2 = _fresh_client()
    r = c2.post("/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert r.status_code == 401


# =============================================================================
# 6. MFA — real backup codes, rate limit, disable
# =============================================================================
def test_mfa_setup_verify_backup_codes_are_random_and_hashed():
    email = _unique_email()
    _register(email)
    token = _login(email).json()["access_token"]
    hdr = {"Authorization": f"Bearer {token}"}

    setup = client.post("/api/v1/auth/mfa/setup", headers=hdr).json()
    secret = setup["secret"]
    assert setup["backup_codes"] == []  # not issued until verify

    totp = pyotp.TOTP(secret)
    verify = client.post("/api/v1/auth/mfa/verify", headers=hdr, json={"code": totp.now()})
    assert verify.status_code == 200
    codes = verify.json()["backup_codes"]
    assert len(codes) == 10
    # Codes must be unique and follow the CONFIT-XXXX-XXXX shape
    assert len(set(codes)) == 10
    for c in codes:
        assert c.startswith("CONFIT-")
        # Format: CONFIT-XXXX-XXXX -> 7 + 4 + 1 + 4 = 16 chars
        assert len(c) == 16

    # DB rows must be BCRYPT-HASHED, not plaintext codes
    db = TestingSessionLocal()
    user = db.query(User).filter(User.email == email).first()
    rows = db.query(MFABackupCode).filter(MFABackupCode.user_id == user.id).all()
    assert len(rows) == 10
    for row in rows:
        assert row.code_hash not in codes  # never plaintext
        assert row.code_hash.startswith("$2b$") or row.code_hash.startswith("$2a$") or row.code_hash.startswith("$2y$")
    db.close()


def test_mfa_login_challenge_flow_and_backup_code_single_use():
    email = _unique_email()
    _register(email)
    token = _login(email).json()["access_token"]
    hdr = {"Authorization": f"Bearer {token}"}

    setup = client.post("/api/v1/auth/mfa/setup", headers=hdr).json()
    totp = pyotp.TOTP(setup["secret"])
    verify = client.post("/api/v1/auth/mfa/verify", headers=hdr, json={"code": totp.now()})
    backup_codes = verify.json()["backup_codes"]

    # Login without MFA code -> 401 with MFA_REQUIRED marker
    r = _login(email)
    assert r.status_code == 401
    body = r.json()
    assert body["error"]["code"] == "AUTH_FAILED"
    assert body["error"]["details"].get("reason") == "MFA_REQUIRED"

    # Login with a backup code -> success
    code = backup_codes[0]
    r = _login(email, mfa_code=code)
    assert r.status_code == 200

    # Reusing the same backup code -> failure (single-use)
    r = _login(email, mfa_code=code)
    assert r.status_code == 401


# =============================================================================
# 7. Forgot password — 501 without email provider
# =============================================================================
def test_forgot_password_501_without_email_provider():
    email = _unique_email()
    _register(email)
    c = _fresh_client()
    r = c.post("/api/v1/auth/forgot-password", json={"email": email})
    assert r.status_code == 501
    assert r.json()["error"]["code"] == "FEATURE_NOT_CONFIGURED"


# =============================================================================
# 8. Onboarding partial + resume
# =============================================================================
def test_onboarding_partial_then_completion_persists():
    email = _unique_email()
    _register(email)
    token = _login(email).json()["access_token"]
    hdr = {"Authorization": f"Bearer {token}"}

    # Partial: only styles + colors on first save
    r = client.post("/api/v1/profile/onboarding-quiz", headers=hdr, json={
        "style_archetypes": ["Minimalist", "Classic"],
        "preferred_colors": ["Navy", "Beige"],
    })
    assert r.status_code == 200
    assert r.json()["onboarding_completed"] is True  # onboarding endpoint completes

    # Later, patch just brands — must not clobber the styles.
    r2 = client.patch("/api/v1/me/brands", headers=hdr, json={
        "preferred_brands": ["COS", "Arket"],
        "blacklisted_brands": ["Shein"],
    })
    assert r2.status_code == 200
    data = r2.json()
    assert data["preferred_brands"] == ["COS", "Arket"]
    assert data["blacklisted_brands"] == ["Shein"]
    assert set(data["style_archetypes"]) == {"Minimalist", "Classic"}  # untouched


# =============================================================================
# 9. Server-side style validation
# =============================================================================
def test_server_side_style_validation_rejects_unknown_values():
    email = _unique_email()
    _register(email)
    token = _login(email).json()["access_token"]
    hdr = {"Authorization": f"Bearer {token}"}

    r = client.post("/api/v1/profile/onboarding-quiz", headers=hdr, json={
        "style_archetypes": ["Not A Real Archetype"],
    })
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


# =============================================================================
# 10. GDPR export uses COUNT(*) and real timestamp
# =============================================================================
def test_gdpr_export_real_timestamp_and_counts():
    email = _unique_email()
    _register(email)
    token = _login(email).json()["access_token"]
    hdr = {"Authorization": f"Bearer {token}"}
    r = client.get("/api/v1/auth/gdpr-export", headers=hdr)
    assert r.status_code == 200
    body = r.json()
    # exported_at must be recent — within the last few seconds of NOW.
    exported_at = datetime.fromisoformat(body["exported_at"].replace("Z", "+00:00"))
    assert (datetime.now(timezone.utc) - exported_at) < timedelta(seconds=30)
    assert body["wardrobe_items_count"] == 0
    assert body["orders_count"] == 0


# =============================================================================
# 11. Mood boards CRUD + ownership isolation
# =============================================================================
def test_mood_board_crud_and_cross_user_isolation():
    email_a = _unique_email()
    email_b = _unique_email()
    _register(email_a)
    _register(email_b)
    token_a = _login(email_a).json()["access_token"]
    token_b = _login(email_b).json()["access_token"]

    hdr_a = {"Authorization": f"Bearer {token_a}"}
    hdr_b = {"Authorization": f"Bearer {token_b}"}

    # A creates a board
    r = client.post("/api/v1/me/mood-boards", headers=hdr_a, json={"title": "Autumn palette"})
    assert r.status_code == 201, r.text
    board_id = r.json()["id"]

    # A adds a URL item
    r = client.post(f"/api/v1/me/mood-boards/{board_id}/items", headers=hdr_a, json={
        "kind": "url",
        "payload": {"url": "https://example.com/inspo.jpg"},
    })
    assert r.status_code == 201
    assert len(r.json()["items"]) == 1

    # A renames
    r = client.patch(f"/api/v1/me/mood-boards/{board_id}", headers=hdr_a, json={"title": "Autumn 2026"})
    assert r.status_code == 200
    assert r.json()["title"] == "Autumn 2026"

    # B tries to read/update/delete A's board — must 403
    r = client.get(f"/api/v1/me/mood-boards/{board_id}", headers=hdr_b)
    assert r.status_code == 403
    r = client.patch(f"/api/v1/me/mood-boards/{board_id}", headers=hdr_b, json={"title": "hijacked"})
    assert r.status_code == 403
    r = client.delete(f"/api/v1/me/mood-boards/{board_id}", headers=hdr_b)
    assert r.status_code == 403

    # B's list is empty (no cross-user leak)
    r = client.get("/api/v1/me/mood-boards", headers=hdr_b)
    assert r.status_code == 200
    assert r.json() == []

    # A lists — one board there
    r = client.get("/api/v1/me/mood-boards", headers=hdr_a)
    assert r.status_code == 200
    assert len(r.json()) == 1

    # A deletes
    r = client.delete(f"/api/v1/me/mood-boards/{board_id}", headers=hdr_a)
    assert r.status_code == 200


def test_mood_board_url_item_rejects_non_http():
    email = _unique_email()
    _register(email)
    token = _login(email).json()["access_token"]
    hdr = {"Authorization": f"Bearer {token}"}
    r = client.post("/api/v1/me/mood-boards", headers=hdr, json={"title": "T"})
    board_id = r.json()["id"]
    r = client.post(f"/api/v1/me/mood-boards/{board_id}/items", headers=hdr, json={
        "kind": "url", "payload": {"url": "javascript:alert(1)"},
    })
    assert r.status_code == 422


# =============================================================================
# 12. Account deletion is FK-safe (anonymizes orders/tryon/stylist)
# =============================================================================
def test_account_deletion_succeeds_even_with_business_history():
    """Regression for G1.AUTH-07. In the old code, DELETE /auth/account
    would FK-fail on Postgres for a user who had orders. The new code
    anonymizes those rows (user_id -> NULL) before deleting the user.
    """
    email = _unique_email()
    _register(email)
    login = _login(email).json()
    hdr = {"Authorization": f"Bearer {login['access_token']}", "X-Session-Token": "acctdel-test"}

    # Add an order via the checkout flow so there's history to anonymize
    client.post("/api/v1/commerce/cart/items", headers=hdr, json={"product_sku_id": 1, "quantity": 1})
    ck = client.post("/api/v1/commerce/checkout", headers=hdr, json={
        "payment_method": "bnpl_tabby",
        "fulfillment_type": "delivery",
        "recipient_name": "G1 Test",
        "phone": "+971500000000",
        "address_line": "1 Test St",
        "city": "Dubai",
        "country": "UAE",
    })
    assert ck.status_code == 200

    r = client.delete("/api/v1/auth/account", headers=hdr)
    assert r.status_code == 200
    # And a subsequent /auth/me with that token must fail
    r2 = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {login['access_token']}"})
    assert r2.status_code == 401
