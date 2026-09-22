"""One GPU, one answer: every capability surface must agree about try-on.

The defect this file exists for (consumer-role closure 2026-09-22)
----------------------------------------------------------------
``capability_flags`` answered ``vton_gpu_ready`` from
``bool(settings.VTON_WORKER_URL)`` while ``get_vton_capabilities`` asked the
worker over the network. Both "shared one source of truth" — and production
served, in the same second:

    GET /api/v1/catalog/capabilities -> "vton_gpu_ready": true
    GET /api/v1/try-on/capabilities  -> "engine_state": "temporarily_unavailable"
    GET /api/v1/health               -> "ready": false,
                                        "blocking_capabilities": ["virtual_try_on"]

Two of the three surfaces were honest. The dishonest one was the surface the
consumer UI binds its promises to (``useCapabilities``), which is the worst
possible arrangement: the platform's marketing honesty layer was the layer
telling the lie.

The lesson pinned here is that unifying the *probe* is not sufficient. Each
surface had the same probe available and each derived the verdict itself, so a
single divergent derivation reintroduced the contradiction. These tests assert
the *agreement invariant* between surfaces rather than either surface's value,
which is what makes them survive the next refactor of how the probe is fetched.

The mutation this file is designed to kill
-----------------------------------------
``M17`` in ``backend/scripts/run_mutation_gates.py`` reverts
``capability_flags`` to the configuration-presence derivation. Every test below
must fail when it does — that is the only evidence that the fix is protected
rather than merely present.
"""

from __future__ import annotations

import pytest

from backend.app.core.config import settings
from backend.app.services import vton_worker_observability as vwo
from backend.app.services.capability_service import capability_flags
from backend.tests.conftest import TestingSessionLocal


@pytest.fixture
def db():
    """A session on the suite's seeded test database.

    Matches the established pattern (``test_admin_analytics_*``) rather than
    adding a fixture to ``conftest.py``: this file is the only consumer, and the
    seeding/lifecycle is already handled session-wide by ``setup_test_db``.
    """
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()

#: A worker that is configured, reachable, and has its model loaded.
PROBE_READY = {
    "verdict": vwo.VERDICT_READY,
    "production_ready": True,
    "error_code": None,
    "detail": "GPU worker reachable and model loaded (live probe)",
    "probe_age_seconds": 0.4,
    "circuit": {"state": "closed", "retry_after_seconds": 0.0},
}

#: The real production state: VTON_WORKER_URL set, workspace disabled by its
#: spend limit, every job doomed. This is the probe that was misreported as
#: "gpu ready" purely because the environment variable existed.
PROBE_WORKSPACE_DISABLED = {
    "verdict": vwo.VERDICT_UNAVAILABLE,
    "production_ready": False,
    "error_code": vwo.CODE_ENGINE_UNAVAILABLE,
    "detail": "GPU worker is NOT reachable: every try-on job will fail.",
    "probe_age_seconds": 0.2,
    "circuit": {"state": "closed", "retry_after_seconds": 0.0},
}

PROBE_COLD = {
    "verdict": vwo.VERDICT_COLD_START,
    "production_ready": False,
    "error_code": vwo.CODE_WORKER_COLD_START,
    "detail": "GPU worker reachable but cold/model not loaded",
    "probe_age_seconds": 1.0,
    "circuit": {"state": "closed", "retry_after_seconds": 0.0},
}


def _flags(db, probe, monkeypatch, configured: bool = True):
    """capability_flags with the worker probe and URL configuration injected."""
    monkeypatch.setattr(settings, "VTON_WORKER_URL", "https://worker.test/process" if configured else None)
    return capability_flags(db, vton_worker=probe)


# ---------------------------------------------------------------------------
# The invariant: the flag tracks the probe, never the configuration
# ---------------------------------------------------------------------------


def test_configured_but_unreachable_worker_is_not_reported_ready(db, monkeypatch):
    """THE regression. A configured worker that cannot serve is not "gpu ready".

    This is the exact production state on 2026-09-22 and the exact assertion the
    old implementation failed: VTON_WORKER_URL was set, so the catalog said
    true, while the worker's own endpoint said every job would fail.
    """
    flags = _flags(db, PROBE_WORKSPACE_DISABLED, monkeypatch, configured=True)
    assert flags["vton_gpu_ready"] is False, (
        "vton_gpu_ready must reflect the live probe, not the presence of "
        "VTON_WORKER_URL — this is the 2026-09-22 production defect"
    )
    assert flags["vton_engine_state"] == vwo.ENGINE_STATE_UNAVAILABLE
    assert flags["vton_renderable"] is False
    # The feature IS offered on this deployment; it is broken, not absent.
    assert flags["vton_offered"] is True


def test_ready_probe_is_reported_ready(db, monkeypatch):
    flags = _flags(db, PROBE_READY, monkeypatch, configured=True)
    assert flags["vton_gpu_ready"] is True
    assert flags["vton_engine_state"] == vwo.ENGINE_STATE_AVAILABLE
    assert flags["vton_renderable"] is True


def test_cold_worker_is_renderable_but_not_ready(db, monkeypatch):
    """A cold worker renders (slowly). It is not an outage and not "ready"."""
    flags = _flags(db, PROBE_COLD, monkeypatch, configured=True)
    assert flags["vton_gpu_ready"] is False
    assert flags["vton_engine_state"] == vwo.ENGINE_STATE_COLD_START
    assert flags["vton_renderable"] is True


def test_unconfigured_worker_is_not_offered_not_broken(db, monkeypatch):
    """Absent is not the same as broken — the UI needs to tell them apart."""
    flags = _flags(db, None, monkeypatch, configured=False)
    assert flags["vton_offered"] is False
    assert flags["vton_renderable"] is False
    assert flags["vton_engine_state"] == vwo.ENGINE_STATE_MISCONFIGURED


def test_unprobed_engine_never_claims_ready(db, monkeypatch):
    """No measurement means "cannot render", never "ready"."""
    flags = _flags(db, {"verdict": vwo.VERDICT_UNKNOWN}, monkeypatch, configured=True)
    assert flags["vton_gpu_ready"] is False
    assert flags["vton_renderable"] is False


# ---------------------------------------------------------------------------
# The agreement invariant, asserted across live HTTP surfaces
# ---------------------------------------------------------------------------


def test_catalog_and_tryon_capabilities_agree(client, monkeypatch):
    """The two endpoints that contradicted each other must agree.

    Asserted as an *invariant between surfaces* (both must say the same thing)
    rather than against a hardcoded expected value, so this test stays meaningful
    as the probe implementation changes.
    """
    monkeypatch.setattr(settings, "VTON_WORKER_URL", "https://worker.test/process")
    monkeypatch.setattr(
        vwo, "vton_health_summary", lambda: dict(PROBE_WORKSPACE_DISABLED)
    )
    # tryon_service imports the module at call time and reads attributes off it,
    # so patching the module attribute is what both surfaces observe.
    catalog = client.get("/api/v1/catalog/capabilities")
    tryon = client.get("/api/v1/try-on/capabilities")
    assert catalog.status_code == 200, catalog.text
    assert tryon.status_code == 200, tryon.text

    cat, trn = catalog.json(), tryon.json()
    assert cat["vton_engine_state"] == trn["engine_state"], (
        "catalog capabilities and try-on capabilities disagree about the engine "
        f"({cat['vton_engine_state']!r} vs {trn['engine_state']!r}) — the "
        "2026-09-22 consumer-role defect"
    )
    assert cat["vton_gpu_ready"] == trn["engine"]["production_ready"]
    assert cat["vton_renderable"] == (trn["engine_state"] in ("available", "cold_start"))
    # And the user-facing sentence is the shared registry's, not a second copy.
    assert trn["user_message"] == vwo.engine_state_user_message(trn["engine_state"])


def test_catalog_flags_agree_with_readiness_capability(db, monkeypatch):
    """`/catalog/capabilities` and the readiness probe must not diverge either."""
    from backend.app.core.readiness import STATE_BLOCKED, STATE_READY
    from backend.app.services.capability_service import capability_probes

    monkeypatch.setattr(settings, "VTON_WORKER_URL", "https://worker.test/process")

    ready_flags = capability_flags(db, vton_worker=dict(PROBE_READY))
    ready_cap = next(
        c for c in capability_probes(db, True, dict(PROBE_READY)) if c.name == "virtual_try_on"
    )
    assert ready_flags["vton_gpu_ready"] is True
    assert ready_cap.state == STATE_READY

    down_flags = capability_flags(db, vton_worker=dict(PROBE_WORKSPACE_DISABLED))
    down_cap = next(
        c
        for c in capability_probes(db, True, dict(PROBE_WORKSPACE_DISABLED))
        if c.name == "virtual_try_on"
    )
    assert down_flags["vton_gpu_ready"] is False
    assert down_cap.state == STATE_BLOCKED


# ---------------------------------------------------------------------------
# The classifier itself — pure, so it is cheap to pin exhaustively
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "verdict,configured,expected",
    [
        (None, False, vwo.ENGINE_STATE_MISCONFIGURED),
        (vwo.VERDICT_NOT_CONFIGURED, True, vwo.ENGINE_STATE_UNAVAILABLE),
        (vwo.VERDICT_READY, True, vwo.ENGINE_STATE_AVAILABLE),
        (vwo.VERDICT_COLD_START, True, vwo.ENGINE_STATE_COLD_START),
        (vwo.VERDICT_UNAVAILABLE, True, vwo.ENGINE_STATE_UNAVAILABLE),
        (vwo.VERDICT_UNKNOWN, True, vwo.ENGINE_STATE_UNAVAILABLE),
        # A verdict of "ready" with no URL configured means the deployment does
        # not offer try-on at all; offering wins the tie, so it is misconfigured.
        (vwo.VERDICT_READY, False, vwo.ENGINE_STATE_MISCONFIGURED),
    ],
)
def test_engine_state_classifier(verdict, configured, expected):
    state = vwo.engine_state_from_probe({"verdict": verdict}, configured=configured)
    assert state == expected


def test_renderable_states_are_exactly_ready_and_cold_start():
    assert vwo.engine_can_render(vwo.ENGINE_STATE_AVAILABLE) is True
    assert vwo.engine_can_render(vwo.ENGINE_STATE_COLD_START) is True
    assert vwo.engine_can_render(vwo.ENGINE_STATE_UNAVAILABLE) is False
    assert vwo.engine_can_render(vwo.ENGINE_STATE_MISCONFIGURED) is False
    assert vwo.engine_can_render(vwo.ENGINE_STATE_UNKNOWN) is False


def test_renderable_states_carry_no_scary_message():
    """A working capability must not apologise; a broken one must speak."""
    for state in (vwo.ENGINE_STATE_AVAILABLE, vwo.ENGINE_STATE_COLD_START):
        if state == vwo.ENGINE_STATE_AVAILABLE:
            assert vwo.engine_state_user_message(state) is None
    down = vwo.engine_state_user_message(vwo.ENGINE_STATE_UNAVAILABLE)
    assert down and "offline" in down
    cold = vwo.engine_state_user_message(vwo.ENGINE_STATE_COLD_START)
    assert cold and "warming up" in cold


def test_unavailable_message_does_not_blame_the_user_or_leak_a_secret():
    """Honesty labels must be user-facing prose, not operator diagnostics."""
    msg = vwo.engine_state_user_message(vwo.ENGINE_STATE_UNAVAILABLE)
    for leak in ("Modal", "workspace", "spend limit", "VTON_WORKER", "GPU worker"):
        assert leak.lower() not in msg.lower(), (
            f"operator diagnostic {leak!r} leaked into a shopper-facing sentence"
        )
