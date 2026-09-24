"""Authenticated authorization denials are security events (ASVS V16.3.2).

Direct endpoint invocation is used — hidden frontend links prove nothing. The
record contains path/method/roles and correlation context, but never the
Authorization header, token, query string or body.
"""
import json

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.user import AuditLog, User
from backend.tests.conftest import TestingSessionLocal

client = TestClient(app)


def _login(email: str) -> dict:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_consumer_direct_admin_request_is_denied_and_audited_without_secrets():
    marker = "SHOULD_NEVER_ENTER_AUDIT"
    headers = _login("shopper@confit.io")
    response = client.get(f"/api/v1/admin/audit?search={marker}", headers=headers)
    assert response.status_code == 403

    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == "shopper@confit.io").one()
        row = (
            db.query(AuditLog)
            .filter(
                AuditLog.action == "AUTHORIZATION_DENIED",
                AuditLog.user_id == user.id,
                AuditLog.resource_id == "/api/v1/admin/audit",
            )
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        payload = json.loads(row.after_json)
        assert payload == {
            "actual_role": "consumer",
            "method": "GET",
            "path": "/api/v1/admin/audit",
            "required_roles": ["admin"],
        }
        stored = " ".join(filter(None, [row.details_json, row.before_json, row.after_json]))
        assert marker not in stored, "query string must not be audited"
        assert headers["Authorization"].split(" ", 1)[1] not in stored
        assert row.entry_hash, "denial event must use the same chained write path"
    finally:
        db.close()


def test_brand_partner_direct_admin_request_is_denied():
    response = client.get(
        "/api/v1/admin/analytics",
        headers=_login("brand@massimodutti.com"),
    )
    assert response.status_code == 403


def test_unauthenticated_request_is_401_not_fabricated_as_an_actor():
    # The shared TestClient retains the httpOnly cookie from prior login tests.
    client.cookies.clear()
    db = TestingSessionLocal()
    before = db.query(AuditLog).filter(AuditLog.action == "AUTHORIZATION_DENIED").count()
    db.close()
    response = client.get("/api/v1/admin/analytics")
    assert response.status_code == 401
    db = TestingSessionLocal()
    try:
        after = db.query(AuditLog).filter(AuditLog.action == "AUTHORIZATION_DENIED").count()
        assert after == before, "there is no authenticated actor to attribute"
    finally:
        db.close()
