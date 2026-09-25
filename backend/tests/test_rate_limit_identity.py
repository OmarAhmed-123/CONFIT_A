"""Bucket identity — the caller must not be able to choose which quota it uses.

DEFECT THIS FILE PINS (found by the independent sweep, 2026-09-25). The limiter
keyed requests on ``x-real-ip`` and, failing that, on the **left-most**
``X-Forwarded-For`` entry. Measured against the running API: three requests with
three different spoofed ``X-Forwarded-For`` values produced three separate
buckets in Redis, i.e. every caller could mint a fresh quota by sending a
header. ``X-Forwarded-For`` is appended by each hop, so its left-most entry is
whatever the client sent; ``backend/app/core/request_context.py`` already
documents that ("client-supplied and spoofable"). One of the two notions of
"who is calling" had to give, and the limiter is the one that spends money.

Policy under test (closed by default):
  1. on the hosting platform (``VERCEL`` in the environment), platform-set
     headers are authoritative — ``x-vercel-forwarded-for``, then ``x-real-ip``,
     then the RIGHT-most ``x-forwarded-for`` hop;
  2. off-platform, headers are trusted only when the socket peer is inside
     ``TRUSTED_PROXY_IPS``; then the right-most hop is used;
  3. otherwise the socket peer.

Every test here fails if the old left-most-trust rule is restored (see the
mutation control in CONFIT_evidence/49-*), which is what makes them evidence
rather than decoration.
"""

import os
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from backend.app.core.rate_limit import _client_ip


class _FakeRequest:
    """Only the two attributes the identity function reads."""

    def __init__(self, headers=None, peer="10.1.2.3"):
        self.headers = headers or {}
        self.client = type("C", (), {"host": peer})() if peer else None


@contextmanager
def _env(**values):
    """Set/clear environment variables for one test, restoring afterwards."""
    saved = {k: os.environ.get(k) for k in values}
    try:
        for k, v in values.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ── 1. off-platform: caller-supplied headers never become the bucket ──────

def test_spoofed_forwarded_for_cannot_choose_the_bucket_off_platform():
    """The core defect: rotating X-Forwarded-For minted a fresh quota."""
    with _env(VERCEL=None, TRUSTED_PROXY_IPS=None):
        a = _client_ip(_FakeRequest({"x-forwarded-for": "203.0.113.7"}))
        b = _client_ip(_FakeRequest({"x-forwarded-for": "203.0.113.8"}))
        c = _client_ip(_FakeRequest({"x-forwarded-for": "198.51.100.9"}))
    assert a == b == c == "10.1.2.3", (
        f"spoofed X-Forwarded-For changed the bucket: {a} vs {b} vs {c}"
    )


def test_spoofed_forwarded_chain_is_ignored_off_platform():
    """A chain must not help either — including one dressed up as a real proxy path."""
    with _env(VERCEL=None, TRUSTED_PROXY_IPS=None):
        value = _client_ip(
            _FakeRequest({"x-forwarded-for": "203.0.113.7, 10.0.0.1, 192.0.2.9"})
        )
    assert value == "10.1.2.3", f"chain influenced the bucket: {value}"


def test_spoofed_x_real_ip_is_ignored_off_platform():
    with _env(VERCEL=None, TRUSTED_PROXY_IPS=None):
        value = _client_ip(_FakeRequest({"x-real-ip": "203.0.113.7"}))
    assert value == "10.1.2.3", f"x-real-ip influenced the bucket: {value}"


def test_junk_headers_never_become_a_bucket():
    """Unvalidated strings must not be usable as bucket names."""
    with _env(VERCEL=None, TRUSTED_PROXY_IPS=None):
        for junk in ("not-an-ip", "'; DROP TABLE users;--", "x" * 300, "1.2.3.4.5", ""):
            value = _client_ip(_FakeRequest({"x-real-ip": junk, "x-forwarded-for": junk}))
            assert value == "10.1.2.3", f"junk {junk[:20]!r} became the bucket: {value}"


def test_missing_peer_fails_closed_into_one_shared_bucket():
    """No address at all must be ONE bucket, not a per-request free pass."""
    with _env(VERCEL=None, TRUSTED_PROXY_IPS=None):
        value = _client_ip(_FakeRequest({}, peer=None))
    assert value == "unknown"


# ── 2. on the platform: the platform-set header is authoritative ──────────

def test_on_vercel_the_platform_header_wins_over_a_spoofed_chain():
    """x-vercel-forwarded-for survives an upstream proxy that rewrites XFF."""
    with _env(VERCEL="1", TRUSTED_PROXY_IPS=None):
        value = _client_ip(
            _FakeRequest(
                {
                    "x-vercel-forwarded-for": "198.51.100.9",
                    "x-forwarded-for": "203.0.113.7, 203.0.113.8",
                    "x-real-ip": "203.0.113.7",
                }
            )
        )
    assert value == "198.51.100.9", f"spoofable header beat the platform one: {value}"


def test_on_vercel_only_the_rightmost_hop_of_forwarded_for_is_used():
    """If the platform header is absent, the near hop is used — never the caller's."""
    with _env(VERCEL="1", TRUSTED_PROXY_IPS=None):
        value = _client_ip(
            _FakeRequest({"x-forwarded-for": "203.0.113.7, 198.51.100.9"})
        )
    assert value == "198.51.100.9", f"left-most (caller-supplied) hop was used: {value}"


def test_on_vercel_a_junk_platform_header_falls_through_to_the_near_hop():
    with _env(VERCEL="1", TRUSTED_PROXY_IPS=None):
        value = _client_ip(
            _FakeRequest({"x-vercel-forwarded-for": "junk", "x-forwarded-for": "198.51.100.9"})
        )
    assert value == "198.51.100.9"


# ── 3. self-hosted: headers honoured only from a configured trusted proxy ──

def test_self_hosted_trusted_proxy_uses_the_hop_that_proxy_appended():
    with _env(VERCEL=None, TRUSTED_PROXY_IPS="10.0.0.0/8"):
        value = _client_ip(_FakeRequest({"x-forwarded-for": "203.0.113.7, 198.51.100.9"}, peer="10.1.2.3"))
    assert value == "198.51.100.9", f"expected the near hop, got {value}"


def test_self_hosted_untrusted_peer_gets_its_headers_ignored():
    """The attack this prevents: an internet client talking straight to the app
    and claiming someone else's address."""
    with _env(VERCEL=None, TRUSTED_PROXY_IPS="10.0.0.0/8"):
        value = _client_ip(_FakeRequest({"x-forwarded-for": "203.0.113.7"}, peer="203.0.113.250"))
    assert value == "203.0.113.250", f"untrusted peer's header was trusted: {value}"


def test_ipv6_and_over_long_values():
    with _env(VERCEL=None, TRUSTED_PROXY_IPS=None):
        assert _client_ip(_FakeRequest({}, peer="2001:db8::1")) == "2001:db8::1"
        assert _client_ip(_FakeRequest({}, peer="2" * 46)) == "unknown"


# ── 4. behavioural proof: the limit still fires under header rotation ────

def test_limit_still_fires_when_the_client_rotates_the_header():
    """Integration-level version of the defect: hit a real limited endpoint
    with a different X-Forwarded-For every time. Before the fix each request had
    its own bucket, so the limit never triggered. 20/hour on /stylist/chat means
    request 21 must 429 no matter what headers it carries."""
    from backend.app.main import app

    limiter = app.state.limiter
    limiter.enabled = True
    limiter.reset()
    client = TestClient(app)
    client.cookies.clear()
    try:
        with _env(VERCEL=None, TRUSTED_PROXY_IPS=None, RATE_LIMIT_STORAGE_URL=None):
            last = None
            for i in range(21):
                last = client.post(
                    "/api/v1/stylist/chat",
                    json={"prompt": "quota probe"},
                    headers={"X-Forwarded-For": f"203.0.113.{i + 1}"},
                )
                if last.status_code == 429:
                    break
        assert last is not None
        assert last.status_code == 429, (
            "rotating X-Forwarded-For defeated the quota again "
            f"(last status {last.status_code} after 21 requests)"
        )
    finally:
        client.cookies.clear()
        limiter.reset()
        limiter.enabled = False
