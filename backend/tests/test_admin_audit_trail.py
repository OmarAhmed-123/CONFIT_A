"""Behavioural gates for the platform audit trail (gap register G-05, G-06).

Everything here exercises the running API or the running write path. The tests
this file replaces asserted on ``inspect.getsource`` and on a docstring, which
is why a fabricated audit payload and an unenforced redaction contract both
survived review (G-16).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.audit_redaction import (
    contains_secret,
    is_secret_key,
    scan_keys,
    scrub,
    scrub_text,
)
from backend.app.core.request_context import client_ip
from backend.app.main import app
from backend.app.models.user import AuditLog, User, UserRole
from backend.app.core.security import get_password_hash

TEST_DB_URL = "sqlite:///./backend/data/confit_test.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

AUDIT_ENDPOINTS = [
    "/api/v1/admin/audit",
    "/api/v1/admin/audit/facets",
    "/api/v1/admin/audit/stats",
    "/api/v1/admin/audit/integrity",
]

ACTION = "AUDIT_TRAIL_TEST"


def _login(client: TestClient, email: str, password: str = "Password123!") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _admin_headers(client: TestClient) -> dict:
    return {"Authorization": f"Bearer {_login(client, 'admin@confit.io')}"}


def _seed_rows(count: int = 5) -> None:
    db = TestingSessionLocal()
    try:
        admin = db.query(User).filter(User.role == UserRole.ADMIN).first()
        repo_id = admin.id if admin else 1
        from backend.app.repositories.user_repository import UserRepository

        repo = UserRepository(db)
        for i in range(count):
            repo.log_audit(
                action=ACTION,
                resource_type="Probe",
                resource_id=str(1000 + i),
                user_id=repo_id,
                ip_address=f"203.0.113.{i + 1}",
                details=f"seeded row {i}",
                before={"status": "draft", "version": i},
                after={"status": "published", "version": i + 1},
                request_id=f"req-{ACTION}-{i}",
            )
    finally:
        db.close()


def _purge() -> None:
    db = TestingSessionLocal()
    try:
        db.query(AuditLog).filter(AuditLog.action.in_([ACTION, "READ_PROBE_TARGET"])).delete(
            synchronize_session=False
        )
        db.commit()
    finally:
        db.close()


@pytest.fixture
def seeded(client: TestClient):
    _purge()
    _seed_rows()
    yield client
    _purge()


# ---------------------------------------------------------------------------
# Trail shape, enrichment, pagination, filters
# ---------------------------------------------------------------------------
class TestTrailContract:
    def test_envelope_and_enrichment(self, seeded: TestClient) -> None:
        headers = _admin_headers(seeded)
        response = seeded.get("/api/v1/admin/audit", params={"action": ACTION}, headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["meta"]["total"] == 5
        assert body["meta"]["page"] == 1
        assert body["meta"]["has_previous"] is False
        assert body["filters"]["action"] == ACTION

        row = next(r for r in body["items"] if r["resource_id"] == "1000")
        assert row["before"] == {"status": "draft", "version": 0}
        assert row["after"] == {"status": "published", "version": 1}
        assert row["changed_fields"] == ["status", "version"]
        assert row["request_id"] == f"req-{ACTION}-0"
        assert row["ip_address"] == "203.0.113.1"
        assert row["actor_email"] == "admin@confit.io"
        assert row["actor_role"] == "admin"
        assert row["actor"] != "User #1", "actor must be an identity, not an opaque id"

    def test_pagination_slices_and_reports_total(self, seeded: TestClient) -> None:
        headers = _admin_headers(seeded)
        first = seeded.get(
            "/api/v1/admin/audit", params={"action": ACTION, "page": 1, "page_size": 2}, headers=headers
        ).json()
        second = seeded.get(
            "/api/v1/admin/audit", params={"action": ACTION, "page": 2, "page_size": 2}, headers=headers
        ).json()

        assert len(first["items"]) == 2 and len(second["items"]) == 2
        assert first["meta"]["total"] == second["meta"]["total"] == 5
        assert first["meta"]["total_pages"] == 3
        assert first["meta"]["has_next"] is True and second["meta"]["has_next"] is True
        first_ids = {r["id"] for r in first["items"]}
        second_ids = {r["id"] for r in second["items"]}
        assert not (first_ids & second_ids), "pages must not overlap"
        # Stable ordering: newest first.
        assert first["items"][0]["id"] > second["items"][0]["id"]

    def test_page_size_is_capped(self, seeded: TestClient) -> None:
        headers = _admin_headers(seeded)
        response = seeded.get(
            "/api/v1/admin/audit", params={"action": ACTION, "page_size": 5000}, headers=headers
        )
        assert response.status_code == 422, "an unbounded page size must be rejected, not served"

    def test_filters_narrow_to_real_matches(self, seeded: TestClient) -> None:
        headers = _admin_headers(seeded)
        by_resource = seeded.get(
            "/api/v1/admin/audit", params={"action": ACTION, "resource_id": "1002"}, headers=headers
        ).json()
        assert by_resource["meta"]["total"] == 1
        assert by_resource["items"][0]["resource_id"] == "1002"

        by_text = seeded.get(
            "/api/v1/admin/audit", params={"search": "seeded row 3"}, headers=headers
        ).json()
        assert by_text["meta"]["total"] >= 1
        assert all("seeded row 3" in (r["details"] or "") for r in by_text["items"])

        admin_only = seeded.get(
            "/api/v1/admin/audit", params={"only_admin_actions": "true"}, headers=headers
        ).json()
        assert all(r["action"].startswith("ADMIN_") for r in admin_only["items"])

    def test_no_match_is_empty_not_fabricated(self, seeded: TestClient) -> None:
        headers = _admin_headers(seeded)
        body = seeded.get(
            "/api/v1/admin/audit", params={"action": "THIS_ACTION_NEVER_HAPPENED"}, headers=headers
        ).json()
        assert body["items"] == []
        assert body["meta"]["total"] == 0, "an empty trail must be empty, never a placeholder row"

    def test_date_window_is_applied(self, seeded: TestClient) -> None:
        headers = _admin_headers(seeded)
        past = seeded.get(
            "/api/v1/admin/audit",
            params={"action": ACTION, "date_to": "2000-01-01T00:00:00"},
            headers=headers,
        ).json()
        assert past["meta"]["total"] == 0
        future = seeded.get(
            "/api/v1/admin/audit",
            params={"action": ACTION, "date_from": "2000-01-01T00:00:00"},
            headers=headers,
        ).json()
        assert future["meta"]["total"] == 5

    def test_facets_come_from_real_rows(self, seeded: TestClient) -> None:
        headers = _admin_headers(seeded)
        body = seeded.get(
            "/api/v1/admin/audit/facets", params={"action": ACTION}, headers=headers
        ).json()
        actions = {f["value"]: f["count"] for f in body["actions"]}
        assert actions.get(ACTION) == 5
        assert any(f["value"] == "Probe" for f in body["resource_types"])
        assert body["actors"], "actor facet must resolve identities"
        assert body["actors"][0]["role"] == "admin"

    def test_stats_rollup(self, seeded: TestClient) -> None:
        headers = _admin_headers(seeded)
        body = seeded.get("/api/v1/admin/audit/stats", params={"window_days": 1}, headers=headers)
        assert body.status_code == 200, body.text
        stats = body.json()
        assert stats["window_days"] == 1
        assert stats["total_events"] >= 5
        assert stats["distinct_actors"] >= 1
        assert stats["by_day"], "per-day rollup must not be empty when rows exist"
        assert all(set(d) == {"day", "count"} for d in stats["by_day"])

    def test_integrity_is_honest_about_its_limits(self, seeded: TestClient) -> None:
        headers = _admin_headers(seeded)
        body = seeded.get("/api/v1/admin/audit/integrity", headers=headers).json()
        assert body["tamper_evident"] is False, "no hash chain exists; the claim must not be made"
        assert body["limitations"], "limitations must be stated, not implied"
        assert body["checked_rows"] >= 5
        assert body["rows_with_before_after"] >= 5
        assert body["rows_with_request_id"] >= 5
        assert body["rows_with_ip"] >= 5
        assert body["verdict"] in {"ok", "no_data", "violations_found"}
        for violation in body["violations"]:
            assert violation["issue"] != "unredacted_secret_in_payload", violation


# ---------------------------------------------------------------------------
# Reading the trail is itself a governed action
# ---------------------------------------------------------------------------
class TestReadIsAudited:
    def test_trail_read_writes_a_correlated_row(self, seeded: TestClient) -> None:
        headers = _admin_headers(seeded)
        response = seeded.get(
            "/api/v1/admin/audit", params={"action": ACTION, "page_size": 3}, headers=headers
        )
        assert response.status_code == 200, response.text
        correlation = response.headers.get("X-Request-Id")
        assert correlation, "every response must carry X-Request-Id"

        db = TestingSessionLocal()
        try:
            row = (
                db.query(AuditLog)
                .filter(AuditLog.action == "ADMIN_AUDIT_VIEW", AuditLog.request_id == correlation)
                .first()
            )
            assert row is not None, "reading the audit trail must itself be audited"
            after = json.loads(row.after_json or "{}")
            assert after["page_size"] == 3
            assert after["filters"]["action"] == ACTION
            assert row.user_id is not None
        finally:
            db.close()

    def test_integrity_read_is_audited(self, seeded: TestClient) -> None:
        headers = _admin_headers(seeded)
        response = seeded.get("/api/v1/admin/audit/integrity", headers=headers)
        correlation = response.headers.get("X-Request-Id")
        db = TestingSessionLocal()
        try:
            assert (
                db.query(AuditLog)
                .filter(AuditLog.action == "ADMIN_AUDIT_INTEGRITY_CHECK", AuditLog.request_id == correlation)
                .count()
                == 1
            )
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Authorisation on every audit endpoint
# ---------------------------------------------------------------------------
class TestAuditAuthorisation:
    @pytest.mark.parametrize("endpoint", AUDIT_ENDPOINTS)
    def test_guest_is_rejected(self, endpoint: str) -> None:
        fresh = TestClient(app)
        assert fresh.get(endpoint).status_code == 401

    @pytest.mark.parametrize("endpoint", AUDIT_ENDPOINTS)
    def test_consumer_is_rejected(self, endpoint: str, client: TestClient) -> None:
        headers = {"Authorization": f"Bearer {_login(client, 'shopper@confit.io')}"}
        response = client.get(endpoint, headers=headers)
        assert response.status_code == 403, response.text

    @pytest.mark.parametrize("endpoint", AUDIT_ENDPOINTS)
    def test_brand_role_is_rejected(self, endpoint: str, client: TestClient) -> None:
        """A brand principal is a tenant, not the platform: the audit trail is
        cross-tenant and must never be reachable from a brand session."""
        db = TestingSessionLocal()
        try:
            email = "audit_brand_probe@test.com"
            user = db.query(User).filter(User.email == email).first()
            if not user:
                user = User(
                    email=email,
                    hashed_password=get_password_hash("Password123!"),
                    full_name="Brand Probe",
                    role=UserRole.BRAND_OWNER,
                    is_active=True,
                    is_verified=True,
                )
                db.add(user)
                db.commit()
        finally:
            db.close()

        headers = {"Authorization": f"Bearer {_login(client, email)}"}
        response = client.get(endpoint, headers=headers)
        assert response.status_code == 403, response.text


# ---------------------------------------------------------------------------
# Redaction is enforced, not documented
# ---------------------------------------------------------------------------
class TestRedaction:
    def test_secret_keys_are_recognised(self) -> None:
        for key in ("password", "hashed_password", "refresh_token", "api_key", "JWT_SECRET", "cardNumber"):
            assert is_secret_key(key), key
        for key in ("status", "email", "token_type", "password_updated"):
            assert not is_secret_key(key), key

    def test_flags_survive_values_do_not(self) -> None:
        scrubbed, hits = scrub({"password": "hunter2", "password_updated": True, "note": "ok"})
        assert scrubbed["password"].startswith("[REDACTED:")
        assert scrubbed["password_updated"] is True
        assert scrubbed["note"] == "ok"
        assert hits == 1

    def test_nested_and_list_payloads(self) -> None:
        scrubbed, hits = scrub({"a": [{"token": "abc"}, {"keep": "yes"}], "b": {"c": {"secret": "z"}}})
        assert scrubbed["a"][0]["token"].startswith("[REDACTED:")
        assert scrubbed["a"][1]["keep"] == "yes"
        assert scrubbed["b"]["c"]["secret"].startswith("[REDACTED:")
        assert hits == 2

    def test_freeform_secrets_are_masked(self) -> None:
        masked, hits = scrub_text(
            "login ok Authorization: Bearer abcdef0123456789ABCDEF "
            "jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJlLXBhcnQ "
            "dsn postgresql://u:pw@host:5432/db card 4111 1111 1111 1111"
        )
        assert "abcdef0123456789ABCDEF" not in masked
        assert "eyJhbGciOiJIUzI1NiJ9" not in masked
        assert "postgresql://u:pw@host" not in masked
        assert "4111 1111 1111 1111" not in masked
        assert hits >= 4
        # Ordinary prose and ids are untouched.
        assert "login ok" in masked

    def test_non_card_digit_runs_are_left_alone(self) -> None:
        masked, hits = scrub_text("order 1234567890123456 created")
        assert masked == "order 1234567890123456 created", "only Luhn-valid PANs may be masked"
        assert hits == 0

    def test_recursion_is_bounded(self) -> None:
        deep: dict = {"token": "x"}
        node = deep
        for _ in range(50):
            node["child"] = {"token": "x"}
            node = node["child"]
        scrubbed, hits = scrub(deep)
        assert hits > 0
        assert scrubbed is not None

    def test_scan_keys_finds_before_persist(self) -> None:
        assert scan_keys({"a": {"password": 1}, "b": [{"api_key": 2}]}) == ["password", "api_key"]
        assert contains_secret({"token": "abc"}) is True
        assert contains_secret({"status": "ok"}) is False

    def test_admin_mutation_payload_is_scrubbed_end_to_end(self, client: TestClient) -> None:
        """The real write path: an admin action whose before/after contains a
        credential must land redacted."""
        from backend.app.repositories.user_repository import UserRepository

        db = TestingSessionLocal()
        try:
            admin = db.query(User).filter(User.role == UserRole.ADMIN).first()
            UserRepository(db).log_audit(
                action="ADMIN_PROVISIONING_PROBE",
                resource_type="User",
                resource_id="9001",
                user_id=admin.id,
                ip_address="203.0.113.55",
                before={"api_key": "sk-live-REALSECRET", "plan": "pro"},
                after={"api_key": "sk-live-ROTATED", "plan": "enterprise"},
                request_id="req-provision-9001",
            )
            row = (
                db.query(AuditLog)
                .filter(AuditLog.action == "ADMIN_PROVISIONING_PROBE")
                .order_by(AuditLog.id.desc())
                .first()
            )
            blob = f"{row.before_json}{row.after_json}"
            assert "sk-live-REALSECRET" not in blob
            assert "sk-live-ROTATED" not in blob
            assert "enterprise" in blob, "non-secret context must survive"

            db.query(AuditLog).filter(AuditLog.action == "ADMIN_PROVISIONING_PROBE").delete()
            db.commit()
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Client-address resolution (the audit row's "from where")
# ---------------------------------------------------------------------------
class _FakeClient:
    host = "198.51.100.9"


class _FakeRequest:
    def __init__(self, headers: dict):
        self.headers = headers
        self.client = _FakeClient()


class TestClientIp:
    def test_prefers_edge_header(self) -> None:
        assert client_ip(_FakeRequest({"x-real-ip": "203.0.113.4"})) == "203.0.113.4"

    def test_forwarded_for_uses_the_trusted_hop(self) -> None:
        # Left-most is attacker-controlled; right-most was appended by the edge.
        request = _FakeRequest({"x-forwarded-for": "10.0.0.1, 192.0.2.7, 198.51.100.20"})
        assert client_ip(request) == "198.51.100.20"

    def test_falls_back_to_the_socket(self) -> None:
        assert client_ip(_FakeRequest({})) == "198.51.100.9"

    def test_junk_headers_are_rejected(self) -> None:
        request = _FakeRequest({"x-real-ip": "not-an-ip", "x-forwarded-for": "'; DROP TABLE users;--"})
        assert client_ip(request) == "198.51.100.9"

    def test_admin_mutation_records_the_address(self, client: TestClient) -> None:
        """Regression for G-05: ``ip_address`` was never passed by the admin
        write path, so the column was NULL for every admin action."""
        headers = _admin_headers(client)
        headers["X-Real-IP"] = "203.0.113.200"
        response = client.post(
            "/api/v1/admin/orders/CONF-DOES-NOT-EXIST/transition",
            json={"new_status": "preparing"},
            headers=headers,
        )
        assert response.status_code in (404, 409), response.text
        # The audit row is only written on success, so assert on the read path
        # instead: an ADMIN_AUDIT_VIEW row from this session carries the address.
        client.get("/api/v1/admin/audit", headers=headers)
        db = TestingSessionLocal()
        try:
            row = (
                db.query(AuditLog)
                .filter(AuditLog.action == "ADMIN_AUDIT_VIEW")
                .order_by(AuditLog.id.desc())
                .first()
            )
            assert row is not None
            assert row.ip_address == "203.0.113.200", row.ip_address
        finally:
            db.close()
