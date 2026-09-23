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
    STATE_NOT_PROBED,
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
    """The two fabricated keys are gone from every surface.

    The word "operational" is NOT banned: PR #142 made ``checks.vton_pipeline``
    report it from a live worker probe, which is a measured verdict and a good
    one. What G-17 forbids is a verdict with no probe behind it.
    """
    for body in (client.get(HEALTH).text, client.get(READY, headers=admin).text):
        assert "ai_stylist_engine" not in body
        assert "bnpl_gateway" not in body
    from pathlib import Path

    src = Path("backend/app/controllers/telemetry_controller.py").read_text()
    assert '"ai_stylist_engine": "operational"' not in src
    assert '"bnpl_gateway": "operational"' not in src


def test_every_reported_capability_state_is_measured(client: TestClient, admin):
    """No capability may report a state its probe did not produce."""
    detail = client.get(READY, headers=admin).json()
    caps = detail["capabilities"]
    assert caps, "the readiness surface must actually report capabilities"
    for name, cap in caps.items():
        assert cap["state"] in {"ready", "degraded", "blocked", "not_probed"}, name
        assert cap["criticality"] in {"core", "supporting"}, name
        assert cap["detail"], f"{name} reported a state without explaining it"
    # and the readiness verdict agrees with the per-capability detail
    blocking = {n for n, c in caps.items()
                if c["criticality"] == "core" and c["state"] == "blocked"}
    assert blocking == set(detail["blocking_capabilities"])


def test_try_on_distinguishes_not_offered_from_broken(monkeypatch):
    """PR #142's lesson: configuration is not availability, and absence is not outage."""
    from backend.app.services.capability_service import _vton_capability

    # not configured, not production -> the feature is simply not offered
    monkeypatch.setattr(capability_service.settings, "VTON_WORKER_URL", None, raising=False)
    cap = _vton_capability({"verdict": "not_configured"})
    assert cap.state == STATE_DEGRADED and cap.criticality == CRITICALITY_SUPPORTING

    # configured and serving -> ready
    monkeypatch.setattr(capability_service.settings, "VTON_WORKER_URL", "https://w", raising=False)
    cap = _vton_capability({"verdict": "ready", "production_ready": True})
    assert cap.state == STATE_READY and cap.criticality == CRITICALITY_CORE

    # configured but cold -> degraded, still core
    cap = _vton_capability({"verdict": "cold_start"})
    assert cap.state == STATE_DEGRADED and cap.criticality == CRITICALITY_CORE

    # configured but cannot serve -> blocked, and the reason is carried
    cap = _vton_capability({"verdict": "unreachable", "production_ready": False,
                            "reason": "VTON_WORKER_NOT_READY"})
    assert cap.state == STATE_BLOCKED and cap.criticality == CRITICALITY_CORE
    assert "VTON_WORKER_NOT_READY" in cap.detail


def test_the_ai_stylist_state_does_not_follow_the_provider_keys(monkeypatch):
    """REWRITTEN 2026-09-22 — this test used to assert a false claim.

    It was ``test_the_ai_stylist_state_follows_the_provider_keys`` and it
    asserted, with two keys configured:

        assert states["ai_stylist"].state == STATE_READY
        assert "2 live provider key(s)" in states["ai_stylist"].detail

    ``ready`` means "probed and working" in this project's own contract, and
    nothing had been probed: no provider had been contacted, and the word
    "live" described a key that had never been used. That is the same
    configuration-as-measurement defect as ``vton_gpu_ready`` — it merely
    failed in the quiet direction (a capability that might be broken reported
    as working) rather than the loud one.

    Same pattern as the VTON case: the defect was encoded as an expectation, so
    the suite defended it. The test now asserts the honest contract — a
    configured key yields ``not_probed``, and only a MEASURED failure yields
    ``degraded``.
    """
    from backend.tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    try:
        # No key: the deterministic grounded fallback answers. Unchanged.
        monkeypatch.setattr(capability_service, "_ai_provider_keys", lambda: [])
        states = {c.name: c for c in capability_service.capability_probes(db, True)}
        assert states["ai_stylist"].state == STATE_DEGRADED
        assert "fallback" in states["ai_stylist"].detail

        # Keys configured, nothing measured: NAME THE GAP, do not claim ready.
        # REWRITTEN 2026-09-23. `_ai_provider_keys` no longer decides anything:
        # the state comes from the readiness measurement, so pinning the key list
        # alone would leave the test measuring the real settings. It pins both
        # halves — providers ARE configured, nothing has been measured.
        from backend.app.services import ai_readiness

        ai_readiness.reset_cache_for_tests()  # no probe has run
        monkeypatch.setattr(
            ai_readiness, "_configured_providers",
            lambda: {"groq": {"url": "https://api.groq.com/openai/v1/models", "auth": "Bearer k"}},
        )
        monkeypatch.setattr(capability_service, "_ai_provider_keys", lambda: ["groq"])
        # Pin the runtime measurement deterministically: no provider is
        # quarantined, so the state must be `not_probed`, never `ready`.
        monkeypatch.setattr(
            capability_service, "_ai_quarantine_state", lambda: ({}, {})
        )
        states = {c.name: c for c in capability_service.capability_probes(db, True)}
        assert states["ai_stylist"].state == STATE_NOT_PROBED, (
            "a configured key is not a measurement — reporting `ready` here is "
            "the 2026-09-22 ai_stylist defect"
        )
        assert states["ai_stylist"].criticality == CRITICALITY_SUPPORTING
        # 2026-09-23: the probe now exists, so the detail names it rather than
        # saying none exists — the state is still `not_probed` until it runs.
        assert "no availability measurement" in states["ai_stylist"].detail
        # And an honest gap must not make the platform unready.
        assert "ai_stylist" not in summarise_capabilities(
            capability_service.capability_probes(db, True)
        )["blocking_capabilities"]
    finally:
        db.close()


def test_the_ai_stylist_state_degrades_from_a_measured_failure(monkeypatch):
    """The half that IS measurable must actually be used.

    A provider enters quarantine only after it really failed (HTTP 402/429/auth),
    so "all configured providers are quarantined" is an observation, not a
    configuration read. When that is true the live path is down and the platform
    must say ``degraded`` — on the fallback — rather than staying silent.
    """
    from backend.tests.conftest import TestingSessionLocal
    from backend.app.providers.orchestrator import get_orchestrator
    from backend.app.services import ai_readiness

    db = TestingSessionLocal()
    try:
        ai_readiness.reset_cache_for_tests()
        monkeypatch.setattr(
            ai_readiness, "_configured_providers",
            lambda: {"groq": {"url": "https://api.groq.com/openai/v1/models", "auth": "Bearer k"}},
        )
        monkeypatch.setattr(capability_service, "_ai_provider_keys", lambda: ["k1"])
        orch = get_orchestrator()
        orch.cooldowns.clear()
        try:
            # Before any failure: not_probed (nothing measured yet).
            states = {c.name: c for c in capability_service.capability_probes(db, True)}
            assert states["ai_stylist"].state == STATE_NOT_PROBED

            # A REAL failure quarantines the provider -> measured degradation.
            orch.mark_cooling("groq", "HTTP 402")
            states = {c.name: c for c in capability_service.capability_probes(db, True)}
            cap = states["ai_stylist"]
            assert cap.state == STATE_DEGRADED, (
                "a quarantined provider is a measured outage; the capability must "
                "degrade rather than report ready/not_probed"
            )
            assert "quarantined" in cap.detail and "fallback" in cap.detail
            # Supporting criticality: visible, but never sets ready=false.
            summary = summarise_capabilities(capability_service.capability_probes(db, True))
            assert "ai_stylist" in summary["degraded_capabilities"]
            assert "ai_stylist" not in summary["blocking_capabilities"]
        finally:
            orch.cooldowns.clear()
    finally:
        db.close()


def test_the_ai_stylist_state_degrades_from_a_measured_probe_failure(monkeypatch):
    """The probe's own verdicts drive the capability, at last.

    Until 2026-09-23 the capability could not do this: no probe existed, so a
    deployment whose provider key was revoked reported an honest `not_probed` and
    nothing else. Now a measured `auth_failed` / `quota_exhausted` / `timeout`
    must surface as `degraded` (served by the deterministic grounded fallback),
    still as a SUPPORTING capability so an AI outage cannot mark the platform
    unready.
    """
    import time

    import httpx

    from backend.app.services import ai_readiness
    from backend.tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    try:
        monkeypatch.setattr(capability_service, "_ai_quarantine_state", lambda: ({}, {}))
        monkeypatch.setattr(
            ai_readiness, "_configured_providers",
            lambda: {"groq": {"url": "https://api.groq.com/openai/v1/models", "auth": "Bearer k"}},
        )

        for status, expected_state in ((200, STATE_READY), (401, STATE_DEGRADED), (429, STATE_DEGRADED)):
            ai_readiness.reset_cache_for_tests()
            transport = httpx.MockTransport(lambda request: httpx.Response(status, json={}))
            ai_readiness._cache.store(ai_readiness.probe_now(transport=transport))

            states = {c.name: c for c in capability_service.capability_probes(db, True)}
            cap = states["ai_stylist"]
            assert cap.state == expected_state, (
                f"a measured HTTP {status} from the provider must map to "
                f"{expected_state}, got {cap.state} ({cap.detail})"
            )
            assert cap.criticality == "supporting"
            summary = summarise_capabilities(capability_service.capability_probes(db, True))
            assert "ai_stylist" not in summary["blocking_capabilities"]
            if expected_state == STATE_READY:
                assert "live probe" in cap.detail
            else:
                assert "fallback" in cap.detail
        assert time.time() > 0
    finally:
        ai_readiness.reset_cache_for_tests()
        db.close()


def test_ai_provider_keys_honours_the_documented_groq_variable(monkeypatch):
    """The capability contract must read the same setting the system uses.

    The Groq slot was read from the deprecated ``GROK_API_KEY`` FIELD while the
    orchestrator resolves it through the ``groq_api_key`` PROPERTY, which prefers
    the documented ``GROQ_API_KEY``. Measured 2026-09-22: a deployment configured
    with the documented spelling reported ``ai_stylist_live: false`` although the
    key resolved and Groq was genuinely being called — a false NEGATIVE, the
    mirror image of the VTON false positive.
    """
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "NVIDIA_API_KEY", None)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    # Only the DOCUMENTED variable is set; the legacy alias is empty.
    monkeypatch.setattr(settings, "GROQ_API_KEY", "gsk_documented")
    monkeypatch.setattr(settings, "GROK_API_KEY", None)
    assert settings.groq_api_key == "gsk_documented"
    # 2026-09-23: this returns provider NAMES now, not key values. The capability
    # contract only ever needs to know *which* providers are configured; the
    # readiness probe resolves the credential itself. Returning secrets here put
    # them one accidental log statement away from a response body.
    assert capability_service._ai_provider_keys() == ["groq"], (
        "the documented GROQ_API_KEY must be visible to the capability contract"
    )

    # The legacy spelling keeps working (backwards compatibility is intentional).
    monkeypatch.setattr(settings, "GROQ_API_KEY", None)
    monkeypatch.setattr(settings, "GROK_API_KEY", "gsk_legacy")
    assert capability_service._ai_provider_keys() == ["groq"]

    # A blank/whitespace value from a partially-filled .env is unset, not a key.
    monkeypatch.setattr(settings, "GROK_API_KEY", "   ")
    assert capability_service._ai_provider_keys() == []


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
    def boom(db, database_ok, vton_worker=None):
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
