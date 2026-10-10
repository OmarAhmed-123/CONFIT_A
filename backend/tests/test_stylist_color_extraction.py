"""Image colour extraction feeds ColorHarmonyEngine — FR-007, SC-004, STY-06.

* Palette extraction is deterministic and works on the pixels, so it cannot
  hallucinate a colour the photo does not contain.
* A colour the model claims but the pixels do not support is marked uncertain,
  and never steers the palette.
* The extracted palette changes the coordination result compared with a
  rules-only view (no image) — the test proves the influence, not just the wiring.
"""
from __future__ import annotations

import io

import pytest
from PIL import Image

from backend.app.services.styling.color_harmony import ColorHarmonyEngine
from backend.app.services.stylist_image_intake import (
    ImageIntakeError,
    PaletteColor,
    color_family_for_rgb,
    extract_palette,
    merge_palettes,
    parse_image_data_url,
)
from backend.app.services.stylist_service import _coordinate_with_palette, _cross_check_colours
from backend.app.services.stylist_vision import GarmentObservation, VisionAnalysis
import base64


def _image(colour, size=(80, 80), fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, format=fmt)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return parse_image_data_url(f"data:image/{fmt.lower()};base64,{b64}")


def _two_tone(top, bottom, size=(80, 80)):
    img = Image.new("RGB", size, top)
    for x in range(size[0]):
        for y in range(size[1] // 2, size[1]):
            img.putpixel((x, y), bottom)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return parse_image_data_url(f"data:image/png;base64,{b64}")


# ─────────────────────────── deterministic extraction ───────────────────────────

@pytest.mark.parametrize("rgb,family", [
    ((27, 31, 59), "navy"),
    ((200, 30, 40), "red"),
    ((250, 250, 248), "white"),
    ((18, 18, 18), "black"),
    ((216, 199, 181), "beige"),
    ((120, 120, 120), "grey"),
    ((197, 160, 89), "gold"),
])
def test_rgb_maps_to_catalogue_family(rgb, family):
    assert color_family_for_rgb(rgb) == family


def test_extraction_is_deterministic_for_identical_bytes():
    img = _image((27, 31, 59))
    assert extract_palette(img) == extract_palette(img)


def test_solid_navy_photo_extracts_navy_as_dominant():
    palette = extract_palette(_image((27, 31, 59)))
    assert palette, "a real photo yields a palette"
    assert palette[0].family == "navy"
    assert palette[0].share > 0.9


def test_two_tone_photo_yields_both_colours_by_share():
    palette = extract_palette(_two_tone((200, 30, 40), (27, 31, 59)))
    families = [c.family for c in palette if c.share >= 0.2]
    assert "red" in families and "navy" in families


def test_undecodable_bytes_raise_intake_error_not_a_guess():
    from backend.app.services.stylist_image_intake import ParsedImage
    with pytest.raises(ImageIntakeError):
        extract_palette(ParsedImage(mime="image/png", data=b"\x89PNG\r\n\x1a\n" + b"\x00" * 40))


# ─────────────────────── model claims vs. pixel evidence ────────────────────────

def test_model_colour_supported_by_pixels_is_confirmed():
    pixels = [extract_palette(_image((27, 31, 59)))]
    vision = VisionAnalysis(available=True, garments=[
        GarmentObservation(category="outerwear", description="blazer", color_family="navy"),
    ])
    checks, palette_items = _cross_check_colours(pixels, vision)
    assert checks[0]["status"] == "confirmed"
    assert any(p["color_family"] == "navy" for p in palette_items)


def test_model_colour_not_in_pixels_is_uncertain():
    pixels = [extract_palette(_image((27, 31, 59)))]  # the photo is navy
    vision = VisionAnalysis(available=True, garments=[
        GarmentObservation(category="top", description="shirt", color_family="emerald"),
    ])
    checks, palette_items = _cross_check_colours(pixels, vision)
    assert checks[0]["status"] == "uncertain"
    assert checks[0]["corroborated_by_pixels"] is False
    # The unsupported colour does not enter the palette used for coordination.
    assert all(p["color_family"] != "emerald" for p in palette_items)


def test_garment_without_colour_is_not_scored():
    pixels = [extract_palette(_image((27, 31, 59)))]
    vision = VisionAnalysis(available=True, garments=[
        GarmentObservation(category="top", description="shirt", color_family=None),
    ])
    checks, _ = _cross_check_colours(pixels, vision)
    assert checks == []


# ───────────────────── extracted palette changes coordination ───────────────────

def _look(*families):
    positions = ["top", "bottom", "footwear", "accessory"]
    return {"items": [
        {"position": positions[i % len(positions)], "color_family": f, "product_title": f"{f} piece"}
        for i, f in enumerate(families)
    ]}


def test_image_palette_changes_the_coordination_score():
    look = _look("navy", "beige", "black")
    rules_only = ColorHarmonyEngine.evaluate_palette(look["items"])["color_harmony_score"]

    # A photo dominated by a clashing emerald/red palette must move the score.
    palette_items = [
        {"color_family": "emerald", "position": "image", "product_title": ""},
        {"color_family": "red", "position": "image", "product_title": ""},
    ]
    with_image = _coordinate_with_palette(look, palette_items)
    assert with_image["score"] != rules_only, "the photo's palette must influence the result"
    assert with_image["image_colours"] == ["emerald", "red"]
    assert with_image["method"].startswith("ColorHarmonyEngine")


def test_merge_palettes_combines_shares_per_family():
    a = [PaletteColor(hex="#1B1F3B", family="navy", share=0.6), PaletteColor(hex="#FFFFFF", family="white", share=0.4)]
    b = [PaletteColor(hex="#1C2140", family="navy", share=0.5), PaletteColor(hex="#C81E28", family="red", share=0.5)]
    merged = merge_palettes([a, b])
    families = {c.family: c.share for c in merged}
    assert families["navy"] > families["red"]
    assert set(families) == {"navy", "white", "red"}
    assert sum(families.values()) == pytest.approx(1.0, abs=0.01)
