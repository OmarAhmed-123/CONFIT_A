"""A capability must not answer differently depending on which instance served it.

Found in production 2026-09-24, measured, not inferred:

    consumer reads BEFORE any /health hit:  not_probed, not_probed, not_probed
    one /health hit (what the 15-minute monitor does)
    consumer reads AFTER:                   ready x6

The AI readiness verdict is measured per process. The probe was reachable only
from the operator surface, so a warm instance that had never been asked for
health served the consumer capability contract with
``ai_stylist_state = not_probed`` and therefore ``ai_stylist_live = false`` —
for a provider that was demonstrably healthy. Same deployment, same capability,
two answers, decided by routing.

The fix keeps every honesty property and adds no new risk:

* the request that triggers it STILL returns immediately, and still reports
  ``not_probed`` when that is the truth — no inline probe, no added latency;
* the refresh is the existing bounded one: one in flight, one attempt per
  provider, no retries, no quota (it reads the model catalogue);
* a retry floor stops a failing provider being retried by page traffic.

These tests pin the behaviour, including the floor and the "no usable verdict
only" condition, with `httpx.MockTransport` so no network and no quota is used.
"""

from __future__ import annotations

import time

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.services import ai_readiness as ar


@pytest.fixture(autouse=True)
def _clean_cache(monkeypatch):
    """Fresh cache AND probing enabled.

    conftest disables AI probing for the whole suite (a consumer read of
    /catalog/capabilities can now start a bounded refresh, and with placeholder
    keys that is a real outbound call). These tests are the escape hatch, the
    same way test_rate_limiting.py re-enables the limiter — every provider call
    here goes through an httpx.MockTransport.
    """
    monkeypatch.setattr(settings, "AI_PROBE_ENABLED", True, raising=False)
    ar.reset_cache_for_tests()
    yield
    ar.reset_cache_for_tests()


def _wait_until(predicate, timeout: float = 5.0) -> bool:
    """Wait for a background thread to reach a state. Returns whether it did.

    Used instead of a bare `sleep` so a slow machine waits and a fast one does
    not: the assertion that follows still fails if the condition never holds.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _configure(monkeypatch, calls=None):
    """Point the probe at one fake provider and return a call recorder.

    The recorder is ALWAYS a list. The first version returned whatever was
    passed in, so `calls = _configure(monkeypatch)` handed back `None`, the
    gated transport raised AttributeError on `None.append`, and the honest
    per-provider error path recorded that as `state='unavailable'` with
    `duration_ms=0`. The test then failed on a product assertion while the
    product was correct. A helper that can silently return None where a list is
    expected is the defect; it cannot do that any more.
    """
    monkeypatch.setattr(ar, "_configured_providers", lambda: {
        "groq": {"url": "https://api.groq.com/openai/v1/models", "auth": "Bearer test-key"},
    })
    return calls if calls is not None else []


def _transport(status_code=200, calls=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(str(request.url))
        return httpx.Response(status_code, json={"data": [{"id": "m"}]})
    return httpx.MockTransport(handler)


def _wait_for_verdict(timeout=5.0):
    """The refresh is a background thread; wait for it the way a request would."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = ar._cache.snapshot()
        if snap is not None and not ar._cache.is_withdrawn(snap):
            return ar.ai_readiness()
        time.sleep(0.02)
    return ar.ai_readiness()


def test_consumer_read_starts_a_refresh_without_blocking(monkeypatch):
    """The proof needs a probe that is still in flight, not an instant mock.

    First version of this test asserted `not_probed` right after triggering and
    failed with `ready`: `httpx.MockTransport` answers instantly, so the
    background thread had already finished. The assertion was measuring the
    mock's speed, not the product's behaviour. A gated transport holds the probe
    open, which is what "does not block the request" actually means.
    """
    import threading

    calls = _configure(monkeypatch)
    gate = threading.Event()

    def slow(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        gate.wait(10)  # released by the test, so the probe is provably in flight
        return httpx.Response(200, json={"data": [{"id": "m"}]})

    started = ar.refresh_when_unmeasured(transport=httpx.MockTransport(slow))
    assert started is True, "an unmeasured instance must be able to establish a verdict"

    t0 = time.time()
    immediate = ar.ai_readiness()
    elapsed = time.time() - t0
    assert elapsed < 1.0, f"the triggering read must not wait for the probe (took {elapsed:.2f}s)"
    assert immediate["state"] == ar.STATE_NOT_PROBED, (
        "while the probe is in flight the honest answer is still 'not measured'"
    )

    gate.set()
    after = _wait_for_verdict()
    assert after["state"] == ar.STATE_READY
    assert calls, "the probe must actually have called the provider catalogue"


def test_a_fresh_verdict_is_never_re_probed_by_consumer_traffic(monkeypatch):
    """A usable verdict must be the reason traffic does not probe.

    Rewritten after a mutation control survived. The first version asserted
    right after a successful probe, where the RETRY FLOOR also refuses — so
    deleting the "no usable verdict" guard left it green: it was proving the
    floor a second time, not the guard it names.

    The clock is therefore moved past the floor while a fresh verdict is held,
    which is exactly a long-lived instance that probed a moment ago and keeps
    serving reads. Now only the guard can answer, and deleting it makes this
    test fail on the provider-call count.
    """
    calls: list = []
    _configure(monkeypatch)
    transport = _transport(200, calls)

    assert ar.refresh_when_unmeasured(transport=transport) is True
    assert _wait_for_verdict()["state"] == ar.STATE_READY
    baseline = len(calls)

    # Past the floor, still holding a fresh verdict: no other rule applies.
    with ar._cache._lock:
        ar._cache._last_attempt = time.time() - (ar._MIN_RETRY + 60)

    snap = ar._cache.snapshot()
    assert snap is not None and not ar._cache.is_withdrawn(snap), "the verdict must still be usable"
    assert not ar._cache.is_stale(snap), "and still fresh, so no refresh is warranted"

    for _ in range(20):
        assert ar.refresh_when_unmeasured(transport=transport) is False, (
            "holding a usable verdict must stop consumer reads from probing"
        )
    assert len(calls) == baseline, (
        f"no further provider calls may be made; saw {len(calls) - baseline} extra"
    )


def test_failed_attempts_are_floored_so_traffic_cannot_become_a_burst(monkeypatch):
    """The floor is what stops page traffic amplifying a broken provider.

    Rewritten after a mutation control proved the first version was not
    load-bearing. That version made the provider raise `httpx.ConnectError`,
    which the probe records as an honest `unavailable` snapshot — and once a
    snapshot exists, `refresh_when_unmeasured` refuses on the "no usable
    verdict" rule *before the floor is ever consulted*. Deleting the floor left
    the test green, so it was measuring a different guard.

    The floor matters when a verdict cannot be obtained at all: an unexpected
    error escapes the refresh, nothing is stored, the instance stays unmeasured,
    and every later read would otherwise start another attempt. To exercise it,
    the refresh itself must fail (patched `probe_now`) so the cache is never
    populated and no other guard can answer first. Deleting the floor makes this
    test fail with 11 attempts instead of 1.
    """
    attempts = []

    def exploding_probe(*_args, **_kwargs):
        attempts.append(time.time())
        raise RuntimeError("refresh failed before a verdict could be stored")

    monkeypatch.setattr(ar, "probe_now", exploding_probe)
    transport = httpx.MockTransport(lambda request: httpx.Response(200))

    assert ar.refresh_when_unmeasured(transport=transport) is True, "the first attempt may be made"
    _wait_until(lambda: len(attempts) == 1)
    assert ar._cache.snapshot() is None, "this scenario needs the instance to stay unmeasured"

    for _ in range(10):
        assert ar.refresh_when_unmeasured(transport=transport) is False, (
            "attempts must be spaced, even when the refresh never produced a verdict"
        )
    assert len(attempts) == 1, f"expected exactly one attempt within the floor, saw {len(attempts)}"


def test_floor_expires_so_a_long_lived_instance_recovers(monkeypatch):
    calls: list = []
    _configure(monkeypatch)
    transport = _transport(200, calls)

    assert ar.refresh_when_unmeasured(transport=transport) is True
    _wait_for_verdict()

    # Simulate the verdict ageing past the hard max age: the instance must be
    # able to establish a new one rather than being stuck permanently.
    snap = ar._cache.snapshot()
    assert snap is not None
    snap.checked_at = time.time() - (max(ar._MAX_AGE, ar._TTL) + 60)
    with ar._cache._lock:
        ar._cache._last_attempt = time.time() - 10_000

    assert ar.refresh_when_unmeasured(transport=transport) is True
    after = _wait_for_verdict()
    assert after["state"] == ar.STATE_READY


def test_disabled_probe_stays_disabled(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(settings, "AI_PROBE_ENABLED", False, raising=False)
    assert ar.refresh_when_unmeasured(transport=_transport(200)) is False


def test_capability_endpoint_triggers_it_through_its_own_read_path(client: TestClient, monkeypatch):
    """The consumer contract itself: a capability read must warm its own instance.

    Rewritten after review: the first version asserted that the string
    ``refresh_when_unmeasured`` appeared in the controller source. That is a
    text check — it cannot tell a live call from one inside dead code, and it
    would also pass if the call were placed somewhere that never runs. This
    version drives the endpoint through the app and observes the trigger.

    Two properties at once, because the fix must not trade one for the other:
    the read STARTS the bounded refresh, and the response it returns is still
    the honest ``not_probed`` (a trigger must not fabricate a verdict).
    """
    triggered = []

    def recorder(*args, **kwargs):
        triggered.append(time.time())
        return True

    monkeypatch.setattr(ar, "refresh_when_unmeasured", recorder)

    r = client.get("/api/v1/catalog/capabilities")
    assert r.status_code == 200, r.text
    assert triggered, (
        "the shopper-facing capability read must be able to give its own instance a verdict; "
        "without this, a warm instance that never served /health answers ai_stylist_live=false "
        "for a healthy provider (measured in production)"
    )

    body = r.json()
    state = body.get("ai_stylist_state")
    assert state in (ar.STATE_NOT_PROBED, ar.STATE_NOT_CONFIGURED, ar.STATE_READY, ar.STATE_UNAVAILABLE), (
        f"unexpected capability state {state!r}"
    )
    if state != ar.STATE_READY:
        assert body.get("ai_stylist_live") is False, (
            "a read that starts a refresh must not claim the capability is live before it is measured"
        )
