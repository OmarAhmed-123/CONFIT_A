"""Which store backs the limiter, and where that answer comes from.

G-03, second pass. The first pass concluded "no shared store in production" after
searching the Vercel project for a variable named like a rate-limit setting. That
search was correct and its conclusion was still incomplete: the live project DOES
carry `REDIS_URL` (targets: production, preview) — the endpoint the deployment
already uses for the Celery broker and the wardrobe cache — while
`RATE_LIMIT_STORAGE_URL` exists in no target. So the deployment owned a shared Redis
and the limiter was not using it.

`REDIS_URL` is marked *sensitive*: the Vercel API will not return its value, so the
secret cannot be copied into another variable by tooling. The fix is therefore in the
application, not in the dashboard: resolve the limiter's store from
`RATE_LIMIT_STORAGE_URL`, else from an operator-provided `REDIS_URL`, else in-process.

These tests pin the resolution order and — more importantly — the two things it must
REFUSE to do:

  * the code default `REDIS_URL=redis://localhost:6379/0` is not "configuration".
    Treating it as one would make every serverless instance dial its own localhost
    on every limited request and call the result a global quota.
  * a value that is not a TCP Redis scheme (the Upstash REST URL, for instance) is
    not a shared store for a `redis://`-speaking client.

Mutation control (CONFIT_evidence/46-*): remove the `REDIS_URL` fallback and
`test_an_operator_redis_url_is_used_when_the_explicit_switch_is_unset` fails.
"""
import pytest

from backend.app.core import rate_limit
from backend.app.core.config import settings


@pytest.fixture
def clean_env(monkeypatch):
    """No rate-limit configuration inherited from the surrounding environment."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setattr(settings, "RATE_LIMIT_STORAGE_URL", None, raising=False)
    return monkeypatch


def report():
    return rate_limit.rate_limit_store_report()


# ── the resolution order ─────────────────────────────────────────────────────

def test_the_explicit_switch_wins(clean_env):
    clean_env.setenv("REDIS_URL", "redis://shared-host.example:6379/0")
    clean_env.setattr(settings, "RATE_LIMIT_STORAGE_URL", "rediss://explicit.example:6380/1")
    r = report()
    assert r["store"] == "rediss"
    assert r["configured_from"] == "RATE_LIMIT_STORAGE_URL"


def test_an_operator_redis_url_is_used_when_the_explicit_switch_is_unset(clean_env):
    clean_env.setenv("REDIS_URL", "redis://shared-host.example:6379/0")
    r = report()
    assert r["shared_across_instances"] is True, r
    assert r["store"] == "redis"
    assert r["configured_from"] == "REDIS_URL (operator-provided in the environment)"
    assert "global" in r["quota_semantics"]


def test_the_code_default_is_not_mistaken_for_configuration(clean_env):
    """The negative control that keeps the fallback honest.

    `settings.REDIS_URL` still holds `redis://localhost:6379/0` in a deployment that
    configured nothing. Using it would be a per-instance store pretending to be
    shared, and would make every limited request attempt a connection to localhost.
    """
    assert settings.REDIS_URL.startswith("redis://localhost")
    r = report()
    assert r["shared_across_instances"] is False, r
    assert r["store"] == "memory"
    assert r["configured_from"] == "default (in-process counters)"


def test_an_http_redis_url_is_not_treated_as_a_shared_store(clean_env):
    """Upstash REST credentials do not satisfy a TCP Redis consumer."""
    clean_env.setenv("REDIS_URL", "https://example-redis.upstash.io")
    r = report()
    assert r["shared_across_instances"] is False, r


def test_a_broken_shared_store_still_reports_the_degradation(clean_env):
    """The store may be down at runtime; the report must keep telling the truth."""
    clean_env.setenv("REDIS_URL", "redis://127.0.0.1:6399/0")     # nothing listens here
    r = report()
    assert r["shared_across_instances"] is True
    assert r["on_store_failure"], "a shared store must state what happens when it fails"


def test_the_limiter_built_from_an_operator_redis_url_is_shared(clean_env):
    """The report and the constructed limiter must not disagree."""
    clean_env.setenv("REDIS_URL", "redis://shared-host.example:6379/0")
    limiter = rate_limit.build_limiter()
    assert "shared-host.example" in str(getattr(limiter, "_storage_uri", "")) or \
        "shared-host.example" in str(limiter.__dict__), limiter.__dict__
