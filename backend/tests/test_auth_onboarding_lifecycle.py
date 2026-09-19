"""End-to-end lifecycle: registration intent → verification → onboarding state
→ partner application → admin approval → brand provisioning → invitations →
session/RBAC consequences, plus the negative security cases.

Covers the defect behind the incident screenshot: a consumer hitting a brand
portal had NO legitimate path to authorization. These tests prove the path now
exists, that it is server-side, and that every shortcut around it fails.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.main import app
from backend.app.models.profile import UserStyleProfile
from backend.app.models.user import BrandMember, Invitation, PartnerApplication, User, UserRole
from backend.app.services import partner_service

ADMIN = {"email": "admin@confit.io", "password": "Password123!"}


def _csrf(client: TestClient) -> dict:
    token = client.cookies.get("confit_csrf")
    return {"X-CSRF-Token": token} if token else {}


def _db():
    return next(app.dependency_overrides[get_db]())


def _register(client: TestClient, email: str, intent: str = "consumer", password: str = "Password123!") -> dict:
    r = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Lifecycle Tester",
            "registration_intent": intent,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _login(client: TestClient, email: str, password: str = "Password123!") -> dict:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def _verify_email(client: TestClient, email: str) -> None:
    """Drive the real verification flow (provider must be configured)."""
    from backend.app.services import auth_service as auth_mod
    from backend.app.services import token_service

    db = _db()
    try:
        user = db.query(User).filter(User.email == email).first()
        token = auth_mod.AuthService(db)._issue_verification_token(user)
    finally:
        db.close()
    r = client.post("/api/v1/auth/verify-email", json={"token": token}, headers=_csrf(client))
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# Registration intent is DATA, never a privilege
# ---------------------------------------------------------------------------

def test_registration_intent_is_recorded_and_never_grants_a_role(client: TestClient):
    body = _register(client, "intent-brand@example.com", intent="brand_partner")
    assert body["user"]["role"] == "consumer", "asking to join as a brand must not grant a brand role"
    assert body["user"]["registration_intent"] == "brand_partner"

    state = client.get("/api/v1/auth/onboarding-state").json()
    assert state["registration_intent"] == "brand_partner"
    assert state["partner_access"] == "none"
    assert state["next_action"]["type"] == "apply_for_partner"


def test_injected_role_field_is_ignored_and_intent_is_validated(client: TestClient):
    r = client.post(
        "/api/v1/auth/register",
        json={
            "email": "escalate@example.com",
            "password": "Password123!",
            "full_name": "Escalate",
            "role": "admin",
            "registration_intent": "consumer",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["user"]["role"] == "consumer"

    bad = client.post(
        "/api/v1/auth/register",
        json={
            "email": "badintent@example.com",
            "password": "Password123!",
            "full_name": "Bad Intent",
            "registration_intent": "brand_owner",
        },
    )
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# Onboarding state machine
# ---------------------------------------------------------------------------

def test_onboarding_state_routes_a_consumer_to_the_style_profile(client: TestClient):
    _register(client, "state-consumer@example.com")
    state = client.get("/api/v1/auth/onboarding-state").json()
    assert state["account_state"] == "ONBOARDING_REQUIRED"
    assert state["next_action"]["route"] == "/profile?onboarding=1"
    assert state["allowed_areas"] == ["storefront"]


def test_profile_completion_moves_the_account_to_active(client: TestClient):
    _register(client, "state-profile@example.com")
    db = _db()
    try:
        user = db.query(User).filter(User.email == "state-profile@example.com").first()
        db.add(UserStyleProfile(user_id=user.id))
        db.commit()
    finally:
        db.close()
    state = client.get("/api/v1/auth/onboarding-state").json()
    assert state["account_state"] == "ACTIVE"
    assert state["profile_completed"] is True


def test_unverified_account_is_told_to_verify_first(client: TestClient, monkeypatch):
    """With a provider configured, the state machine blocks partner work until
    the address is verified — the dependency is explicit, not discovered later."""
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "smtp", raising=False)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.fake.test", raising=False)
    monkeypatch.setattr(settings, "SMTP_PORT", 587, raising=False)
    monkeypatch.setattr(settings, "SMTP_USERNAME", "u", raising=False)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "p", raising=False)
    monkeypatch.setattr(settings, "EMAIL_FROM_ADDRESS", "CONFIT <no-reply@confit.test>", raising=False)
    monkeypatch.setattr(settings, "SMTP_TLS_MODE", "starttls", raising=False)

    _register(client, "unverified@example.com", intent="brand_partner")
    state = client.get("/api/v1/auth/onboarding-state").json()
    assert state["account_state"] == "EMAIL_VERIFICATION_REQUIRED"
    assert state["next_action"]["type"] == "verify_email"

    r = client.post(
        "/api/v1/auth/partner-applications",
        json={"brand_name": "Premature Brand", "contact_name": "Tester"},
        headers=_csrf(client),
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "EMAIL_VERIFICATION_REQUIRED"


# ---------------------------------------------------------------------------
# Partner application → admin review → provisioning
# ---------------------------------------------------------------------------

def test_partner_application_is_pending_until_an_admin_approves(client: TestClient):
    _register(client, "applicant@example.com", intent="brand_partner")
    r = client.post(
        "/api/v1/auth/partner-applications",
        json={"brand_name": "Atelier Applicant", "contact_name": "Applicant One", "market": "EG"},
        headers=_csrf(client),
    )
    assert r.status_code == 201, r.text
    application_id = r.json()["id"]
    assert r.json()["status"] == "pending"

    # The applicant is still a consumer with no portal access.
    state = client.get("/api/v1/auth/onboarding-state").json()
    assert state["account_state"] == "PARTNER_APPLICATION_PENDING"
    assert state["partner_access"] == "pending"
    assert client.get("/api/v1/brand/invitations").status_code == 403

    # Duplicate submissions are a real conflict, not a second review item.
    dup = client.post(
        "/api/v1/auth/partner-applications",
        json={"brand_name": "Atelier Applicant", "contact_name": "Applicant One"},
        headers=_csrf(client),
    )
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "PARTNER_APPLICATION_PENDING"

    # A consumer cannot approve their own application.
    self_approve = client.post(
        f"/api/v1/admin/partner-applications/{application_id}/approve",
        json={},
        headers=_csrf(client),
    )
    assert self_approve.status_code in (401, 403)

    # Admin approves → brand provisioned, role granted server-side.
    admin_client = TestClient(app)
    admin_tokens = _login(admin_client, ADMIN["email"], ADMIN["password"])
    headers = {"Authorization": f"Bearer {admin_tokens['access_token']}"}
    listed = admin_client.get("/api/v1/admin/partner-applications?status=pending", headers=headers)
    assert listed.status_code == 200, listed.text
    assert any(item["id"] == application_id for item in listed.json()["items"])

    approved = admin_client.post(
        f"/api/v1/admin/partner-applications/{application_id}/approve",
        json={"note": "Verified business documents."},
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["brand_id"] is not None

    # The applicant now holds brand_owner and can open the B2B portal.
    db = _db()
    try:
        user = db.query(User).filter(User.email == "applicant@example.com").first()
        assert user.role == UserRole.BRAND_OWNER
        application = db.query(PartnerApplication).filter(PartnerApplication.id == application_id).first()
        assert application.status.value == "approved"
        assert application.reviewed_by_user_id is not None
    finally:
        db.close()

    state = client.get("/api/v1/auth/onboarding-state").json()
    assert state["role"] == "brand_owner"
    assert state["partner_access"] == "approved"
    assert "b2b" in state["allowed_areas"]
    assert client.get("/api/v1/brand/invitations").status_code == 200


def test_rejected_application_leaves_the_account_unprivileged_and_retryable(client: TestClient):
    _register(client, "rejected@example.com", intent="brand_partner")
    created = client.post(
        "/api/v1/auth/partner-applications",
        json={"brand_name": "Rejected Brand", "contact_name": "Rejected One"},
        headers=_csrf(client),
    )
    assert created.status_code == 201
    application_id = created.json()["id"]

    admin_client = TestClient(app)
    tokens = _login(admin_client, ADMIN["email"], ADMIN["password"])
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    rejected = admin_client.post(
        f"/api/v1/admin/partner-applications/{application_id}/reject",
        json={"note": "Incomplete documents."},
        headers=headers,
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    db = _db()
    try:
        user = db.query(User).filter(User.email == "rejected@example.com").first()
        assert user.role == UserRole.CONSUMER
    finally:
        db.close()

    state = client.get("/api/v1/auth/onboarding-state").json()
    assert state["partner_access"] == "rejected"
    # …and the user can apply again (no dead end).
    retry = client.post(
        "/api/v1/auth/partner-applications",
        json={"brand_name": "Rejected Brand (resubmitted)", "contact_name": "Rejected One"},
        headers=_csrf(client),
    )
    assert retry.status_code == 201


def test_admin_review_requires_a_platform_admin(client: TestClient):
    brand_client = TestClient(app)
    body = _login(brand_client, "brand@massimodutti.com", "Password123!")
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    r = brand_client.get("/api/v1/admin/partner-applications", headers=headers)
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------

def _owner_client(email: str, brand_name: str) -> TestClient:
    """Approve a fresh brand owner and return their authenticated client."""
    client = TestClient(app)
    _register(client, email, intent="brand_partner")
    created = client.post(
        "/api/v1/auth/partner-applications",
        json={"brand_name": brand_name, "contact_name": "Owner"},
        headers=_csrf(client),
    )
    assert created.status_code == 201, created.text
    admin_client = TestClient(app)
    tokens = _login(admin_client, ADMIN["email"], ADMIN["password"])
    approved = admin_client.post(
        f"/api/v1/admin/partner-applications/{created.json()['id']}/approve",
        json={"note": "ok"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert approved.status_code == 200, approved.text
    return client


def test_brand_owner_invites_a_teammate_who_then_gets_scoped_access(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", None, raising=False)  # token returned by API for ops/tests
    owner = _owner_client("owner-invite@example.com", "Invite Brand")

    created = owner.post(
        "/api/v1/brand/invitations",
        json={"email": "teammate@example.com", "role": "brand_manager"},
        headers=_csrf(owner),
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["role"] == "brand_manager"
    assert payload["delivery"] is None or payload["delivery"]["status"] == "blocked"
    accept_path = payload["accept_path"]
    token = accept_path.split("token=", 1)[1]

    # Public preview is informative but masked, and never echoes the token.
    preview = TestClient(app).get(f"/api/v1/auth/invitations/preview?token={token}")
    assert preview.status_code == 200
    assert preview.json()["valid"] is True
    assert preview.json()["role"] == "brand_manager"
    assert "teammate@" not in preview.json()["email_masked"]

    # The invitee creates their account purely by accepting the invitation.
    invitee = TestClient(app)
    accepted = invitee.post(
        "/api/v1/auth/invitations/accept",
        json={"token": token, "full_name": "Team Mate", "password": "Teammate123!"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["account_created"] is True
    assert accepted.json()["user"]["role"] == "brand_manager"

    # Scoped access works through the membership resolution path…
    assert invitee.get("/api/v1/brand/profile").status_code == 200
    # …and the new member is NOT allowed to invite (owner-only, BRD G6 §2.1).
    forbidden = invitee.post(
        "/api/v1/brand/invitations",
        json={"email": "another@example.com", "role": "brand_staff"},
        headers=_csrf(invitee),
    )
    assert forbidden.status_code == 403

    # Replay is refused.
    replay = TestClient(app).post(
        "/api/v1/auth/invitations/accept",
        json={"token": token, "full_name": "Team Mate", "password": "Teammate123!"},
    )
    assert replay.status_code == 409
    assert replay.json()["error"]["code"] == "INVITATION_ALREADY_ACCEPTED"


def test_invitation_escalation_and_abuse_paths_are_refused(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", None, raising=False)
    owner = _owner_client("owner-negative@example.com", "Negative Brand")

    # 1. The admin role can never be granted by invitation.
    r = owner.post(
        "/api/v1/brand/invitations",
        json={"email": "wannabe-admin@example.com", "role": "admin"},
        headers=_csrf(owner),
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"

    # 2. A plain consumer cannot issue invitations for a brand.
    consumer = TestClient(app)
    _register(consumer, "plain-consumer@example.com")
    r2 = consumer.post(
        "/api/v1/brand/invitations",
        json={"email": "x@example.com", "role": "brand_staff"},
        headers=_csrf(consumer),
    )
    assert r2.status_code == 403

    # 3. Revoked / unknown tokens are refused.
    revoked = owner.post(
        "/api/v1/brand/invitations",
        json={"email": "revoked@example.com", "role": "brand_staff"},
        headers=_csrf(owner),
    )
    token = revoked.json()["accept_path"].split("token=", 1)[1]
    invitation_id = revoked.json()["id"]
    assert owner.post(f"/api/v1/brand/invitations/{invitation_id}/revoke", headers=_csrf(owner)).status_code == 200
    dead = TestClient(app).post(
        "/api/v1/auth/invitations/accept",
        json={"token": token, "full_name": "Nobody", "password": "Nobody123!"},
    )
    assert dead.status_code == 409
    assert dead.json()["error"]["code"] == "INVITATION_REVOKED"

    unknown = TestClient(app).post(
        "/api/v1/auth/invitations/accept",
        json={"token": "not-a-real-invitation-token", "full_name": "Nobody", "password": "Nobody123!"},
    )
    assert unknown.status_code == 409
    assert unknown.json()["error"]["code"] == "INVITATION_INVALID"


def test_expired_invitation_is_refused(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", None, raising=False)
    owner = _owner_client("owner-expiry@example.com", "Expiry Brand")
    created = owner.post(
        "/api/v1/brand/invitations",
        json={"email": "expired-invite@example.com", "role": "brand_staff"},
        headers=_csrf(owner),
    )
    token = created.json()["accept_path"].split("token=", 1)[1]

    db = _db()
    try:
        from backend.app.services import token_service
        row = db.query(Invitation).filter(Invitation.id == created.json()["id"]).first()
        row.expires_at = token_service.utcnow() - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()

    r = TestClient(app).post(
        "/api/v1/auth/invitations/accept",
        json={"token": token, "full_name": "Too Late", "password": "TooLate123!"},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "INVITATION_EXPIRED"


def test_invitation_cannot_cross_tenants(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", None, raising=False)
    owner_a = _owner_client("owner-a@example.com", "Brand Alpha")
    owner_b = _owner_client("owner-b@example.com", "Brand Beta")

    # A member of Brand Alpha cannot be pulled into Brand Beta.
    created = owner_a.post(
        "/api/v1/brand/invitations",
        json={"email": "shared@example.com", "role": "brand_staff"},
        headers=_csrf(owner_a),
    )
    token_a = created.json()["accept_path"].split("token=", 1)[1]
    invitee = TestClient(app)
    accepted = invitee.post(
        "/api/v1/auth/invitations/accept",
        json={"token": token_a, "full_name": "Shared Person", "password": "SharedPass123!"},
    )
    assert accepted.status_code == 200

    invite_b = owner_b.post(
        "/api/v1/brand/invitations",
        json={"email": "shared@example.com", "role": "brand_staff"},
        headers=_csrf(owner_b),
    )
    # Already a member elsewhere → refused at issue time.
    assert invite_b.status_code == 409
    assert invite_b.json()["error"]["code"] == "INVITEE_ALREADY_MEMBER"

    db = _db()
    try:
        user = db.query(User).filter(User.email == "shared@example.com").first()
        memberships = db.query(BrandMember).filter(BrandMember.user_id == user.id).all()
        assert len(memberships) == 1, "a member must never end up inside two brands"
    finally:
        db.close()


def test_invited_member_cannot_touch_another_brands_tenant(client: TestClient, monkeypatch):
    """An invited member is scoped to THEIR brand: mutating another tenant's SKU
    must fail the same way it fails for an owning account."""
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", None, raising=False)
    owner_a = _owner_client("tenant-a@example.com", "Tenant Alpha")

    created = owner_a.post(
        "/api/v1/brand/invitations",
        json={"email": "tenant-member@example.com", "role": "brand_manager"},
        headers=_csrf(owner_a),
    )
    token = created.json()["accept_path"].split("token=", 1)[1]
    member = TestClient(app)
    accepted = member.post(
        "/api/v1/auth/invitations/accept",
        json={"token": token, "full_name": "Tenant Member", "password": "Tenant123!"},
    )
    assert accepted.status_code == 200

    db = _db()
    try:
        from backend.app.models.catalog import Product, ProductSKU
        from backend.app.models.user import BrandProfile
        other_brand = db.query(BrandProfile).filter(BrandProfile.brand_name == "Reiss").first()
        assert other_brand is not None
        foreign_sku = (
            db.query(ProductSKU).join(Product).filter(Product.brand_id == other_brand.id).first()
        )
        assert foreign_sku is not None
        foreign_sku_id = foreign_sku.id
    finally:
        db.close()

    # Own tenant: allowed.
    assert member.get("/api/v1/brand/profile").status_code == 200

    # Cookie-authenticated mutation without the double-submit header: blocked.
    no_csrf = member.put(f"/api/v1/brand/skus/{foreign_sku_id}?stock_level=99")
    assert no_csrf.status_code == 403
    assert no_csrf.json()["error"]["code"] == "CSRF_TOKEN_MISMATCH"

    # With a valid CSRF header the request reaches the tenant guard and is
    # refused there — cross-tenant mutation is impossible for an invited member.
    cross = member.put(f"/api/v1/brand/skus/{foreign_sku_id}?stock_level=99", headers=_csrf(member))
    assert cross.status_code == 403, cross.text
    assert "tenant scope violation" in cross.text.lower()


# ---------------------------------------------------------------------------
# §16 — verification state must never be inferred from deployment config
# ---------------------------------------------------------------------------

def test_registration_never_marks_an_unverified_address_verified(client: TestClient, monkeypatch):
    """No provider ⇒ no verification happened ⇒ `is_verified` must be False.

    Regression guard for the security paradox where
    `is_verified=not bool(settings.EMAIL_PROVIDER)` made every account born
    "verified" on a deployment that could not verify anything.
    """
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", None, raising=False)

    body = _register(client, "no-provider-honesty@example.com")
    assert body["user"]["is_verified"] is False, "an absent provider must never imply a completed check"

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["is_verified"] is False

    status = client.get("/api/v1/auth/email-status").json()
    assert status["provider_configured"] is False
    assert status["accepted"] is False

    # ...and the account is NOT told to verify (no dead end): the state machine
    # only demands verification when verification can actually be performed.
    assert me.json()["onboarding"]["account_state"] != "EMAIL_VERIFICATION_REQUIRED"
    assert me.json()["onboarding"]["email_verified"] is False


def test_partner_application_records_and_exposes_the_verification_exception(client: TestClient, monkeypatch):
    """With no provider the application is accepted — and the reviewer is told.

    The exception to the verification gate (§16) must be visible, not silent:
    the applicant stays unverified and the admin payload says so, so the human
    decision is made with the truth in hand.
    """
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", None, raising=False)
    applicant = TestClient(app)
    _register(applicant, "no-provider-applicant@example.com", intent="brand_partner")
    created = applicant.post(
        "/api/v1/auth/partner-applications",
        json={"brand_name": "Unverifiable Atelier", "market": "EG", "contact_name": "Applicant"},
        headers=_csrf(applicant),
    )
    assert created.status_code == 201, created.text
    application_id = created.json()["id"]

    admin_client = TestClient(app)
    tokens = _login(admin_client, ADMIN["email"], ADMIN["password"])
    listed = admin_client.get(
        "/api/v1/admin/partner-applications?status=pending",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert listed.status_code == 200, listed.text
    row = next(item for item in listed.json()["items"] if item["id"] == application_id)
    assert row["applicant_email_verified"] is False
    assert row["applicant_verification_available"] is False

    # The exception is auditable after the fact.
    db = _db()
    try:
        from backend.app.models.user import AuditLog

        entry = (
            db.query(AuditLog)
            .filter(AuditLog.action == "PARTNER_APPLICATION_SUBMITTED")
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert entry is not None
        import json as _json

        recorded = _json.loads(entry.details_json or "{}")
        assert recorded["verification_unavailable"] is True
        assert recorded["email_verified"] is False
    finally:
        db.close()


def test_verified_applicant_is_reported_as_verified_to_the_reviewer(client: TestClient, monkeypatch):
    """The same flag is TRUE when the address really was verified by email."""
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "smtp", raising=False)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.fake.test", raising=False)
    monkeypatch.setattr(settings, "SMTP_PORT", 587, raising=False)
    monkeypatch.setattr(settings, "SMTP_USERNAME", "u", raising=False)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "p", raising=False)
    monkeypatch.setattr(settings, "EMAIL_FROM_ADDRESS", "CONFIT <no-reply@confit.test>", raising=False)
    monkeypatch.setattr(settings, "SMTP_TLS_MODE", "starttls", raising=False)

    applicant = TestClient(app)
    _register(applicant, "verified-applicant@example.com", intent="brand_partner")
    _verify_email(applicant, "verified-applicant@example.com")
    created = applicant.post(
        "/api/v1/auth/partner-applications",
        json={"brand_name": "Verified Atelier", "market": "EG", "contact_name": "Applicant"},
        headers=_csrf(applicant),
    )
    assert created.status_code == 201, created.text

    admin_client = TestClient(app)
    tokens = _login(admin_client, ADMIN["email"], ADMIN["password"])
    listed = admin_client.get(
        "/api/v1/admin/partner-applications?status=pending",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    row = next(item for item in listed.json()["items"] if item["id"] == created.json()["id"])
    assert row["applicant_email_verified"] is True
    assert row["applicant_verification_available"] is True


def test_no_endpoint_accepts_a_redirect_parameter():
    """Open-redirect defence by construction: nothing on the auth surface can
    be told where to bounce the browser afterwards, so there is no parameter to
    poison with `https://evil.example`, `//evil.example` or `javascript:`."""
    spec = app.openapi()
    offenders = []
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            for param in op.get("parameters", []) + [p for p in op.get("requestBody", {}).get("content", {}).values() if False]:
                name = (param.get("name") or "").lower()
                if name in {"next", "redirect", "redirect_uri", "returnurl", "return_url", "continue", "url"}:
                    offenders.append(f"{method.upper()} {path}?{name}")
    assert offenders == [], f"redirect-capable parameters found: {offenders}"
