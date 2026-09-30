"""Contract tests for the NVIDIA GARMENT_VISION tier in the vision fallback chain.

Context
-------
``ModelRole.GARMENT_VISION`` was defined and live-verified in
``backend/app/providers/nvidia/registry.py`` but no caller consumed it, so
Smart Wardrobe auto-tagging and Visual Search still had exactly ONE working
backend (Gemini) — the Qwen worker is unset in production and UnoRouter needs
its own key. These tests lock in the new tier and, more importantly, lock in
the honesty rules around it: a tier that cannot produce a usable payload must
step aside, never fabricate.
"""
from __future__ import annotations

import pytest

from backend.app.providers.nvidia.errors import NvidiaCapacityError
from backend.app.providers.tryon_provider import VisualSearchAIProvider

# A 1x1 transparent PNG — enough to exercise the data-URL path without I/O.
PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

WARDROBE_PAYLOAD = {
    "category": "Outerwear",
    "item_type": "Oversized Blazer",
    "primary_color": "Navy",
    "primary_color_hex": "#1B1F3B",
    "secondary_colors": [],
    "style": "Smart Casual",
    "style_tags": ["Tailored"],
    "pattern": "Solid",
    "occasion_suitability": ["Work & Business"],
    "seasonality": "All-Season",
    "confidence": 0.92,
    "_model_id": "google/diffusiongemma-26b-a4b-it",
    "_latency_s": 1.7,
}


class _FakeClient:
    """Minimal stand-in for ``nvidia_client`` — no network, no credentials."""

    def __init__(self, *, configured=True, result=None, error=None):
        self.configured = configured
        self._result = result
        self._error = error
        self.calls = []

    async def chat_json(self, role, *, user, images=None, **kwargs):
        self.calls.append({"role": role, "user": user, "images": images})
        if self._error is not None:
            raise self._error
        return dict(self._result)


@pytest.fixture(autouse=True)
def _no_other_tiers(monkeypatch):
    """Isolate the NVIDIA tier: Qwen and UnoRouter stay unconfigured."""
    monkeypatch.setattr(
        "backend.app.providers.qwen_vision.QwenVisionProvider.is_configured",
        lambda self: False,
    )
    from backend.app.providers import unorouter_provider

    monkeypatch.setattr(unorouter_provider, "is_configured", lambda: False)


def _install(monkeypatch, client):
    monkeypatch.setattr("backend.app.providers.nvidia.nvidia_client", client)


@pytest.mark.asyncio
async def test_wardrobe_tagging_uses_nvidia_when_gemini_is_absent(monkeypatch):
    """The exact production gap: no GEMINI_API_KEY must no longer mean no AI."""
    monkeypatch.setattr("backend.app.core.config.settings.GEMINI_API_KEY", "", raising=False)
    client = _FakeClient(result=WARDROBE_PAYLOAD)
    _install(monkeypatch, client)

    result = await VisualSearchAIProvider().analyze_wardrobe_image(PNG_DATA_URL)

    assert result["analysis_available"] is True
    assert result["category"] == "Outerwear"
    # Attribution names the SERVED model, so an audit can never be misled
    # about which engine produced a tag.
    assert result["analysis_source"] == "nvidia:google/diffusiongemma-26b-a4b-it"
    # Internal transport metadata must not leak into the persisted payload.
    assert "_model_id" not in result and "_latency_s" not in result

    # The wardrobe prompt (not the visual-search one) reached the model, and
    # the image travelled as a single vision part.
    assert client.calls[0]["user"] == VisualSearchAIProvider.WARDROBE_TAG_PROMPT
    assert len(client.calls[0]["images"]) == 1
    assert client.calls[0]["images"][0].url == PNG_DATA_URL


@pytest.mark.asyncio
async def test_visual_search_uses_its_own_prompt_and_key_set(monkeypatch):
    monkeypatch.setattr("backend.app.core.config.settings.GEMINI_API_KEY", "", raising=False)
    client = _FakeClient(result={
        "detected_category": "Tops",
        "detected_color": "White",
        "detected_pattern": "Solid",
        "detected_style": "Minimalist",
        "detected_attributes": {},
        "_model_id": "moonshotai/kimi-k3",
    })
    _install(monkeypatch, client)

    result = await VisualSearchAIProvider().analyze_fashion_image(PNG_DATA_URL)

    assert result["analysis_available"] is True
    assert result["detected_category"] == "Tops"
    assert result["analysis_source"] == "nvidia:moonshotai/kimi-k3"
    assert client.calls[0]["user"] == VisualSearchAIProvider.VISION_PROMPT


@pytest.mark.asyncio
async def test_non_garment_null_category_is_preserved_not_invented(monkeypatch):
    """A null detection is a RESULT, not a failure — it must survive the tier.

    ``wardrobe_service`` turns ``category=None`` into "no clothing item
    detected". If this tier treated null as "unusable" and fell through, a
    colour swatch could reach a weaker downstream tier and be mis-tagged.
    """
    monkeypatch.setattr("backend.app.core.config.settings.GEMINI_API_KEY", "", raising=False)
    client = _FakeClient(result={"category": None, "confidence": 0.0, "_model_id": "x"})
    _install(monkeypatch, client)

    result = await VisualSearchAIProvider().analyze_wardrobe_image(PNG_DATA_URL)

    assert result["analysis_available"] is True
    assert result["category"] is None


@pytest.mark.asyncio
async def test_payload_missing_the_decision_key_is_rejected(monkeypatch):
    """A 200 with the wrong shape is not an answer. Degrade honestly."""
    monkeypatch.setattr("backend.app.core.config.settings.GEMINI_API_KEY", "", raising=False)
    _install(monkeypatch, _FakeClient(result={"colour": "navy", "_model_id": "x"}))

    result = await VisualSearchAIProvider().analyze_wardrobe_image(PNG_DATA_URL)

    assert result["analysis_available"] is False
    assert result["category"] is None


@pytest.mark.asyncio
async def test_provider_error_degrades_honestly_and_never_fabricates(monkeypatch):
    monkeypatch.setattr("backend.app.core.config.settings.GEMINI_API_KEY", "", raising=False)
    _install(monkeypatch, _FakeClient(
        error=NvidiaCapacityError("all pooled keys exhausted", model_id="m")))

    result = await VisualSearchAIProvider().analyze_wardrobe_image(PNG_DATA_URL)

    assert result["analysis_available"] is False
    assert result["detected_category"] is None
    assert result["category"] is None


@pytest.mark.asyncio
async def test_tier_is_skipped_when_no_nvidia_credentials(monkeypatch):
    monkeypatch.setattr("backend.app.core.config.settings.GEMINI_API_KEY", "", raising=False)
    client = _FakeClient(configured=False, result=WARDROBE_PAYLOAD)
    _install(monkeypatch, client)

    result = await VisualSearchAIProvider().analyze_wardrobe_image(PNG_DATA_URL)

    assert result["analysis_available"] is False
    assert client.calls == []  # never dialled without credentials


@pytest.mark.asyncio
async def test_gemini_still_wins_when_configured(monkeypatch):
    """The new tier is a FALLBACK. It must not steal traffic from the primary."""
    monkeypatch.setattr("backend.app.core.config.settings.GEMINI_API_KEY", "k", raising=False)
    client = _FakeClient(result=WARDROBE_PAYLOAD)
    _install(monkeypatch, client)

    async def _gemini(image_url_or_base64, prompt):
        return {"category": "Tops", "analysis_available": True, "analysis_source": "gemini"}

    provider = VisualSearchAIProvider()
    monkeypatch.setattr(provider, "_call_gemini_vision", _gemini)

    result = await provider.analyze_wardrobe_image(PNG_DATA_URL)

    assert result["analysis_source"] == "gemini"
    assert client.calls == []
