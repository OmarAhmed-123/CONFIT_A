"""Multi-photo vision: every attached photo is analysed, partial results are
reported as partial, and no image content reaches the public payload.

WHY THESE TESTS EXIST (live evidence, 2026-10-10, NVIDIA chain, 4 requests used):
a single request carrying TWO photos timed out at 15s on both candidate models,
while each photo alone answered in 3.7s and 5.0s. The fix is one request per photo.

The provider call is stubbed (no network). The stubs follow the real
`chat_json` contract: they receive exactly one image part per call.
"""
from __future__ import annotations

import asyncio

import pytest

from backend.app.core.config import settings
from backend.app.services import stylist_vision as sv
from backend.app.services.stylist_image_intake import ParsedImage


def _img(tag: bytes) -> ParsedImage:
    return ParsedImage(mime="image/jpeg", data=b"\xff\xd8\xff" + tag)


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "STYLIST_VISION_ENABLED", True, raising=False)
    monkeypatch.setattr(type(sv._vision_client), "configured", property(lambda self: True))


def _fake_chat(outcomes):
    """outcomes: list, one per call, each a dict payload or an Exception."""
    calls = []

    async def chat_json(role, *, user, system=None, images=None, timeout_s=None):
        calls.append({"role": role, "images": len(images or []), "timeout_s": timeout_s})
        outcome = outcomes[len(calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return {**outcome, "_model_id": "google/diffusiongemma-26b-a4b-it"}

    return chat_json, calls


PAYLOAD_A = {"garments": [{"category": "top", "description": "white shirt", "color_family": "white"}],
             "summary": "A white shirt."}
PAYLOAD_B = {"garments": [{"category": "bottom", "description": "navy trousers", "color_family": "navy"},
                          {"category": "footwear", "description": "brown shoes", "color_family": "brown"}],
             "summary": "Navy trousers with brown shoes."}


def test_each_photo_gets_its_own_request_and_keeps_its_index(monkeypatch, configured):
    chat, calls = _fake_chat([PAYLOAD_A, PAYLOAD_B])
    monkeypatch.setattr(sv._vision_client, "chat_json", chat)
    res = asyncio.run(sv.analyze_images([_img(b"a"), _img(b"b")], "what shoes?"))
    assert len(calls) == 2
    assert all(c["images"] == 1 for c in calls), "a request must never carry several photos"
    assert res.available is True
    assert res.images_total == 2 and res.images_analysed == 2
    assert [(g.description, g.image_index) for g in res.garments] == [
        ("white shirt", 0), ("navy trousers", 1), ("brown shoes", 1),
    ]


def test_one_failed_photo_is_reported_as_partial_not_as_full(monkeypatch, configured):
    chat, _ = _fake_chat([PAYLOAD_A, TimeoutError("request exceeded 15.0s")])
    monkeypatch.setattr(sv._vision_client, "chat_json", chat)
    res = asyncio.run(sv.analyze_images([_img(b"a"), _img(b"b")], "x"))
    assert res.available is True
    assert res.images_total == 2 and res.images_analysed == 1
    assert "1 of 2" in (res.reason or "")
    assert res.per_image[1]["analysed"] is False and res.per_image[0]["analysed"] is True
    assert all(g.image_index == 0 for g in res.garments)


def test_every_photo_failing_is_honest_unavailable(monkeypatch, configured):
    chat, _ = _fake_chat([TimeoutError("t1"), TimeoutError("t2")])
    monkeypatch.setattr(sv._vision_client, "chat_json", chat)
    res = asyncio.run(sv.analyze_images([_img(b"a"), _img(b"b")], "x"))
    assert res.available is False
    assert res.images_analysed == 0 and res.garments == []
    assert "did not answer" in (res.reason or "")


def test_single_photo_still_works(monkeypatch, configured):
    chat, calls = _fake_chat([PAYLOAD_B])
    monkeypatch.setattr(sv._vision_client, "chat_json", chat)
    res = asyncio.run(sv.analyze_images([_img(b"a")], "x"))
    assert len(calls) == 1 and res.available is True and res.images_analysed == 1


def test_disabled_or_unconfigured_never_calls_the_provider(monkeypatch):
    chat, calls = _fake_chat([PAYLOAD_A])
    monkeypatch.setattr(sv._vision_client, "chat_json", chat)
    monkeypatch.setattr(settings, "STYLIST_VISION_ENABLED", False, raising=False)
    res = asyncio.run(sv.analyze_images([_img(b"a")], "x"))
    assert res.available is False and calls == []


def test_public_payload_carries_no_image_content(monkeypatch, configured):
    chat, _ = _fake_chat([PAYLOAD_A, PAYLOAD_B])
    monkeypatch.setattr(sv._vision_client, "chat_json", chat)
    res = asyncio.run(sv.analyze_images([_img(b"secret-bytes-a"), _img(b"secret-bytes-b")], "x"))
    public = repr(res.to_public())
    assert "base64" not in public and "data:" not in public and "secret-bytes" not in public
    assert res.to_public()["images_total"] == 2
