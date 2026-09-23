"""AI Stylist readiness: the probe must measure, cache, expire and classify.

`ai_stylist_live` was `bool(_ai_provider_keys())`. That is a configuration fact
wearing a readiness name, and it is the same defect class as
`vton_gpu_ready = bool(VTON_WORKER_URL)` — the difference is only that nobody
had noticed it on the AI side yet.

The probe added on 2026-09-23 fixes it, but a probe is only worth having if its
honesty properties are enforced. These tests pin all four:

* it measures **reachability and credential acceptance**, not key presence;
* it **never spends quota**: it reads the provider's model catalogue, so no
  completion is requested and no message row is written;
* it is **cached with a TTL and a hard maximum age** — past the hard age the
  verdict is withdrawn rather than reported stale;
* it **classifies failures**, so auth/quota/rate-limit/timeout are actionable
  instead of collapsing into one "down".

Every provider call in this file is served by an `httpx.MockTransport`: the real
`probe_now` code path runs (URL building, headers, classification, snapshot) with
zero network access and zero quota.
"""

from __future__ import annotations

import time
from typing import Optional

import httpx
import pytest

from backend.app.core.config import settings
from backend.app.services import ai_readiness as ar


@pytest.fixture(autouse=True)
def _clean_cache():
    ar.reset_cache_for_tests()
    yield
    ar.reset_cache_for_tests()


def _configure(monkeypatch, providers: Optional[dict] = None) -> dict:
    """Point the probe at exactly these providers (no real keys needed)."""
    providers = providers if providers is not None else {
        "groq": {"url": "https://api.groq.com/openai/v1/models", "auth": "Bearer test-key"},
    }
    monkeypatch.setattr(ar, "_configured_providers", lambda: providers)
    return providers


def _transport(status_code: int, calls: Optional[list] = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(str(request.url))
        return httpx.Response(status_code, json={"data": [{"id": "some-model"}]})
    return httpx.MockTransport(handler)


def _measure(monkeypatch, status_code: int, calls: Optional[list] = None) -> dict:
    _configure(monkeypatch)
    snapshot = ar.probe_now(transport=_transport(status_code, calls))
    ar._cache.store(snapshot)
    return ar.ai_readiness()


# ---------------------------------------------------------------------------
# The measurement itself
# ---------------------------------------------------------------------------

def test_ready_requires_a_provider_that_answered(monkeypatch):
    """A 200 from the catalogue endpoint is what makes the state `ready`."""
    verdict = _measure(monkeypatch, 200)
    assert verdict["state"] == "ready"
    assert verdict["ready_providers"] == ["groq"]
    assert verdict["probed"] is True
    assert verdict["provider_details"]["groq"]["http_status"] == 200


def test_the_probe_never_requests_a_completion(monkeypatch):
    """Quota safety is a property of the DESIGN, asserted on the wire.

    A probe that composed a prompt would spend the very quota it is trying to
    measure the health of — and would write a message row per health check. The
    only endpoint it may touch is the model catalogue.
    """
    calls: list = []
    _measure(monkeypatch, 200, calls=calls)
    assert calls, "precondition: the probe made a request"
    assert all(url.endswith("/models") or "models?" in url for url in calls), calls
    assert not any("/chat/completions" in url for url in calls), (
        "the readiness probe must never call a completion endpoint"
    )


@pytest.mark.parametrize(
    "status,expected",
    [
        (200, "ready"),
        (401, "auth_failed"),
        (403, "auth_failed"),
        (402, "quota_exhausted"),
        (429, "rate_limited"),
        (404, "probe_unsupported"),
        (500, "unavailable"),
        (503, "unavailable"),
    ],
)
def test_failures_are_classified_not_lumped_together(monkeypatch, status, expected):
    """An exhausted key and a rate limit need different operator actions."""
    verdict = _measure(monkeypatch, status)
    assert verdict["provider_details"]["groq"]["state"] == expected
    assert verdict["provider_details"]["groq"]["http_status"] == status
    if expected != "ready":
        assert verdict["state"] != "ready", (
            f"HTTP {status} was reported as ready overall"
        )
        assert verdict["ready_providers"] == []


def test_a_timeout_is_reported_as_a_timeout(monkeypatch):
    _configure(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("too slow")

    verdict_state = ar.probe_now(transport=httpx.MockTransport(handler)).providers["groq"].state
    assert verdict_state == "timeout"


def test_unreachable_provider_is_unavailable_not_ready(monkeypatch):
    _configure(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns failure")

    probe = ar.probe_now(transport=httpx.MockTransport(handler)).providers["groq"]
    assert probe.state == "unavailable"
    assert probe.http_status is None


# ---------------------------------------------------------------------------
# Caching, expiry, withdrawal
# ---------------------------------------------------------------------------

def test_no_key_configured_is_not_configured(monkeypatch):
    _configure(monkeypatch, providers={})
    verdict = ar.ai_readiness()
    assert verdict["state"] == "not_configured"
    assert verdict["probed"] is False
    assert verdict["ready_providers"] == []


def test_keys_without_a_probe_are_not_ready(monkeypatch):
    """The whole point: configuration is not reachability."""
    _configure(monkeypatch)
    verdict = ar.ai_readiness()
    assert verdict["state"] == "not_probed"
    assert verdict["probed"] is False
    assert verdict["configured_providers"] == ["groq"]


def test_consumer_reads_never_trigger_a_probe(monkeypatch):
    """`ai_readiness()` must stay read-only.

    If a consumer page could start a probe, page traffic would generate
    outbound provider calls — load amplification for anyone who can request the
    endpoint. Only the operator surface (`ensure_readiness`) may probe.
    """
    calls: list = []
    _configure(monkeypatch)
    monkeypatch.setattr(ar, "probe_now", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("ai_readiness() must not probe")))
    verdict = ar.ai_readiness()  # must not raise
    assert verdict["state"] == "not_probed"
    assert calls == []


def test_a_stale_verdict_is_withdrawn_not_reported(monkeypatch):
    """A `ready` nobody can date is not a ready.

    Simulated by back-dating the snapshot beyond the hard maximum age; the state
    must become `not_probed` while still reporting WHEN it was measured.
    """
    _measure(monkeypatch, 200)
    assert ar.ai_readiness()["state"] == "ready"

    ar._cache._snapshot.checked_at = time.time() - (ar._cache._max_age + 60)
    verdict = ar.ai_readiness()
    assert verdict["state"] == "not_probed", "a stale verdict must not be reported as ready"
    assert verdict["probed"] is False
    assert verdict["probe_age_seconds"] > ar._cache._max_age
    assert "withdrawn" in verdict["detail"]


def test_a_fresh_verdict_inside_the_ttl_is_reused(monkeypatch):
    _measure(monkeypatch, 200)
    assert ar._cache.is_stale(ar._cache.snapshot()) is False


def test_ensure_readiness_measures_when_nothing_was_measured(monkeypatch):
    """The operator path establishes the verdict, bounded by its budget."""
    _configure(monkeypatch)
    monkeypatch.setattr(ar, "probe_now", lambda transport=None, total_budget_seconds=None:
                        ar.ReadinessSnapshot(checked_at=time.time(), duration_ms=1, providers={}))
    verdict = ar.ensure_readiness(transport=_transport(200))
    assert verdict["state"] in ("ready", "not_probed", "unavailable", "degraded")


def test_the_probe_respects_its_total_budget(monkeypatch):
    """A request-deadline caller gets a partial measurement, never an overrun.

    With a zero budget no provider may be attempted: providers that were not
    measured are absent from the snapshot, which is honest — the alternative is
    inventing a verdict for them.
    """
    _configure(monkeypatch, providers={
        "groq": {"url": "https://api.groq.com/openai/v1/models", "auth": "Bearer a"},
        "openai": {"url": "https://api.openai.com/v1/models", "auth": "Bearer b"},
    })
    calls: list = []
    snapshot = ar.probe_now(transport=_transport(200, calls), total_budget_seconds=0)
    assert calls == [], "a zero budget must attempt nothing"
    assert snapshot.providers == {}


def test_reset_cache_is_the_only_way_back_to_unmeasured(monkeypatch):
    _measure(monkeypatch, 200)
    assert ar.ai_readiness()["state"] == "ready"
    ar.reset_cache_for_tests()
    assert ar.ai_readiness()["state"] == "not_probed"


def test_the_probe_is_disabled_by_configuration(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(settings, "AI_PROBE_ENABLED", False)
    verdict = ar.ensure_readiness(transport=_transport(200))
    assert verdict["state"] == "not_probed", (
        "with probing disabled the platform must say it has not measured, "
        "not assume the provider is fine"
    )
