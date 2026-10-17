"""Offline eval harness for the StyleList AI stylist (SC-001..SC-006).

A fixed golden set is run through the real endpoint with every provider mocked, so
the harness is free, deterministic and never calls a paid model. It scores the
properties the spec makes non-negotiable and prints a scorecard:

* grounding    — every recommended item is a real catalogue product (SC-001)
* served model — every Mode A answer names the model that actually answered (SC-001/003)
* honesty      — an unavailable vision leg falls back to Mode B with a reason (SC-003)
* wardrobe     — toggling include_wardrobe_items changes the output (SC-002)
* colour       — extracted photo colours change the coordination score (SC-004)
* safety       — blocked images are refused and never analysed (SC-005)
* storage      — no base64 image is stored in any stylist table (SC-005)

Run it alone with:  pytest backend/tests/test_stylist_eval_harness.py -s
"""
from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field
from typing import List

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text

from backend.app.core.config import settings
from backend.app.services import stylist_service as stylist_service_module
from backend.app.services.content_safety_service import SafetyVerdict, Severity, content_safety_service
from backend.app.services.stylist_vision import GarmentObservation, VisionAnalysis
from backend.tests.conftest import TestingSessionLocal
from backend.tests.test_stylist_wardrobe_influence import (
    _add_wardrobe_piece,
    _pairings,
    _post,
    _register,
)

# ── Golden set ───────────────────────────────────────────────────────────────
TEXT_PROMPTS = [
    "a smart casual dinner look",
    "formal wedding outfit under 500",
    "relaxed weekend brunch outfit",
    "office-ready look for a client meeting",
]
PHOTO_PROMPTS = [
    "Put together a look around this blazer",
    "match these colours",
    "what goes with this outfit for an evening out",
]


def _png(colour, size=(64, 64)) -> str:
    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


@dataclass
class Scorecard:
    cases: int = 0
    grounded: int = 0
    mode_a_cases: int = 0
    served_model_reported: int = 0
    honest_fallbacks: int = 0
    honest_fallback_cases: int = 0
    notes: List[str] = field(default_factory=list)

    def render(self) -> str:
        def pct(a, b):
            return "n/a" if not b else f"{100 * a / b:.0f}% ({a}/{b})"

        lines = [
            "StyleList eval scorecard (offline, mocked providers)",
            f"  cases run ............... {self.cases}",
            f"  grounded in catalogue ... {pct(self.grounded, self.cases)}",
            f"  Mode A served model ..... {pct(self.served_model_reported, self.mode_a_cases)}",
            f"  honest fallback ......... {pct(self.honest_fallbacks, self.honest_fallback_cases)}",
        ]
        lines += [f"  note: {n}" for n in self.notes]
        return "\n".join(lines)


@pytest.fixture
def mocked_text(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDERS", "none")


@pytest.fixture
def vision_ok(monkeypatch):
    async def fake(images, shopper_request):
        return VisionAnalysis(
            available=True,
            engine="NVIDIA nvidia/nemotron-3-eval-vision",
            summary="A navy blazer over a white shirt.",
            garments=[
                GarmentObservation(category="outerwear", description="navy blazer", color_family="navy"),
                GarmentObservation(category="top", description="white shirt", color_family="white"),
            ],
        )

    monkeypatch.setattr(stylist_service_module, "analyze_images", fake)


@pytest.fixture
def vision_down(monkeypatch):
    async def fake(images, shopper_request):
        return VisionAnalysis(available=False, reason="The image service did not answer.")

    monkeypatch.setattr(stylist_service_module, "analyze_images", fake)


@pytest.fixture(scope="module")
def catalogue_ids():
    db = TestingSessionLocal()
    try:
        rows = db.execute(text("select id from products")).fetchall()
        return {r[0] for r in rows}
    finally:
        db.close()


def _grounded(data, real_ids) -> bool:
    """Every recommended item is a real catalogue product. A turn that recommends
    NOTHING is grounded only when it states why (no invented look to fill the gap)."""
    items = [i for o in data["recommendations"] for i in o["items"]]
    if not items:
        return bool(data.get("fallback_reason"))
    return all(i["product_id"] in real_ids for i in items)


def _no_base64_in_storage() -> bool:
    db = TestingSessionLocal()
    try:
        n = db.execute(text(
            "select count(*) from stylist_messages where "
            "content like '%base64,%' or intent_json like '%base64,%' or recommendations_json like '%base64,%'"
        )).scalar()
        return n == 0
    finally:
        db.close()


# ── The harness ──────────────────────────────────────────────────────────────
def test_eval_golden_set_meets_the_spec(client: TestClient, mocked_text, vision_ok, catalogue_ids, monkeypatch):
    card = Scorecard()

    # Mode B text turns: grounded, labelled B, no image analysis.
    for prompt in TEXT_PROMPTS:
        res = client.post("/api/v1/stylist/chat", json={"prompt": prompt})
        assert res.status_code == 200, res.text
        data = res.json()
        card.cases += 1
        card.grounded += _grounded(data, catalogue_ids)
        assert data["mode"] == "B" and data["image_analysis"] is None

    # Mode A photo turns: grounded, served model reported, colour attached.
    for prompt in PHOTO_PROMPTS:
        res = client.post("/api/v1/stylist/chat", json={"prompt": prompt, "images": [_png((27, 31, 59))]})
        assert res.status_code == 200, res.text
        data = res.json()
        card.cases += 1
        card.mode_a_cases += 1
        card.grounded += _grounded(data, catalogue_ids)
        served = (data.get("image_analysis") or {}).get("engine", "")
        card.served_model_reported += data["mode"] == "A" and served.startswith("NVIDIA ")
        assert all(o.get("color_coordination") for o in data["recommendations"])

    # Vision down: the shopper gets Mode B with a reason, never a silent answer.
    monkeypatch.setattr(stylist_service_module, "analyze_images", _unavailable_stub())
    card.honest_fallback_cases += 1
    res = client.post("/api/v1/stylist/chat", json={"prompt": "smart casual dinner", "images": [_png((9, 9, 9))]})
    data = res.json()
    card.cases += 1
    card.grounded += _grounded(data, catalogue_ids)
    card.honest_fallbacks += data["mode"] == "B" and bool(data["fallback_reason"])

    print("\n" + card.render())

    # Thresholds from the spec.
    assert card.grounded == card.cases, "SC-001: every recommendation must be a real catalogue product"
    assert card.served_model_reported == card.mode_a_cases, "SC-001/003: Mode A must report the served model"
    assert card.honest_fallbacks == card.honest_fallback_cases, "SC-003: failures must be stated, not hidden"
    assert _no_base64_in_storage(), "SC-005: no base64 image may be stored"


def _unavailable_stub():
    async def fake(images, shopper_request):
        return VisionAnalysis(available=False, reason="The image service did not answer.")
    return fake


def test_eval_wardrobe_toggle_changes_output(client: TestClient, mocked_text):
    headers = _register(client)
    _add_wardrobe_piece(headers["_email"], title="Eval Navy Overshirt", category="Outerwear",
                        color_name="Navy", color_hex="#1B1F3B")
    auth = {"Authorization": headers["Authorization"]}
    on = _post(client, auth, include_wardrobe_items=True)
    off = _post(client, auth, include_wardrobe_items=False)
    assert _pairings(on), "SC-002: with owned pieces and the flag on, pairings must appear"
    assert not _pairings(off), "SC-002: with the flag off, owned pieces must not appear"


def test_eval_extracted_colour_changes_the_palette(client: TestClient, mocked_text, monkeypatch):
    """SC-004: the same look scores differently once the photo's colours are known."""
    async def navy_photo(images, shopper_request):
        return VisionAnalysis(available=True, engine="NVIDIA nvidia/nemotron-3-eval-vision",
                              summary="navy", garments=[])

    monkeypatch.setattr(stylist_service_module, "analyze_images", navy_photo)
    navy = client.post("/api/v1/stylist/chat", json={"prompt": "match", "images": [_png((27, 31, 59))]}).json()
    red = client.post("/api/v1/stylist/chat", json={"prompt": "match", "images": [_png((200, 30, 40))]}).json()
    navy_scores = [o["color_coordination"]["score"] for o in navy["recommendations"]]
    red_scores = [o["color_coordination"]["score"] for o in red["recommendations"]]
    assert navy_scores and red_scores
    assert navy_scores != red_scores, "different photo colours must change the coordination score"


def test_eval_blocked_image_never_reaches_analysis(client: TestClient, mocked_text, monkeypatch):
    """SC-005: a classifier block is final and the vision model is never called."""
    monkeypatch.setattr(type(content_safety_service), "configured", property(lambda self: True))
    calls = {"analysed": 0}

    async def blocked(image_url, *, caption="", context="upload"):
        return SafetyVerdict(safe=False, measured=True, severity=Severity.HARD_BLOCK,
                             categories=["test"], model_id="nvidia/test-safety")

    async def counting(images, shopper_request):
        calls["analysed"] += 1
        return VisionAnalysis(available=False, reason="unused")

    monkeypatch.setattr(content_safety_service, "check_image", blocked)
    monkeypatch.setattr(stylist_service_module, "analyze_images", counting)
    res = client.post("/api/v1/stylist/chat", json={"prompt": "look", "images": [_png((1, 1, 1))]})
    assert res.status_code == 422
    assert calls["analysed"] == 0
