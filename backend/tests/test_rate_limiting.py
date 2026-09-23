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
