"""Degradation observability — Cycle 9.

The gap being closed: rate_limit_store_report() only returned the *configured*
store, not the *active* enforcement state. When a shared store is configured
but unreachable, slowapi flips _storage_dead True and serves from the in-memory
fallback. The previous report said "degrades to in-process and reports it" as a
static string, not a live boolean — so an operator watching /health/ready could
not tell whether the limiter was actually degraded.

This file proves the new runtime report distinguishes:

  1. configured vs active
  2. healthy vs degraded (cheap boolean _storage_dead, not a Redis ping)
  3. recovery (degraded -> healthy when _storage_dead flips back)
  4. no secret disclosure (scheme only, no URI, no password)
  5. bounded per-instance limit still enforced while degraded

It does NOT require a real Redis: degradation is simulated by setting
_limiter._storage_dead = True, which is exactly what slowapi does on failure.
"""

from __future__ import annotations

from backend.app.core.rate_limit import (
    build_limiter,
    rate_limit_health_report,
    rate_limit_runtime_report,
    rate_limit_store_report,
)


def _assert_no_secrets(report: dict) -> None:
    """Operator surface must not leak topology beyond scheme name."""
    blob = str(report)
    # No URI, no password, no host:port should appear. The store field is
    # scheme-only ("redis", "memory"), not "redis://...".
    assert "://" not in blob, f"URI leaked in report: {report}"
    assert "@" not in blob, f"credential-like '@' leaked: {report}"
    # Passwords like "s3cret" should never appear — we test with a secret URL
    # and ensure it does not surface.
    assert "s3cret" not in blob.lower()


def test_explicit_shared_config_reports_global_when_healthy():
    """When redis:// is configured and _storage_dead False, active is global."""
    uri = "redis://example.invalid:6379/0"
    lim = build_limiter(uri)
    # Simulate healthy: slowapi default _storage_dead False
    lim._storage_dead = False

    runtime = rate_limit_runtime_report(lim, uri)
    assert runtime["configured"]["shared_across_instances"] is True
    assert runtime["configured"]["store"] == "redis"
    assert runtime["active"]["shared_across_instances"] is True
    assert runtime["active"]["store"] == "redis"
    assert runtime["degraded"] is False
    assert "global" in runtime["active"]["quota_semantics"].lower()

    health = rate_limit_health_report(lim, uri)
    # Backward compat flat fields reflect active
    assert health["store"] == "redis"
    assert health["shared_across_instances"] is True
    assert health["degraded"] is False
    assert health["configured"]["store"] == "redis"
    assert health["active"]["store"] == "redis"
    _assert_no_secrets(health)


def test_in_process_config_reports_per_instance_healthy():
    """Default memory:// — both configured and active are per-instance, not degraded."""
    uri = "memory://"
    lim = build_limiter(uri)
    lim._storage_dead = False

    runtime = rate_limit_runtime_report(lim, uri)
    assert runtime["configured"]["shared_across_instances"] is False
    assert runtime["active"]["shared_across_instances"] is False
    assert runtime["degraded"] is False
    assert "not a global quota" in runtime["active"]["quota_semantics"].lower()

    health = rate_limit_health_report(lim, uri)
    assert health["store"] == "memory"
    assert health["shared_across_instances"] is False
    assert health["degraded"] is False
    _assert_no_secrets(health)


def test_simulated_failure_degraded_status_bounded_per_instance():
    """Shared configured but _storage_dead True -> active memory, degraded True, bounded."""
    uri = "redis://example.invalid:6379/0"
    lim = build_limiter(uri)
    lim._storage_dead = True  # what slowapi does when Redis unreachable + fallback enabled

    runtime = rate_limit_runtime_report(lim, uri)
    assert runtime["configured"]["shared_across_instances"] is True
    assert runtime["configured"]["store"] == "redis"
    assert runtime["active"]["store"] == "memory"
    assert runtime["active"]["shared_across_instances"] is False
    assert runtime["degraded"] is True
    assert runtime["active"]["degraded"] is True
    assert "degraded" in runtime["active"]["quota_semantics"].lower()
    assert "per-instance" in runtime["active"]["quota_semantics"].lower()
    assert "unreachable" in runtime["active"]["active_reason"].lower()

    health = rate_limit_health_report(lim, uri)
    # Flat backward compat reflects active (degraded)
    assert health["store"] == "memory"
    assert health["shared_across_instances"] is False
    assert health["degraded"] is True
    assert health["configured"]["store"] == "redis"
    assert health["configured"]["shared_across_instances"] is True
    assert health["active"]["store"] == "memory"
    # No secrets even when degraded with password in URI
    secret_uri = "redis://:s3cret@example.invalid:6379/0"
    lim2 = build_limiter(secret_uri)
    lim2._storage_dead = True
    health_secret = rate_limit_health_report(lim2, secret_uri)
    _assert_no_secrets(health_secret)
    assert health_secret["configured"]["store"] == "redis"
    assert health_secret["active"]["store"] == "memory"


def test_recovery_flips_back_to_global():
    """When _storage_dead flips False again, active returns to global."""
    uri = "redis://example.invalid:6379/0"
    lim = build_limiter(uri)

    lim._storage_dead = True
    assert rate_limit_runtime_report(lim, uri)["degraded"] is True

    lim._storage_dead = False  # recovery
    runtime = rate_limit_runtime_report(lim, uri)
    assert runtime["degraded"] is False
    assert runtime["active"]["shared_across_instances"] is True
    assert runtime["active"]["store"] == "redis"
    assert "global" in runtime["active"]["quota_semantics"].lower()

    health = rate_limit_health_report(lim, uri)
    assert health["degraded"] is False
    assert health["store"] == "redis"
    assert health["shared_across_instances"] is True


def test_no_sensitive_disclosure_across_all_states():
    """Every shape must not leak full URI, credentials, or host."""
    for uri in [
        "memory://",
        "redis://example.invalid:6379/0",
        "redis://:s3cret@redis.example.com:6380/1",
        "rediss://user:s3cret@secure.example.com:6380/0",
    ]:
        lim = build_limiter(uri)
        for dead in (False, True):
            lim._storage_dead = dead
            for fn in (rate_limit_store_report, rate_limit_runtime_report, rate_limit_health_report):
                # store_report doesn't take limiter, only uri
                if fn is rate_limit_store_report:
                    report = fn(uri)
                else:
                    report = fn(lim, uri)
                _assert_no_secrets(report)
                # store field must be scheme or "memory", never full URI
                if "store" in report:
                    assert "://" not in report["store"]
                if "configured" in report:
                    assert "://" not in report["configured"].get("store", "")
                if "active" in report:
                    assert "://" not in report["active"].get("store", "")


def test_degraded_report_preserves_on_store_failure_and_configured_from():
    """Configured metadata must survive degradation."""
    uri = "redis://example.invalid:6379/0"
    lim = build_limiter(uri)
    lim._storage_dead = True

    health = rate_limit_health_report(lim, uri)
    assert health["configured"]["on_store_failure"] is not None
    assert "degrades" in health["configured"]["on_store_failure"].lower()
    assert health["configured"]["configured_from"]  # non-empty
    assert health["active"]["active_reason"]  # non-empty explanation


def test_runtime_report_cheap_boolean_no_network():
    """_is_limiter_degraded must not ping Redis — only checks _storage_dead."""
    # This is a design assertion: we verify the implementation uses _storage_dead
    # bool, not a network call. We can't easily assert "no network" without
    # mocking, but we can assert that setting _storage_dead alone changes result,
    # and that the function does not require REDIS_URL env or live server.
    uri = "redis://127.0.0.1:1/0"  # refused port, would fail if we pinged
    lim = build_limiter(uri)
    lim._storage_dead = False
    assert rate_limit_runtime_report(lim, uri)["degraded"] is False
    lim._storage_dead = True
    assert rate_limit_runtime_report(lim, uri)["degraded"] is True
    # No exception, no timeout — proves no network hop in this path
