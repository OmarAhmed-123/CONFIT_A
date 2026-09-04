"""AI failover regression tests: an empty answer is not an answer.

The defect (found by a real end-to-end call against the live Groq endpoint,
2026-09-04):

    POST /api/v1/stylist/advise  ->  HTTP 200
    {
      "styling_advice_text": "",
      "provider_used": "Groq openai/gpt-oss-120b"
    }

Two root causes, one enabling the other:

1. `openai/gpt-oss-120b` is a REASONING model. It writes `message.reasoning`
   first and those tokens count against the same `max_tokens` budget, which was
   hardcoded to 300. The model exhausted the budget on reasoning and returned
   `content=""` with `finish_reason="length"` - observed on 2 of 4 real calls.

2. The model-truthfulness fix had changed `_call_*` to return a TUPLE
   `(content, model_id)` so the label could name the model actually served. The
   failover loop still guarded with `if res:` - and a tuple containing an empty
   string is TRUTHY. So the empty answer was accepted, the loop never reached
   the next provider, and the response claimed a provider served content it did
   not produce. Truthful labelling is worthless if the thing labelled never
   existed.

`gemini-flash-latest` (currently serving `gemini-3.8-flash`) has the same class
of trap twice over, both measured live on the same day: thought tokens count
against `maxOutputTokens` (a 200 with finishReason=MAX_TOKENS and 63 truncated
characters), and a thinking model can emit parts carrying only a
`thoughtSignature` and no `text`, which `parts[0]["text"]` would read as empty
or KeyError on.

These tests pin: an empty/whitespace completion is a provider FAILURE, it fails
over to the next real provider, and the label names whichever provider actually
produced the text - or names the deterministic engine when none did.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import httpx
import pytest

from backend.app.core.config import settings
from backend.app.providers.orchestrator import MultiProviderAIOrchestrator


GOOD_TEXT = "The unstructured navy blazer keeps the wool lightweight for a summer wedding."
FALLBACK_LABEL = "CONFIT Grounded Styling Engine (Grounded & Resilient)"


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------
class _FakeResponse:
    def __init__(self, payload=None, status_code: int = 200, request_url: str = "https://ai/"):
        self._payload = payload if payload is not None else {}
        self.status_code = status_code
        self._request_url = request_url

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("POST", self._request_url),
                response=httpx.Response(self.status_code, request=httpx.Request("POST", self._request_url)),
            )

    def json(self):
        return self._payload


def _chat(content, model, finish_reason="stop", reasoning=None):
    message = {"content": content}
    if reasoning is not None:
        message["reasoning"] = reasoning
    return {"model": model, "choices": [{"message": message, "finish_reason": finish_reason}]}


def _gemini(parts, model_version, finish_reason="STOP", thoughts=None):
    usage = {"candidatesTokenCount": 40}
    if thoughts is not None:
        usage["thoughtsTokenCount"] = thoughts
    return {
        "modelVersion": model_version,
        "candidates": [{"content": {"parts": parts}, "finishReason": finish_reason}],
        "usageMetadata": usage,
    }


class _ScriptedClient:
    """Dispatches by URL so one test can script a whole failover chain."""

    def __init__(self, script: dict):
        self.script = script          # url substring -> _FakeResponse
        self.calls: list[str] = []    # ordered log of hosts actually called
        self.captured_bodies: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url: str, **kwargs):
        self.captured_bodies.append(kwargs.get("json") or {})
        for needle, response in self.script.items():
            if needle in url:
                self.calls.append(needle)
                response._request_url = url
                return response
        raise AssertionError(f"unexpected provider URL in test: {url}")


def _factory(client):
    return lambda *a, **k: client


def _configured(monkeypatch, providers="groq,gemini,openai"):
    """Give every provider in the chain a key so the loop actually reaches it."""
    monkeypatch.setattr(settings, "AI_PROVIDERS", providers)
    # GROQ_API_KEY is the name the production deployment contract documents;
    # GROK_API_KEY is the legacy alias. Clear the alias so these tests exercise
    # the documented spelling.
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-groq-key")
    monkeypatch.setattr(settings, "GROK_API_KEY", None)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setattr(settings, "NVIDIA_API_KEY", "")
    monkeypatch.setattr(settings, "NVIDIA_CHAT_KEY_2", "")


# --------------------------------------------------------------------------
# Unit: the validators
# --------------------------------------------------------------------------
class TestChatCompletionValidation:
    @pytest.mark.parametrize("content", ["", "   ", "\n\t ", None])
    def test_empty_content_is_rejected(self, content):
        orch = MultiProviderAIOrchestrator()
        res = orch._accept_chat_completion(
            "groq", _chat(content, "openai/gpt-oss-120b", "length", reasoning="x" * 400),
            "openai/gpt-oss-120b")
        assert res is None, "an empty completion must never be returned as an answer"

    def test_valid_content_is_accepted_and_stripped(self):
        orch = MultiProviderAIOrchestrator()
        res = orch._accept_chat_completion(
            "groq", _chat(f"  {GOOD_TEXT}  ", "openai/gpt-oss-120b"), "openai/gpt-oss-120b")
        assert res == (GOOD_TEXT, "openai/gpt-oss-120b")

    def test_malformed_body_is_rejected_not_an_exception(self):
        orch = MultiProviderAIOrchestrator()
        for body in ({}, {"choices": []}, {"choices": [{}]}, "not-a-dict", None):
            assert orch._accept_chat_completion("groq", body, "m") is None

    def test_reported_model_falls_back_to_the_requested_model(self):
        orch = MultiProviderAIOrchestrator()
        body = {"choices": [{"message": {"content": GOOD_TEXT}, "finish_reason": "stop"}]}
        assert orch._accept_chat_completion("groq", body, "openai/gpt-oss-120b")[1] == \
            "openai/gpt-oss-120b"


class TestGeminiValidation:
    def test_text_is_joined_across_every_part(self):
        """A thinking model can interleave parts that carry only a
        thoughtSignature; parts[0]["text"] would have missed the answer."""
        orch = MultiProviderAIOrchestrator()
        body = _gemini([
            {"thoughtSignature": "abc123"},
            {"text": "The unstructured navy blazer "},
            {"text": "keeps the wool lightweight."},
        ], "gemini-3.8-flash")
        assert orch._accept_gemini_completion(body, "gemini-flash-latest") == (
            "The unstructured navy blazer keeps the wool lightweight.", "gemini-3.8-flash")

    @pytest.mark.parametrize("body", [
        _gemini([{"thoughtSignature": "abc"}], "gemini-3.8-flash", "MAX_TOKENS", thoughts=284),
        _gemini([{"text": ""}], "gemini-3.8-flash", "MAX_TOKENS", thoughts=284),
        _gemini([], "gemini-3.8-flash"),
        {"candidates": []},
        {},
        None,
    ])
    def test_thought_only_or_truncated_responses_are_rejected(self, body):
        assert MultiProviderAIOrchestrator()._accept_gemini_completion(
            body, "gemini-flash-latest") is None


class TestUsableGuard:
    @pytest.mark.parametrize("res,expected", [
        (None, False),
        (("", "model"), False),        # the exact shape that used to slip through
        (("   ", "model"), False),
        (("real advice", "model"), True),
    ])
    def test_a_tuple_holding_an_empty_string_is_not_usable(self, res, expected):
        assert MultiProviderAIOrchestrator._is_usable(res) is expected


# --------------------------------------------------------------------------
# End-to-end: the failover chain
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_empty_response_fails_over_to_the_next_real_provider(monkeypatch):
    """THE regression. Groq answers with empty content (reasoning ate the
    budget); the orchestrator must not accept it, must call Gemini, and must
    label Gemini - not Groq."""
    _configured(monkeypatch)
    client = _ScriptedClient({
        "api.groq.com": _FakeResponse(_chat("", "openai/gpt-oss-120b", "length", reasoning="r" * 500)),
        "generativelanguage.googleapis.com": _FakeResponse(_gemini([{"text": GOOD_TEXT}], "gemini-3.8-flash")),
        "api.openai.com": _FakeResponse(_chat("never reached", "gpt-4o-mini")),
    })
    orch = MultiProviderAIOrchestrator()
    with patch("backend.app.providers.orchestrator.httpx.AsyncClient", _factory(client)):
        out = await orch.generate_styling_advice("navy blazer at a summer wedding")

    assert out["styling_advice_text"].strip() == GOOD_TEXT
    assert out["provider_used"] == "Google gemini-3.8-flash", (
        "the label must name the provider that actually produced the text")
    assert client.calls == ["api.groq.com", "generativelanguage.googleapis.com"], (
        "must stop at the first provider that produced real content")


@pytest.mark.asyncio
async def test_every_provider_empty_reaches_the_labelled_deterministic_engine(monkeypatch):
    _configured(monkeypatch)
    client = _ScriptedClient({
        "api.groq.com": _FakeResponse(_chat("", "openai/gpt-oss-120b", "length", reasoning="r" * 500)),
        "generativelanguage.googleapis.com": _FakeResponse(_gemini([{"thoughtSignature": "x"}],
                                                                  "gemini-3.8-flash", "MAX_TOKENS", 284)),
        "api.openai.com": _FakeResponse(_chat("  ", "gpt-4o-mini", "length")),
    })
    orch = MultiProviderAIOrchestrator()
    with patch("backend.app.providers.orchestrator.httpx.AsyncClient", _factory(client)):
        out = await orch.generate_styling_advice("navy blazer at a summer wedding")

    assert client.calls == ["api.groq.com", "generativelanguage.googleapis.com", "api.openai.com"], (
        "all three configured providers must be attempted")
    assert out["provider_used"] == FALLBACK_LABEL, (
        "the deterministic engine must be labelled as itself, never as a provider")
    assert "Groq" not in out["provider_used"] and "OpenAI" not in out["provider_used"]
    assert out["styling_advice_text"].strip(), "the fallback still owes the user an answer"


@pytest.mark.asyncio
async def test_http_429_cools_the_provider_down_and_fails_over(monkeypatch):
    """The live OpenAI key returns 429 credit_balance_exhausted. That must be a
    failover with a cooldown, not an error surfaced to the shopper."""
    _configured(monkeypatch, providers="openai,groq")
    client = _ScriptedClient({
        "api.openai.com": _FakeResponse({"error": {"message": "credit_balance_exhausted"}}, 429),
        "api.groq.com": _FakeResponse(_chat(GOOD_TEXT, "openai/gpt-oss-120b")),
    })
    orch = MultiProviderAIOrchestrator()
    with patch("backend.app.providers.orchestrator.httpx.AsyncClient", _factory(client)):
        out = await orch.generate_styling_advice("navy blazer at a summer wedding")

    assert out["provider_used"] == "Groq openai/gpt-oss-120b"
    assert "openai" in orch.cooldowns, "an exhausted key must be cooled down, not retried per request"


@pytest.mark.asyncio
async def test_timeout_is_treated_as_failure_and_fails_over(monkeypatch):
    """The live Gemini leg read-times-out under the old 4.0s budget."""
    _configured(monkeypatch, providers="gemini,groq")

    class _TimeoutClient(_ScriptedClient):
        async def post(self, url, **kwargs):
            self.captured_bodies.append(kwargs.get("json") or {})
            if "generativelanguage.googleapis.com" in url:
                self.calls.append("gemini")
                raise httpx.ReadTimeout("timed out")
            self.calls.append("api.groq.com")
            return _FakeResponse(_chat(GOOD_TEXT, "openai/gpt-oss-120b"), request_url=url)

    client = _TimeoutClient({})
    orch = MultiProviderAIOrchestrator()
    with patch("backend.app.providers.orchestrator.httpx.AsyncClient", _factory(client)):
        out = await orch.generate_styling_advice("navy blazer at a summer wedding")

    assert client.calls == ["gemini", "api.groq.com"]
    assert out["provider_used"] == "Groq openai/gpt-oss-120b"


# --------------------------------------------------------------------------
# The root cause must stay fixed in the request itself
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reasoning_models_get_a_completion_budget_that_leaves_room(monkeypatch):
    """300 tokens was tuned for a non-reasoning model; gpt-oss-120b spends it on
    `message.reasoning` before writing any content."""
    _configured(monkeypatch, providers="groq")
    client = _ScriptedClient({"api.groq.com": _FakeResponse(_chat(GOOD_TEXT, "openai/gpt-oss-120b"))})
    orch = MultiProviderAIOrchestrator()
    with patch("backend.app.providers.orchestrator.httpx.AsyncClient", _factory(client)):
        await orch.generate_styling_advice("navy blazer at a summer wedding")

    sent = client.captured_bodies[0]
    assert sent["max_tokens"] == settings.AI_MAX_TOKENS
    assert sent["max_tokens"] > 300, (
        "the budget that produced empty reasoning-model completions must not come back")


def test_no_hardcoded_provider_timeout_or_token_budget_left():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "app", "providers", "orchestrator.py")
    src = open(path, encoding="utf-8").read()
    assert "timeout=4.0" not in src, "per-provider HTTP budget must come from configuration"
    assert '"max_tokens": 300' not in src, "completion budget must come from configuration"


def test_every_provider_call_validates_before_returning():
    """No `_call_*` may hand back a raw subscript of the provider body again."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "app", "providers", "orchestrator.py")
    lines = open(path, encoding="utf-8").read().splitlines()
    offenders = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("return data[") or stripped.startswith('return res.json()["'):
            offenders.append(f"line {i}: {stripped[:110]}")
    assert offenders == [], "unvalidated provider return reappeared:\n" + "\n".join(offenders)

# --------------------------------------------------------------------------
# The Groq key name: docs/PRODUCTION_DEPLOYMENT_CONTRACT.md says GROQ_API_KEY,
# .env.example/README/config.py said GROK_API_KEY. An operator who followed the
# contract silently disabled the only provider verified working end to end.
# --------------------------------------------------------------------------
class TestGroqKeySpelling:
    def _build(self, **kwargs):
        from backend.app.core.config import Settings
        env = {
            "ENVIRONMENT": "development",
            "DATABASE_URL": "postgresql://u:p@localhost:5432/confit",
            "SECRET_KEY": "x" * 48, "JWT_REFRESH_SECRET": "y" * 48,
            "ENCRYPTION_KEY_FOR_BODY_DATA": "z" * 48,
        }
        env.update(kwargs)
        return Settings(_env_file=None, **env)

    def test_documented_name_is_accepted(self):
        assert self._build(GROQ_API_KEY="gsk_live").groq_api_key == "gsk_live"

    def test_legacy_name_is_still_accepted(self):
        assert self._build(GROK_API_KEY="gsk_legacy").groq_api_key == "gsk_legacy"

    def test_documented_name_wins_over_legacy(self):
        s = self._build(GROQ_API_KEY="gsk_live", GROK_API_KEY="gsk_legacy")
        assert s.groq_api_key == "gsk_live"

    @pytest.mark.parametrize("kwargs", [{}, {"GROQ_API_KEY": ""}, {"GROQ_API_KEY": "   "},
                                        {"GROQ_API_KEY": "", "GROK_API_KEY": ""}])
    def test_absent_or_blank_means_unconfigured(self, kwargs):
        assert self._build(**kwargs).groq_api_key is None

    @pytest.mark.asyncio
    async def test_legacy_spelling_still_reaches_the_wire(self, monkeypatch):
        """Backwards compatibility: an existing deployment that only set
        GROK_API_KEY must keep working, and must send that key."""
        _configured(monkeypatch, providers="groq")
        monkeypatch.setattr(settings, "GROQ_API_KEY", None)
        monkeypatch.setattr(settings, "GROK_API_KEY", "gsk_legacy_value")
        captured = {}

        class _CaptureClient(_ScriptedClient):
            async def post(self, url, **kwargs):
                captured["auth"] = (kwargs.get("headers") or {}).get("Authorization")
                return _FakeResponse(_chat(GOOD_TEXT, "openai/gpt-oss-120b"), request_url=url)

        orch = MultiProviderAIOrchestrator()
        with patch("backend.app.providers.orchestrator.httpx.AsyncClient",
                   _factory(_CaptureClient({}))):
            out = await orch.generate_styling_advice("navy blazer at a summer wedding")

        assert out["provider_used"] == "Groq openai/gpt-oss-120b"
        assert captured["auth"] == "Bearer gsk_legacy_value"

    @pytest.mark.asyncio
    async def test_unconfigured_groq_is_skipped_not_called(self, monkeypatch):
        """If neither spelling is set the leg must be skipped entirely rather
        than sending an unauthenticated request that 401s and burns the budget."""
        _configured(monkeypatch, providers="groq,openai")
        monkeypatch.setattr(settings, "GROQ_API_KEY", None)
        monkeypatch.setattr(settings, "GROK_API_KEY", None)
        client = _ScriptedClient({"api.openai.com": _FakeResponse(_chat(GOOD_TEXT, "gpt-4o-mini"))})
        orch = MultiProviderAIOrchestrator()
        with patch("backend.app.providers.orchestrator.httpx.AsyncClient", _factory(client)):
            out = await orch.generate_styling_advice("navy blazer at a summer wedding")

        assert client.calls == ["api.openai.com"]
        assert out["provider_used"] == "OpenAI gpt-4o-mini"
