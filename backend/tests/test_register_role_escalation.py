"""P0 regression: public registration must NEVER accept a client-supplied role.

Production evidence (2026-09-05, live): `POST /api/v1/auth/register` with
`"role": "admin"` returned HTTP 201 and created a platform-admin account —
any unauthenticated visitor could self-escalate to platform admin (the
exploit also opened brand-staff roles and auto-created brand profiles).

The invariant is enforced at the service layer: `AuthService.register` has
no `role` parameter and hard-codes `UserRole.CONSUMER`; the `UserRegister`
schema no longer carries a `role` field and silently ignores stray
privilege fields (no 422 oracle). These tests pin every layer of the fix.
"""

import inspect
import uuid

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.tests.conftest import TestingSessionLocal as SessionLocal
from backend.app.models.user import BrandProfile, User, UserRole
from backend.app.repositories.user_repository import UserRepository
from backend.app.services.auth_service import AuthService

SUFFIX = uuid.uuid4().hex[:10]
PW = "Sec!Test#Pass2026x9"


def _register(client: TestClient, extra: dict | None = None, full_name: str = "Reg Test") -> dict:
    body = {
        "email": f"regtest.{uuid.uuid4().hex[:12]}@{SUFFIX}.test.dev",
        "password": PW,
        "full_name": full_name,
    }
    if extra:
        body.update(extra)
    res = client.post("/api/v1/auth/register", json=body)
    return res


def test_normal_registration_creates_consumer():
    client = TestClient(app)
    res = _register(client)
    assert res.status_code == 201, res.text
    assert res.json()["user"]["role"] == UserRole.CONSUMER.value


def test_role_admin_in_body_cannot_create_admin():
    client = TestClient(app)
    res = _register(client, extra={"role": "admin"})
    # extra field is silently discarded — no 422 oracle, and the account
    # is a consumer, full stop.
    assert res.status_code == 201, res.text
    assert res.json()["user"]["role"] == UserRole.CONSUMER.value


def test_no_privileged_role_can_be_self_assigned():
    client = TestClient(app)
    for role_value in [
        "admin",
        "ADMIN",
        "brand_owner",
        "brand_manager",
        "brand_staff",
        "platform_admin",
        "staff",
        "moderator",
        "root",
    ]:
        res = _register(client, extra={"role": role_value})
        assert res.status_code == 201, (role_value, res.text)
        assert res.json()["user"]["role"] == UserRole.CONSUMER.value, role_value


def test_crafted_body_fields_cannot_bypass():
    """Malformed / alternate / nested privilege payloads are all ignored."""
    client = TestClient(app)
    crafted = [
        {"role": {"$ne": None}},
        {"role": None},
        {"role": 5},
        {"role": ["admin"]},
        {"user_role": "admin"},
        {"roles": ["admin"]},
        {"is_admin": True},
        {"privilege": "admin"},
        {"role": "admin", "user_role": "admin", "is_admin": True},
    ]
    for extra in crafted:
        res = _register(client, extra=extra)
        assert res.status_code == 201, (extra, res.text)
        assert res.json()["user"]["role"] == UserRole.CONSUMER.value, extra


def test_register_schema_no_longer_exposes_role_field():
    """The role field is removed from the API contract (not merely hidden)."""
    client = TestClient(app)
    spec = client.get("/openapi.json").json()
    user_register = spec["components"]["schemas"]["UserRegister"]
    assert "role" not in user_register.get("properties", {}), user_register


def test_service_register_has_no_role_parameter():
    """Structural invariant: no code path can pass a role through the
    public registration service method."""
    params = inspect.signature(AuthService.register).parameters
    assert "role" not in params, list(params)


def test_direct_service_call_creates_consumer():
    """Even bypassing the HTTP layer, the service hard-codes CONSUMER."""
    client = TestClient(app)  # ensures app/db fixtures are up
    email = f"direct.{uuid.uuid4().hex[:12]}@{SUFFIX}.test.dev"
    with SessionLocal() as db:
        service = AuthService(db)
        result = service.register(email=email, password=PW, full_name="Direct Call")
        assert result["user"].role == UserRole.CONSUMER


def test_brand_profile_not_auto_created_on_register():
    """The removed side-effect: registering can no longer mint brand
    organization membership (brand_manager path)."""
    client = TestClient(app)
    res = _register(client, extra={"role": "brand_manager"}, full_name="Some Brand")
    assert res.status_code == 201
    user_id = res.json()["user"]["id"]
    with SessionLocal() as db:
        count = db.query(BrandProfile).filter(BrandProfile.user_id == user_id).count()
        assert count == 0


def test_legitimate_admin_provisioning_still_functions():
    """Trusted internal provisioning (direct repository use) still works:
    a repo-created admin can log in and access admin-gated routes, while a
    consumer cannot."""
    client = TestClient(app)

    admin_email = f"provisioned.admin.{uuid.uuid4().hex[:10]}@{SUFFIX}.test.dev"
    with SessionLocal() as db:
        user_repo = UserRepository(db)
        user_repo.create(email=admin_email, password=PW, full_name="Provisioned Admin",
                         role=UserRole.ADMIN)

    login = client.post("/api/v1/auth/login", json={"email": admin_email, "password": PW})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    admin_res = client.get("/api/v1/admin/analytics", headers={"Authorization": f"Bearer {token}"})
    assert admin_res.status_code == 200, admin_res.text

    # A consumer (public registration) is still locked out of admin routes.
    reg = _register(client)
    assert reg.status_code == 201
    consumer_token = reg.json()["access_token"]
    denied = client.get("/api/v1/admin/analytics", headers={"Authorization": f"Bearer {consumer_token}"})
    assert denied.status_code == 403, denied.text


def test_social_login_still_creates_consumer_shape():
    """The other public identity path is unchanged (hard-coded CONSUMER)."""
    src = inspect.getsource(AuthService.social_login)
    assert "UserRole.CONSUMER" in src
