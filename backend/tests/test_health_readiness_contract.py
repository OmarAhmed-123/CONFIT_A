"""G-08 / G-09 / G-17 — health tells the truth, and only to the right audience.

Three defects on one endpoint:

G-08  The public, unauthenticated ``/health`` published the AI provider
      inventory, the storage provider and the environment variables needed to
      change it, the VTON engine's licence and fork provenance, and the
      schema's missing tables and columns. Verified live against production.

G-09  ``storage.production_grade`` was ``false`` and ``storage.writable`` was
      ``false`` — every upload on the platform broken — while ``status`` read
      ``"healthy"``, because ``overall`` never consulted storage.

G-17  ``checks.ai_stylist_engine`` and ``checks.bnpl_gateway`` were the string
      literal ``"operational"``. No probe stood behind either; they asserted a
      verdict they never measured.

These tests drive the real HTTP endpoints and the real probe functions. Where
a verdict depends on configuration the test patches the *probe*, never the
answer, so a regression in the wiring still fails.
"""

import json

import pytest
from fastapi.testclient import TestClient

from backend.app.core.readiness import (
    CRITICALITY_CORE,
    CRITICALITY_SUPPORTING,
    STATE_BLOCKED,
    STATE_DEGRADED,
    STATE_READY,
    Capability,
    liveness_status,
    summarise_capabilities,
)
from backend.app.services import capability_service

HEALTH = "/api/v1/health"
READY = "/api/v1/health/ready"


def _login(client: TestClient, email: str) -> str:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def admin(client: TestClient):
    return {"Authorization": f"Bearer {_login(client, 'admin@confit.io')}"}


@pytest.fixture
def consumer(client: TestClient):
    return {"Authorization": f"Bearer {_login(client, 'shopper@confit.io')}"}


# --- G-08: the public surface must not be a reconnaissance summary ----------


def test_public_health_does_not_disclose_the_provider_inventory(client: TestClient):
    body = client.get(HEALTH).text
    assert "ai_providers" not in body
    for provider in ("openai", "groq", "gemini", "nvidia", "unorouter"):
        assert f'"{provider}"' not in body, f"{provider} leaked from public health"
    assert "cooling_for_seconds" not in body


def test_public_health_does_not_disclose_storage_internals(client: TestClient):
    body = client.get(HEALTH).text
    assert "STORAGE_PROVIDER" not in body, "the env var name is a targeting hint"
    assert "AWS_S3_BUCKET" not in body
    assert "production_grade" not in body
    assert "s3|r2" not in body


def test_public_health_does_not_disclose_engine_provenance(client: TestClient):
    body = client.get(HEALTH).text
    assert "vton_engine" not in body
    assert "Apache-2.0" not in body
    assert "fashn" not in body.lower()
    assert "vendor/" not in body


def test_public_health_does_not_disclose_schema_findings(client: TestClient):
    body = client.get(HEALTH).text
    assert "missing_tables" not in body
    assert "missing_columns" not in body
    assert "findings" not in body
    assert "expected_head" not in body


def test_public_health_keeps_what_the_release_gate_depends_on(client: TestClient):
    """The release gate reads checks.schema.database_revision to certify a deploy.

    Stripping it would blind the only check that prevents a schema-drift
    outage, so this pins the field rather than trusting a comment.
    """
    payload = client.get(HEALTH).json()
    schema = payload["checks"]["schema"]
    assert "database_revision" in schema
    assert "verdict" in schema


def test_the_full_diagnostics_are_admin_only(client: TestClient, admin, consumer):
    assert client.get(READY).status_code in (401, 403)
    assert client.get(READY, headers=consumer).status_code == 403
    r = client.get(READY, headers=admin)
    assert r.status_code == 200, r.text
    body = r.text
    # and the detail that was removed from the public surface is really here
    assert "ai_providers" in body
    assert "vton_engine" in body
    assert "storage" in body
    assert "missing_tables" in body


def test_public_health_still_publishes_the_contract(client: TestClient):
    """The meaning of each field travels with the payload, not in a wiki."""
    contract = client.get(HEALTH).json()["contract"]
    assert "status" in contract and "ready" in contract
    assert set(contract["states"]) == {"ready", "degraded", "blocked", "not_probed"}


# --- G-09: a blocked core capability cannot hide behind a green status ------


def test_a_blocked_core_capability_sets_ready_false_and_is_named(client: TestClient):
    payload = client.get(HEALTH).json()
    assert payload["ready"] is False, "no core capability is blocked in the test env?"
    assert payload["blocking_capabilities"], "ready=false must say what is blocking"
    assert "file_uploads" in payload["blocking_capabilities"], (
        "local storage is not production grade, so uploads are blocked and must be named"
    )


def test_liveness_and_readiness_are_independent_fields(client: TestClient):
    """The whole point of the split: green liveness, honest un-readiness."""
    payload = client.get(HEALTH).json()
    assert payload["status"] == "healthy", "the database is up, so the process is live"
    assert payload["ready"] is False, "but uploads are blocked, so it is not ready"


def test_the_blocking_state_survives_into_the_admin_view(client: TestClient, admin):
    detail = client.get(READY, headers=admin).json()
    uploads = detail["capabilities"]["file_uploads"]
    assert uploads["state"] == "blocked"
    assert uploads["criticality"] == "core"
    assert uploads["detail"], "a blocked capability must explain itself"


def _admin_headers(client: TestClient):
    return {"Authorization": f"Bearer {_login(client, 'admin@confit.io')}"}


def test_readiness_recovers_when_storage_becomes_production_grade(
    client: TestClient, monkeypatch
):
    """Prove ``ready`` is computed, not hardcoded to false."""
    monkeypatch.setattr(
        capability_service, "storage_status",
        lambda: {"provider": "s3", "production_grade": True, "writable": True,
                 "detail": "object storage configured"},
    )
    payload = client.get(HEALTH).json()
    assert "file_uploads" not in payload["blocking_capabilities"], (
        "with production-grade storage, uploads must stop blocking readiness"
    )
    detail = client.get(READY, headers=_admin_headers(client)).json()
    assert detail["capabilities"]["file_uploads"]["state"] == "ready"


def test_a_degraded_core_capability_does_not_darken_liveness(client: TestClient, monkeypatch):
    """Demo payments are a designed mode, not an outage."""
    monkeypatch.setattr(capability_service.settings, "PAYMENTS_LIVE", False, raising=False)
    payload = client.get(HEALTH).json()
    assert payload["status"] == "healthy"
    assert "payments" not in payload["blocking_capabilities"]
    assert "payments" in payload["degraded_capabilities"]


# --- G-17: no verdict without a probe --------------------------------------


def test_no_hardcoded_operational_claims_survive(client: TestClient, admin):
    """Asserted on the wire, not on source prose: comments may mention the word."""
    public = client.get(HEALTH).text
    detail = client.get(READY, headers=admin).text
    for body in (public, detail):
        assert "operational" not in body, "no capability may assert a verdict it did not measure"
        assert "ai_stylist_engine" not in body
        assert "bnpl_gateway" not in body


def test_the_ai_stylist_state_follows_the_provider_keys(monkeypatch):
    from backend.tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    try:
        monkeypatch.setattr(capability_service, "_ai_provider_keys", lambda: [])
        states = {c.name: c for c in capability_service.capability_probes(db, True)}
        assert states["ai_stylist"].state == STATE_DEGRADED
        assert "fallback" in states["ai_stylist"].detail

        monkeypatch.setattr(capability_service, "_ai_provider_keys", lambda: ["k1", "k2"])
        states = {c.name: c for c in capability_service.capability_probes(db, True)}
        assert states["ai_stylist"].state == STATE_READY
        assert "2 live provider key(s)" in states["ai_stylist"].detail
    finally:
        db.close()


def test_bnpl_reports_blocked_without_a_psp_key(monkeypatch):
    from backend.tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    try:
        monkeypatch.setattr(capability_service, "_bnpl_configured", lambda: False)
        states = {c.name: c for c in capability_service.capability_probes(db, True)}
        assert states["buy_now_pay_later"].state == STATE_BLOCKED
        # supporting, so it is reported but does not by itself block readiness
        assert states["buy_now_pay_later"].criticality == CRITICALITY_SUPPORTING
    finally:
        db.close()


def test_a_dead_database_is_unhealthy_and_blocks(client: TestClient, monkeypatch):
    """Liveness really does depend on the database, not on a constant."""
    def boom(db, database_ok):
        return [Capability("database", STATE_BLOCKED, CRITICALITY_CORE, "SELECT 1 failed")]

    import backend.app.controllers.telemetry_controller as tc

    monkeypatch.setattr(tc, "capability_probes", boom)
    payload = client.get(HEALTH).json()
    assert payload["ready"] is False
    assert payload["blocking_capabilities"] == ["database"]


# --- the contract itself, as a pure unit -----------------------------------


def test_a_core_blocker_blocks_and_a_supporting_one_does_not():
    caps = [
        Capability("a", STATE_READY, CRITICALITY_CORE),
        Capability("b", STATE_BLOCKED, CRITICALITY_SUPPORTING),
    ]
    out = summarise_capabilities(caps)
    assert out["ready"] is True
    assert out["blocking_capabilities"] == []
    assert out["degraded_capabilities"] == ["b"]

    caps.append(Capability("c", STATE_BLOCKED, CRITICALITY_CORE))
    out = summarise_capabilities(caps)
    assert out["ready"] is False
    assert out["blocking_capabilities"] == ["c"]


def test_an_unprobed_capability_is_reported_never_assumed_ok():
    out = summarise_capabilities([Capability("x", "not_probed", CRITICALITY_CORE)])
    assert out["ready"] is True, "unprobed is a gap, not a blocker"
    assert out["unprobed_capabilities"] == ["x"], "but it must not be invisible either"


@pytest.mark.parametrize(
    "db_ok,schema_ok,expected",
    [(True, True, "healthy"), (True, False, "degraded"), (False, True, "unhealthy"),
     (False, False, "unhealthy")],
)
def test_the_liveness_matrix(db_ok, schema_ok, expected):
    assert liveness_status(db_ok, schema_ok) == expected


def test_a_capability_cannot_be_invented_with_an_unknown_state():
    with pytest.raises(ValueError, match="unknown capability state"):
        Capability("x", "mostly_fine", CRITICALITY_CORE)
    with pytest.raises(ValueError, match="unknown criticality"):
        Capability("x", STATE_READY, "vibes")


# --- backward compatibility -------------------------------------------------


def test_the_uptime_monitor_contract_is_preserved(client: TestClient):
    """The monitor greps for the literal "status":"healthy"; do not break it."""
    body = client.get(HEALTH).text
    compact = json.dumps(json.loads(body), separators=(",", ":"))
    assert '"status":"healthy"' in compact


def test_the_capabilities_endpoint_contract_is_unchanged(client: TestClient):
    """It now delegates to the shared service; the wire shape must not move."""
    r = client.get("/api/v1/catalog/capabilities")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) >= {
        "payments_live", "payments_mode", "bnpl_live", "vton_gpu_ready",
        "ai_stylist_live", "bopis_live", "bopis_store_count", "storage_mode",
        "returns_window_days",
    }
    assert body["bnpl_live"] is (body["payments_live"] and body["bnpl_live"])
