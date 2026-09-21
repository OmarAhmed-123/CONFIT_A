"""Authorization & data-ownership matrix — identity scope (gap-closure round 2).

The 2026-09-21 audit asked for a systematic proof that "authenticated users
can access ONLY their own data" and that a consumer cannot escalate. IDOR
tests existed for try-on/measurement sessions, but no single suite covered
the identity/profile scope end-to-end. This is that suite.

Matrix:
  A. Same-user access works (control group — proves the tests can pass).
  B. Cross-user: A can never read/modify B's profile, consents, body data,
     mood boards, export, or delete B's account. Where the API takes an id
     (mood boards), a foreign id must 404/403 — never leak.
  C. Role escalation: a consumer cannot self-promote via register payload,
     profile PATCH, or a forged-role token claim; consumer tokens are
     refused by admin and brand endpoints.
  D. Deletion step-up: no deletion on session alone; wrong password
     refused; wrong confirm refused; MFA users must present a code;
     success invalidates the session AND the refresh token; the account
     is gone (idempotent second call is 401, login is 401).

All requests are direct API calls — no frontend involved. Nothing in the
authorization path is mocked.
"""
from __future__ import annotations

import uuid

import pyotp
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.user import AuditLog, MFABackupCode, RefreshToken, User
from backend.app.models.profile import UserStyleProfile
from backend.app.services.auth_service import AuthService
from backend.tests.conftest import TestingSessionLocal

PASSWORD = "StrongPassw0rd!"


def _fresh() -> TestClient:
    # A fresh client per actor: no cookie bleed between identities.
    return TestClient(app)


def _email() -> str:
    return f"authz-{uuid.uuid4().hex[:10]}@confit-testing.example.com"


def _register(client: TestClient, email: str, **extra) -> dict:
    r = client.post("/api/v1/auth/register", json={
        "email": email, "password": PASSWORD, "full_name": "Authz Matrix", **extra,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _user_id(email: str) -> int:
    db = TestingSessionLocal()
    try:
        return db.query(User).filter(User.email == email).one().id
    finally:
        db.close()


# =============================================================================
# A. Same-user control group
# =============================================================================
def test_same_user_full_profile_lifecycle():
    c = _fresh()
    email = _email()
    tok = _register(c, email)["access_token"]

    r = c.get("/api/v1/auth/me", headers=_hdr(tok))
    assert r.status_code == 200 and r.json()["email"] == email

    r = c.patch("/api/v1/me/profile", headers=_hdr(tok),
                json={"full_name": "Updated Name", "phone": "+20 100 123-4567"})
    assert r.status_code == 200 and r.json()["updated"] is True

    r = c.get("/api/v1/auth/me", headers=_hdr(tok))
    assert r.json()["full_name"] == "Updated Name"
    assert r.json()["phone"] == "+201001234567"  # normalized


def test_me_profile_patch_validation_enforced():
    c = _fresh()
    tok = _register(c, _email())["access_token"]

    # Oversized full_name: must be a 422, not a DB error.
    r = c.patch("/api/v1/me/profile", headers=_hdr(tok),
                json={"full_name": "x" * 5000})
    assert r.status_code == 422

    # Blank name refused.
    r = c.patch("/api/v1/me/profile", headers=_hdr(tok), json={"full_name": "   "})
    assert r.status_code == 422

    # Junk phone refused.
    r = c.patch("/api/v1/me/profile", headers=_hdr(tok), json={"phone": "not-a-phone"})
    assert r.status_code == 422

    # Unsupported language refused.
    r = c.patch("/api/v1/me/profile", headers=_hdr(tok), json={"preferred_language": "xx"})
    assert r.status_code == 422


def test_me_profile_patch_privileged_keys_ignored():
    c = _fresh()
    email = _email()
    tok = _register(c, email)["access_token"]
    r = c.patch("/api/v1/me/profile", headers=_hdr(tok), json={
        "role": "admin", "is_active": False, "is_verified": True,
        "id": 1, "email": "hijack@example.com", "full_name": "Legit",
    })
    assert r.status_code == 200
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == email).one()
        assert user.role.value == "consumer"      # not escalated
        assert user.is_active is True             # not deactivated
        assert user.email == email                # not hijacked
        assert user.full_name == "Legit"          # allowed field applied
    finally:
        db.close()


# =============================================================================
# B. Cross-user isolation
# =============================================================================
def test_cross_user_profile_and_export_isolation():
    ca, cb = _fresh(), _fresh()
    email_a, email_b = _email(), _email()
    tok_a = _register(ca, email_a)["access_token"]
    tok_b = _register(cb, email_b)["access_token"]

    # B onboards with distinctive data.
    r = cb.post("/api/v1/profile/onboarding-quiz", headers=_hdr(tok_b), json={
        "style_archetypes": ["Classic"],
        "body_attributes": {"height_cm": 199, "weight_kg": 99},
    })
    assert r.status_code == 200

    # A's profile view NEVER contains B's data.
    r = ca.get("/api/v1/profile/me", headers=_hdr(tok_a))
    assert r.status_code == 200
    assert r.json().get("state") == "not_completed"  # A never onboarded

    # A's export contains nothing of B.
    r = ca.get("/api/v1/auth/gdpr-export", headers=_hdr(tok_a))
    body = r.text
    assert email_b not in body
    assert "199" not in str(r.json()["data"].get("profile"))


def test_cross_user_mood_board_id_manipulation():
    ca, cb = _fresh(), _fresh()
    tok_a = _register(ca, _email())["access_token"]
    tok_b = _register(cb, _email())["access_token"]

    # B creates a board; A tries to read/write/delete it by id.
    r = cb.post("/api/v1/me/mood-boards", headers=_hdr(tok_b), json={"title": "B private"})
    assert r.status_code in (200, 201), r.text
    board_id = r.json()["id"]

    assert ca.get(f"/api/v1/me/mood-boards/{board_id}", headers=_hdr(tok_a)).status_code in (403, 404)
    assert ca.patch(f"/api/v1/me/mood-boards/{board_id}", headers=_hdr(tok_a),
                    json={"title": "hacked"}).status_code in (403, 404, 405)
    assert ca.delete(f"/api/v1/me/mood-boards/{board_id}", headers=_hdr(tok_a)).status_code in (403, 404)

    # B's board is intact.
    r = cb.get(f"/api/v1/me/mood-boards/{board_id}", headers=_hdr(tok_b))
    assert r.status_code == 200 and r.json()["title"] == "B private"


def test_cross_user_deletion_impossible_by_construction():
    """The deletion surface takes NO target id — user comes from the JWT.
    A's step-up-valid delete removes A only; B is untouched."""
    ca, cb = _fresh(), _fresh()
    email_a, email_b = _email(), _email()
    tok_a = _register(ca, email_a)["access_token"]
    _register(cb, email_b)
    id_b = _user_id(email_b)

    r = ca.request("DELETE", "/api/v1/auth/account", headers=_hdr(tok_a),
                   json={"confirm": "DELETE", "password": PASSWORD})
    assert r.status_code == 200

    db = TestingSessionLocal()
    try:
        assert db.query(User).filter(User.email == email_a).first() is None
        b = db.query(User).filter(User.id == id_b).one()
        assert b.email == email_b and b.is_active is True
    finally:
        db.close()


# =============================================================================
# C. Role escalation
# =============================================================================
def test_register_role_injection_ignored():
    c = _fresh()
    email = _email()
    _register(c, email, role="admin", is_admin=True)
    db = TestingSessionLocal()
    try:
        assert db.query(User).filter(User.email == email).one().role.value == "consumer"
    finally:
        db.close()


def test_consumer_token_refused_by_admin_and_brand_endpoints():
    c = _fresh()
    tok = _register(c, _email())["access_token"]
    for path in ("/api/v1/admin/analytics", "/api/v1/admin/users",
                 "/api/v1/brand/analytics", "/api/v1/brand/products"):
        r = c.get(path, headers=_hdr(tok))
        assert r.status_code in (403, 404, 405), (
            f"consumer token was not refused by {path}: {r.status_code}"
        )
        assert r.status_code != 200


def test_forged_role_claim_does_not_escalate():
    """A token whose payload claims role=admin but whose subject is a
    consumer must not open admin endpoints: authorization reads the DB row
    via get_current_user, never the token claim."""
    from backend.app.core.security import create_access_token

    c = _fresh()
    email = _email()
    _register(c, email)
    uid = _user_id(email)
    forged = create_access_token({"sub": str(uid), "email": email, "role": "admin"})
    r = c.get("/api/v1/admin/analytics", headers=_hdr(forged))
    assert r.status_code in (401, 403), (
        f"forged role claim escalated: {r.status_code}"
    )


# =============================================================================
# D. Deletion step-up contract
# =============================================================================
def test_delete_refused_without_password():
    c = _fresh()
    email = _email()
    tok = _register(c, email)["access_token"]
    r = c.request("DELETE", "/api/v1/auth/account", headers=_hdr(tok),
                  json={"confirm": "DELETE"})
    assert r.status_code == 401
    assert r.json()["error"]["details"].get("reason") == "PASSWORD_REQUIRED"
    # Account intact.
    assert c.get("/api/v1/auth/me", headers=_hdr(tok)).status_code == 200


def test_delete_refused_with_wrong_password_and_wrong_confirm():
    c = _fresh()
    email = _email()
    tok = _register(c, email)["access_token"]

    r = c.request("DELETE", "/api/v1/auth/account", headers=_hdr(tok),
                  json={"confirm": "DELETE", "password": "WrongPass123!"})
    assert r.status_code == 401

    r = c.request("DELETE", "/api/v1/auth/account", headers=_hdr(tok),
                  json={"confirm": "yes please", "password": PASSWORD})
    assert r.status_code == 401
    assert r.json()["error"]["details"].get("reason") == "CONFIRMATION_REQUIRED"

    # Failed attempts audited, account intact.
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == email).one()
        assert user.is_active is True
        audited = db.query(AuditLog).filter(
            AuditLog.user_id == user.id,
            AuditLog.action == "ACCOUNT_DELETE_REAUTH_FAILED",
        ).count()
        assert audited >= 1
    finally:
        db.close()


def test_delete_mfa_user_requires_code():
    c = _fresh()
    email = _email()
    tok = _register(c, email)["access_token"]
    # Enroll MFA for real.
    r = c.post("/api/v1/auth/mfa/setup", headers=_hdr(tok))
    secret = r.json()["secret"]
    r = c.post("/api/v1/auth/mfa/verify", headers=_hdr(tok),
               json={"code": pyotp.TOTP(secret).now()})
    assert r.status_code == 200
    backup = r.json()["backup_codes"][0]

    # Password alone is not enough for an MFA-enrolled account.
    r = c.request("DELETE", "/api/v1/auth/account", headers=_hdr(tok),
                  json={"confirm": "DELETE", "password": PASSWORD})
    assert r.status_code == 401
    assert r.json()["error"]["details"].get("reason") == "MFA_CODE_REQUIRED"

    # Recovery code completes the step-up.
    r = c.request("DELETE", "/api/v1/auth/account", headers=_hdr(tok),
                  json={"confirm": "DELETE", "password": PASSWORD, "mfa_code": backup})
    assert r.status_code == 200


def test_delete_cleans_related_rows_and_kills_sessions():
    c = _fresh()
    email = _email()
    reg = _register(c, email)
    tok, refresh = reg["access_token"], reg["refresh_token"]
    uid = _user_id(email)

    # Onboard + enroll MFA so profile/MFA rows exist to clean.
    c.post("/api/v1/profile/onboarding-quiz", headers=_hdr(tok), json={
        "style_archetypes": ["Minimalist"],
        "body_attributes": {"height_cm": 170},
    })
    r = c.post("/api/v1/auth/mfa/setup", headers=_hdr(tok))
    secret = r.json()["secret"]
    c.post("/api/v1/auth/mfa/verify", headers=_hdr(tok),
           json={"code": pyotp.TOTP(secret).now()})

    db = TestingSessionLocal()
    try:
        assert db.query(UserStyleProfile).filter_by(user_id=uid).count() == 1
        assert db.query(MFABackupCode).filter_by(user_id=uid).count() == 10
    finally:
        db.close()

    r = c.request("DELETE", "/api/v1/auth/account", headers=_hdr(tok),
                  json={"confirm": "DELETE", "password": PASSWORD,
                        "mfa_code": pyotp.TOTP(secret).at(
                            __import__("time").time() + 30)})
    # TOTP step may be consumed by enrollment; fall back through recovery
    # behaviour is covered in the previous test — accept either fresh-code
    # success or an MFA challenge we then satisfy differently.
    if r.status_code != 200:
        # Extremely unlikely: same 30s window. Use a future-window code.
        import time as _t
        _t.sleep(31)
        r = c.request("DELETE", "/api/v1/auth/account", headers=_hdr(tok),
                      json={"confirm": "DELETE", "password": PASSWORD,
                            "mfa_code": pyotp.TOTP(secret).now()})
    assert r.status_code == 200, r.text

    db = TestingSessionLocal()
    try:
        assert db.query(User).filter_by(id=uid).first() is None
        assert db.query(UserStyleProfile).filter_by(user_id=uid).count() == 0
        assert db.query(MFABackupCode).filter_by(user_id=uid).count() == 0
        # Refresh rows are gone with the user (cascade) — nothing dangling.
        assert db.query(RefreshToken).filter_by(user_id=uid).count() == 0
    finally:
        db.close()

    # Access token dead, refresh dead, login dead — idempotent second
    # delete is also 401 (no ghost path).
    assert c.get("/api/v1/auth/me", headers=_hdr(tok)).status_code == 401
    # A cookie-carrying client gets 403 (CSRF gate) before token validation;
    # a bare client gets 401 (revoked/unknown). Both are refusals — assert
    # with a cookie-free client for the precise 401, then the cookie path.
    bare = _fresh()
    r = bare.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 401
    r = c.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 401
    r = c.request("DELETE", "/api/v1/auth/account", headers=_hdr(tok),
                  json={"confirm": "DELETE", "password": PASSWORD})
    assert r.status_code == 401
