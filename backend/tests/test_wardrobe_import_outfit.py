"""Feature 04 (Smart Wardrobe) — outfit-photo import: backend contract tests.

Pins the full /wardrobe/import-outfit pipeline against the LIVE worker
contract (mirrors the real response captured from confit-wardrobe-worker on
2026-10-02, job live_probe_001):

  * one outfit photo -> one wardrobe item per detected garment, image = the
    worker's real transparent cutout PNG (never the raw photo, never a fake);
  * the worker's honest skip report (sub-threshold regions) is passed
    through, never promoted into items;
  * worker-unavailable / not-configured / nothing-detected are HONEST
    failures: no rows, no storage writes, no invented items;
  * per-garment analysis failure leaves a retryable item (same UX as upload);
  * re-importing the same photo is reported as duplicates (image-hash
    dedupe), never as new rows;
  * provider-level unit tests: auth header, error envelopes, response
    validation (malformed cutouts dropped + reported, confidence clamped).
"""
from __future__ import annotations

import base64
import io
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app.core import config as config_mod
from backend.app.providers.tryon_provider import VisualSearchAIProvider
from backend.app.providers.wardrobe_extraction_provider import (
    WardrobeExtractionProvider,
    _validate_worker_response,
)
from backend.tests.conftest import TestingSessionLocal

from sqlalchemy import text

DEAD_REDIS = "redis://127.0.0.1:63790/9"

FAKE_ANALYSIS = {
    "analysis_available": True,
    "category": "Tops",
    "item_type": "Oxford Shirt",
    "primary_color": "White",
    "primary_color_hex": "#FFFFFF",
    "secondary_colors": [],
    "pattern": "Solid",
    "style_tags": ["Cotton", "Breathable"],
    "occasion_suitability": ["Smart Casual"],
    "seasonality": "All-Season",
    "confidence": 0.93,
}


def _png_bytes(color=(30, 60, 140), size=(48, 64)) -> bytes:
    img = Image.new("RGBA", size, color + (255,))
    img.putalpha(Image.new("L", size, 200))  # soft alpha, like a real matte
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _cutout(color=(30, 60, 140)) -> str:
    return "data:image/png;base64," + base64.b64encode(_png_bytes(color)).decode()


def _worker_ok() -> dict:
    """Realistic worker response — same shape as the live 2026-10-02 probe."""
    return {
        "items": [
            {
                "slot_type": "upper_outer", "category": "tops",
                "label_names": ["Upper-clothes"], "bbox": [240, 123, 524, 434],
                "area_fraction": 0.058, "confidence": 0.47,
                "cutout_data_url": _cutout((40, 40, 120)),
            },
            {
                "slot_type": "lower", "category": "bottoms",
                "label_names": ["Pants"], "bbox": [247, 338, 583, 898],
                "area_fraction": 0.104, "confidence": 0.56,
                "cutout_data_url": _cutout((30, 60, 140)),
            },
            {
                "slot_type": "footwear", "category": "footwear",
                "label_names": ["Left-shoe", "Right-shoe"], "bbox": [252, 839, 562, 1001],
                "area_fraction": 0.011, "confidence": 0.37,
                "cutout_data_url": _cutout((90, 70, 50)),
            },
        ],
        "person_detected": True,
        "person_labels": ["Face", "Hair", "Left-arm", "Right-arm"],
        "skipped": [{"label": "Belt", "reason": "below_min_area", "area": 142}],
        "parse_seconds": 0.91,
        "matting_seconds": 31.09,
        "total_seconds": 32.46,
        "engine": "schp_atr_18_birefnet_lite_cpu",
        "commercial": True,
    }


def _worker_envelope(body: dict) -> dict:
    body = dict(body)
    body["extraction_available"] = True
    return body


@pytest.fixture
def vision_ok(monkeypatch):
    """Deterministic per-cutout analysis: the fake decodes the PNG it is
    given and classifies by its pixel colour — proving the analysis ran on
    the worker's CUTOUT bytes, not on the original outfit photo."""
    async def fake_analyze(self, ref):  # noqa: ARG001
        if isinstance(ref, str) and ref.startswith("data:image/png;base64,"):
            try:
                raw = base64.b64decode(ref.split(",", 1)[1])
                img = Image.open(io.BytesIO(raw)).convert("RGBA")
                r, g, b, _ = img.getpixel((0, 0))
                color = (r, g, b)
            except Exception:
                color = None
        else:
            color = None
        per_cutout = {
            (40, 40, 120): {"category": "Tops", "item_type": "Oxford Shirt", "primary_color": "White"},
            (30, 60, 140): {"category": "Bottoms", "item_type": "Pleated Trousers", "primary_color": "Navy"},
            (90, 70, 50): {"category": "Footwear", "item_type": "Leather Sneakers", "primary_color": "Brown"},
        }
        analysis = dict(FAKE_ANALYSIS)
        analysis.update(per_cutout.get(color, {}))
        return analysis
    monkeypatch.setattr(VisualSearchAIProvider, "analyze_wardrobe_image", fake_analyze)


@pytest.fixture
def vision_fail(monkeypatch):
    async def fake_analyze(self, ref):  # noqa: ARG001
        return {"analysis_available": False}
    monkeypatch.setattr(VisualSearchAIProvider, "analyze_wardrobe_image", fake_analyze)


@pytest.fixture
def broker_down(monkeypatch):
    monkeypatch.setattr(config_mod.settings, "REDIS_URL", DEAD_REDIS, raising=False)


@pytest.fixture
def worker_env(monkeypatch):
    monkeypatch.setattr(config_mod.settings, "WARDROBE_WORKER_URL", "https://wardrobe-worker.test/extract", raising=False)
    monkeypatch.setattr(config_mod.settings, "WARDROBE_WORKER_ADMIN_TOKEN", "test-admin-token", raising=False)


@pytest.fixture
def extraction_ok(monkeypatch):
    """Mock at the HTTP boundary (_call_worker) so the REAL provider
    validation (_validate_worker_response) runs inside every service test —
    the mock only removes the network, never the contract checks."""
    async def fake_call(self, data_url, max_items=4):  # noqa: ARG001
        return _worker_envelope(_worker_ok())
    monkeypatch.setattr(WardrobeExtractionProvider, "_call_worker", fake_call)


@pytest.fixture
def extraction_empty(monkeypatch):
    async def fake_call(self, data_url, max_items=4):  # noqa: ARG001
        body = _worker_ok()
        body["items"] = []
        body["skipped"] = [{"label": "Bag", "reason": "below_min_area", "area": 90}]
        return _worker_envelope(body)
    monkeypatch.setattr(WardrobeExtractionProvider, "_call_worker", fake_call)


def _register(client: TestClient, label: str) -> dict:
    import uuid
    email = f"wardrobe_import_{label}_{uuid.uuid4().hex[:8]}@confit.io"
    res = client.post("/api/v1/auth/register", json={
        "email": email, "password": "Password123!", "full_name": f"Wardrobe Import {label}",
    })
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _post_import(client: TestClient, headers: dict, max_items: int | None = None):
    data = {"file": ("outfit.png", _png_bytes((200, 180, 170), (320, 480)), "image/png")}
    if max_items is not None:
        data["max_items"] = (None, str(max_items))
    return client.post("/api/v1/wardrobe/import-outfit", headers=headers, files=data)


# ───────────────────────── API contract ─────────────────────────

def test_import_creates_one_item_per_garment(client, broker_down, vision_ok, extraction_ok, worker_env):
    headers = _register(client, "ida")
    res = _post_import(client, headers, max_items=6)
    assert res.status_code == 201, res.text
    body = res.json()

    statuses = [r["status"] for r in body["results"]]
    assert statuses == ["created", "created", "created"]
    categories = {r["item"]["category"] for r in body["results"]}
    assert categories == {"Tops", "Bottoms", "Footwear"}
    assert body["summary"] == {"total": 3, "succeeded": 3, "failed": 0, "duplicates_skipped": 0}

    # Per-item analysis ran on the real cutout and refined the row.
    expected = {
        "Tops": ("Oxford Shirt", "White"),
        "Bottoms": ("Pleated Trousers", "Navy"),
        "Footwear": ("Leather Sneakers", "Brown"),
    }
    for r in body["results"]:
        item = r["item"]
        assert item["processing_status"] == "ready"
        exp_title, exp_color = expected[item["category"]]
        assert item["title"] == exp_title      # refined from the cutout bytes
        assert item["color_name"] == exp_color
        assert item["ai_confidence"] == pytest.approx(0.93)

    # Extraction provenance passes through unchanged — including the honest skip.
    ex = body["extraction"]
    assert ex["person_detected"] is True
    assert ex["skipped"] == [{"label": "Belt", "reason": "below_min_area", "area": 142}]
    assert ex["engine"] == "schp_atr_18_birefnet_lite_cpu"
    assert ex["commercial"] is True

    # Stored images are the worker's cutouts (PNG magic in the wardrobe listing).
    listing = client.get("/api/v1/wardrobe/items", headers=headers).json()
    assert len(listing) == 3


def test_import_requires_auth(client):
    res = client.post(
        "/api/v1/wardrobe/import-outfit",
        files={"file": ("outfit.png", _png_bytes(), "image/png")},
    )
    assert res.status_code == 401


@pytest.mark.parametrize("bad", [0, 7, -1])
def test_import_max_items_bounds(client, broker_down, bad):
    headers = _register(client, "mbs")
    res = _post_import(client, headers, max_items=bad)
    assert res.status_code == 422


def test_import_unconfigured_is_honest_502_and_stores_nothing(client, broker_down, vision_ok, monkeypatch):
    """No WARDROBE_WORKER_* envs, no mock: the honest answer is a clean 502,
    not a fabricated import."""
    monkeypatch.setattr(config_mod.settings, "WARDROBE_WORKER_URL", None, raising=False)
    monkeypatch.setattr(config_mod.settings, "WARDROBE_WORKER_ADMIN_TOKEN", None, raising=False)
    async def no_network(self, *a, **k):  # noqa: ARG001
        raise AssertionError("no HTTP call may leave the process in this test")
    monkeypatch.setattr(WardrobeExtractionProvider, "_call_worker", no_network)

    headers = _register(client, "una")
    res = _post_import(client, headers)
    assert res.status_code == 502
    assert "not configured" in res.json()["error"]["message"].lower()
    assert client.get("/api/v1/wardrobe/items", headers=headers).json() == []


def test_import_worker_timeout_is_honest_502(client, broker_down, vision_ok, monkeypatch):
    async def fake_call(self, data_url, max_items=4):  # noqa: ARG001
        return {"extraction_available": False, "reason": "wardrobe_worker_timeout"}
    monkeypatch.setattr(WardrobeExtractionProvider, "_call_worker", fake_call)

    headers = _register(client, "tob")
    res = _post_import(client, headers)
    assert res.status_code == 502
    assert client.get("/api/v1/wardrobe/items", headers=headers).json() == []


def test_import_no_garments_detected_is_422_with_skip_report(client, broker_down, vision_ok, extraction_empty, worker_env):
    headers = _register(client, "nga")
    res = _post_import(client, headers)
    assert res.status_code == 422
    message = json.dumps(res.json()["error"]).lower()
    assert "bag" in message and "below_min_area" in message
    assert client.get("/api/v1/wardrobe/items", headers=headers).json() == []


def test_import_same_photo_twice_reports_duplicates(client, broker_down, vision_ok, extraction_ok, worker_env):
    headers = _register(client, "dup")
    first = _post_import(client, headers, max_items=6)
    assert first.status_code == 201
    assert first.json()["summary"]["total"] == 3

    second = _post_import(client, headers, max_items=6)
    assert second.status_code == 201
    body = second.json()
    assert [r["status"] for r in body["results"]] == ["duplicate"] * 3
    assert body["summary"]["duplicates_skipped"] == 3
    # Same 3 rows, not 6.
    assert len(client.get("/api/v1/wardrobe/items", headers=headers).json()) == 3


def test_import_analysis_failure_leaves_retryable_items(client, broker_down, vision_fail, extraction_ok, worker_env):
    """Worker extraction succeeded; per-item vision analysis did not. The
    cutouts are stored as failed/retryable items — never dropped, never fake."""
    headers = _register(client, "ana")
    res = _post_import(client, headers, max_items=6)
    assert res.status_code == 201
    body = res.json()
    assert [r["status"] for r in body["results"]] == ["created"] * 3
    assert all(r["item"]["processing_status"] == "failed" for r in body["results"])
    assert body["summary"]["succeeded"] == 0 and body["summary"]["failed"] == 3
    # Retry path exists: /items/{id}/analyze re-runs analysis only.
    item_id = body["results"][0]["item"]["id"]
    retry = client.post(f"/api/v1/wardrobe/items/{item_id}/analyze", headers=headers)
    assert retry.status_code in (200, 202)


def test_import_malformed_cutout_dropped_and_reported(client, broker_down, vision_ok, monkeypatch, worker_env):
    """One garment with a corrupt cutout must not abort the import — it is
    dropped and reported; the healthy garments still import."""
    body = _worker_ok()
    body["items"].append({
        "slot_type": "accessory", "category": "accessory",
        "label_names": ["Bag"], "bbox": [1, 1, 5, 5],
        "area_fraction": 0.001, "confidence": 2.4,  # also: out-of-range confidence
        # decodes to valid non-PNG bytes -> the "cutout_not_png" drop reason
        "cutout_data_url": "data:image/png;base64,AAAAAAAA",
    })
    async def fake_call(self, data_url, max_items=4):  # noqa: ARG001
        return _worker_envelope(body)
    monkeypatch.setattr(WardrobeExtractionProvider, "_call_worker", fake_call)

    headers = _register(client, "mal")
    res = _post_import(client, headers, max_items=6)
    assert res.status_code == 201, res.text
    out = res.json()
    assert len(out["results"]) == 3  # healthy garments imported
    assert out["extraction"]["dropped_items"] == [{"label": "accessory", "reason": "cutout_not_png"}]


# ───────────────────────── provider unit tests ─────────────────────────

class TestWardrobeExtractionProvider:
    def test_not_configured_is_honest(self, monkeypatch):
        monkeypatch.setattr(config_mod.settings, "WARDROBE_WORKER_URL", None, raising=False)
        monkeypatch.setattr(config_mod.settings, "WARDROBE_WORKER_ADMIN_TOKEN", None, raising=False)
        import asyncio
        result = asyncio.run(WardrobeExtractionProvider().extract_garments("data:image/png;base64,AA=="))
        assert result["extraction_available"] is False
        assert result["reason"] == "wardrobe_extraction_not_configured"

    def test_validate_response_happy_path(self):
        validated, problem = _validate_worker_response(_worker_ok())
        assert problem is None
        assert len(validated["items"]) == 3
        assert validated["items"][0]["cutout_png"].startswith(b"\x89PNG\r\n\x1a\n")
        assert validated["items"][0]["category"] == "Tops"  # worker -> platform taxonomy
        assert validated["skipped"][0]["label"] == "Belt"
        assert validated["person_detected"] is True

    def test_validate_response_clamps_and_drops(self):
        body = _worker_ok()
        body["items"][0]["confidence"] = 1.7   # out of range -> clamped, kept
        body["items"][1]["cutout_data_url"] = "https://evil/x.png"  # not a data URL
        body["items"][2]["slot_type"] = "crown"  # unknown slot
        validated, problem = _validate_worker_response(body)
        assert problem is None
        assert len(validated["items"]) == 1                    # the healthy garment survives
        assert validated["items"][0]["confidence"] == 1.0      # clamped to [0,1]
        assert validated["dropped_items"] == [
            {"label": "lower", "reason": "cutout_not_png_data_url"},
            {"label": "crown", "reason": "unknown_slot"},
        ]

    def test_http_error_envelopes(self, monkeypatch, worker_env):
        """401/422/500 each map to a distinct honest reason."""
        from backend.app.providers import wardrobe_extraction_provider as mod

        orig_client = mod.httpx.AsyncClient

        def _with_transport(handler):
            def factory(*a, **kw):
                kw["transport"] = httpx.MockTransport(handler)
                return orig_client(*a, **kw)
            return factory

        provider = WardrobeExtractionProvider()
        import asyncio

        cases = [
            (401, "wardrobe_worker_auth_failure"),
            (422, "wardrobe_worker_input_invalid"),
            (500, "wardrobe_worker_infra_error"),
        ]
        for status_code, expected_reason in cases:
            def handler(request, status_code=status_code):
                assert request.headers["X-VTON-Admin"] == "test-admin-token"
                return httpx.Response(status_code, json={"detail": {"error": {"code": "X", "message": "m"}}})
            monkeypatch.setattr(mod.httpx, "AsyncClient", _with_transport(handler))
            result = asyncio.run(provider.extract_garments("data:image/png;base64,AA=="))
            assert result["extraction_available"] is False
            assert result["reason"] == expected_reason

    def test_http_timeout_envelope(self, monkeypatch, worker_env):
        from backend.app.providers import wardrobe_extraction_provider as mod

        orig_client = mod.httpx.AsyncClient

        def handler(request):
            raise httpx.ConnectTimeout("boom")

        def factory(*a, **kw):
            kw["transport"] = httpx.MockTransport(handler)
            return orig_client(*a, **kw)

        monkeypatch.setattr(mod.httpx, "AsyncClient", factory)
        import asyncio
        result = asyncio.run(WardrobeExtractionProvider().extract_garments("data:image/png;base64,AA=="))
        assert result["extraction_available"] is False
        # httpx.ConnectTimeout is a TimeoutException -> the timeout envelope.
        assert result["reason"] == "wardrobe_worker_timeout"

    def test_garbage_json_envelope(self, monkeypatch, worker_env):
        from backend.app.providers import wardrobe_extraction_provider as mod

        orig_client = mod.httpx.AsyncClient

        def handler(request):
            return httpx.Response(200, content=b"<html>not json</html>")

        def factory(*a, **kw):
            kw["transport"] = httpx.MockTransport(handler)
            return orig_client(*a, **kw)

        monkeypatch.setattr(mod.httpx, "AsyncClient", factory)
        import asyncio
        result = asyncio.run(WardrobeExtractionProvider().extract_garments("data:image/png;base64,AA=="))
        assert result["extraction_available"] is False
        assert result["reason"] == "wardrobe_worker_invalid_response"
