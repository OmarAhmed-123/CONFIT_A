"""End-to-end (provider-stubbed) proof that photo colour changes the selected products.

Chain exercised for real:
  decoded image bytes -> pixel palette (Pillow) -> colour families -> intent
  -> composer scoring (ColorHarmonyEngine) -> published looks -> response.

Only the two provider calls are stubbed (vision and text), and they are labelled
MOCKED-PROVIDER in the report. Nothing here is a live provider result.
"""
import base64
import io

import pytest
from PIL import Image

from backend.app.core.database import SessionLocal
from backend.app.models.catalog import Product
from backend.app.services import stylist_vision as sv
from backend.app.services.stylist_image_intake import ParsedImage
from backend.app.services.stylist_service import StylistService
from backend.tests.test_stylist_candidate_fixture import committed_catalogue

PROMPT = "Build an office look for work from these photos"
OLIVE = (110, 110, 50)
NAVY = (27, 31, 59)


def _png(rgb):
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), rgb).save(buf, "PNG")
    return buf.getvalue()


OLIVE_PNG, NAVY_PNG = _png(OLIVE), _png(NAVY)


def _url(png):
    return "data:image/png;base64," + base64.b64encode(png).decode()


#: What the (stubbed) vision model says about each photo. The colour words describe
#: the photo; the palette used for scoring comes from the pixels, not from these words.
_VISION_BY_URL = {
    _url(OLIVE_PNG): {"garments": [{"category": "trousers", "color_family": "olive", "description": "olive trousers"}]},
    _url(NAVY_PNG): {"garments": [{"category": "blazer", "color_family": "navy", "description": "navy blazer"}]},
}


class _VisionStub:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    async def chat_json(self, role, system, user, images, timeout_s):
        self.calls += 1
        if self.fail:
            raise TimeoutError("stubbed outage")
        return {**_VISION_BY_URL[images[0].url], "_model_id": "stub-vision"}


class _TextStub:
    async def generate_styling_advice(self, **kwargs):
        return {"styling_advice_text": "", "provider_used": "TEST STUB"}


def _selected(db, reply):
    """Slugs of each published look, in order."""
    out = []
    for look in reply.get("recommendations") or []:
        out.append(sorted(db.get(Product, i["product_id"]).slug for i in look.get("items", [])))
    return out


async def _run(monkeypatch, images, *, vision=None):
    vision = vision or _VisionStub()
    monkeypatch.setattr(sv._vision_client, "chat_json", vision.chat_json)
    monkeypatch.setattr(type(sv._vision_client), "configured", property(lambda self: True))
    db = SessionLocal()
    try:
        service = StylistService(db)
        service.orchestrator = _TextStub()
        reply = await service.interact_with_stylist(
            user_id=None, prompt=PROMPT, images=images, include_wardrobe_items=False,
        )
        return reply, _selected(db, reply), vision
    finally:
        db.close()


@pytest.mark.asyncio
async def test_olive_photo_selects_olive_pieces_and_navy_photo_selects_navy(monkeypatch):
    """The catalogue includes seeded products too, so assert the photo-driven pieces
    that must be present, plus the palette the response reports."""
    with committed_catalogue():
        olive_reply, olive_sel, v1 = await _run(
            monkeypatch, [ParsedImage(mime="image/png", data=OLIVE_PNG)])
        navy_reply, navy_sel, v2 = await _run(
            monkeypatch, [ParsedImage(mime="image/png", data=NAVY_PNG)])
        base_reply, base_sel, _ = await _run(monkeypatch, [])

    assert v1.calls == 1 and v2.calls == 1, "one vision request per photo"
    assert olive_reply["image_analysis"]["available"] is True
    assert navy_reply["image_analysis"]["available"] is True
    assert olive_reply["image_analysis"]["palette_used"] == ["olive"]
    assert navy_reply["image_analysis"]["palette_used"] == ["navy"]

    olive_first, navy_first, base_first = olive_sel[0], navy_sel[0], base_sel[0]
    assert {"fx-trousers-olive", "fx-shirt-olive", "fx-shoes-suede-olive"} <= set(olive_first)
    assert {"fx-trousers-navy-2", "fx-shoes-loafer-navy"} <= set(navy_first)
    # The olive photo changes the outcome relative to no photo, and the navy photo too.
    assert "fx-trousers-olive" not in base_first
    assert olive_sel != navy_sel != base_sel


@pytest.mark.asyncio
async def test_two_photos_are_each_analysed_and_both_colours_reach_the_composer(monkeypatch):
    with committed_catalogue():
        reply, sel, vision = await _run(monkeypatch, [
            ParsedImage(mime="image/png", data=OLIVE_PNG),
            ParsedImage(mime="image/png", data=NAVY_PNG),
        ])
    assert vision.calls == 2
    ia = reply["image_analysis"]
    assert ia["images_total"] == 2 and ia["images_analysed"] == 2
    assert sel, "a complete look is still published"
    for look in sel:
        assert any(s.startswith("fx-") for s in look)


@pytest.mark.asyncio
async def test_vision_outage_is_reported_and_selection_falls_back_to_no_palette(monkeypatch):
    with committed_catalogue():
        reply, sel, vision = await _run(
            monkeypatch, [ParsedImage(mime="image/png", data=OLIVE_PNG)], vision=_VisionStub(fail=True))
        base_reply, base_sel, _ = await _run(monkeypatch, [])
    assert vision.calls == 1
    assert reply["image_analysis"]["available"] is False
    assert reply["image_analysis"]["reason"], "the outage must be stated, not hidden"
    # No analysed colour -> the palette is empty -> the choice equals the no-photo choice.
    assert sel == base_sel
