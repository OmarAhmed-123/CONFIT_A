"""VTON worker observability — the fix for "production said available while
every job failed".

Production evidence these tests encode (2026-09-21, live):

    GET  /api/v1/health                -> "vton_pipeline": "configured: GPU worker
                                         URL + admin token present"
    GET  /api/v1/try-on/capabilities   -> "engine_state": "available"
    POST /api/v1/try-on/jobs (real)    -> 202, then status=failed after 39.4 s
                                         error_code=VTON_WORKER_NOT_READY
                                         error_message="... not ready after 3
                                         attempts: unreachable"
    direct probe of the Modal endpoint -> HTTP 404
                                         "modal-http: workspace ac-io3nXB7Q2nuaHHl8mVkeLH is disabled"
    `modal` SDK, minimal function      -> ResourceExhaustedError: Workspace
                                         ac-io3nXB7Q2nuaHHl8mVkeLH has exceeded
                                         its spend limit

So the honest verdict is "the GPU workspace cannot serve traffic", and the
user-facing code must be VTON_ENGINE_UNAVAILABLE (do not retry), not
VTON_WORKER_NOT_READY (retry in a moment).
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.main import app
from backend.app.services import vton_worker_observability as vwo
from backend.app.services.vton_worker_observability import (
    WorkerCircuitBreaker,
    WorkerProbe,
    classify_worker_failure,
)

client = TestClient(app)

def _admin():
    """G-08: per-capability diagnostics moved to the admin-only readiness surface."""
    # A throwaway client: TestClient shares a cookie jar per instance, and
    # logging in on the module-level one would authenticate every later call.
    r = TestClient(app).post("/api/v1/auth/login",
                             json={"email": "admin@confit.io", "password": "Password123!"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}



# The literal response body the production endpoint returned.
MODAL_DISABLED_BODY = "modal-http: workspace ac-io3nXB7Q2nuaHHl8mVkeLH is disabled"
MODAL_SPEND_LIMIT = "ResourceExhaustedError: Workspace ac-io3nXB7Q2nuaHHl8mVkeLH has exceeded its spend limit"


# ---------------------------------------------------------------------------
# 1. Error classification — what the platform said, not what we assumed.
# ---------------------------------------------------------------------------
def test_disabled_workspace_is_engine_unavailable_not_not_ready():
    out = classify_worker_failure(status_code=404, body_text=MODAL_DISABLED_BODY)
    assert out["code"] == "VTON_ENGINE_UNAVAILABLE"
    assert out["retryable"] is False
    assert "not going to work" not in out["user_message"]  # copy stays factual
    assert "offline" in out["user_message"]


def test_spend_limit_exhaustion_is_engine_unavailable():
    out = classify_worker_failure(exception=MODAL_SPEND_LIMIT)
    assert out["code"] == "VTON_ENGINE_UNAVAILABLE"
    assert out["retryable"] is False


def test_cold_start_is_retryable_and_distinct():
    out = classify_worker_failure(status_code=404, body_text="modal-http: invalid function call")
    assert out["code"] == "VTON_WORKER_COLD_START"
    assert out["retryable"] is True
    out2 = classify_worker_failure(status_code=503, body_text="VTON_NOT_READY: model is loading")
    assert out2["code"] == "VTON_WORKER_COLD_START"


def test_auth_and_input_failures_keep_their_codes():
    assert classify_worker_failure(status_code=401)["code"] == "VTON_AUTH_FAILURE"
    assert classify_worker_failure(status_code=403)["code"] == "VTON_AUTH_FAILURE"
    assert classify_worker_failure(status_code=422)["code"] == "VTON_INPUT_INVALID"
    # a plain timeout is transient
    t = classify_worker_failure(exception="ReadTimeout: timed out")
    assert t["code"] == "VTON_WORKER_NOT_READY" and t["retryable"] is True


def test_user_messages_are_actionable_not_internal():
    """The old message leaked internals ("after 3 attempts: unreachable")."""
    for kwargs in (
        dict(status_code=404, body_text=MODAL_DISABLED_BODY),
        dict(status_code=404, body_text="invalid function call"),
        dict(status_code=503, body_text="not ready"),
    ):
        msg = classify_worker_failure(**kwargs)["user_message"]
        assert "attempt" not in msg.lower()
        assert "unreachable" not in msg.lower()
        assert len(msg) > 30


# ---------------------------------------------------------------------------
# 2. Circuit breaker — fail in milliseconds instead of ~39 s.
# ---------------------------------------------------------------------------
class _FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


def test_circuit_opens_after_threshold_and_fails_fast():
    clock = _FakeClock()
    cb = WorkerCircuitBreaker(failure_threshold=2, open_seconds=120.0, clock=clock)
    assert cb.allow() is True
    cb.record_failure(code="VTON_WORKER_NOT_READY", retryable=True)
    assert cb.snapshot()["state"] == "closed"
    assert cb.allow() is True
    cb.record_failure(code="VTON_WORKER_NOT_READY", retryable=True)
    assert cb.snapshot()["state"] == "open"
    assert cb.allow() is False  # <- the user no longer waits 39 s


def test_non_retryable_failure_opens_the_circuit_immediately():
    cb = WorkerCircuitBreaker(failure_threshold=5, open_seconds=60.0, clock=_FakeClock())
    cb.record_failure(code="VTON_ENGINE_UNAVAILABLE", retryable=False)
    snap = cb.snapshot()
    assert snap["state"] == "open"
    assert snap["last_error_code"] == "VTON_ENGINE_UNAVAILABLE"
    assert cb.allow() is False


def test_circuit_half_opens_and_closes_on_success():
    clock = _FakeClock()
    cb = WorkerCircuitBreaker(failure_threshold=1, open_seconds=30.0, clock=clock)
    cb.record_failure(code="VTON_WORKER_COLD_START", retryable=True)
    assert cb.allow() is False
    clock.advance(31)
    assert cb.allow() is True            # exactly one probe is let through
    assert cb.snapshot()["state"] == "half_open"
    assert cb.allow() is False           # concurrent callers keep failing fast
    cb.record_success()
    assert cb.snapshot()["state"] == "closed"
    assert cb.allow() is True


def test_half_open_failure_reopens():
    clock = _FakeClock()
    cb = WorkerCircuitBreaker(failure_threshold=1, open_seconds=10.0, clock=clock)
    cb.record_failure(code="X", retryable=True)
    clock.advance(11)
    assert cb.allow() is True
    cb.record_failure(code="X", retryable=True)
    assert cb.snapshot()["state"] == "open"
    assert cb.allow() is False


def test_open_circuit_reports_retry_after():
    clock = _FakeClock()
    cb = WorkerCircuitBreaker(failure_threshold=1, open_seconds=120.0, clock=clock)
    cb.trip(code="VTON_ENGINE_UNAVAILABLE", detail="workspace disabled")
    clock.advance(20)
    snap = cb.snapshot()
    assert snap["state"] == "open"
    assert 95 <= snap["retry_after_seconds"] <= 100


# ---------------------------------------------------------------------------
# 3. Cached probe — bounded, never blocking a request after the first call.
# ---------------------------------------------------------------------------
def test_probe_cache_serves_last_verdict_and_refreshes_in_background(monkeypatch):
    """Exercises the REAL WorkerProbe cache, so this one stubs the network
    primitive (`_perform_probe`) rather than the module-level accessor."""
    calls = {"n": 0}

    def fake_probe(timeout):
        calls["n"] += 1
        return {"verdict": "ready", "ok": True, "reason": None, "status_code": 200}

    monkeypatch.setattr(vwo, "_perform_probe", fake_probe)
    clock = _FakeClock()
    probe = WorkerProbe(ttl_seconds=60.0, probe_timeout=1.0, clock=clock)
    first = probe.get()
    assert first["verdict"] == "ready" and calls["n"] == 1
    # within TTL: served from cache, no new probe
    assert probe.get()["verdict"] == "ready" and calls["n"] == 1
    # after TTL: stale value returned immediately + background refresh
    clock.advance(61)
    stale = probe.get()
    assert stale["verdict"] == "ready"
    for _ in range(50):
        if calls["n"] == 2:
            break
        time.sleep(0.02)
    assert calls["n"] == 2, "background refresh did not run"


def test_probe_never_raises(monkeypatch):
    def boom(timeout):
        raise RuntimeError("socket exploded")

    monkeypatch.setattr(vwo, "_perform_probe", boom)
    out = WorkerProbe(ttl_seconds=60.0, probe_timeout=1.0, clock=_FakeClock()).get()
    assert out["verdict"] == "unavailable"
    assert out["ok"] is False
    assert "socket exploded" in out["reason"]


def test_health_summary_is_never_production_ready_on_configuration_alone(monkeypatch):
    monkeypatch.setattr(settings, "VTON_WORKER_URL", "https://worker.example/process", raising=False)
    monkeypatch.setattr(settings, "VTON_WORKER_ADMIN_TOKEN", "tok", raising=False)
    monkeypatch.setattr(
        vwo, "probe_worker_state",
        lambda force=False, allow_refresh=True: {"verdict": "unavailable", "ok": False, "status_code": 404,
                         "reason": f"HTTP 404: {MODAL_DISABLED_BODY}",
                         "error_code": "VTON_ENGINE_UNAVAILABLE"},
    )
    # the process-wide probe is a cache: without this it can serve a verdict
    # produced by an earlier test instead of the stubbed one.
    vwo.reset_worker_observability()
    try:
        s = vwo.vton_health_summary()
        assert s["production_ready"] is False
        assert s["verdict"] == "unavailable"
        assert "is disabled" in (s["reason"] or "")
        assert "Configuration alone is not availability" in s["detail"]
    finally:
        vwo.reset_worker_observability()


# ---------------------------------------------------------------------------
# 4. End-to-end through the real app: health + capabilities + fail-fast job.
# ---------------------------------------------------------------------------
@pytest.fixture
def dead_worker(monkeypatch):
    """Configure a worker URL, but make the live probe report the real
    production condition: HTTP 404 'workspace ... is disabled'."""
    monkeypatch.setattr(settings, "VTON_WORKER_URL", "https://worker.example/-process", raising=False)
    monkeypatch.setattr(settings, "VTON_WORKER_ADMIN_TOKEN", "tok", raising=False)
    monkeypatch.setattr(settings, "VTON_WORKER_PROBE_TIMEOUT_SECONDS", 1.0, raising=False)
    monkeypatch.setattr(
        vwo, "probe_worker_state",
        lambda force=False, allow_refresh=True: {
            "verdict": "unavailable", "ok": False, "status_code": 404,
            "reason": f"HTTP 404: {MODAL_DISABLED_BODY}",
            "error_code": "VTON_ENGINE_UNAVAILABLE",
            "retryable": False,
        },
    )
    vwo.reset_worker_observability()
    yield
    vwo.reset_worker_observability()


def test_health_reports_degraded_and_the_real_reason(dead_worker, monkeypatch):
    """A dead try-on engine must be reported — and named, not just darkened.

    G-09 split the two questions this test used to fold into one field.
    ``status`` is liveness scope: the API is still serving traffic, so it stays
    healthy. The outage is reported through ``ready`` and
    ``blocking_capabilities``, which is a stronger statement than "degraded"
    because it says *what* is broken. The machine-readable worker verdict and
    the human string moved to the admin-only readiness surface (G-08).
    """
    # Pin the WORKER's honesty: close the pilot path so this test measures
    # what it was written to measure. A pilot-tier engine can now serve a
    # down worker (2026-09-28), which is a different question.
    monkeypatch.setattr(settings, "VTON_LICENSE_TIER", "commercial", raising=False)
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    public = res.json()
    assert public["status"] == "healthy", "the API is still serving; liveness is unaffected"
    assert public["ready"] is False, "but a core capability is down"
    assert "virtual_try_on" in public["blocking_capabilities"]

    body = client.get("/api/v1/health/ready", headers=_admin()).json()
    worker = body["checks"]["vton_worker"]
    assert worker["production_ready"] is False
    assert worker["error_code"] == "VTON_ENGINE_UNAVAILABLE"
    assert body["checks"]["vton_pipeline"].startswith("unavailable:")
    assert "is disabled" in body["checks"]["vton_pipeline"]
    # and the capability carries the real reason, not just a state
    assert "VTON_ENGINE_UNAVAILABLE" in body["capabilities"]["virtual_try_on"]["detail"]


def test_capabilities_no_longer_claims_available(dead_worker, monkeypatch):
    # Pin the WORKER's honesty: close the pilot path so this test measures
    # what it was written to measure. A pilot-tier engine can now serve a
    # down worker (2026-09-28), which is a different question.
    monkeypatch.setattr(settings, "VTON_LICENSE_TIER", "commercial", raising=False)
    res = client.get("/api/v1/try-on/capabilities?product_ids=3")
    assert res.status_code == 200
    body = res.json()
    assert body["engine_state"] == "temporarily_unavailable"
    assert body["engine"]["verdict"] == "unavailable"
    assert body["engine"]["production_ready"] is False
    assert body["engine"]["error_code"] == "VTON_ENGINE_UNAVAILABLE"
    # the SLA is published, so the UI can set real expectations
    assert body["sla"]["cold_start_seconds_budget"] > 0
    assert body["sla"]["fail_fast_seconds"] <= 1.0
    assert body["user_message"]
    # and a supported category is NOT advertised as supported while the engine
    # cannot render — that is what made users lose 40 s per attempt.
    product = body["products"][0]
    assert product["state"] == "temporarily_unavailable"
    assert product["reason_code"] == "VTON_ENGINE_UNAVAILABLE"


def test_job_fails_fast_with_the_honest_code_when_the_circuit_is_open(dead_worker):
    """The user must not wait ~39 s for an answer the API already knows."""
    vwo.circuit_breaker.trip(code="VTON_ENGINE_UNAVAILABLE", detail="workspace is disabled")
    started = time.time()
    res = client.post("/api/v1/try-on/jobs", json={
        "product_ids": [3],
        "user_image_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600",
    })
    elapsed = time.time() - started
    assert res.status_code == 202
    job = res.json()
    assert job["status"] == "failed"
    assert job["error_code"] == "VTON_ENGINE_UNAVAILABLE"
    assert job["metrics"]["failed_fast"] is True
    # measured production failure took 39.4 s; fail-fast must be orders of
    # magnitude cheaper (the assertion leaves generous room for CI).
    assert elapsed < 5.0, f"fail-fast took {elapsed:.1f}s"
    # a finished job is marked finished
    assert job["metrics"]["user_message"]
    assert "not stored" in job["metrics"]["user_message"]


def test_input_validation_failure_does_not_open_the_circuit(dead_worker):
    """A bad photo says nothing about worker availability."""
    cb = vwo.circuit_breaker
    cb.reset()
    res = client.post("/api/v1/try-on/jobs", json={
        "product_ids": [],  # rejected before any worker interaction
        "user_image_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600",
    })
    assert res.status_code in (202, 422)
    assert cb.snapshot()["state"] == "closed"


def test_health_stays_healthy_when_tryon_is_simply_not_configured(monkeypatch):
    """No VTON_WORKER_URL in a non-production host = the feature is not
    offered, not an outage. (Otherwise CI and local dev would read "degraded"
    forever and the signal would be meaningless.)"""
    monkeypatch.delenv("VTON_WORKER_URL", raising=False)
    monkeypatch.setattr(settings, "VTON_WORKER_URL", None, raising=False)
    monkeypatch.setattr(settings, "ENVIRONMENT", "development", raising=False)
    vwo.reset_worker_observability()
    try:
        body = client.get("/api/v1/health").json()
        assert body["status"] == "healthy"
        # not offered is not broken: it must not block readiness either
        assert "virtual_try_on" not in body["blocking_capabilities"]
        detail = client.get("/api/v1/health/ready", headers=_admin()).json()
        assert detail["checks"]["vton_worker"]["verdict"] == "not_configured"
    finally:
        vwo.reset_worker_observability()


def test_health_degrades_in_production_when_tryon_is_not_configured(monkeypatch):
    monkeypatch.delenv("VTON_WORKER_URL", raising=False)
    monkeypatch.setattr(settings, "VTON_WORKER_URL", None, raising=False)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production", raising=False)
    vwo.reset_worker_observability()
    try:
        body = client.get("/api/v1/health").json()
        assert body["status"] == "degraded"
    finally:
        monkeypatch.setattr(settings, "ENVIRONMENT", "development", raising=False)
        vwo.reset_worker_observability()


# ---------------------------------------------------------------------------
# 5. PASSIVE health (2026-10-03): a public health read must never be the
# reason a billed, scaled-to-zero GPU container spins up.
# ---------------------------------------------------------------------------
def test_public_health_never_probes_the_worker(monkeypatch):
    """/health serves cached evidence only; with no cache it says unknown.

    Before 2026-10-03 the /health vton line live-probed (first call
    synchronously, later reads via background refresh), so an external
    uptime monitor polling /health kept an A10G container alive forever
    without a single real try-on job.
    """
    monkeypatch.delenv("VTON_WORKER_URL", raising=False)
    monkeypatch.setattr(settings, "VTON_WORKER_URL", "https://worker.example/process", raising=False)
    monkeypatch.setattr(settings, "VTON_WORKER_ADMIN_TOKEN", "tok", raising=False)
    vwo.reset_worker_observability()

    calls = {"n": 0}

    def _count_probe(*a, **k):
        calls["n"] += 1
        return {"verdict": vwo.VERDICT_READY, "ok": True, "status_code": 200}

    monkeypatch.setattr(WorkerProbe, "_run_probe", _count_probe)
    try:
        # PUBLIC /health: cold cache — must answer WITHOUT a single probe.
        body = client.get("/api/v1/health").json()
        assert body["status"] in ("healthy", "degraded")  # never a crash
        assert "virtual_try_on" in body.get("degraded_capabilities", []) or \
            body.get("ready") is False
        assert calls["n"] == 0, "public /health must not probe the GPU worker"
        # unknown must not silently claim availability either
        summary = vwo.vton_health_summary(allow_refresh=False)
        assert summary["verdict"] == vwo.VERDICT_UNKNOWN
        assert summary["production_ready"] is False
    finally:
        vwo.reset_worker_observability()


def test_real_job_success_feeds_the_passive_line(monkeypatch):
    """After a real try-on job, /health reports the last known state — no probe.

    record_job_observation is the zero-cost evidence source: the worker
    proved itself by serving inference, so the passive line can be both
    honest AND informative.
    """
    monkeypatch.delenv("VTON_WORKER_URL", raising=False)
    monkeypatch.setattr(settings, "VTON_WORKER_URL", "https://worker.example/process", raising=False)
    monkeypatch.setattr(settings, "VTON_WORKER_ADMIN_TOKEN", "tok", raising=False)
    vwo.reset_worker_observability()

    calls = {"n": 0}

    def _count_probe(*a, **k):
        calls["n"] += 1
        return {"verdict": vwo.VERDICT_READY, "ok": True, "status_code": 200}

    monkeypatch.setattr(WorkerProbe, "_run_probe", _count_probe)
    try:
        vwo.record_job_observation(vwo.VERDICT_READY, device="NVIDIA A10", git_sha="abc1234")
        # Public /health: the observation IS the last known state -> operational
        # without a probe (cache is fresh, so even an active read would not
        # fire — the point is the passive path serves real evidence).
        body = client.get("/api/v1/health").json()
        assert calls["n"] == 0
        # Operator surface carries the human string built from that evidence.
        ready = client.get("/api/v1/health/ready", headers=_admin()).json()
        line = ready["checks"]["vton_pipeline"]
        assert line.startswith("operational:")
        assert "real try-on traffic" in line
        summary = vwo.vton_health_summary(allow_refresh=False)
        assert summary["verdict"] == vwo.VERDICT_READY
        assert summary["production_ready"] is True
        assert summary["evidence_source"] == "real_job"
        assert "no probe was made" in summary["detail"]
        assert calls["n"] == 0, "a fresh real-job observation needs no probe"
    finally:
        vwo.reset_worker_observability()


def test_stale_cache_is_served_passively_without_refresh(monkeypatch):
    """A stale verdict is served with its age instead of triggering a refresh."""
    monkeypatch.delenv("VTON_WORKER_URL", raising=False)
    monkeypatch.setattr(settings, "VTON_WORKER_URL", "https://worker.example/process", raising=False)
    vwo.reset_worker_observability()

    class _FrozenClock:
        def __init__(self): self.t = 1_000_000.0
        def __call__(self): return self.t

    clock = _FrozenClock()
    probe = WorkerProbe(ttl_seconds=60.0, probe_timeout=1.0, clock=clock)
    probe.set_observation({"verdict": vwo.VERDICT_READY, "ok": True, "source": "real_job"})

    def _no_network(*a, **k):  # pragma: no cover - fails the test if reached
        raise AssertionError("stale passive read must not refresh")

    monkeypatch.setattr(WorkerProbe, "_run_probe", _no_network)
    monkeypatch.setattr(WorkerProbe, "_refresh_in_background", _no_network)

    clock.t += 3_600.0  # an hour later — far past the TTL
    out = probe.get(allow_refresh=False)
    assert out["verdict"] == vwo.VERDICT_READY
    assert out["passive"] is True
    assert out["age_seconds"] == 3600.0


def test_active_read_still_refreshes_for_operator_surfaces(monkeypatch):
    """allow_refresh=True (the default) keeps the live behaviour: a cold cache
    performs one bounded probe. /health/ready and /health/vton-contract rely
    on this — operators keep a place to get live truth."""
    monkeypatch.delenv("VTON_WORKER_URL", raising=False)
    monkeypatch.setattr(settings, "VTON_WORKER_URL", "https://worker.example/process", raising=False)
    probe = WorkerProbe(ttl_seconds=60.0, probe_timeout=0.2)
    called = {"n": 0}

    def _fake_run_probe():
        called["n"] += 1
        return {"verdict": vwo.VERDICT_READY, "ok": True, "status_code": 200}

    monkeypatch.setattr(probe, "_run_probe", _fake_run_probe)
    out = probe.get()  # cold cache, active mode
    assert out["verdict"] == vwo.VERDICT_READY
    assert called["n"] == 1
