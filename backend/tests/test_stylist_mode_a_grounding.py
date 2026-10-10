"""StyleList Mode A (multi-image styling) — FR-001/003/006, SC-001, STY-01/05/07.

Contract under test
-------------------
* ``images[]`` is accepted on the stylist request, validated at the boundary, and
  derives ``mode`` (A with images, B without).
* A Mode A answer is grounded in the real catalogue: every recommended item is a
  real product with a currency, and the response reports the mode that ACTUALLY
  ran plus the vision engine that answered.
* When vision is unavailable the turn is answered as Mode B, with the reason
  shown; nothing is invented from the image.
* Image bytes are never written to the database (FR-008 / SC-005).

Vision is stubbed at the service seam for the end-to-end cases so the suite makes
no paid call. The vision parser itself is exercised separately below against a
recorded-shape provider response.
"""
from __future__ import annotations

import base64
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text

from backend.app.core.config import settings
from backend.app.schemas.stylist import StylistPromptRequest
from backend.app.services import stylist_service as stylist_service_module
from backend.app.services.stylist_image_intake import (
    STYLIST_IMAGE_MAX_BYTES,
    STYLIST_MAX_IMAGES,
    ImageIntakeError,
    parse_image_data_url,
)
from backend.app.services.stylist_vision import GarmentObservation, VisionAnalysis
from backend.tests.conftest import TestingSessionLocal


def _png_data_url(colour=(27, 31, 59), size=(64, 64)) -> str:
    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _jpeg_data_url(colour=(200, 30, 40)) -> str:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), colour).save(buf, format="JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


@pytest.fixture
def no_text_provider(monkeypatch):
    """Keep the text leg deterministic: no provider call, grounded fallback prose."""
    monkeypatch.setattr(settings, "AI_PROVIDERS", "none")


@pytest.fixture
def vision_available(monkeypatch):
    async def fake(images, shopper_request):
        return VisionAnalysis(
            available=True,
            engine="NVIDIA nvidia/nemotron-3-test-vision",
            summary="A navy blazer over a white shirt.",
            garments=[
                GarmentObservation(category="outerwear", description="navy blazer", color_family="navy"),
                GarmentObservation(category="top", description="white shirt", color_family="white"),
            ],
        )

    monkeypatch.setattr(stylist_service_module, "analyze_images", fake)
    return fake


@pytest.fixture
def vision_unavailable(monkeypatch):
    async def fake(images, shopper_request):
        return VisionAnalysis(
            available=False,
            reason="The image analysis service did not answer, so this reply uses your text request only.",
        )

    monkeypatch.setattr(stylist_service_module, "analyze_images", fake)


def _catalog_product_ids() -> set:
    db = TestingSessionLocal()
    try:
        return {row[0] for row in db.execute(text("select id from products")).all()}
    finally:
        db.close()


# ─────────────────────────── schema & mode derivation ───────────────────────────

class TestRequestSchema:
    def test_text_only_request_is_mode_b(self):
        req = StylistPromptRequest(prompt="smart casual dinner")
        assert req.images == []
        assert req.mode == "B"

    def test_one_valid_image_is_mode_a(self):
        req = StylistPromptRequest(prompt="what goes with this?", images=[_png_data_url()])
        assert req.mode == "A"

    def test_up_to_three_images_are_accepted(self):
        req = StylistPromptRequest(prompt="x", images=[_png_data_url(), _jpeg_data_url(), _png_data_url((1, 2, 3))])
        assert len(req.images) == STYLIST_MAX_IMAGES

    def test_more_than_three_images_is_refused(self):
        with pytest.raises(ValueError):
            StylistPromptRequest(prompt="x", images=[_png_data_url()] * (STYLIST_MAX_IMAGES + 1))

    def test_unsupported_mime_is_refused(self):
        gif = "data:image/gif;base64," + base64.b64encode(b"GIF89a" + b"\x00" * 20).decode()
        with pytest.raises(ValueError):
            StylistPromptRequest(prompt="x", images=[gif])

    def test_spoofed_bytes_are_refused_even_with_a_valid_mime(self):
        spoof = "data:image/png;base64," + base64.b64encode(b"not really a png at all").decode()
        with pytest.raises(ValueError):
            StylistPromptRequest(prompt="x", images=[spoof])

    def test_oversized_image_is_refused(self):
        big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (STYLIST_IMAGE_MAX_BYTES + 10)
        url = "data:image/png;base64," + base64.b64encode(big).decode()
        with pytest.raises(ValueError):
            StylistPromptRequest(prompt="x", images=[url])

    def test_non_base64_payload_is_refused(self):
        with pytest.raises(ImageIntakeError):
            parse_image_data_url("data:image/png;base64,@@@not-base64@@@")

    def test_remote_urls_are_not_accepted_as_images(self):
        # A URL would make the server fetch an arbitrary address (SSRF surface).
        with pytest.raises(ValueError):
            StylistPromptRequest(prompt="x", images=["https://example.com/a.png"])


# ─────────────────────────────── HTTP contract ───────────────────────────────────

class TestModeAEndToEnd:
    def test_mode_a_returns_grounded_catalogue_items_with_currency(
        self, client: TestClient, no_text_provider, vision_available
    ):
        res = client.post("/api/v1/stylist/chat", json={
            "prompt": "Put together a look around this blazer",
            "images": [_png_data_url((27, 31, 59))],
        })
        assert res.status_code == 200, res.text
        data = res.json()

        assert data["mode"] == "A"
        assert data["fallback_reason"] is None
        assert data["image_analysis"]["available"] is True
        assert data["image_analysis"]["engine"] == "NVIDIA nvidia/nemotron-3-test-vision"
        assert data["recommendations"], "a Mode A turn with a catalogue must recommend looks"

        real_ids = _catalog_product_ids()
        for outfit in data["recommendations"]:
            assert outfit["items"], "no empty looks"
            for item in outfit["items"]:
                assert item["product_id"] in real_ids, "every item must be a real catalogue product"
                assert item["currency"], "every item carries its real currency (STY-13)"

    def test_mode_a_colour_coordination_is_attached_to_each_look(
        self, client: TestClient, no_text_provider, vision_available
    ):
        res = client.post("/api/v1/stylist/chat", json={
            "prompt": "match these colours", "images": [_png_data_url((27, 31, 59))],
        })
        data = res.json()
        for outfit in data["recommendations"]:
            coord = outfit.get("color_coordination")
            assert coord is not None, "Mode A looks report colour coordination"
            assert isinstance(coord["score"], int)
            assert coord["method"].startswith("ColorHarmonyEngine")

    def test_unavailable_vision_falls_back_to_mode_b_with_reason(
        self, client: TestClient, no_text_provider, vision_unavailable
    ):
        res = client.post("/api/v1/stylist/chat", json={
            "prompt": "a smart casual dinner look", "images": [_png_data_url()],
        })
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["mode"] == "B"
        assert data["fallback_reason"], "the shopper is told why images were not used"
        assert data["image_analysis"]["available"] is False
        # Fallback is still grounded, never fabricated.
        real_ids = _catalog_product_ids()
        for outfit in data["recommendations"]:
            for item in outfit["items"]:
                assert item["product_id"] in real_ids

    def test_text_only_turn_is_unchanged_mode_b(self, client: TestClient, no_text_provider):
        res = client.post("/api/v1/stylist/chat", json={"prompt": "formal wedding outfit under 500"})
        assert res.status_code == 200
        data = res.json()
        assert data["mode"] == "B"
        assert data["image_analysis"] is None
        assert data["fallback_reason"] is None

    def test_undecodable_image_is_refused_before_anything_is_persisted(
        self, client: TestClient, no_text_provider
    ):
        # Valid MIME and magic bytes, but not a decodable picture.
        bogus = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32).decode()
        before = _message_count()
        res = client.post("/api/v1/stylist/chat", json={"prompt": "look", "images": [bogus]})
        assert res.status_code == 422
        assert _message_count() == before, "a refused image must leave no transcript row"


# ─────────────────────────────── privacy (FR-008) ────────────────────────────────

def _message_count() -> int:
    db = TestingSessionLocal()
    try:
        return db.execute(text("select count(*) from stylist_messages")).scalar()
    finally:
        db.close()


def test_image_bytes_are_never_persisted(client: TestClient, no_text_provider, vision_available):
    marker = _png_data_url((9, 200, 9))
    res = client.post("/api/v1/stylist/chat", json={"prompt": "look", "images": [marker]})
    assert res.status_code == 200, res.text
    payload = marker.split(",", 1)[1]

    db = TestingSessionLocal()
    try:
        rows = db.execute(text("select content, intent_json, recommendations_json from stylist_messages")).all()
    finally:
        db.close()
    blob = json.dumps([list(r) for r in rows])
    assert "data:image" not in blob
    assert payload[:60] not in blob, "no fragment of the base64 payload may reach the database"


# ─────────────────────────── vision parser (provider seam) ───────────────────────

class _FakeHTTPResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class _VisionHTTP:
    """Records the vision request and answers as the NVIDIA endpoint would."""

    def __init__(self, status_code=200, content=None, model="nvidia/nemotron-3-super-120b-a12b"):
        self.calls = []
        self._status = status_code
        self._content = content
        self._model = model

    def __call__(self, *args, **kwargs):
        outer = self

        class _Client:
            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, *exc):
                return False

            async def post(self_inner, url, headers=None, json=None):
                outer.calls.append({"url": url, "payload": json})
                if outer._status != 200:
                    return _FakeHTTPResponse(outer._status, {"error": "boom"})
                return _FakeHTTPResponse(200, {
                    "model": outer._model,
                    "choices": [{"message": {"content": outer._content}, "finish_reason": "stop"}],
                })

        return _Client()


@pytest.fixture
def vision_nvidia_key(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-not-a-real-key")
    monkeypatch.setattr(settings, "NVIDIA_API_KEY", "nvapi-test-not-a-real-key", raising=False)
    from backend.app.providers.nvidia import key_pool
    key_pool.reload()
    yield
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setattr(settings, "NVIDIA_API_KEY", None, raising=False)
    key_pool.reload()


@pytest.mark.asyncio
async def test_vision_parser_reads_recorded_model_answer(monkeypatch, vision_nvidia_key):
    from unittest.mock import patch
    from backend.app.services.stylist_image_intake import parse_image_data_url
    from backend.app.services.stylist_vision import analyze_images

    answer = json.dumps({
        "garments": [
            {"category": "top", "description": "white shirt", "color_family": "White"},
            {"category": "shoes", "description": "boots", "color_family": "brown"},  # not a category
            {"category": "bottom", "description": "chinos", "color_family": "beige"},
        ],
        "summary": "A smart casual look.",
    })
    http = _VisionHTTP(content=answer, model="nvidia/nemotron-3-test-vision")
    img = parse_image_data_url(_png_data_url())
    with patch("backend.app.providers.nvidia.client.httpx.AsyncClient", http):
        result = await analyze_images([img], "smart casual")

    assert result.available is True
    assert result.engine == "NVIDIA nvidia/nemotron-3-test-vision", "reports the model that served"
    cats = [g.category for g in result.garments]
    assert cats == ["top", "bottom"], "unknown categories are dropped, not guessed"
    assert result.garments[0].color_family == "white"
    # The request carried the image as an image_url content part.
    content = http.calls[0]["payload"]["messages"][-1]["content"]
    assert any(part.get("type") == "image_url" for part in content)


@pytest.mark.asyncio
async def test_vision_total_failure_is_honest_unavailable(monkeypatch, vision_nvidia_key):
    from unittest.mock import patch
    from backend.app.services.stylist_image_intake import parse_image_data_url
    from backend.app.services.stylist_vision import analyze_images

    http = _VisionHTTP(status_code=503)
    img = parse_image_data_url(_png_data_url())
    with patch("backend.app.providers.nvidia.client.httpx.AsyncClient", http):
        result = await analyze_images([img], "smart casual")
    assert result.available is False
    assert result.garments == []
    assert result.reason


@pytest.mark.asyncio
async def test_vision_disabled_by_flag_never_calls_a_provider(monkeypatch, vision_nvidia_key):
    from unittest.mock import patch
    from backend.app.services.stylist_image_intake import parse_image_data_url
    from backend.app.services.stylist_vision import analyze_images

    monkeypatch.setattr(settings, "STYLIST_VISION_ENABLED", False)
    http = _VisionHTTP(content="{}")
    img = parse_image_data_url(_png_data_url())
    with patch("backend.app.providers.nvidia.client.httpx.AsyncClient", http):
        result = await analyze_images([img], "x")
    assert result.available is False
    assert http.calls == [], "a disabled feature must not spend a provider call"
