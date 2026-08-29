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
    yield limiter
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


def test_limiter_disabled_state_restored():
    """Sanity: after the proof tests, the suite-wide disabled state holds."""
    assert app.state.limiter.enabled is False
