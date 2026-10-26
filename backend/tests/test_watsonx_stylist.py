"""IBM watsonx.ai stylist tier — client, vision parsing, recommendation contract.

All model calls are MOCKED at the HTTP boundary (httpx.MockTransport) so the
suite is deterministic and free. Nothing here proves live inference; the live
smoke lives in scripts/watsonx_smoke.py and is reported separately.
"""
from __future__ import annotations

import io
import json
import uuid
from typing import Any, Dict, List

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app.core import config as config_mod
from backend.app.providers.watsonx import client as wx_client_mod
from backend.app.providers.watsonx.client import (
    WatsonxAuthError,
    WatsonxClient,
    WatsonxModelUnsupportedError,
    WatsonxNotConfiguredError,
    WatsonxTimeoutError,
)
from backend.app.providers.watsonx.prompts import STYLIST_PROMPT_VERSION, STYLIST_SYSTEM_PROMPT
from backend.app.providers.watsonx.vision import WatsonxVisionProvider, parse_vision_json, prepare_image_data_url
from backend.app.schemas.wardrobe_stylist import OutfitRecommendationRequest

settings = config_mod.settings
IAM = "https://iam.cloud.ibm.com/identity/token"
WX_URL = "https://eu-de.ml.cloud.ibm.com"


# ───────────────────────── helpers ──────────────────────────
def _chat_response(content: Any, model_id: str = "ibm/granite-4-h-small", warnings=None) -> Dict[str, Any]:
    body = {
        "id": "chat-1", "model_id": model_id, "model": model_id,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    if warnings:
        body["system"] = {"warnings": warnings}
    return body


def make_client(handler, **kw) -> WatsonxClient:
    return WatsonxClient(
        api_key="test-key", project_id="proj-1", url=WX_URL, max_retries=kw.pop("max_retries", 0),
        timeout_seconds=5.0, transport=httpx.MockTransport(handler), **kw,
    )


def iam_ok(request: httpx.Request) -> httpx.Response | None:
    if request.url.host in ("iam.cloud.ibm.com", "iam.invalid"):
        assert b"apikey=test-key" in request.content
        return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
    return None


def _png_bytes(size=(1600, 1200), color=(20, 40, 90)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _register(client: TestClient) -> dict:
    email = f"wx_stylist_{uuid.uuid4().hex[:8]}@confit.io"
    res = client.post("/api/v1/auth/register", json={"email": email, "password": "Password123!", "full_name": "WX Stylist"})
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _add_item(client: TestClient, headers: dict, **over) -> dict:
    payload = {
        "title": over.pop("title", "White Oxford Shirt"), "category": over.pop("category", "Tops"),
        "subcategory": over.pop("subcategory", "Oxford Shirt"), "color_name": over.pop("color_name", "White"),
        "color_hex": "#FFFFFF", "pattern": "Solid",
        "image_url": over.pop("image_url", f"https://cdn.example.com/{uuid.uuid4().hex}.jpg"),
        "occasions": over.pop("occasions", ["Smart Casual"]), "seasonality": over.pop("seasonality", "All-Season"),
    }
    payload.update(over)
    res = client.post("/api/v1/wardrobe/items", json=payload, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


@pytest.fixture(autouse=True)
def _never_touch_real_ibm(monkeypatch):
    """Belt and braces: if any code path builds a real transport, the IAM
    exchange must fail on DNS instead of spending the operator's quota."""
    monkeypatch.setattr(wx_client_mod, "IAM_TOKEN_URL", "https://iam.invalid/identity/token")


@pytest.fixture
def wx_env(monkeypatch):
    """Configured watsonx, deterministic fallback allowed (auto)."""
    monkeypatch.setattr(settings, "WATSONX_APIKEY", "test-key")
    monkeypatch.setattr(settings, "WATSONX_PROJECT_ID", "proj-1")
    monkeypatch.setattr(settings, "WATSONX_URL", WX_URL)
    monkeypatch.setattr(settings, "WATSONX_REASONING_MODEL_ID", "ibm/granite-4-h-small")
    monkeypatch.setattr(settings, "WARDROBE_STYLIST_PROVIDER", "auto")
    monkeypatch.setattr(settings, "WARDROBE_VISION_PROVIDER", "auto")
    wx_client_mod.reset_watsonx_client()
    yield
    wx_client_mod.reset_watsonx_client()


def _install_chat(monkeypatch, handler, max_retries=0):
    """Route the service's client to a mock transport."""
    c = make_client(handler, max_retries=max_retries)
    monkeypatch.setattr(wx_client_mod, "get_watsonx_client", lambda: c)
    return c


# ───────────────────────── client ───────────────────────────
@pytest.mark.asyncio
async def test_client_not_configured_raises_actionable_error():
    c = WatsonxClient(api_key=None, project_id=None, url=WX_URL)
    assert not c.configured
    with pytest.raises(WatsonxNotConfiguredError) as ei:
        await c.chat(model_id="x", messages=[])
    assert "WATSONX_APIKEY" in str(ei.value) and "WATSONX_PROJECT_ID" in str(ei.value)


@pytest.mark.asyncio
async def test_client_sends_tutorial_shaped_request_and_caches_token():
    seen: List[httpx.Request] = []

    def handler(req):
        r = iam_ok(req)
        if r:
            seen.append(req)
            return r
        body = json.loads(req.content)
        assert req.url.path == "/ml/v1/text/chat" and req.url.params["version"] == settings.WATSONX_API_VERSION
        assert body["model_id"] == "ibm/granite-4-h-small" and body["project_id"] == "proj-1"
        assert body["messages"][0]["role"] == "system"
        assert req.headers["authorization"] == "Bearer tok"
        return httpx.Response(200, json=_chat_response('{"ok": true}'))

    c = make_client(handler)
    r1 = await c.chat(model_id="ibm/granite-4-h-small", messages=[{"role": "system", "content": "x"}])
    r2 = await c.chat(model_id="ibm/granite-4-h-small", messages=[{"role": "system", "content": "x"}])
    assert r1.content == '{"ok": true}' and r2.model_id == "ibm/granite-4-h-small"
    assert len(seen) == 1, "IAM token must be cached across calls"


@pytest.mark.asyncio
async def test_client_maps_404_model_not_supported():
    def handler(req):
        return iam_ok(req) or httpx.Response(404, json={"errors": [{"code": "model_not_supported",
                                                                    "message": "Model 'ibm/granite-vision-3-2-2b' was not found."}]})
    with pytest.raises(WatsonxModelUnsupportedError) as ei:
        await make_client(handler).chat(model_id="ibm/granite-vision-3-2-2b", messages=[])
    assert "granite-vision-3-2-2b" in str(ei.value)


@pytest.mark.asyncio
async def test_client_auth_failure_never_leaks_key():
    def handler(req):
        if req.url.host in ("iam.cloud.ibm.com", "iam.invalid"):
            return httpx.Response(400, json={"errorMessage": "Provided API key could not be found"})
        return httpx.Response(200)
    with pytest.raises(WatsonxAuthError) as ei:
        await make_client(handler).chat(model_id="m", messages=[])
    assert "test-key" not in str(ei.value)


@pytest.mark.asyncio
async def test_client_retries_transient_then_succeeds(monkeypatch):
    calls = {"n": 0}

    async def no_sleep(_):
        return None
    monkeypatch.setattr(wx_client_mod.asyncio, "sleep", no_sleep)

    def handler(req):
        r = iam_ok(req)
        if r:
            return r
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"errors": [{"code": "rate_limit"}]})
        if calls["n"] == 2:
            raise httpx.ReadTimeout("slow")
        return httpx.Response(200, json=_chat_response("done"))

    r = await make_client(handler, max_retries=2).chat(model_id="m", messages=[])
    assert r.content == "done" and calls["n"] == 3


@pytest.mark.asyncio
async def test_client_timeout_without_retries_is_timeout_error():
    def handler(req):
        r = iam_ok(req)
        if r:
            return r
        raise httpx.ReadTimeout("slow")
    with pytest.raises(WatsonxTimeoutError):
        await make_client(handler).chat(model_id="m", messages=[])


# ───────────────────────── vision ───────────────────────────
def test_prepare_image_downscales_and_rejects_garbage():
    url, info = prepare_image_data_url(_png_bytes((1600, 1200)))
    assert url.startswith("data:image/jpeg;base64,")
    assert max(info["sent_size"]) <= 1024 and info["original_size"] == (1600, 1200)
    with pytest.raises(ValueError):
        prepare_image_data_url(b"not an image at all")
    with pytest.raises(ValueError):
        prepare_image_data_url("data:image/png;base64,@@@")


@pytest.mark.parametrize("text", [
    '{"category": "Tops", "confidence": 0.9}',
    '```json\n{"category": "Tops", "confidence": 0.9}\n```',
    'Sure! Here is the JSON: {"category": "Tops", "confidence": 0.9} hope it helps',
])
def test_parse_vision_json_tolerates_fences_and_prose(text):
    assert parse_vision_json(text)["category"] == "Tops"


@pytest.mark.parametrize("text", ["", "no json here", "[1,2,3]", '{"broken": '])
def test_parse_vision_json_rejects_non_objects(text):
    with pytest.raises(ValueError):
        parse_vision_json(text)


@pytest.mark.asyncio
async def test_vision_provider_returns_platform_envelope_with_real_source():
    def handler(req):
        r = iam_ok(req)
        if r:
            return r
        body = json.loads(req.content)
        parts = body["messages"][0]["content"]
        assert parts[1]["type"] == "image_url" and parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
        return httpx.Response(200, json=_chat_response(json.dumps({
            "category": "Tops", "item_type": "Oxford Shirt", "description": "A white cotton shirt.",
            "primary_color": "White", "primary_color_hex": "#FFFFFF", "secondary_colors": [],
            "pattern": "Solid", "style_tags": ["Tailored"], "occasion_suitability": ["Smart Casual"],
            "seasonality": "All-Season", "confidence": 0.91,
        }), model_id="meta-llama/llama-4-maverick-17b-128e-instruct-fp8"))

    p = WatsonxVisionProvider(client=make_client(handler), model_id="meta-llama/llama-4-maverick-17b-128e-instruct-fp8")
    out = await p.analyze_wardrobe_image(_png_bytes())
    assert out["analysis_available"] is True
    assert out["analysis_source"] == "meta-llama/llama-4-maverick-17b-128e-instruct-fp8"
    assert out["category"] == "Tops" and out["description"].startswith("A white")


@pytest.mark.asyncio
async def test_vision_provider_malformed_json_is_unavailable_not_crash():  # Scenario C
    def handler(req):
        return iam_ok(req) or httpx.Response(200, json=_chat_response("I think this is a shirt {category: Tops"))
    out = await WatsonxVisionProvider(client=make_client(handler)).analyze_wardrobe_image(_png_bytes())
    assert out["analysis_available"] is False and out["reason"] == "watsonx_vision_malformed_output"


@pytest.mark.asyncio
async def test_vision_provider_timeout_is_unavailable_retryable():  # Scenario F
    def handler(req):
        r = iam_ok(req)
        if r:
            return r
        raise httpx.ReadTimeout("slow")
    out = await WatsonxVisionProvider(client=make_client(handler)).analyze_wardrobe_image(_png_bytes())
    assert out["analysis_available"] is False and out["reason"] == "watsonx_timeout" and out["retryable"] is True


@pytest.mark.asyncio
async def test_vision_provider_unconfigured_is_honest():  # Scenario E
    p = WatsonxVisionProvider(client=WatsonxClient(api_key=None, project_id=None, url=WX_URL))
    out = await p.analyze_wardrobe_image(_png_bytes())
    assert out == {"analysis_available": False, "reason": "watsonx_not_configured", "analysis_source": None}


# ───────────────────── wardrobe analysis chain ──────────────
@pytest.mark.asyncio
async def test_wardrobe_analysis_persists_source_from_watsonx(client, wx_env, monkeypatch):
    """Upload → watsonx vision → ready item with analysis_source + description."""
    def handler(req):
        return iam_ok(req) or httpx.Response(200, json=_chat_response(json.dumps({
            "category": "Footwear", "item_type": "Chelsea Boots", "description": "Brown leather boots.",
            "primary_color": "Brown", "primary_color_hex": "#5B3A29", "pattern": "Solid",
            "style_tags": ["Leather"], "occasion_suitability": ["Smart Casual", "Casual"],
            "seasonality": "Autumn", "confidence": 0.88,
        }), model_id="meta-llama/llama-4-maverick-17b-128e-instruct-fp8"))
    _install_chat(monkeypatch, handler)
    monkeypatch.setattr(settings, "WARDROBE_ANALYSIS_MODE", "sync")
    headers = _register(client)
    res = client.post("/api/v1/wardrobe/upload", headers=headers,
                      files={"file": ("boots.png", _png_bytes((64, 64)), "image/png")})
    assert res.status_code == 201, res.text
    item = res.json()["results"][0]["item"]
    assert item["processing_status"] == "ready", res.json()
    assert item["category"] == "Footwear" and item["subcategory"] == "Chelsea Boots"
    assert item["analysis_source"] == "meta-llama/llama-4-maverick-17b-128e-instruct-fp8"
    assert item["analysis_description"] == "Brown leather boots."


@pytest.mark.asyncio
async def test_wardrobe_analysis_watsonx_only_mode_fails_honestly_when_unconfigured(client, monkeypatch):
    monkeypatch.setattr(settings, "WATSONX_APIKEY", None)
    monkeypatch.setattr(settings, "WARDROBE_VISION_PROVIDER", "watsonx")
    monkeypatch.setattr(settings, "WARDROBE_ANALYSIS_MODE", "sync")
    wx_client_mod.reset_watsonx_client()
    headers = _register(client)
    res = client.post("/api/v1/wardrobe/upload", headers=headers,
                      files={"file": ("x.png", _png_bytes((64, 64)), "image/png")})
    assert res.status_code == 201
    item = res.json()["results"][0]["item"]
    assert item["processing_status"] == "failed"
    assert "WATSONX_" in (item["processing_error"] or "")
    assert item["analysis_source"] is None


def test_manual_correction_changes_provenance(client):  # FR-05 / FR-18
    headers = _register(client)
    item = _add_item(client, headers)
    assert item["analysis_source"] is None
    res = client.patch(f"/api/v1/wardrobe/items/{item['id']}", json={"category": "Outerwear"}, headers=headers)
    assert res.status_code == 200 and res.json()["category"] == "Outerwear"
    assert res.json()["analysis_source"] == "manual"
    res = client.patch(f"/api/v1/wardrobe/items/{item['id']}", json={"is_favorite": True}, headers=headers)
    assert res.json()["analysis_source"] == "manual"  # bookkeeping does not alter provenance


# ───────────────────── recommendation contract ──────────────
def _closet(client, headers):
    top = _add_item(client, headers, title="Blue Plaid Shirt", category="Tops", color_name="Blue",
                    occasions=["Casual"], seasonality="Autumn")
    bottom = _add_item(client, headers, title="Khaki Chinos", category="Bottoms", subcategory="Chinos",
                       color_name="Beige", occasions=["Casual", "Smart Casual"])
    shoes = _add_item(client, headers, title="Tan Leather Boots", category="Footwear", subcategory="Boots",
                      color_name="Tan", occasions=["Casual"], seasonality="Autumn")
    return top, bottom, shoes


def test_recommendation_scenario_a_valid_model_output(client, wx_env, monkeypatch):
    headers = _register(client)
    top, bottom, shoes = _closet(client, headers)
    captured: Dict[str, Any] = {}

    def handler(req):
        r = iam_ok(req)
        if r:
            return r
        body = json.loads(req.content)
        captured["body"] = body
        return httpx.Response(200, json=_chat_response(json.dumps({
            "title": "Relaxed autumn park look",
            "summary": "Layer-friendly casual pieces in earthy tones.",
            "items": [
                {"wardrobe_item_id": top["id"], "role": "top", "reason": "Plaid flannel suits a cool autumn morning."},
                {"wardrobe_item_id": bottom["id"], "role": "bottom", "reason": "Khaki balances the blue plaid."},
                {"wardrobe_item_id": shoes["id"], "role": "footwear", "reason": "Boots handle park paths."},
            ],
            "styling_notes": ["Roll the sleeves once for a relaxed line."],
            "limitations": [], "missing_categories": [], "assumptions": ["Mild weather assumed."],
        })))
    _install_chat(monkeypatch, handler)

    res = client.post("/api/v1/wardrobe/outfit-recommendation", headers=headers, json={
        "occasion": "Casual", "time_of_day": "morning", "season": "autumn", "location": "park",
        "style_preferences": ["relaxed"], "color_preferences": ["earth tones"],
    })
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["source"] == "watsonx" and out["ai_generated"] is True
    assert out["model_id"] == "ibm/granite-4-h-small" and out["prompt_version"] == STYLIST_PROMPT_VERSION
    assert [i["wardrobe_item_id"] for i in out["items"]] == [top["id"], bottom["id"], shoes["id"]]
    assert out["items"][0]["image_url"] == top["image_url"]  # FR-10: image from trusted row
    assert out["is_complete"] is True and out["missing_categories"] == []
    assert out["items"][1]["reason"] == "Khaki balances the blue plaid."
    # Prompt hygiene: system prompt is the versioned one; closet has ids but no URLs
    body = captured["body"]
    assert body["messages"][0]["content"] == STYLIST_SYSTEM_PROMPT
    user_msg = body["messages"][1]["content"]
    assert "cdn.example.com" not in user_msg and f'"wardrobe_item_id": {top["id"]}' in user_msg
    assert "season: autumn" in user_msg and "location: park" in user_msg and "time_of_day: morning" in user_msg
    assert body.get("response_format") == {"type": "json_object"}


def test_recommendation_scenario_g_rejects_invalid_reference(client, wx_env, monkeypatch):
    headers = _register(client)
    top, bottom, shoes = _closet(client, headers)
    other_headers = _register(client)
    foreign = _add_item(client, other_headers, title="Someone else's jacket", category="Outerwear")

    def handler(req):
        return iam_ok(req) or httpx.Response(200, json=_chat_response(json.dumps({
            "title": "t", "summary": "s",
            "items": [
                {"wardrobe_item_id": top["id"], "role": "top", "reason": "ok"},
                {"wardrobe_item_id": 999999, "role": "bottom", "reason": "ghost"},
                {"wardrobe_item_id": foreign["id"], "role": "outerwear", "reason": "not yours"},
                {"wardrobe_item_id": shoes["id"], "role": "footwear", "reason": "ok"},
                {"wardrobe_item_id": shoes["id"], "role": "footwear", "reason": "dup"},
            ],
        })))
    _install_chat(monkeypatch, handler)
    res = client.post("/api/v1/wardrobe/outfit-recommendation", headers=headers, json={"occasion": "Casual"})
    assert res.status_code == 200, res.text
    out = res.json()
    ids = [i["wardrobe_item_id"] for i in out["items"]]
    assert ids == [top["id"], shoes["id"]]
    assert sorted(out["rejected_references"]) == sorted([999999, foreign["id"]])
    assert out["is_complete"] is False
    assert any("discarded" in l for l in out["limitations"])
    # The bottom exists in the wardrobe but the model skipped it → not "missing"
    assert out["missing_categories"] == []


def test_recommendation_scenario_d_missing_shoes_is_reported_not_invented(client, wx_env, monkeypatch):
    headers = _register(client)
    top = _add_item(client, headers, title="Shirt", category="Tops")
    bottom = _add_item(client, headers, title="Trousers", category="Bottoms")

    def handler(req):
        return iam_ok(req) or httpx.Response(200, json=_chat_response(json.dumps({
            "title": "t", "summary": "s",
            "items": [{"wardrobe_item_id": top["id"], "role": "top", "reason": "r"},
                      {"wardrobe_item_id": bottom["id"], "role": "bottom", "reason": "r"}],
            "missing_categories": ["shoes"], "limitations": ["No footwear available."],
        })))
    _install_chat(monkeypatch, handler)
    out = client.post("/api/v1/wardrobe/outfit-recommendation", headers=headers, json={"occasion": "Formal"}).json()
    assert out["missing_categories"] == ["Footwear"]
    assert out["is_complete"] is False
    assert all(i["category"] != "Footwear" for i in out["items"])
    assert any("footwear" in l.lower() for l in out["limitations"])


def test_recommendation_scenario_c_malformed_json_falls_back_labelled(client, wx_env, monkeypatch):
    headers = _register(client)
    _closet(client, headers)

    def handler(req):
        return iam_ok(req) or httpx.Response(200, json=_chat_response("Here is my thought process: wear the plaid shirt"))
    _install_chat(monkeypatch, handler)
    res = client.post("/api/v1/wardrobe/outfit-recommendation", headers=headers, json={"occasion": "Casual", "season": "autumn"})
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["source"] == "deterministic_fallback" and out["ai_generated"] is False  # Scenario J
    assert out["model_id"] is None and "malformed" in out["fallback_reason"]
    assert len(out["items"]) == 3 and out["is_complete"] is True
    assert any("rule-based" in l for l in out["limitations"])


def test_recommendation_scenario_f_timeout_strict_mode_is_502(client, wx_env, monkeypatch):
    headers = _register(client)
    _closet(client, headers)
    monkeypatch.setattr(settings, "WARDROBE_STYLIST_PROVIDER", "watsonx")

    def handler(req):
        r = iam_ok(req)
        if r:
            return r
        raise httpx.ReadTimeout("slow")
    _install_chat(monkeypatch, handler)
    res = client.post("/api/v1/wardrobe/outfit-recommendation", headers=headers, json={"occasion": "Casual"})
    assert res.status_code == 502, res.text
    body = res.json()["error"]
    assert body["code"] == "PROVIDER_ERROR" and "watsonx_timeout" in body["message"]
    assert body["details"]["retryable"] is True


def test_recommendation_scenario_e_unconfigured_strict_is_501_with_hint(client, monkeypatch):
    monkeypatch.setattr(settings, "WATSONX_APIKEY", None)
    monkeypatch.setattr(settings, "WARDROBE_STYLIST_PROVIDER", "watsonx")
    wx_client_mod.reset_watsonx_client()
    headers = _register(client)
    _closet(client, headers)
    res = client.post("/api/v1/wardrobe/outfit-recommendation", headers=headers, json={"occasion": "Casual"})
    assert res.status_code == 501, res.text
    assert "WATSONX_APIKEY" in res.json()["error"]["details"]["hint"]


def test_recommendation_unconfigured_auto_uses_labelled_fallback(client, monkeypatch):
    monkeypatch.setattr(settings, "WATSONX_APIKEY", None)
    monkeypatch.setattr(settings, "WARDROBE_STYLIST_PROVIDER", "auto")
    wx_client_mod.reset_watsonx_client()
    headers = _register(client)
    _closet(client, headers)
    out = client.post("/api/v1/wardrobe/outfit-recommendation", headers=headers, json={"occasion": "Casual"}).json()
    assert out["source"] == "deterministic_fallback" and out["fallback_reason"] == "watsonx_not_configured"


def test_recommendation_empty_wardrobe_is_422(client, wx_env):
    headers = _register(client)
    res = client.post("/api/v1/wardrobe/outfit-recommendation", headers=headers, json={"occasion": "Casual"})
    assert res.status_code == 422
    assert "Upload" in res.json()["error"]["message"]


def test_recommendation_scenario_h_edited_category_drives_selection(client, wx_env, monkeypatch):
    """User corrects a mis-tagged item (Tops → Footwear); the model is given
    AND the response reflects the corrected category."""
    headers = _register(client)
    top = _add_item(client, headers, title="Shirt", category="Tops")
    bottom = _add_item(client, headers, title="Jeans", category="Bottoms")
    mis = _add_item(client, headers, title="Sneakers", category="Tops")  # wrongly tagged
    client.patch(f"/api/v1/wardrobe/items/{mis['id']}", json={"category": "Footwear"}, headers=headers)
    seen: Dict[str, Any] = {}

    def handler(req):
        r = iam_ok(req)
        if r:
            return r
        seen["closet"] = json.loads(req.content)["messages"][1]["content"]
        return httpx.Response(200, json=_chat_response(json.dumps({
            "title": "t", "summary": "s",
            "items": [{"wardrobe_item_id": top["id"], "role": "top", "reason": "r"},
                      {"wardrobe_item_id": bottom["id"], "role": "bottom", "reason": "r"},
                      {"wardrobe_item_id": mis["id"], "role": "top", "reason": "model mislabels role"}],
        })))
    _install_chat(monkeypatch, handler)
    out = client.post("/api/v1/wardrobe/outfit-recommendation", headers=headers, json={"occasion": "Casual"}).json()
    assert f'"wardrobe_item_id": {mis["id"]}, "category": "Footwear"' in seen["closet"]
    sneakers = next(i for i in out["items"] if i["wardrobe_item_id"] == mis["id"])
    assert sneakers["role"] == "footwear" and sneakers["category"] == "Footwear"
    assert sneakers["analysis_source"] == "manual"
    assert out["is_complete"] is True


def test_recommendation_respects_exclusions_and_previous(client, wx_env, monkeypatch):
    headers = _register(client)
    top, bottom, shoes = _closet(client, headers)
    top2 = _add_item(client, headers, title="Black Tee", category="Tops", color_name="Black", occasions=["Casual"])
    monkeypatch.setattr(settings, "WARDROBE_STYLIST_PROVIDER", "deterministic")
    out = client.post("/api/v1/wardrobe/outfit-recommendation", headers=headers, json={
        "occasion": "Casual", "excluded_item_ids": [top["id"]], "previous_item_ids": [top2["id"]],
    }).json()
    assert out["source"] == "deterministic_fallback"
    tops = [i for i in out["items"] if i["role"] == "top"]
    assert tops and tops[0]["wardrobe_item_id"] == top2["id"]  # only remaining top, even though "previous"
    # the model path must also never return an excluded id
    monkeypatch.setattr(settings, "WARDROBE_STYLIST_PROVIDER", "auto")

    def handler(req):
        return iam_ok(req) or httpx.Response(200, json=_chat_response(json.dumps({
            "title": "t", "summary": "s",
            "items": [{"wardrobe_item_id": top["id"], "role": "top", "reason": "excluded!"},
                      {"wardrobe_item_id": bottom["id"], "role": "bottom", "reason": "r"}],
        })))
    _install_chat(monkeypatch, handler)
    out = client.post("/api/v1/wardrobe/outfit-recommendation", headers=headers,
                      json={"occasion": "Casual", "excluded_item_ids": [top["id"]]}).json()
    assert top["id"] not in [i["wardrobe_item_id"] for i in out["items"]]
    assert top["id"] in out["rejected_references"]


def test_stylist_status_never_exposes_secrets(client, wx_env):
    headers = _register(client)
    _add_item(client, headers)
    res = client.get("/api/v1/wardrobe/stylist/status", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["watsonx_configured"] is True and body["reasoning_model_id"] == "ibm/granite-4-h-small"
    assert body["ready_items"] == 1 and body["categories_present"] == ["Tops"]
    assert "test-key" not in res.text and "proj-1" not in res.text


def test_request_schema_bounds():
    with pytest.raises(Exception):
        OutfitRecommendationRequest(occasion="x")  # too short
    with pytest.raises(Exception):
        OutfitRecommendationRequest(season="monsoon")
    r = OutfitRecommendationRequest(occasion="  Smart   Casual ", style_preferences=["a", "a", " b "])
    assert r.occasion == "Smart Casual" and r.style_preferences == ["a", "b"]


def test_cross_user_items_are_not_styled(client, wx_env, monkeypatch):
    """Another user's wardrobe must never leak into the closet sent to the model."""
    h1, h2 = _register(client), _register(client)
    mine = _add_item(client, h1, title="Mine")
    theirs = _add_item(client, h2, title="Theirs")
    seen: Dict[str, Any] = {}

    def handler(req):
        r = iam_ok(req)
        if r:
            return r
        seen["msg"] = json.loads(req.content)["messages"][1]["content"]
        return httpx.Response(200, json=_chat_response(json.dumps(
            {"title": "t", "summary": "s", "items": [{"wardrobe_item_id": mine["id"], "role": "top", "reason": "r"}]})))
    _install_chat(monkeypatch, handler)
    client.post("/api/v1/wardrobe/outfit-recommendation", headers=h1, json={"occasion": "Casual"})
    assert f'"wardrobe_item_id": {mine["id"]}' in seen["msg"]
    assert f'"wardrobe_item_id": {theirs["id"]}' not in seen["msg"]


# ───────────── deploy-on-demand routing (Granite Vision is DoD-only) ─────────────
class TestDeployOnDemandRouting:
    """IBM serves granite-vision-3-3-2b / 4-1-4b only as dedicated deployments.
    When a deployment id is configured the client must hit
    ``/ml/v1/deployments/{id}/text/chat`` WITHOUT model_id/project_id in the
    body, and provenance must come from the *response's* model_id."""

    @pytest.mark.asyncio
    async def test_deployment_endpoint_and_body_shape(self):
        seen = {}

        def handler(request: httpx.Request):
            r = iam_ok(request)
            if r:
                return r
            seen["path"] = request.url.path
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json=_chat_response("{}", model_id="ibm/granite-vision-3-3-2b"))

        client = make_client(handler)
        res = await client.chat(model_id="ibm/granite-vision-3-3-2b", messages=[{"role": "user", "content": "x"}],
                                deployment_id="dep-123")
        assert seen["path"] == "/ml/v1/deployments/dep-123/text/chat"
        assert "model_id" not in seen["body"] and "project_id" not in seen["body"]
        assert seen["body"]["messages"] == [{"role": "user", "content": "x"}]
        assert res.model_id == "ibm/granite-vision-3-3-2b"

    @pytest.mark.asyncio
    async def test_provenance_follows_served_model_not_configured_label(self):
        """If a deployment actually serves a different model than configured, the
        served id wins — the UI must never claim Granite on a label alone."""
        def handler(request: httpx.Request):
            r = iam_ok(request)
            if r:
                return r
            return httpx.Response(200, json=_chat_response("{}", model_id="meta-llama/llama-4-maverick-17b-128e-instruct-fp8"))

        client = make_client(handler)
        res = await client.chat(model_id="ibm/granite-vision-3-3-2b", messages=[{"role": "user", "content": "x"}],
                                deployment_id="dep-999")
        assert res.model_id == "meta-llama/llama-4-maverick-17b-128e-instruct-fp8"

    @pytest.mark.asyncio
    async def test_no_deployment_id_keeps_multitenant_contract(self):
        seen = {}

        def handler(request: httpx.Request):
            r = iam_ok(request)
            if r:
                return r
            seen["path"] = request.url.path
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json=_chat_response("{}"))

        client = make_client(handler)
        await client.chat(model_id="ibm/granite-4-h-small", messages=[{"role": "user", "content": "x"}])
        assert seen["path"] == "/ml/v1/text/chat"
        assert seen["body"]["model_id"] == "ibm/granite-4-h-small" and seen["body"]["project_id"] == "proj-1"
