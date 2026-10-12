"""C05 pass 3: the stylist image-turns throttle must speak the standard
RATE_LIMITED envelope, not FastAPI's bare {"detail": ...} shape.

Before this contract, the drawer received a 429 with no error.code: the
client could not branch, showed a generic failure with a futile Retry
button, and could surface the English diagnostic verbatim in an Arabic
transcript."""

import pytest

from backend.app.controllers.stylist_controller import _enforce_image_budget
from backend.app.core.exceptions import RateLimitExceededError
from backend.app.core import rate_limit as rl


class _Request:
    client = type("C", (), {"host": "10.9.8.7"})()
    headers: dict = {}
    cookies: dict = {}


def test_image_turns_throttle_raises_rate_limited_envelope(monkeypatch):
    monkeypatch.setattr(rl.limiter, "enabled", True, raising=False)

    class _Denies:
        def hit(self, *_a, **_k):
            return False

    monkeypatch.setattr(rl.limiter, "_limiter", _Denies(), raising=False)

    with pytest.raises(RateLimitExceededError) as exc:
        _enforce_image_budget(_Request())

    err = exc.value
    assert err.status_code == 429
    assert err.code == "RATE_LIMITED"
    assert err.details.get("scope") == "stylist_image_turns"
    # the message is a machine-facing diagnostic; the client renders its own
    # translated sentence and must branch on the code, never this string
    assert "photo" in err.message.lower()
