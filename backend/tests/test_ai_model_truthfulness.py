"""AI model-truthfulness regression tests.

Root cause (audit): the styling orchestrator reported a human-facing
``provider_used`` label that could drift from the model actually invoked. In
particular the Groq branch claimed ``"Groq LLaMA-3.3-70B"`` while the request
sent ``model: "openai/gpt-oss-120b"``; the NVIDIA nemotron branch claimed
``"NVIDIA Nemotron-12B"`` while sending ``nvidia/nemotron-nano-12b-v2-vl``.

Per the project's no-fabrication rule, an AI response must never report a model
that was not the one called. The orchestrator now derives ``provider_used`` from
the model echoed in the provider response (falling back to the exact request
model), so the reported model equals the invoked model.

These tests pin the actual model sent in each provider request and assert the
label reflects it, so any future drift fails CI.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.app.providers.orchestrator import MultiProviderAIOrchestrator
from backend.app.core.config import settings


class _FakeResponse:
    """Canned completion. For Gemini the provider echoes ``modelVersion`` and the
    candidates shape; for OpenAI/Groq/NVIDIA it echoes ``model`` and choices."""

    def __init__(self, content: str, echo_model: str, is_gemini: bool = False):
        self._content = content
        self._echo_model = echo_model
        self._is_gemini = is_gemini

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        if self._is_gemini:
            return {
                "candidates": [{"content": {"parts": [{"text": self._content}]}}],
                "modelVersion": self._echo_model,
            }
        # OpenAI/Groq/NVIDIA chat-completions shape (echoes `model`).
        return {
            "choices": [{"message": {"content": self._content}}],
            "model": self._echo_model,
        }


class _FakeClient:
    """Captures the request `model` and returns a canned completion."""

    def __init__(self, echo_model: str):
        self.echo_model = echo_model
        self.captured_model: str | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url: str, **kwargs):
        body = kwargs.get("json") or {}
        self.captured_model = body.get("model")
        is_gemini = "generativelanguage.googleapis.com" in url
        return _FakeResponse("style advice", self.echo_model, is_gemini=is_gemini)


class _FakeClientFactory:
    def __init__(self, echo_model: str):
        self.client = _FakeClient(echo_model)

    def __call__(self, *args, **kwargs):
        return self.client


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_name,url_substr,expected_model",
    [
        ("_call_nvidia_llama", "integrate.api.nvidia.com", "meta/llama-3.1-70b-instruct"),
        ("_call_nvidia_nemotron", "integrate.api.nvidia.com", "nvidia/nemotron-nano-12b-v2-vl"),
        ("_call_groq", "api.groq.com", "openai/gpt-oss-120b"),
        ("_call_openai", "api.openai.com", "gpt-4o-mini"),
    ],
)
async def test_reported_model_equals_invoked_model(method_name, url_substr, expected_model):
    """The model in the request body must equal the model reported in the label."""
    factory = _FakeClientFactory(expected_model)
    orchestrator = MultiProviderAIOrchestrator()
    method = getattr(orchestrator, method_name)

    with patch("backend.app.providers.orchestrator.httpx.AsyncClient", factory):
        result = await method("system", "user")

    assert result is not None
    content, reported_model = result
    assert reported_model == expected_model, (
        f"{method_name} reported model {reported_model!r} but sent {factory.client.captured_model!r}"
    )
    assert factory.client.captured_model == expected_model
    assert content


@pytest.mark.asyncio
async def test_gemini_reports_model_version():
    """Gemini echoes `modelVersion`; the label must come from that (not the text alias)."""
    echo_model = f"{settings.GEMINI_TEXT_MODEL}-gemini"
    factory = _FakeClientFactory(echo_model)
    orchestrator = MultiProviderAIOrchestrator()

    with patch("backend.app.providers.orchestrator.httpx.AsyncClient", factory):
        result = await orchestrator._call_gemini("system", "user")

    assert result is not None
    _, reported_model = result
    assert reported_model == echo_model


@pytest.mark.asyncio
async def test_orchestrator_uses_reported_model_in_response_label():
    """End-to-end: generate_styling_advice must surface the invoked model, not a stale label."""
    # Poke a provider key and force the groq path to be the only configured one.
    # We patch settings so no key lookup prevents the branch, and mock the client.
    factory = _FakeClientFactory("openai/gpt-oss-120b")
    orchestrator = MultiProviderAIOrchestrator()

    with patch("backend.app.providers.orchestrator.httpx.AsyncClient", factory), \
         patch.object(settings, "AI_PROVIDERS", "groq"), \
         patch.object(settings, "GROK_API_KEY", "test-key"):
        advice = await orchestrator.generate_styling_advice(
            prompt="a quiet luxury evening look", budget_limit=300.0
        )

    assert "provider_used" in advice
    assert "gpt-oss-120b" in advice["provider_used"].lower()
    assert "llama" not in advice["provider_used"].lower()
