"""AI provider readiness — measured, cached, and economically bounded.

Why this exists
---------------
``ai_stylist_live`` was ``bool(_ai_provider_keys())``: a key is a *configuration*
fact, and it was the only thing standing behind the word "live". The health
capability answered ``not_probed`` for exactly that reason ("no probe exists —
an honest gap, never a silent ok"), which was truthful and still a gap: nothing
in the platform could tell whether the stylist could actually reach a provider.

Design constraints (all four were requirements, not preferences)
----------------------------------------------------------------
1. **No quota burn.** A chat completion costs tokens; so the probe never
   composes a prompt. It reads each provider's *model catalogue*
   (``GET /models``), which is free, and verifies exactly the things a key check
   cannot: DNS, TLS, reachability, and that the credential is accepted
   (401/402/403 are distinguished from 200). No message rows, no tokens, no
   user data leaves the process.
2. **Never block a request.** Probing is a background refresh over a cached
   snapshot — the same shape ``vton_worker_observability`` already uses, so
   ``/health`` answers from the last verdict instead of waiting on the network.
3. **No unbounded staleness.** The snapshot has a TTL *and* a hard maximum age.
   Past the hard age the verdict is withdrawn (``not_probed``) rather than
   continuing to report a ``ready`` that nobody can date.
4. **Bounded work.** One attempt per provider per refresh (no retries — a retry
   loop against a provider that is quota-blocked turns an outage into a
   self-inflicted burst), per-attempt timeout, and a single lock so concurrent
   callers cannot stampede the providers.

Vocabulary (this project's, from ``backend/app/core/readiness``)
---------------------------------------------------------------
``not_configured`` no key · ``not_probed`` nothing measured (or measurement too
old) · ``ready`` a provider answered 200 to an authenticated request ·
``degraded`` configured providers exist but none is ready (the deterministic
grounded engine still answers the shopper) · ``unavailable`` the probe reached
nobody · ``auth_failed`` / ``quota_exhausted`` / ``rate_limited`` / ``timeout``
classification of *why*, so operations can act on it.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from backend.app.core.config import settings
from backend.app.core.logging import logger

# --- verdict vocabulary ------------------------------------------------------
STATE_NOT_CONFIGURED = "not_configured"
STATE_NOT_PROBED = "not_probed"
STATE_READY = "ready"
STATE_DEGRADED = "degraded"
STATE_UNAVAILABLE = "unavailable"
STATE_AUTH_FAILED = "auth_failed"
STATE_QUOTA_EXHAUSTED = "quota_exhausted"
STATE_RATE_LIMITED = "rate_limited"
STATE_TIMEOUT = "timeout"
STATE_PROBE_UNSUPPORTED = "probe_unsupported"

#: States that mean "this provider can answer right now".
_REACHABLE_STATES = {STATE_READY}


@dataclass(frozen=True)
class ProviderProbe:
    """One provider's probe result — status code, latency, and the reason."""

    provider: str
    state: str
    http_status: Optional[int]
    latency_ms: Optional[int]
    detail: str


@dataclass
class ReadinessSnapshot:
    """A dated measurement of provider readiness (never a bare boolean)."""

    checked_at: float
    duration_ms: int
    providers: Dict[str, ProviderProbe] = field(default_factory=dict)

    @property
    def ready_providers(self) -> List[str]:
        return sorted(p for p, r in self.providers.items() if r.state in _REACHABLE_STATES)

    def age_seconds(self, now: Optional[float] = None) -> float:
        return max(0.0, (now if now is not None else time.time()) - self.checked_at)


def _classify(provider: str, status_code: int, latency_ms: int) -> ProviderProbe:
    if status_code == 200:
        return ProviderProbe(provider, STATE_READY, status_code, latency_ms,
                             "credential accepted by the provider's model catalogue")
    if status_code in (401, 403):
        return ProviderProbe(provider, STATE_AUTH_FAILED, status_code, latency_ms,
                             "the provider rejected the credential")
    if status_code == 402:
        return ProviderProbe(provider, STATE_QUOTA_EXHAUSTED, status_code, latency_ms,
                             "the provider reports payment required / quota exhausted")
    if status_code == 429:
        return ProviderProbe(provider, STATE_RATE_LIMITED, status_code, latency_ms,
                             "the provider is rate limiting this deployment")
    if status_code == 404:
        # The probe endpoint itself is wrong for this provider — that is a fact
        # about the probe, not about availability. Never report either verdict.
        return ProviderProbe(provider, STATE_PROBE_UNSUPPORTED, status_code, latency_ms,
                             "provider does not expose this catalogue endpoint at the expected path")
    if status_code >= 500:
        return ProviderProbe(provider, STATE_UNAVAILABLE, status_code, latency_ms,
                             "provider-side error during the probe")
    return ProviderProbe(provider, STATE_UNAVAILABLE, status_code, latency_ms,
                         f"unexpected status {status_code}")


def _configured_providers() -> Dict[str, Dict[str, str]]:
    """provider -> {"url": ..., "auth": ...} for every configured provider only.

    Reads the same settings the orchestrator calls with, so the probe cannot
    verify a key the stylist does not use (or miss one it does).
    """
    out: Dict[str, Dict[str, str]] = {}
    if settings.OPENAI_API_KEY:
        out["openai"] = {"url": "https://api.openai.com/v1/models",
                         "auth": f"Bearer {settings.OPENAI_API_KEY}"}
    groq_key = getattr(settings, "groq_api_key", None)
    if groq_key:
        out["groq"] = {"url": "https://api.groq.com/openai/v1/models",
                       "auth": f"Bearer {groq_key}"}
    if settings.GEMINI_API_KEY:
        out["gemini"] = {
            "url": f"https://generativelanguage.googleapis.com/v1beta/models?key={settings.GEMINI_API_KEY}",
            "auth": "",
        }
    if settings.NVIDIA_API_KEY:
        out["nvidia"] = {"url": "https://integrate.api.nvidia.com/v1/models",
                         "auth": f"Bearer {settings.NVIDIA_API_KEY}"}
    return out


def configured_provider_names() -> List[str]:
    """The providers this deployment has credentials for — one authority.

    `capability_service._ai_provider_keys()` delegates here rather than keeping
    its own list. Two enumerations of "which providers are configured" is how
    the flag and the probe would drift apart and start disagreeing about
    reality, which is the failure this whole module exists to prevent.
    """
    return sorted(_configured_providers())


def probe_now(
    transport: Optional[httpx.BaseTransport] = None,
    total_budget_seconds: Optional[float] = None,
) -> ReadinessSnapshot:
    """Measure configured providers, once each. Bounded, no retries.

    ``transport`` exists so tests can supply an ``httpx.MockTransport`` and pin
    every classification without touching the network.

    ``total_budget_seconds`` stops the sweep once the budget is spent, so a
    caller that must answer within a request deadline can still get a partial —
    and honestly partial — measurement: providers that were not attempted are
    simply absent from the snapshot rather than guessed at.
    """
    started = time.time()
    configured = _configured_providers()
    timeout = float(getattr(settings, "AI_PROBE_TIMEOUT_SECONDS", 3.0) or 3.0)
    providers: Dict[str, ProviderProbe] = {}

    for name, cfg in configured.items():
        if total_budget_seconds is not None and (time.time() - started) >= total_budget_seconds:
            logger.info("AI readiness probe stopped at its total budget",
                        attempted=sorted(providers), remaining=sorted(set(configured) - set(providers)))
            break
        t0 = time.time()
        try:
            with httpx.Client(timeout=timeout, transport=transport) as client:
                res = client.get(cfg["url"], headers={"Authorization": cfg["auth"]} if cfg["auth"] else {})
            latency = int((time.time() - t0) * 1000)
            providers[name] = _classify(name, res.status_code, latency)
        except httpx.TimeoutException:
            providers[name] = ProviderProbe(name, STATE_TIMEOUT, None,
                                            int((time.time() - t0) * 1000),
                                            f"no answer within {timeout}s")
        except Exception as exc:  # DNS, TLS, connection refused — all "unreachable"
            providers[name] = ProviderProbe(name, STATE_UNAVAILABLE, None,
                                            int((time.time() - t0) * 1000),
                                            f"probe could not reach the provider ({type(exc).__name__})")

    snapshot = ReadinessSnapshot(checked_at=time.time(), duration_ms=int((time.time() - started) * 1000),
                                 providers=providers)
    logger.info(
        "AI readiness probe finished",
        configured=len(configured),
        ready=len(snapshot.ready_providers),
        states={p: r.state for p, r in providers.items()},
        duration_ms=snapshot.duration_ms,
    )
    return snapshot


class _CachedReadiness:
    """TTL cache with a hard maximum age, and a background refresh.

    The two expiries are deliberately different concepts:

    * **TTL** — after this, the snapshot is refreshed (in the background).
    * **hard max age** — after this, the snapshot is *withdrawn*. If the refresh
      keeps failing, the platform must stop asserting a ``ready`` it can no
      longer date, so the verdict becomes ``not_probed`` instead.
    """

    def __init__(self, ttl_seconds: float, max_age_seconds: float) -> None:
        self._ttl = ttl_seconds
        self._max_age = max_age_seconds
        self._lock = threading.Lock()
        self._snapshot: Optional[ReadinessSnapshot] = None
        self._refreshing = False

    # -- reading ------------------------------------------------------------
    def snapshot(self) -> Optional[ReadinessSnapshot]:
        with self._lock:
            snap = self._snapshot
            if snap is None:
                return None
            if snap.age_seconds() > self._max_age:
                # Withdrawn: too old to stand behind. Keep the object so the
                # caller can still report *when* it was measured.
                return snap
            return snap

    def is_stale(self, snap: Optional[ReadinessSnapshot]) -> bool:
        return snap is None or snap.age_seconds() >= self._ttl

    def is_withdrawn(self, snap: Optional[ReadinessSnapshot]) -> bool:
        return snap is not None and snap.age_seconds() > self._max_age

    # -- writing ------------------------------------------------------------
    def store(self, snap: ReadinessSnapshot) -> None:
        with self._lock:
            self._snapshot = snap

    def refresh_in_background(self, transport: Optional[httpx.BaseTransport] = None) -> bool:
        """Start a refresh unless one is already running. Never blocks."""
        with self._lock:
            if self._refreshing:
                return False
            self._refreshing = True

        def _work() -> None:
            try:
                self.store(probe_now(transport=transport))
            except Exception as exc:  # a failed refresh must never raise into a request
                logger.warn("AI readiness refresh failed", error=str(exc))
            finally:
                with self._lock:
                    self._refreshing = False

        threading.Thread(target=_work, name="ai-readiness-probe", daemon=True).start()
        return True


_TTL = float(getattr(settings, "AI_PROBE_TTL_SECONDS", 300.0) or 300.0)
_MAX_AGE = float(getattr(settings, "AI_PROBE_MAX_AGE_SECONDS", 900.0) or 900.0)
_cache = _CachedReadiness(_TTL, max(_TTL, _MAX_AGE))


def ai_readiness() -> Dict[str, Any]:
    """The cached verdict, in the shape the capability layer and /health read.

    Read-only by construction: **it never probes.** A consumer request must not
    be able to trigger outbound provider calls (that would turn page traffic
    into provider load and latency). Probing is started by the health surface,
    which is the operator-facing one.
    """
    configured = _configured_providers()
    snap = _cache.snapshot()

    if not configured:
        return {
            "state": STATE_NOT_CONFIGURED,
            "probed": False,
            "probe_age_seconds": snap.age_seconds() if snap else None,
            "ready_providers": [],
            "configured_providers": [],
            "providers": {},
            "detail": "no provider key configured; the deterministic grounded engine answers",
        }

    if snap is None:
        return {
            "state": STATE_NOT_PROBED,
            "probed": False,
            "probe_age_seconds": None,
            "ready_providers": [],
            "configured_providers": sorted(configured),
            "providers": {},
            "detail": "no readiness probe has run yet — configured keys are not evidence of reachability",
        }

    withdrawn = _cache.is_withdrawn(snap)
    ready = snap.ready_providers
    states = {p: r.state for p, r in snap.providers.items()}

    if withdrawn:
        state = STATE_NOT_PROBED
        detail = (
            f"the last probe is {int(snap.age_seconds())}s old (limit "
            f"{int(_cache._max_age)}s) and could not be refreshed — the verdict is withdrawn "
            "rather than reported as a stale ready"
        )
    elif ready:
        state = STATE_READY
        detail = f"{len(ready)} provider(s) answered an authenticated model-catalogue request"
    elif any(s in (STATE_AUTH_FAILED, STATE_QUOTA_EXHAUSTED) for s in states.values()):
        state = STATE_DEGRADED
        detail = "no provider is reachable: " + ", ".join(
            f"{p}={s}" for p, s in sorted(states.items())
        )
    else:
        state = STATE_UNAVAILABLE
        detail = "no provider answered the probe: " + ", ".join(
            f"{p}={s}" for p, s in sorted(states.items())
        )

    return {
        "state": state,
        "probed": not withdrawn,
        "probe_age_seconds": round(snap.age_seconds(), 1),
        "probe_duration_ms": snap.duration_ms,
        "ready_providers": ready,
        "configured_providers": sorted(configured),
        "providers": states,
        "provider_details": {
            p: {"state": r.state, "http_status": r.http_status, "latency_ms": r.latency_ms,
                "detail": r.detail}
            for p, r in sorted(snap.providers.items())
        },
        "detail": detail,
    }


def refresh_ai_readiness_if_stale(transport: Optional[httpx.BaseTransport] = None) -> bool:
    """Called by the operator-facing health surface: refresh when due.

    Returns True when a refresh was started. Satisfies "bounded probe, cached
    readiness, TTL" without letting ordinary consumer traffic pay for it.
    """
    if not getattr(settings, "AI_PROBE_ENABLED", True):
        return False
    snap = _cache.snapshot()
    if not _cache.is_stale(snap):
        return False
    return _cache.refresh_in_background(transport=transport)


def ensure_readiness(transport: Optional[httpx.BaseTransport] = None) -> Dict[str, Any]:
    """Operator path: make sure a *fresh* verdict exists, then return it.

    Why synchronous probing exists at all: on Vercel the handler runs in a
    serverless function and a background thread may be frozen the moment the
    response is written, so "refresh in the background" alone cannot guarantee a
    verdict ever lands. ``/health`` (which is hit every 15 minutes by the
    repository's uptime monitor) therefore refreshes inline when the snapshot is
    missing or stale, under a TOTAL budget so the probe can never become the
    slowest thing in a health check.

    This is called only from the operator-facing health surface. Consumer reads
    (``ai_readiness``) never probe — page traffic must not become provider load.
    """
    if not getattr(settings, "AI_PROBE_ENABLED", True):
        return ai_readiness()
    snap = _cache.snapshot()
    if snap is not None and not _cache.is_stale(snap):
        return ai_readiness()

    budget = float(getattr(settings, "AI_PROBE_SYNC_BUDGET_SECONDS", 5.0) or 5.0)
    try:
        _cache.store(probe_now(transport=transport, total_budget_seconds=budget))
    except Exception as exc:  # never let an observability helper fail /health
        logger.warn("AI readiness inline probe failed", error=str(exc))
    return ai_readiness()


def reset_cache_for_tests() -> None:
    """Drop the cached snapshot. Test-only; there is no production caller."""
    _cache.store(None)  # type: ignore[arg-type]
    with _cache._lock:
        _cache._snapshot = None
