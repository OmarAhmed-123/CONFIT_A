"""Regression: provider error logs must never leak an API key/token that rides
in a request URL (httpx error strings include the full URL). See base._scrub."""
from backend.app.providers.base import _scrub


def test_scrub_redacts_gemini_key_in_url():
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           "gemini-3.5-flash:generateContent?key=AQ.Ab8RN6_secret_value_123")
    out = _scrub(f"Client error '429' for url '{url}'")
    assert "AQ.Ab8RN6_secret_value_123" not in out
    assert "key=REDACTED" in out


def test_scrub_redacts_common_secret_params():
    for param in ("token", "api_key", "apikey", "access_token", "password", "secret"):
        out = _scrub(f"https://x/y?{param}=supersecretvalue&other=1")
        assert "supersecretvalue" not in out
        assert f"{param}=REDACTED" in out
        assert "other=1" in out


def test_scrub_leaves_non_secret_query_untouched():
    assert _scrub("model=gemini-3.5-flash&max_tokens=60") == "model=gemini-3.5-flash&max_tokens=60"
