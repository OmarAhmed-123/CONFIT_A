"""Error tracking must not export the data the product is trusted with.

CONFIT stores body measurements, photographs and addresses. An error tracker
that ships request bodies to a third party would silently export exactly what
ENCRYPTION_KEY_FOR_BODY_DATA exists to protect — on every crash, to a server
outside the operator's control.

These tests pin the privacy contract, and the fail-open contract: telemetry
must never be able to stop the API from booting.
"""
from __future__ import annotations

import pytest

from backend.app.core import error_tracking as et


def test_no_dsn_disables_tracking_without_raising(monkeypatch):
    monkeypatch.setattr("backend.app.core.config.settings.GLITCHTIP_DSN", None, raising=False)
    assert et.is_configured() is False
    assert et.init_error_tracking() is False


def test_init_failure_never_stops_the_app(monkeypatch):
    """Telemetry that can take the product down is worse than no telemetry."""
    monkeypatch.setattr("backend.app.core.config.settings.GLITCHTIP_DSN",
                        "https://x@example.test/1", raising=False)
    import sentry_sdk

    def _boom(**kwargs):
        raise RuntimeError("SDK exploded")

    monkeypatch.setattr(sentry_sdk, "init", _boom)
    assert et.init_error_tracking() is False  # returns False, does not raise


@pytest.mark.parametrize("key", [
    "password", "hashed_password", "SMTP_PASSWORD", "api_key", "NVIDIA_API_KEY",
    "authorization", "X-CSRF-Token", "session_token", "secret", "GLITCHTIP_DSN",
    "email", "phone", "address", "full_name", "recipient_name",
    "waist_cm", "bust_cm", "height_cm", "weight_kg", "body_shape",
    "photo_url", "image_base64", "avatar_id", "card_number", "cvv",
])
def test_sensitive_keys_are_redacted(key):
    out = et._scrub({key: "SENSITIVE-VALUE"})
    assert out[key] == et.REDACTED, f"{key} leaked"


@pytest.mark.parametrize("key", ["product_id", "order_number", "status", "quantity", "currency"])
def test_harmless_keys_survive(key):
    """Over-redaction makes the tracker useless — the point is to keep the
    fields that identify WHICH request broke."""
    assert et._scrub({key: "keep-me"})[key] == "keep-me"


def test_scrubbing_reaches_every_nesting_level():
    event = {"extra": {"ctx": [{"user": {"waist_cm": 81, "id": 7}}]}}
    out = et._scrub(event)
    assert out["extra"]["ctx"][0]["user"]["waist_cm"] == et.REDACTED
    assert out["extra"]["ctx"][0]["user"]["id"] == 7


def test_pathological_nesting_is_bounded():
    deep = current = {}
    for _ in range(60):
        current["nest"] = {}
        current = current["nest"]
    current["password"] = "x"
    et._scrub(deep)  # must terminate, not recurse to death


def test_before_send_strips_request_body_headers_cookies_and_query():
    event = {
        "request": {
            "url": "https://confit-a.vercel.app/api/v1/me/body-profile",
            "method": "PATCH",
            "query_string": "token=reset-secret",
            "data": {"waist_cm": 81},
            "cookies": {"session": "abc"},
            "headers": {"Authorization": "Bearer x"},
        },
        "user": {"id": 42, "email": "shopper@example.test", "ip_address": "1.2.3.4"},
    }
    out = et._before_send(event, None)
    req = out["request"]
    assert "data" not in req and "cookies" not in req
    assert "headers" not in req and "query_string" not in req
    # The URL path is kept — it is how you find the broken handler.
    assert "body-profile" in req["url"]
    # Only the user id survives; it is meaningless without database access.
    assert out["user"] == {"id": 42}


def test_before_send_drops_the_event_if_scrubbing_fails(monkeypatch):
    """If we cannot prove the event is clean, losing one report beats leaking
    a measurement."""
    monkeypatch.setattr(et, "_scrub", lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")))
    assert et._before_send({"anything": 1}, None) is None


def test_before_send_never_raises_while_handling_an_exception(monkeypatch):
    monkeypatch.setattr(et, "_scrub", lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")))
    et._before_send({"x": 1}, None)  # must not propagate
