"""Tests for the Qwen2.5-VL local vision fallback (lightweight client + routing).

Covers the client contract, the failure taxonomy, and the Gemini -> Qwen ->
honest-degradation wiring in VisualSearchAIProvider (matching the CURRENT main
provider API: analyze_fashion_image / analyze_wardrobe_image -> fallback()),
WITHOUT any GPU / model / network (the worker is mocked at the transport level).

Run:  pytest backend/tests/test_qwen_vision.py -q --noconftest
(needs pydantic-settings + fastapi + httpx; no torch)
"""
from __future__ import annotations

import asyncio
import sys
from types import ModuleType, SimpleNamespace
from typing import Any, Dict

import httpx
import pytest

from backend.app.providers.qwen_vision import QwenVisionError, QwenVisionProvider
from backend.app.providers.tryon_provider import VisualSearchAIProvider

_TINY_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
_B64 = "data:image/png;base64," + _TINY_PNG
_PROMPT = "Return STRICT JSON with detected_category, detected_color."
_IMG = "https://cdn.example.com/product.jpg"


def _settings(**over: Any) -> SimpleNamespace:
    base = {
        "QWEN_VL_ENABLED": True,
        "QWEN_VL_WORKER_URL": "http://127.0.0.1:9499",
        "QWEN_VL_WORKER_TOKEN": "tok-secret",
        "QWEN_VL_MODEL_ID": "Qwen/Qwen2.5-VL-7B-Instruct",
        "QWEN_VL_TIMEOUT_SECONDS": 2.0,
        "GEMINI_API_KEY": "unused-in-tests",
        "VISION_MODEL": "gemini-flash",
    }
    base.update(over)
    return SimpleNamespace(**base)


@pytest.fixture
def monkey_settings(monkeypatch):
    def _set(**over: Any) -> None:
        monkeypatch.setattr(
            "backend.app.providers.qwen_vision.provider.settings", _settings(**over)
        )
        monkeypatch.setenv("QWEN_VL_WORKER_TOKEN", over.get("QWEN_VL_WORKER_TOKEN", "tok-secret"))
        monkeypatch.setattr(
            "backend.app.providers.tryon_provider.settings", _settings(**over)
        )
    return _set


# ---------------------------------------------------------------------------
# QwenVisionProvider (lightweight client)
# ---------------------------------------------------------------------------

def test_not_configured_when_url_missing(monkey_settings):
    monkey_settings(QWEN_VL_WORKER_URL="")
    assert QwenVisionProvider().is_configured() is False

def test_not_configured_when_disabled(monkey_settings):
    monkey_settings(QWEN_VL_ENABLED=False)
    assert QwenVisionProvider().is_configured() is False

def test_configured_when_url_set(monkey_settings):
    monkey_settings()
    assert QwenVisionProvider().is_configured() is True


def test_analyze_returns_gemini_contract(monkey_settings, monkeypatch):
    monkey_settings()
    sent: Dict[str, Any] = {}

    async def handler(*args, **kwargs) -> httpx.Response:
        url = next((a for a in args if isinstance(a, str)), "")
        headers = kwargs.get("headers") or {}
        sent["url"] = url
        sent["auth"] = headers.get("X-VLM-Admin")
        sent["body"] = kwargs.get("json") or {}
        return httpx.Response(200, json={
            "analysis_available": True,
            "detected_category": "Tops",
            "detected_color": "black",
            "detected_style": "Casual",
        })

    monkeypatch.setattr(httpx.AsyncClient, "post", handler)
    out = asyncio.run(QwenVisionProvider().analyze(_B64, _PROMPT, mode="visual_search"))
    assert out["analysis_available"] is True
    assert out["analysis_source"] == "Qwen/Qwen2.5-VL-7B-Instruct"
    assert out["detected_category"] == "Tops"
    assert sent["url"].endswith("/analyze")
    assert sent["auth"] == "tok-secret"
    assert sent["body"]["mode"] == "visual_search"
    assert sent["body"]["image"].startswith("data:image/png;base64,")


def test_analyze_raises_not_configured(monkey_settings):
    monkey_settings(QWEN_VL_WORKER_URL="")
    with pytest.raises(QwenVisionError) as ei:
        asyncio.run(QwenVisionProvider().analyze(_B64, _PROMPT))
    assert ei.value.reason == "not_configured"


def test_analyze_timeout_maps_to_timeout(monkey_settings, monkeypatch):
    monkey_settings(QWEN_VL_TIMEOUT_SECONDS=0.05)

    async def handler(*args, **kwargs) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(httpx.AsyncClient, "post", handler)
    with pytest.raises(QwenVisionError) as ei:
        asyncio.run(QwenVisionProvider().analyze(_B64, _PROMPT))
    assert ei.value.reason == "timeout"


def test_analyze_503_maps_to_worker_not_ready(monkey_settings, monkeypatch):
    monkey_settings()

    async def handler(*args, **kwargs) -> httpx.Response:
        return httpx.Response(503, json={"error": {"code": "VLM_NOT_READY", "message": "model not loaded"}})

    monkeypatch.setattr(httpx.AsyncClient, "post", handler)
    with pytest.raises(QwenVisionError) as ei:
        asyncio.run(QwenVisionProvider().analyze(_B64, _PROMPT))
    assert ei.value.reason == "worker_not_ready"
    assert ei.value.http_status == 503


def test_analyze_401_maps_to_auth(monkey_settings, monkeypatch):
    monkey_settings()

    async def handler(*args, **kwargs) -> httpx.Response:
        return httpx.Response(401, json={"error": {"code": "UNAUTHORIZED", "message": "invalid token"}})

    monkeypatch.setattr(httpx.AsyncClient, "post", handler)
    with pytest.raises(QwenVisionError) as ei:
        asyncio.run(QwenVisionProvider().analyze(_B64, _PROMPT))
    assert ei.value.reason == "auth"


def test_analyze_oom_maps_to_worker_error(monkey_settings, monkeypatch):
    monkey_settings()

    async def handler(*args, **kwargs) -> httpx.Response:
        return httpx.Response(500, json={"error": {"code": "GPU_OOM", "message": "out of memory"}})

    monkeypatch.setattr(httpx.AsyncClient, "post", handler)
    with pytest.raises(QwenVisionError) as ei:
        asyncio.run(QwenVisionProvider().analyze(_B64, _PROMPT))
    assert ei.value.reason == "worker_error"
    assert "GPU_OOM" in ei.value.message


def test_analyze_bad_input(monkey_settings):
    monkey_settings()
    with pytest.raises(QwenVisionError) as ei:
        asyncio.run(QwenVisionProvider().analyze("", _PROMPT))
    assert ei.value.reason == "bad_input"
    with pytest.raises(QwenVisionError) as ei:
        asyncio.run(QwenVisionProvider().analyze(_B64, "   "))
    assert ei.value.reason == "bad_input"


# ---------------------------------------------------------------------------
# VisualSearchAIProvider.fallback wiring (Gemini primary -> Qwen -> honest)
# ---------------------------------------------------------------------------

def _fallback(monkey_settings, **over: Any):
    monkey_settings(**over)
    return asyncio.run(VisualSearchAIProvider().fallback(_IMG))


def test_fallback_not_configured_returns_honest_unavailable(monkey_settings):
    out = _fallback(monkey_settings, QWEN_VL_WORKER_URL="")
    assert out["analysis_available"] is False
    assert out["detected_category"] is None


def test_fallback_qwen_success(monkey_settings, monkeypatch):
    async def _ok(self, img, prompt, mode=None):
        return {
            "analysis_available": True,
            "analysis_source": "Qwen/Qwen2.5-VL-7B-Instruct",
            "detected_category": "Tops",
            "detected_color": "white",
            "detected_style": "Casual",
            "detected_attributes": {},
        }

    monkeypatch.setattr(QwenVisionProvider, "analyze", _ok)
    out = _fallback(monkey_settings)
    assert out["analysis_available"] is True
    assert out["analysis_source"] == "Qwen/Qwen2.5-VL-7B-Instruct"
    assert out["detected_color"] == "white"


def test_fallback_worker_unusable_returns_honest(monkey_settings, monkeypatch):
    async def unusable(self, img, prompt, mode=None):
        return {"analysis_available": False, "analysis_source": "Qwen/Qwen2.5-VL-7B-Instruct", "error": "output_invalid"}

    monkeypatch.setattr(QwenVisionProvider, "analyze", unusable)
    out = _fallback(monkey_settings)
    assert out["analysis_available"] is False
    assert out["detected_category"] is None


def test_fallback_qwen_error_degrades_honest(monkey_settings, monkeypatch):
    def boom(self, img, prompt, mode=None):
        raise QwenVisionError("worker_unavailable", "conn refused")

    monkeypatch.setattr(QwenVisionProvider, "analyze", boom)
    out = _fallback(monkey_settings)
    assert out["analysis_available"] is False


def test_analyze_fashion_image_forwards_prompt_to_fallback(monkey_settings, monkeypatch):
    """Regression: on Gemini failure, the fashion path must route to fallback
    WITH the vision prompt (so a local Qwen fallback asks for the same keys)."""
    captured: Dict[str, Any] = {}

    async def capture_fallback(self, image_url_or_base64: str, **kwargs):
        captured["prompt"] = kwargs.get("prompt")
        return {"analysis_available": False}

    # Force the Gemini path to fail (no GEMINI key) so execute_with_resilience
    # routes to fallback, and capture the prompt it forwards.
    monkey_settings(GEMINI_API_KEY="")
    monkeypatch.setattr(VisualSearchAIProvider, "fallback", capture_fallback)
    out = asyncio.run(VisualSearchAIProvider().analyze_fashion_image(_B64))
    assert out["analysis_available"] is False
    assert captured.get("prompt") == VisualSearchAIProvider.VISION_PROMPT


# ---------------------------------------------------------------------------
# QwenVisionProvider — remote (Modal Function .remote()) transport
# ---------------------------------------------------------------------------

def _fake_modal(remote_result):
    """Minimal fake `modal` module: Function.from_name(...).remote() returns
    `remote_result`, recording the (app, fn, args) it was called with."""
    fake = ModuleType("modal")
    calls: Dict[str, Any] = {}

    class _Fn:
        def remote(self, b64, mime, prompt, mode):
            calls["args"] = (b64, mime, prompt, mode)
            return remote_result

    class _Function:
        @staticmethod
        def from_name(app, name):
            calls["app"] = app
            calls["fn"] = name
            return _Fn()

    fake.Function = _Function
    fake._calls = calls
    return fake


def test_remote_not_configured_without_creds(monkey_settings, monkeypatch):
    monkey_settings(QWEN_VL_TRANSPORT="remote")
    monkeypatch.delenv("MODAL_TOKEN_ID", raising=False)
    monkeypatch.delenv("MODAL_TOKEN_SECRET", raising=False)
    assert QwenVisionProvider().is_configured() is False


def test_remote_is_configured_with_creds(monkey_settings, monkeypatch):
    monkey_settings(QWEN_VL_TRANSPORT="remote")
    monkeypatch.setenv("MODAL_TOKEN_ID", "ak-test")
    monkeypatch.setenv("MODAL_TOKEN_SECRET", "as-test")
    assert QwenVisionProvider().is_configured() is True


def test_remote_analyze_success(monkey_settings, monkeypatch):
    monkey_settings(QWEN_VL_TRANSPORT="remote",
                    QWEN_VL_REMOTE_APP="confit-vlm-worker", QWEN_VL_REMOTE_FN="vlm_analyze")
    monkeypatch.setenv("MODAL_TOKEN_ID", "ak-test")
    monkeypatch.setenv("MODAL_TOKEN_SECRET", "as-test")
    fake = _fake_modal({
        "analysis_available": True,
        "analysis_source": "Qwen/Qwen2.5-VL-7B-Instruct",
        "detected_category": "Tops",
        "detected_color": "black",
    })
    monkeypatch.setitem(sys.modules, "modal", fake)
    out = asyncio.run(QwenVisionProvider().analyze(_B64, _PROMPT, mode="visual_search"))
    assert out["analysis_available"] is True
    assert out["detected_category"] == "Tops"
    assert fake._calls["app"] == "confit-vlm-worker"
    assert fake._calls["fn"] == "vlm_analyze"
    b64, mime, prompt, mode = fake._calls["args"]
    assert mime == "image/png"
    assert b64 == _TINY_PNG  # raw base64 (data URL prefix stripped)
    assert mode == "visual_search"


def test_remote_not_ready_maps_to_worker_not_ready(monkey_settings, monkeypatch):
    monkey_settings(QWEN_VL_TRANSPORT="remote")
    monkeypatch.setenv("MODAL_TOKEN_ID", "ak-test")
    monkeypatch.setenv("MODAL_TOKEN_SECRET", "as-test")
    monkeypatch.setitem(sys.modules, "modal", _fake_modal(
        {"analysis_available": False, "error": "VLM_NOT_READY", "detail": "model not loaded"}))
    with pytest.raises(QwenVisionError) as ei:
        asyncio.run(QwenVisionProvider().analyze(_B64, _PROMPT))
    assert ei.value.reason == "worker_not_ready"


def test_image_ref_data_url(monkey_settings):
    b64, mime = QwenVisionProvider._image_ref_to_base64_mime(_B64)
    assert b64 == _TINY_PNG
    assert mime == "image/png"


def test_image_ref_ssrf_guard(monkey_settings):
    with pytest.raises(QwenVisionError) as ei:
        QwenVisionProvider._image_ref_to_base64_mime("http://127.0.0.1/product.jpg")
    assert ei.value.reason == "bad_input"


# ---------------------------------------------------------------------------
# Wardrobe non-garment gate (regression for the color-swatch false positive)
# ---------------------------------------------------------------------------

def test_wardrobe_non_garment_not_treated_as_valid(monkey_settings, monkeypatch):
    """REGRESSION: a wardrobe analysis whose category is null -- the model's honest
    'not a garment' signal (now returned for plain color swatches by the
    restructured WARDROBE_TAG_PROMPT) -- must be rejected as 'No clothing item
    detected' and NEVER surfaced/persisted as a valid wardrobe item.

    Before the fix the weaker Qwen model completed the rich schema and returned
    category='Tops'/'Sweater' on a solid color block, which the service then
    accepted as a real item.
    """
    from backend.app.services.wardrobe_service import WardrobeService

    non_garment = {
        "analysis_available": True,
        "analysis_source": "Qwen/Qwen2.5-VL-7B-Instruct",
        "category": None,
        "item_type": None,
        "confidence": 0.0,
    }

    async def fake_analyze_wardrobe(self, image_ref):
        return non_garment

    monkeypatch.setattr(
        "backend.app.providers.tryon_provider.VisualSearchAIProvider.analyze_wardrobe_image",
        fake_analyze_wardrobe,
    )
    svc = WardrobeService(db=None)  # auto_tag_image does not touch the DB
    out = asyncio.run(svc.auto_tag_image(image_url="data:image/png;base64,AAAA", image_base64="AAAA"))
    assert out["analysis_available"] is False
    assert "No clothing item detected" in out["detail"]
    assert "detected_category" not in out


def test_wardrobe_real_garment_still_tagged(monkey_settings, monkeypatch):
    """Positive control: the non-garment gate must not over-reject. A genuine
    garment (category present) is still normalized + returned as available."""
    from backend.app.services.wardrobe_service import WardrobeService

    garment = {
        "analysis_available": True,
        "analysis_source": "Qwen/Qwen2.5-VL-7B-Instruct",
        "category": "Outerwear",
        "item_type": "Blazer",
        "primary_color": "Blue",
        "primary_color_hex": "#1B3A5B",
        "secondary_colors": ["White"],
        "style": "Formal",
        "style_tags": ["Tailored"],
        "pattern": "Checked",
        "occasion_suitability": ["Business Formal"],
        "seasonality": "All-Season",
        "confidence": 1.0,
    }

    async def fake_analyze_wardrobe(self, image_ref):
        return garment

    monkeypatch.setattr(
        "backend.app.providers.tryon_provider.VisualSearchAIProvider.analyze_wardrobe_image",
        fake_analyze_wardrobe,
    )
    svc = WardrobeService(db=None)
    out = asyncio.run(svc.auto_tag_image(image_url="data:image/png;base64,AAAA", image_base64="AAAA"))
    assert out["analysis_available"] is True
    assert out["detected_category"] == "Outerwear"
    assert out["detected_subcategory"] == "Blazer"
