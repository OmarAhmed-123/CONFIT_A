"""Proof that rate limiting actually fires — not just that middleware exists.

The limiter is disabled for the general suite (conftest) because the suite
issues more requests than production limits allow. These tests re-enable it,
exceed the real thresholds, and assert real 429 responses, then restore state.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


@pytest.fixture
def limiter_on():
    limiter = app.state.limiter
    limiter.enabled = True
    limiter.reset()  # clean buckets so this test is deterministic
    client.cookies.clear()  # anonymous client: no session cookie, so no CSRF gate
    yield limiter
    client.cookies.clear()
    limiter.reset()
    limiter.enabled = False


def test_login_rate_limit_returns_429(limiter_on):
    """10/minute on /auth/login: the 11th request in the window must 429."""
    last = None
    for i in range(11):
        last = client.post("/api/v1/auth/login", json={
            "email": "shopper@confit.io",
            "password": "Password123!"
        })
        if last.status_code == 429:
            break
    assert last is not None
    assert last.status_code == 429, f"expected 429 by request 11, got {last.status_code}"
    assert "Rate limit" in last.text or "rate" in last.text.lower()


def test_tryon_job_rate_limit_returns_429(limiter_on):
    """20/hour on /try-on/jobs (GPU cost control): the 21st must 429."""
    last = None
    for i in range(21):
        last = client.post("/api/v1/try-on/jobs", json={
            "product_ids": [1],
            "user_image_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600",
        })
        if last.status_code == 429:
            break
    assert last is not None
    assert last.status_code == 429, f"expected 429 by request 21, got {last.status_code}"


def test_stylist_chat_rate_limit_returns_429(limiter_on):
    """20/hour on /stylist/chat: the 21st request must 429.

    Measured 2026-09-23: this endpoint had NO limit while /try-on/* (GPU spend)
    and /auth/* (brute force) did. It spends provider quota on every call and
    accepts anonymous callers, so an unlimited version is a free LLM proxy keyed
    to this deployment's credentials.
    """
    last = None
    for i in range(21):
        last = client.post("/api/v1/stylist/chat", json={"prompt": "what goes with navy?"})
        if last.status_code == 429:
            break
    assert last is not None
    assert last.status_code == 429, (
        f"expected 429 by request 21 on /stylist/chat, got {last.status_code}"
    )


def test_the_key_isolates_callers_by_token_not_only_by_address():
    """Two callers behind one proxy must not share one bucket.

    IP-only keying is wrong behind a proxy (every shopper shares the edge's
    address); token-only keying would leave anonymous traffic unmetered. The key
    prefers the credential and falls back to the address — asserted directly, so
    a future 'simplification' to `get_remote_address` fails here.
    """
    # Imported through the DECLARED dependency (fastapi re-exports Request),
    # not from starlette directly: starlette is transitive, and a direct import
    # of a transitive package is exactly the undeclared-dependency outage class
    # the deployment gate exists to catch. My first version imported starlette
    # and `check_runtime_imports.py` failed the build — the gate was right.
    from fastapi import Request

    from backend.app.core.rate_limit import client_key

    def make(headers=None, cookies=None, host="203.0.113.9"):
        raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
        return Request({
            "type": "http", "method": "POST", "path": "/", "headers": raw,
            "client": (host, 1234), "query_string": b"",
            "cookie": cookies or {},
        })

    alice = client_key(make(headers={"authorization": "Bearer alice-token"}))
    bob = client_key(make(headers={"authorization": "Bearer bob-token"}))
    guest_a = client_key(make(headers={"x-session-token": "guest-a"}))
    guest_b = client_key(make(headers={"x-session-token": "guest-b"}))

    assert alice != bob, "two authenticated callers must not share a bucket"
    assert guest_a != guest_b, "two guests must not share a bucket"
    assert alice != guest_a

    # Same credential -> same bucket (the limit must actually accumulate).
    assert alice == client_key(make(headers={"authorization": "Bearer alice-token"}))
    # Same address, different credentials -> different buckets.
    assert client_key(make(headers={"authorization": "Bearer alice-token"}, host="198.51.100.1")) == alice
    # No credential -> the address is the bucket, and XFF's first hop is the client.
    assert client_key(make(headers={"x-forwarded-for": "198.51.100.7, 10.0.0.1"})) == "ip:198.51.100.7"
    assert client_key(make(headers={"x-real-ip": "198.51.100.8"})) == "ip:198.51.100.8"
    assert client_key(make()) == "ip:203.0.113.9"

    # The key must never contain the credential itself (logs/metrics).
    assert "alice-token" not in alice
    assert "guest-a" not in guest_a


def test_every_expensive_consumer_endpoint_declares_a_limit():
    """Structural guard: cost-bearing endpoints carry a limit in the source.

    Behaviour cannot be asserted for endpoints whose dependencies reject an
    unauthenticated probe before the limiter runs (upload/analyze require a
    session), so the presence of the decorator is checked here instead — and the
    list is explicit, so removing a limit from one of these endpoints fails.
    Removing the limit is exactly how the /stylist/chat gap appeared.
    """
    import pathlib
    import re

    sources = {
        path.name: path.read_text()
        for path in pathlib.Path("backend/app/controllers").glob("*.py")
    }

    protected = {
        ("stylist_controller.py", '/chat'): "20/hour",
        ("wardrobe_controller.py", '/upload"'): "30/hour",
        ("wardrobe_controller.py", '/upload/bulk'): "10/hour",
        ("wardrobe_controller.py", '/items/{item_id}/analyze'): "30/hour",
        ("wardrobe_controller.py", '/auto-tag'): "30/hour",
        ("commerce_controller.py", '/cart/promo'): "10/minute",
        ("commerce_controller.py", '/checkout",'): "10/minute",
        ("commerce_controller.py", '/checkout/sessions'): "10/minute",
    }

    for (filename, route), limit in protected.items():
        src = sources[filename]
        idx = src.find(route)
        assert idx != -1, f"{filename}: route {route} not found — the guard is stale"
        window = src[max(0, idx - 1200): idx + 1200]
        assert f'@limiter.limit("{limit}")' in window, (
            f"{filename} {route} no longer declares @limiter.limit(\"{limit}\"): an "
            "unmetered cost-bearing endpoint is the 2026-09-23 /stylist/chat gap"
        )
        assert re.search(r"request: Request", window), (
            f"{filename} {route}: slowapi requires the Request parameter"
        )


def test_limiter_disabled_state_restored():
    """Sanity: after the proof tests, the suite-wide disabled state holds."""
    assert app.state.limiter.enabled is False


def test_429_carries_a_machine_code_and_a_retry_delay(limiter_on):
    """The throttle response must be actionable and machine-readable.

    Two contract points measured on this API before the handler existed:

    * the body was slowapi's ``{"error": "Rate limit exceeded: 30 per 1 minute"}`` — a
      bare string where every other error path returns
      ``{"error": {"code", "message", "details"}}``, so a client could not branch on a
      stable code;
    * no ``Retry-After`` and no ``X-RateLimit-*`` headers were emitted (slowapi only
      injects them when the limiter is built with ``headers_enabled=True``, which is
      unusable here — it raises for any endpoint without a ``response: Response``
      parameter, which is most of them), so a throttled caller was told "no" with no
      indication of when to ask again. RFC 6585 defines ``Retry-After`` for 429.

    This asserts the fixed contract: the project's error envelope, a stable code, and a
    positive retry delay that agrees between the header and the body.
    """
    last = None
    for _ in range(11):
        last = client.post("/api/v1/auth/login", json={
            "email": "shopper@confit.io", "password": "Password123!",
        })
        if last.status_code == 429:
            break
    assert last is not None and last.status_code == 429, (
        f"expected the login limit to fire within 11 requests, got {last and last.status_code}"
    )

    payload = last.json()
    assert "error" in payload and isinstance(payload["error"], dict), payload
    assert payload["error"]["code"] == "RATE_LIMITED", payload
    assert payload["error"]["message"], payload
    details = payload["error"]["details"]
    assert details.get("limit"), details

    retry_after = last.headers.get("Retry-After")
    assert retry_after is not None, (
        "a 429 without Retry-After gives the client no way to back off: "
        f"headers={dict(last.headers)}"
    )
    assert int(retry_after) > 0
    assert details.get("retry_after_seconds") is not None, payload
    # Both channels must agree — two different numbers would be worse than one.
    assert abs(int(details["retry_after_seconds"]) - int(retry_after)) <= 1, (details, retry_after)


def test_aliases_and_prefixes_share_one_bucket(limiter_on):
    """One logical route must have ONE allowance, whatever spelling reaches it.

    Measured 2026-09-23 in production before this test existed: after exhausting
    ``/api/v1/orders/{n}`` (30 × 404 then 429), ``/api/v1/commerce/orders/{n}``
    still answered 404 — processed, not throttled — with the same client identity
    in the same minute, because slowapi's default ``key_style="url"`` buckets by
    the URL string rather than by the endpoint. The same call reached the router
    under three prefixes locally, giving six buckets for one limit.

    The limit exists to bound enumeration of order numbers, so an allowance that
    multiplies with the number of spellings is not the control it claims to be.
    """
    import json as _json
    import urllib.request as _req
    import urllib.error as _err

    # TestClient + the limiter share one in-process store, but TestClient requests
    # all carry the same address, so the bucket identity is stable across calls.
    statuses = []
    for _ in range(31):
        r = client.get("/api/v1/orders/CONF-00000000")
        statuses.append(r.status_code)
    assert 429 in statuses, f"the detail limit never fired: {statuses}"

    # The alias must now be throttled by the SAME counter…
    alias = client.get("/api/v1/commerce/orders/CONF-00000000")
    assert alias.status_code == 429, (
        "the /commerce alias has its own bucket — the 30/minute bound is bypassable "
        f"by changing spelling: {alias.status_code}"
    )
    # …and the same must hold for the other mounted prefix if this router serves it.
    for prefix in ("/v1", ""):
        st = client.get(f"{prefix}/orders/CONF-00000000").status_code
        assert st in (429, 404), f"{prefix}/orders unexpectedly {st}"
        if st == 404:
            # A 404 before the limit is exhausted would mean a separate bucket again.
            # It can only be correct here if this prefix is not served at all, which
            # the body distinguishes: a served route answers with the domain code.
            body = client.get(f"{prefix}/orders/CONF-00000000").json()
            assert body.get("detail") == "Not Found", (
                f"{prefix}/orders is served but was not throttled: {body}"
            )
