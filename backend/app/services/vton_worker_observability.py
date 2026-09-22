"""Live, cached, non-blocking observability for the VTON GPU worker.

Why this module exists (audit closure 2026-09-21, VTON / Photo-Match)
--------------------------------------------------------------------
Production was reporting a working try-on pipeline while every job failed:

    GET /api/v1/health          -> "vton_pipeline": "configured: GPU worker URL
                                   + admin token present"
    GET /api/v1/try-on/capabilities -> "engine_state": "available"
    POST /api/v1/try-on/jobs    -> 202 then status=failed after ~39 s with
                                   VTON_WORKER_NOT_READY

The root cause was not the worker code: the GPU workspace had exceeded its
spend limit, so every endpoint returned HTTP 404 "workspace ... is disabled"
while the API kept deriving "available" from the mere PRESENCE of two
environment variables. Configuration is not reachability.

Two more consequences of that design:

* every user request paid the full failure cost: 3 readiness/health attempts
  with exponential backoff (1 s + 2 s) plus 5 s timeouts each — ~39 s of
  blocking time for a job that could not possibly succeed. A two-layer outfit
  would have paid it twice.
* the failure surfaced as a developer string ("GPU Inference Worker Failure:
  ... not ready after 3 attempts: unreachable"), so the user could not tell a
  cold start from a permanently unavailable engine.

What this module provides
-------------------------
1. ``probe_worker_state()`` — one bounded, cached probe of health/readiness.
   It never blocks a request: the caller gets the last known verdict while a
   background thread refreshes it. Cache TTL bounds how stale the verdict can
   be; the value is timestamped so consumers can say how old it is.
2. ``classify_worker_failure()`` — turns what the platform actually said into
   an honest error code and a user-facing message. A disabled/exhausted GPU
   workspace is reported as ``VTON_ENGINE_UNAVAILABLE`` (do not retry now),
   NOT as a transient readiness problem.
3. ``circuit_breaker`` — after ``VTON_CIRCUIT_FAILURE_THRESHOLD`` consecutive
   non-transient failures the API fails fast for ``VTON_CIRCUIT_OPEN_SECONDS``
   instead of making every user wait ~39 s for the same answer. Half-open:
   the first request after the window performs one real probe; a success
   closes the circuit immediately.

Design rules
------------
* No secrets are ever logged or returned (the admin token is only used as a
  header; only booleans/status codes leave this module).
* Nothing here raises: an observability helper that can take down the health
  endpoint is worse than no observability helper.
* Deterministic under test: the cache is explicit and resettable, and the
  clock is injectable.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional

from backend.app.core.config import settings
from backend.app.core.logging import logger

# Verdicts (string enum; kept as plain strings so they serialize into /health).
VERDICT_READY = "ready"
VERDICT_COLD_START = "cold_start"
VERDICT_UNAVAILABLE = "unavailable"
VERDICT_NOT_CONFIGURED = "not_configured"
VERDICT_UNKNOWN = "unknown"

# Error codes surfaced to the API contract. Two of them are new and exist
# because the old single code conflated three different operator situations.
CODE_ENGINE_UNAVAILABLE = "VTON_ENGINE_UNAVAILABLE"
CODE_WORKER_NOT_READY = "VTON_WORKER_NOT_READY"
CODE_WORKER_COLD_START = "VTON_WORKER_COLD_START"
CODE_AUTH_FAILURE = "VTON_AUTH_FAILURE"

# Phrases a serverless GPU platform emits when the workspace itself cannot
# serve traffic (spend limit reached, workspace disabled, app stopped). None
# of these are fixed by retrying, so they must not be reported as "not ready".
_PLATFORM_UNAVAILABLE_MARKERS = (
    "spend limit",
    "exceeded its spend",
    "resourceexhausted",
    "resource exhausted",
    "billing",
    "no credits",
    "quota exceeded",
    "payment required",
    # Modal's exact wording when the workspace cannot serve traffic. Kept as a
    # substring of the real response body ("modal-http: workspace ac-… is
    # disabled") so it matches whatever prefix the platform adds.
    "is disabled",
    "workspace is disabled",
    "workspace disabled",
    "workspace has been disabled",
)

# Phrases that mean "the container exists but is still booting" — a real,
# retryable cold start, distinct from a dead workspace.
_COLD_START_MARKERS = (
    "invalid function call",
    "cold start",
    "container is starting",
    "model is loading",
    "model_loaded\": false",
    "model not loaded",
    "still loading",
    "warming up",
)


# ---------------------------------------------------------------------------
# Error classification — the single source of truth for "what does this
# failure mean, and what should the user be told".
# ---------------------------------------------------------------------------
def classify_worker_failure(
    *,
    status_code: Optional[int] = None,
    body_text: str = "",
    exception: str = "",
    attempts: int = 1,
) -> Dict[str, Any]:
    """Map a worker failure to ``{code, retryable, user_message, detail}``.

    ``code`` is the API error_code (the contract the frontend already switches
    on). ``retryable`` tells the caller whether a client retry can help at all
    — the frontend uses it to choose between "try again in a moment" and
    "this is not going to work right now".
    """
    text = f"{body_text or ''} {exception or ''}".lower()

    def _has(markers: tuple) -> bool:
        return any(m in text for m in markers)

    if status_code in (401, 403) or "unauthorized" in text or "forbidden" in text:
        return {
            "code": CODE_AUTH_FAILURE,
            "retryable": False,
            "user_message": (
                "Try-on is temporarily unavailable while we re-authorise the rendering "
                "service. Please try again shortly."
            ),
            "detail": "worker rejected the API credential (X-VTON-Admin)",
        }

    if _has(_PLATFORM_UNAVAILABLE_MARKERS):
        return {
            "code": CODE_ENGINE_UNAVAILABLE,
            "retryable": False,
            "user_message": (
                "Virtual try-on is offline right now — the rendering capacity is not "
                "available. Your photo was not stored. Please try again later."
            ),
            "detail": "GPU workspace cannot serve traffic (spend limit / disabled / no credits)",
        }

    if _has(_COLD_START_MARKERS):
        return {
            "code": CODE_WORKER_COLD_START,
            "retryable": True,
            "user_message": (
                "The rendering engine is warming up. This can take up to a minute on "
                "the first try — please retry in about 30 seconds."
            ),
            "detail": "GPU container was cold; the model is still loading",
        }

    if status_code == 422 or "input_invalid" in text:
        return {
            "code": "VTON_INPUT_INVALID",
            "retryable": False,
            "user_message": (
                "We could not use that image or garment. Please use a clear, full-body "
                "photo on a plain background."
            ),
            "detail": "worker rejected the input payload",
        }

    if status_code == 503 or "not ready" in text:
        return {
            "code": CODE_WORKER_NOT_READY,
            "retryable": True,
            "user_message": (
                "The rendering engine is busy starting up. Please retry in a few seconds."
            ),
            "detail": f"worker reported not ready after {attempts} attempt(s)",
        }

    return {
        "code": CODE_WORKER_NOT_READY,
        "retryable": True,
        "user_message": (
            "Virtual try-on did not respond in time. Please retry in a few seconds."
        ),
        "detail": f"worker unreachable or unexpected response after {attempts} attempt(s)",
    }


# ---------------------------------------------------------------------------
# Circuit breaker — fail fast instead of making every user wait.
# ---------------------------------------------------------------------------
class WorkerCircuitBreaker:
    """Consecutive-failure circuit breaker with a half-open recovery probe.

    State machine:
        CLOSED  -> normal operation; failures increment the counter.
        OPEN    -> ``trip()`` fired; ``allow()`` is False until the window
                   elapses, so callers fail fast with an honest code.
        HALF_OPEN -> the window elapsed; exactly one caller is let through to
                   re-probe (``begin_probe``), the rest keep failing fast.
                   ``record_success()`` closes it, ``record_failure()`` re-opens.

    Thread-safe. The clock is injectable so tests are deterministic.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        failure_threshold: int = 2,
        open_seconds: float = 120.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.failure_threshold = max(1, int(failure_threshold))
        self.open_seconds = max(1.0, float(open_seconds))
        self._clock = clock
        self._lock = threading.Lock()
        self._state = self.CLOSED
        self._failures = 0
        self._opened_at: Optional[float] = None
        self._probe_in_flight = False
        self._last_code: Optional[str] = None
        self._last_detail: Optional[str] = None

    # ------------------------------------------------------------- introspection
    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            remaining = 0.0
            if self._state == self.OPEN and self._opened_at is not None:
                remaining = max(0.0, self.open_seconds - (self._clock() - self._opened_at))
            return {
                "state": self._state,
                "consecutive_failures": self._failures,
                "retry_after_seconds": round(remaining, 1),
                "last_error_code": self._last_code,
                "last_error_detail": self._last_detail,
            }

    # ------------------------------------------------------------------ decisions
    def allow(self) -> bool:
        """True when a real worker call is permitted right now."""
        with self._lock:
            if self._state == self.CLOSED:
                return True
            if self._state == self.OPEN:
                if self._opened_at is not None and (self._clock() - self._opened_at) >= self.open_seconds:
                    self._state = self.HALF_OPEN
                    self._probe_in_flight = False
                else:
                    return False
            # HALF_OPEN: let exactly one probe through.
            if self._probe_in_flight:
                return False
            self._probe_in_flight = True
            return True

    def trip(self, code: Optional[str] = None, detail: Optional[str] = None) -> None:
        """Open the circuit immediately (used for non-retryable failures)."""
        with self._lock:
            self._state = self.OPEN
            self._opened_at = self._clock()
            self._probe_in_flight = False
            self._last_code = code
            self._last_detail = detail
            logger.warn(
                "vton_circuit_open",
                code=code,
                detail=(detail or "")[:160],
                open_seconds=self.open_seconds,
            )

    def record_failure(
        self,
        code: Optional[str] = None,
        detail: Optional[str] = None,
        retryable: bool = True,
    ) -> None:
        with self._lock:
            self._last_code = code
            self._last_detail = detail
            self._failures += 1
            if not retryable:
                # A non-retryable failure will not fix itself by waiting a
                # moment, so open immediately rather than after N users paid
                # for it.
                self._state = self.OPEN
                self._opened_at = self._clock()
                self._probe_in_flight = False
                return
            if self._state == self.HALF_OPEN or self._failures >= self.failure_threshold:
                self._state = self.OPEN
                self._opened_at = self._clock()
                self._probe_in_flight = False

    def record_success(self) -> None:
        with self._lock:
            if self._state != self.CLOSED:
                logger.info("vton_circuit_closed", previous_state=self._state)
            self._state = self.CLOSED
            self._failures = 0
            self._opened_at = None
            self._probe_in_flight = False

    def reset(self) -> None:
        with self._lock:
            self._state = self.CLOSED
            self._failures = 0
            self._opened_at = None
            self._probe_in_flight = False
            self._last_code = None
            self._last_detail = None


# ---------------------------------------------------------------------------
# Cached live probe
# ---------------------------------------------------------------------------
class WorkerProbe:
    """Cached health/readiness probe with background refresh.

    ``get()`` is safe to call from a synchronous request handler: it returns
    the cached verdict immediately and, when the cache is older than the TTL,
    kicks off a background refresh. The first ever call has no cache, so it
    performs one bounded synchronous probe (bounded by ``probe_timeout``) —
    after that no request path ever blocks on the worker.
    """

    def __init__(self, ttl_seconds: float = 60.0, probe_timeout: float = 6.0,
                 clock: Callable[[], float] = time.time) -> None:
        self.ttl_seconds = max(1.0, float(ttl_seconds))
        self.probe_timeout = max(1.0, float(probe_timeout))
        self._clock = clock
        self._lock = threading.Lock()
        self._result: Optional[Dict[str, Any]] = None
        self._at: float = 0.0
        self._refreshing = False

    # ------------------------------------------------------------------ public
    def get(self, force: bool = False) -> Dict[str, Any]:
        now = self._clock()
        with self._lock:
            cached = self._result
            age = now - self._at if self._at else None
            stale = cached is None or (age is not None and age >= self.ttl_seconds)
        if cached is not None and not stale and not force:
            out = dict(cached)
            out["age_seconds"] = round(age or 0.0, 1)
            return out
        if force or cached is None:
            # Nothing to serve yet (cold process) — do one bounded probe so the
            # first request gets a truthful answer instead of "unknown".
            return self._run_probe()
        self._refresh_in_background()
        out = dict(cached)
        out["age_seconds"] = round(age or 0.0, 1)
        return out

    def reset(self) -> None:
        with self._lock:
            self._result = None
            self._at = 0.0
            self._refreshing = False

    # ----------------------------------------------------------------- internal
    def _refresh_in_background(self) -> None:
        with self._lock:
            if self._refreshing:
                return
            self._refreshing = True

        def _work() -> None:
            try:
                self._run_probe()
            finally:
                with self._lock:
                    self._refreshing = False

        thread = threading.Thread(target=_work, name="vton-worker-probe", daemon=True)
        thread.start()

    def _run_probe(self) -> Dict[str, Any]:
        started = self._clock()
        try:
            result = _perform_probe(self.probe_timeout)
        except Exception as exc:  # noqa: BLE001 - observability must not raise
            result = {
                "verdict": VERDICT_UNAVAILABLE,
                "ok": False,
                "reason": f"{type(exc).__name__}: {str(exc)[:160]}",
                "status_code": None,
            }
        result["probe_ms"] = round((self._clock() - started) * 1000, 1)
        result["probed_at"] = time.time()
        with self._lock:
            self._result = result
            self._at = self._clock()
        out = dict(result)
        out["age_seconds"] = 0.0
        return out


def _worker_endpoints() -> Optional[Dict[str, str]]:
    """Resolve (health, readiness, process) URLs for the configured worker."""
    import os

    from backend.app.services.tryon_service import TryOnService

    worker_url = (
        getattr(settings, "VTON_WORKER_URL", None) or os.environ.get("VTON_WORKER_URL") or ""
    ).strip()
    if not worker_url:
        return None
    svc = TryOnService.__new__(TryOnService)  # _derive_worker_urls is pure
    health_url, readiness_url, process_url = TryOnService._derive_worker_urls(svc, worker_url)
    return {"health": health_url, "readiness": readiness_url, "process": process_url,
            "worker": worker_url}


def _perform_probe(timeout: float) -> Dict[str, Any]:
    """One bounded health/readiness probe. Runs its own event loop so it can be
    called from the synchronous /health handler."""
    import asyncio
    import os

    endpoints = _worker_endpoints()
    if not endpoints:
        return {
            "verdict": VERDICT_NOT_CONFIGURED,
            "ok": False,
            "reason": "no GPU worker configured (VTON_WORKER_URL)",
            "status_code": None,
        }

    token_present = bool(
        getattr(settings, "VTON_WORKER_ADMIN_TOKEN", None)
        or getattr(settings, "CONFIT_WORKER_ADMIN_TOKEN", None)
        or os.environ.get("VTON_WORKER_ADMIN_TOKEN")
        or os.environ.get("CONFIT_WORKER_ADMIN_TOKEN")
    )

    async def _probe() -> Dict[str, Any]:
        import httpx

        async with httpx.AsyncClient(timeout=timeout) as client:
            last_status: Optional[int] = None
            last_body = ""
            for url, kind in ((endpoints["readiness"], "readiness"), (endpoints["health"], "health")):
                try:
                    resp = await client.get(url)
                    last_status = resp.status_code
                    last_body = (resp.text or "")[:300]
                    if resp.status_code == 200:
                        try:
                            payload = resp.json()
                        except Exception:  # noqa: BLE001
                            payload = {}
                        ready = payload.get("ready") is True or payload.get("model_loaded") is True
                        return {
                            "verdict": VERDICT_READY if ready else VERDICT_COLD_START,
                            "ok": ready,
                            "reason": None if ready else "worker reachable but the model is not loaded",
                            "status_code": 200,
                            "endpoint": kind,
                            "device": payload.get("device"),
                            "model": payload.get("model"),
                            "git_sha": payload.get("git_sha"),
                            "token_configured": token_present,
                        }
                except Exception as exc:  # noqa: BLE001
                    last_body = f"{type(exc).__name__}: {str(exc)[:160]}"
            classified = classify_worker_failure(
                status_code=last_status, body_text=last_body, attempts=2
            )
            verdict = VERDICT_COLD_START if classified["code"] == CODE_WORKER_COLD_START else VERDICT_UNAVAILABLE
            # Prefer what the platform literally said over a generic "after N
            # attempts" string — that generic wording is what hid the real
            # cause (workspace over its spend limit) in production.
            reason = classified["detail"]
            if last_body and last_status not in (None, 200):
                reason = f"HTTP {last_status}: {last_body.strip()[:150]}"
            return {
                "verdict": verdict,
                "ok": False,
                "reason": reason,
                "status_code": last_status,
                "error_code": classified["code"],
                "retryable": classified["retryable"],
                "body_excerpt": last_body[:160],
                "token_configured": token_present,
            }

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        # Already inside an event loop (async endpoint): run in a worker thread
        # with its own loop rather than deadlocking on a nested run().
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(_probe())).result(timeout=timeout + 2)
    return asyncio.run(_probe())


# Process-wide singletons (the API is single-process per Vercel instance).
_probe = WorkerProbe(
    ttl_seconds=float(getattr(settings, "VTON_WORKER_PROBE_TTL_SECONDS", 60.0) or 60.0),
    probe_timeout=float(getattr(settings, "VTON_WORKER_PROBE_TIMEOUT_SECONDS", 6.0) or 6.0),
)
circuit_breaker = WorkerCircuitBreaker(
    failure_threshold=int(getattr(settings, "VTON_CIRCUIT_FAILURE_THRESHOLD", 2) or 2),
    open_seconds=float(getattr(settings, "VTON_CIRCUIT_OPEN_SECONDS", 120.0) or 120.0),
)


def probe_worker_state(force: bool = False) -> Dict[str, Any]:
    """Cached live verdict about the GPU worker. Never raises."""
    return _probe.get(force=force)


def reset_worker_observability() -> None:
    """Test helper: drop the cached verdict and close the circuit."""
    _probe.reset()
    circuit_breaker.reset()


def vton_health_summary() -> Dict[str, Any]:
    """The block /health publishes.

    Honest by construction: it states whether the verdict came from
    configuration or from a live probe, how old that probe is, and what the
    worker actually said. ``production_ready`` is only true for a live
    ``ready`` verdict — never for "the env vars are present".
    """
    state = probe_worker_state()
    circuit = circuit_breaker.snapshot()
    verdict = state.get("verdict")
    summary: Dict[str, Any] = {
        "verdict": verdict,
        "live_probed": True,
        "probe_age_seconds": state.get("age_seconds"),
        "probe_ms": state.get("probe_ms"),
        "status_code": state.get("status_code"),
        "reason": state.get("reason"),
        "error_code": state.get("error_code"),
        "token_configured": state.get("token_configured"),
        "device": state.get("device"),
        "worker_git_sha": state.get("git_sha"),
        "circuit": circuit,
        # The single field an operator should read.
        "production_ready": verdict == VERDICT_READY,
    }
    if verdict == VERDICT_READY:
        summary["detail"] = "GPU worker reachable and model loaded (live probe)"
    elif verdict == VERDICT_COLD_START:
        summary["detail"] = (
            "GPU worker reachable but cold/model not loaded — the first job may need "
            "a warm-up retry"
        )
    elif verdict == VERDICT_NOT_CONFIGURED:
        summary["detail"] = "no GPU worker configured (VTON_WORKER_URL) — try-on cannot render"
    else:
        summary["detail"] = (
            "GPU worker is NOT reachable: every try-on job will fail. "
            "Check the Modal workspace (spend limit / disabled app) and the "
            "VTON_WORKER_* URLs. Configuration alone is not availability."
        )
    return summary


# ---------------------------------------------------------------------------
# Canonical engine-state classifier — the ONE place the question
# "can try-on render right now?" is answered.
# ---------------------------------------------------------------------------
# Why this exists (consumer-role closure 2026-09-22)
# ------------------------------------------------
# ``tryon_service.get_vton_capabilities`` derived ``engine_state`` from the live
# probe; ``capability_service.capability_flags`` derived ``vton_gpu_ready`` from
# ``bool(settings.VTON_WORKER_URL)``. Two surfaces, two derivations, two answers
# — and the consumer UI binds to the *second* one. Production therefore served:
#
#     GET /api/v1/catalog/capabilities -> "vton_gpu_ready": true
#     GET /api/v1/try-on/capabilities  -> "engine_state": "temporarily_unavailable"
#     GET /api/v1/health               -> "ready": false, blocking: virtual_try_on
#
# The first two disagreed while both were believed to share "one source of
# truth". Unifying the *probe* was not enough: the defect was a second
# *derivation* of the same fact. So the derivation itself now lives here, once,
# and every surface — try-on capabilities, catalog capability flags, readiness,
# the health contract — calls :func:`engine_state_from_probe`.
#
# Adding a surface that reports try-on availability means calling this function.
# There is no supported way to answer the question any other way, and
# ``tests/test_capability_single_source.py`` fails if a surface re-derives it.

#: Wire values published as ``engine_state`` (try-on capabilities contract).
ENGINE_STATE_AVAILABLE = "available"
ENGINE_STATE_COLD_START = "cold_start"
ENGINE_STATE_UNAVAILABLE = "temporarily_unavailable"
ENGINE_STATE_MISCONFIGURED = "misconfigured"
ENGINE_STATE_UNKNOWN = "unknown"

#: States in which a job can still produce a render. A cold worker renders too —
#: it is slow on the first call, not broken — so both are "renderable".
RENDERABLE_ENGINE_STATES = frozenset({ENGINE_STATE_AVAILABLE, ENGINE_STATE_COLD_START})

#: Backend-authored user-facing sentences. Kept here (not in the controller and
#: not in the frontend) so the platform cannot describe one engine state two
#: ways, and so an honesty label cannot drift away from the verdict it labels.
_ENGINE_STATE_USER_MESSAGES: Dict[str, str] = {
    ENGINE_STATE_MISCONFIGURED: (
        "Virtual try-on is not configured for this deployment."
    ),
    ENGINE_STATE_UNAVAILABLE: (
        "Virtual try-on is offline right now — the rendering capacity is not "
        "available. Your photo is never stored. Please try again later."
    ),
    ENGINE_STATE_COLD_START: (
        "The rendering engine is warming up. The first try can take up to a "
        "minute; please retry in about 30 seconds."
    ),
}


def engine_state_from_probe(
    probe: Dict[str, Any] | None, configured: bool | None = None
) -> str:
    """Map a live worker probe to the canonical ``engine_state`` wire value.

    ``configured`` defaults to whether ``VTON_WORKER_URL`` is set, but it is a
    *gate on the feature being offered at all*, never evidence that it works:
    a configured-but-unreachable worker is ``temporarily_unavailable``, which is
    exactly the case production was in while the catalog claimed ``true``.

    An ``unknown`` verdict (the probe could not be performed) resolves to
    ``temporarily_unavailable``: the honest answer when availability was not
    established is "we cannot render", never "ready".
    """
    if configured is None:
        configured = bool(getattr(settings, "VTON_WORKER_URL", None))
    if not configured:
        return ENGINE_STATE_MISCONFIGURED

    verdict = (probe or {}).get("verdict")
    if verdict == VERDICT_READY:
        return ENGINE_STATE_AVAILABLE
    if verdict == VERDICT_COLD_START:
        return ENGINE_STATE_COLD_START
    if verdict == VERDICT_UNKNOWN:
        # Not measured is not the same as measured-and-broken; the operator
        # detail differs even though the user-facing gate does not.
        return ENGINE_STATE_UNAVAILABLE
    return ENGINE_STATE_UNAVAILABLE


def engine_state_user_message(engine_state: str) -> Optional[str]:
    """The backend-authored sentence for an engine state, or ``None``.

    ``None`` for renderable states: the platform does not apologise for a
    capability that works, and a banner on a healthy engine teaches users to
    ignore banners.
    """
    return _ENGINE_STATE_USER_MESSAGES.get(engine_state)


def engine_can_render(engine_state: str) -> bool:
    """Whether a job submitted in this state can produce a render."""
    return engine_state in RENDERABLE_ENGINE_STATES
