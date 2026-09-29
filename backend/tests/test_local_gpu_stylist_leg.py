"""Self-hosted stylist inference: dormant today, live the day a GPU exists.

WHY THIS LEG EXISTS
-------------------
The stylist runs entirely on hosted providers. When the GPU subscription
renews, the project should be able to move query understanding onto owned
hardware WITHOUT a code change or a redeploy of application logic —
otherwise "we'll switch when the GPU is back" is a promise with no
mechanism behind it.

The mechanism is one environment variable. These tests pin both halves of
it: the leg must cost nothing while unset, and must actually serve when set.
A leg that is only ever skipped is dead code; a leg that runs when it should
not is worse.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict

import pytest

from backend.app.core.config import settings
from backend.app.providers.orchestrator import MultiProviderAIOrchestrator


def _orchestrator() -> MultiProviderAIOrchestrator:
    return MultiProviderAIOrchestrator()


def test_local_gpu_leads_the_provider_chain():
    """Preferred when present — otherwise the hosted chain always wins first."""
    chain = [p.strip() for p in settings.AI_PROVIDERS.split(",")]
    assert chain[0] == "local_gpu", chain
    # and the hosted providers are still behind it, not replaced
    for expected in ("nvidia", "groq", "gemini"):
        assert expected in chain, f"{expected} must remain in the chain"


def test_leg_returns_none_when_no_server_is_configured(monkeypatch):
    """Today's state: zero cost, no network, no exception."""
    monkeypatch.setattr(settings, "LOCAL_LLM_BASE_URL", "", raising=False)
    result = asyncio.run(_orchestrator()._call_local_gpu("sys", "user"))
    assert result is None


def test_leg_calls_an_openai_compatible_endpoint_when_configured(monkeypatch):
    """The day the GPU renews: one env var and it serves."""
    captured: Dict[str, Any] = {}

    class _Resp:
        status_code = 200

        def raise_for_status(self): return None

        def json(self):
            return {
                "choices": [{"message": {"content": "A tailored navy blazer anchors the look."}}],
                "model": "qwen-stylist",
            }

    class _Client:
        def __init__(self, *a, **k): captured["timeout"] = k.get("timeout")
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["model"] = (json or {}).get("model")
            captured["messages"] = (json or {}).get("messages")
            return _Resp()

    import backend.app.providers.orchestrator as orch

    monkeypatch.setattr(settings, "LOCAL_LLM_BASE_URL", "http://gpu-box:8001/v1", raising=False)
    monkeypatch.setattr(settings, "LOCAL_LLM_MODEL", "qwen-stylist", raising=False)
    monkeypatch.setattr(orch.httpx, "AsyncClient", lambda *a, **k: _Client(*a, **k))

    result = asyncio.run(_orchestrator()._call_local_gpu("sys prompt", "user prompt"))

    assert result is not None, "a configured server must be called"
    text, model_id = result
    assert "navy blazer" in text
    # The reported model is the one the SERVER echoed, never a hard-coded
    # label — the same invariant the Groq leg had to be corrected for.
    assert model_id == "qwen-stylist"
    assert captured["url"] == "http://gpu-box:8001/v1/chat/completions"
    assert captured["messages"][0]["role"] == "system"


def test_a_trailing_slash_in_the_base_url_does_not_double(monkeypatch):
    """Operators will paste a URL with a slash; it must not become //."""
    seen: Dict[str, Any] = {}

    class _Resp:
        def raise_for_status(self): return None
        def json(self): return {"choices": [{"message": {"content": "ok text here"}}], "model": "m"}

    class _Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, json=None):
            seen["url"] = url
            return _Resp()

    import backend.app.providers.orchestrator as orch

    monkeypatch.setattr(settings, "LOCAL_LLM_BASE_URL", "http://gpu-box:8001/v1/", raising=False)
    monkeypatch.setattr(orch.httpx, "AsyncClient", lambda *a, **k: _Client())
    asyncio.run(_orchestrator()._call_local_gpu("s", "u"))
    assert seen["url"] == "http://gpu-box:8001/v1/chat/completions"


def test_the_timeout_is_tight_enough_to_fall_back(monkeypatch):
    """A slow self-hosted box must yield to the hosted chain, not stall the user."""
    assert settings.LOCAL_LLM_TIMEOUT_SECONDS <= 20.0, (
        "a long local timeout would make an unhealthy GPU worse than no GPU"
    )
