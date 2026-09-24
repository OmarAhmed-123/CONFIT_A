"""Where the rate limiter's counters live — and what the project is allowed to claim.

The gap being closed (G-03): the limiter's counters were in-process, so on
serverless every warm instance kept its own quota and a client could multiply its
allowance by getting routed to different instances. The fix is not "add Redis" —
it is to make the store a configured decision whose answer is REPORTED, so the
honest statement ("per-instance") and the strong statement ("global") are
distinguishable at runtime instead of by reading the source.

Two claims, two kinds of proof:

* **The honesty claim** (this deployment is per-instance and says so; a shared
  store is reported as global; no store URL is synthesised): asserted directly,
  and guardable against future edits.
* **The capability claim** (a shared store really does make the quota global):
  proven by running the limiter in TWO SEPARATE PROCESSES against a real Redis and
  counting how many requests the pair are allowed. The negative control runs the
  same two processes against the in-process store and requires the count to
  DOUBLE — without that control, a test that "passes" could simply be measuring
  one process.

Set ``CONFIT_TEST_REDIS_URL`` (e.g. ``redis://localhost:6379/0``) to run the
Redis-backed tests; without it they skip with the reason stated, because a
skipped test that pretends to prove a shared store would be worse than no test.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded

from backend.app.core.config import Settings, settings
from backend.app.core.rate_limit import (
    MEMORY_STORE,
    rate_limit_exceeded_handler,
    build_limiter,
    configured_storage_uri,
    is_shared_store,
    rate_limit_store_report,
)

REDIS_URL = os.environ.get("CONFIT_TEST_REDIS_URL", "").strip()

#: Runs the limiter's own limits-level strategy in a fresh process, so "two
#: processes" means two interpreters with separate memory, which is the only way
#: to tell an in-process store from a shared one.
CHILD = r"""
import os, sys
os.environ.setdefault("PYTHONPATH", ".")
from limits import parse
from backend.app.core.rate_limit import build_limiter

uri, key, attempts, limit = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
limiter = build_limiter(uri)
strategy = getattr(limiter, "_limiter", None) or getattr(limiter, "limiter")
item = parse(limit)
allowed = 0
for _ in range(attempts):
    if strategy.hit(item, key):
        allowed += 1
print(allowed)
"""


def _run_child(uri: str, key: str, attempts: int, limit: str) -> int:
    env = dict(os.environ)
    env["PYTHONPATH"] = "."
    out = subprocess.run(
        [sys.executable, "-c", CHILD, uri, key, str(attempts), limit],
        capture_output=True, text=True, env=env, timeout=120,
    )
    assert out.returncode == 0, f"child failed: {out.stderr[-400:]}"
    return int(out.stdout.strip().splitlines()[-1])


# ── the honesty claim ────────────────────────────────────────────────────────
def test_this_deployment_is_in_process_and_says_so():
    report = rate_limit_store_report()
    assert report["store"] == "memory", report
    assert report["shared_across_instances"] is False, (
        "with no shared store configured the limiter must not claim a global quota"
    )
    assert "NOT a global quota" in report["quota_semantics"], (
        "the report has to state the limitation in words, not just a flag"
    )


def test_a_shared_store_is_reported_as_global_with_its_degradation():
    report = rate_limit_store_report("redis://example.invalid:6379/0")
    assert report["shared_across_instances"] is True
    assert "global" in report["quota_semantics"]
    assert report["on_store_failure"], "the fallback must be named, not implied"


def test_no_store_url_is_synthesised_in_the_settings_model():
    """A default of ``redis://localhost`` would be a fake distributed limiter.

    Nothing in CI or production runs Redis on localhost, so such a default would
    make the limiter *look* shared while every instance kept its own counters —
    exactly the claim this file exists to prevent.
    """
    default = Settings.model_fields["RATE_LIMIT_STORAGE_URL"].default
    assert default is None, f"RATE_LIMIT_STORAGE_URL must default to None, found {default!r}"
    assert configured_storage_uri() == MEMORY_STORE
    assert is_shared_store(configured_storage_uri()) is False


def test_the_shared_store_does_not_change_the_alias_invariance():
    """One logical operation keeps ONE bucket, shared store or not.

    #190 proved endpoint keying against the in-process store: the same route
    mounted under several prefixes must not hand out one allowance per spelling.
    Making the store shared must not reopen that hole, which it would if the
    factory ever left key_style at slowapi's ``url`` default (per-spelling
    buckets, now persisted in Redis instead of process memory).
    """
    assert getattr(build_limiter(), "_key_style", None) == "endpoint"
    assert getattr(build_limiter("redis://example.invalid:6379/0"), "_key_style", None) == "endpoint"


def test_an_unrecognised_store_url_is_reported_as_unknown_not_as_global():
    report = rate_limit_store_report("somethingelse://host")
    assert report["shared_across_instances"] is False
    assert report["store"] == "somethingelse"


# ── the capability claim: shared means shared ACROSS PROCESSES ───────────────
@pytest.mark.skipif(not REDIS_URL, reason="set CONFIT_TEST_REDIS_URL to a real Redis to prove sharing")
def test_a_real_redis_shares_one_counter_between_two_processes():
    """Two interpreters, one Redis: the pair must consume ONE allowance.

    4 attempts in each of two processes against a 5/minute limit. If the store is
    genuinely shared, the two processes together may spend 5 — not 10.
    """
    key = f"confit-test-shared-{os.getpid()}-{time.time_ns()}"
    first = _run_child(REDIS_URL, key, 4, "5/minute")
    second = _run_child(REDIS_URL, key, 4, "5/minute")
    assert first == 4, f"first process should spend its 4 within the shared 5: got {first}"
    assert second == 1, (
        f"the shared store must leave exactly 1 of the 5 for the second process, got {second}. "
        "If this is 4, the counters are per-process (the counters are NOT shared) and the "
        "global-quota claim would be false."
    )


#: The control runs always: it needs no Redis, and its value is highest in the
#: SAME invocation as the shared-store proof, where both must disagree.
@pytest.mark.skipif(False, reason="never skipped: it is the control for the Redis test")
def test_the_in_process_store_does_not_share_between_processes():
    """The control that gives the test above its meaning.

    Same two processes, same key, same 5/minute limit, but the in-process store:
    each process gets its full 5, so the pair spends 10. This is what the defect
    looked like, and it proves the Redis test can tell the two apart — otherwise
    "shares one counter" could pass for a reason unrelated to sharing.
    """
    key = f"confit-test-memory-{os.getpid()}-{time.time_ns()}"
    first = _run_child(MEMORY_STORE, key, 4, "5/minute")
    second = _run_child(MEMORY_STORE, key, 4, "5/minute")
    assert (first, second) == (4, 4), (
        f"expected each process to spend its own 4 against its own counters, got {(first, second)}"
    )


@pytest.mark.skipif(not REDIS_URL, reason="set CONFIT_TEST_REDIS_URL to a real Redis")
def test_a_broken_shared_store_degrades_instead_of_failing_requests():
    """A store outage must not become an API outage.

    First version of this test called the `limits` strategy directly and FAILED
    with `redis.exceptions.ConnectionError` — correctly, because `swallow_errors`
    and the in-memory fallback are **slowapi's** features: they wrap the strategy
    call inside the limiter's request check. Driving the storage layer therefore
    tested neither the product behaviour nor the promise in the docstring. The
    test now drives a real app through TestClient, which is where the promise
    lives.

    A refused TCP port stands in for "the shared store is down".
    """
    from backend.app.core.rate_limit import rate_limit_exceeded_handler

    app = FastAPI()
    limiter = build_limiter("redis://127.0.0.1:1/0")
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    @app.get("/probe")
    @limiter.limit("5/minute")
    def probe(request: Request):  # noqa: ANN001 - slowapi requires the request parameter
        return {"ok": True}

    client = TestClient(app)
    started = time.time()
    response = client.get("/probe")
    elapsed = time.time() - started

    assert response.status_code == 200, (
        f"an unreachable shared store must degrade, not fail the request; got "
        f"{response.status_code}: {response.text[:200]}"
    )
    assert elapsed < 10, f"the degradation path must be bounded, took {elapsed:.1f}s"

    # Degraded does not mean unprotected: the in-process fallback still counts.
    seen = [client.get("/probe").status_code for _ in range(8)]
    assert 429 in seen, (
        f"after falling back, the per-instance counters must still enforce the limit; saw {seen}"
    )


@pytest.mark.skipif(not REDIS_URL, reason="set CONFIT_TEST_REDIS_URL to a real Redis")
def test_without_the_fallback_the_same_outage_fails_the_request():
    """Negative control: proves the degradation configuration is load-bearing.

    Identical app, identical unreachable store, but the limiter is built WITHOUT
    the fallback flags. If this control also returned 200, then the previous
    test would be proving nothing about the configuration — the 200 could have
    come from somewhere else. The control must fail the request (5xx), and then
    the difference between the two results IS the evidence that the fallback is
    what protects the API during a store outage.
    """
    from slowapi import Limiter

    from backend.app.core.rate_limit import client_key

    app = FastAPI()
    app.state.limiter = Limiter(
        key_func=client_key, key_style="endpoint", storage_uri="redis://127.0.0.1:1/0"
    )
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    @app.get("/probe")
    @app.state.limiter.limit("5/minute")
    def probe(request: Request):  # noqa: ANN001
        return {"ok": True}

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/probe")
    assert response.status_code >= 500, (
        "control expected a failed request without the fallback, got "
        f"{response.status_code} — if this is 200 the degradation test proves nothing"
    )


@pytest.mark.skipif(not REDIS_URL, reason="set CONFIT_TEST_REDIS_URL to a real Redis")
def test_concurrent_requests_against_a_shared_store_do_not_over_admit():
    """Burst behaviour: parallelism must not buy extra allowance.

    20 threads, one client identity, a 5/minute limit, one shared store. Redis
    INCR is atomic, so exactly 5 may pass even though every thread races the
    others. A window that allowed more than 5 would mean the counter is not
    atomic — the classic way a distributed limiter leaks capacity under load.
    """
    import concurrent.futures as cf

    from limits import parse

    limiter = build_limiter(REDIS_URL)
    strategy = getattr(limiter, "_limiter", None) or getattr(limiter, "limiter")
    item = parse("5/minute")
    # a fresh key per run so earlier tests cannot consume this allowance
    key = f"confit-test-burst-{os.getpid()}-{time.time_ns()}"

    with cf.ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(lambda _: strategy.hit(item, key), range(20)))

    allowed = sum(1 for r in results if r)
    assert allowed == 5, (
        f"20 concurrent requests against a 5/minute shared limit admitted {allowed}; "
        "more than 5 means the shared counter is not atomic under concurrency"
    )


def test_the_operator_surface_publishes_the_store_and_the_public_one_does_not(
    client: TestClient,
):
    """The honesty claim must be readable at runtime, not only in a docstring.

    MEASURED while writing this: the first version of the change put the report in
    the internal probe payload and the docstring said ``/health`` publishes it —
    but ``/health`` and ``/health/ready`` each build their own response dict, so
    the value was dead data and the claim was false. This test pins both halves:
    the operator surface carries it, the public contract does not.
    """
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@confit.io", "password": "Password123!"},
    ).json()["access_token"]
    ready = client.get("/api/v1/health/ready", headers={"Authorization": f"Bearer {token}"})
    assert ready.status_code == 200, ready.text
    report = ready.json().get("rate_limit")
    assert report, "the operator readiness surface must publish the limiter's store"
    assert report["shared_across_instances"] is False
    assert "NOT a global quota" in report["quota_semantics"]

    public = client.get("/api/v1/health").json()
    assert "rate_limit" not in public, (
        "storage topology does not belong in the public capability contract"
    )
