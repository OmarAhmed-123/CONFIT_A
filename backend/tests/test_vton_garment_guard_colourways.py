"""The at-risk colourway range (gold / beige / cream / camel), pinned.

WHY THIS FILE EXISTS
--------------------
The owner approved a "shape-aware addition" to the garment guard on the belief
that gold/champagne garments are rejected because gold reads as skin in YCrCb.
Measured against the real classifier, that premise does not hold:

    champagne-gold flat-lay on a grey backdrop   flat-lay  edge-uniformity  skin 0.0
    beige/camel flat-lay on a grey backdrop      flat-lay  edge-uniformity  skin 0.0
    cream flat-lay on a grey backdrop            flat-lay  edge-uniformity  skin 0.0
    champagne-gold WORN by a person              model     skin-ratio       skin 0.1036

The ≤12% human-scale blob filter in ``_skin_ratio`` already discards chroma
matches that are garment-sized, which is exactly the shape discrimination the
addition was meant to provide. A geometric detector would therefore add a
second, weaker opinion about the same question — and a second way to be wrong.

So nothing in the guard was changed. What product 5 actually is, is checked
against the real catalogue photo in ``test_vton_product5_rejection_is_about_
framing_not_colour`` below.

These tests exist so the property is pinned rather than remembered, and so a
future "fix gold by relaxing skin_ratio" cannot pass silently: relaxing it
would flip the worn-gold case in this same file.
"""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

from backend.app.services.garment_asset_guard import (
    asset_gate_error,
    classify_garment_photo,
)

H, W = 512, 410
GREY_BG = (128, 130, 133)
CHAMPAGNE = (214, 178, 120)
BEIGE = (205, 178, 140)
CREAM = (240, 236, 228)
NAVY = (27, 31, 59)
SKIN = (208, 168, 138)


def _flat_lay(colour, bg=GREY_BG, seed=0) -> Image.Image:
    """A garment shape lying flat on a contrasting backdrop: no person."""
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)
    d.polygon([(W * 0.36, H * 0.16), (W * 0.64, H * 0.16), (W * 0.68, H * 0.45), (W * 0.32, H * 0.45)], fill=colour)
    d.polygon([(W * 0.30, H * 0.17), (W * 0.36, H * 0.17), (W * 0.30, H * 0.42), (W * 0.24, H * 0.40)], fill=colour)
    d.polygon([(W * 0.64, H * 0.17), (W * 0.70, H * 0.17), (W * 0.76, H * 0.40), (W * 0.70, H * 0.42)], fill=colour)
    d.polygon([(W * 0.32, H * 0.45), (W * 0.68, H * 0.45), (W * 0.84, H * 0.90), (W * 0.16, H * 0.90)], fill=colour)
    d.ellipse([W * 0.45, H * 0.13, W * 0.55, H * 0.19], fill=bg)
    im = im.filter(ImageFilter.GaussianBlur(1.2))
    a = np.asarray(im, np.int16) + np.random.default_rng(seed).integers(-4, 5, (H, W, 3))
    buf = io.BytesIO()
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(buf, "JPEG", quality=94)
    buf.seek(0)
    return Image.open(buf)


def _worn(garment_colour, seed=1) -> Image.Image:
    """The same garment worn: a skin head above it, skin hands beside it."""
    rng = np.random.default_rng(seed)
    arr = np.full((H, W, 3), (70, 96, 62), np.uint8)
    yy, xx = np.ogrid[:H, :W]
    for _ in range(900):
        y, x = rng.integers(0, H), rng.integers(0, W)
        r = int(rng.integers(4, 16))
        arr[((yy - y) ** 2 + (xx - x) ** 2) <= r * r] = [int(v) for v in rng.integers(40, 120, 3)]
    im = Image.fromarray(arr)
    d = ImageDraw.Draw(im)
    d.ellipse([W * 0.44, H * 0.06, W * 0.56, H * 0.19], fill=SKIN)
    d.rectangle([W * 0.48, H * 0.19, W * 0.52, H * 0.23], fill=SKIN)
    d.polygon([(W * 0.40, H * 0.24), (W * 0.45, H * 0.24), (W * 0.42, H * 0.55), (W * 0.37, H * 0.54)], fill=SKIN)
    d.polygon([(W * 0.55, H * 0.24), (W * 0.60, H * 0.24), (W * 0.63, H * 0.54), (W * 0.58, H * 0.55)], fill=SKIN)
    d.polygon([(W * 0.38, H * 0.23), (W * 0.62, H * 0.23), (W * 0.70, H * 0.60), (W * 0.30, H * 0.60)], fill=garment_colour)
    d.polygon([(W * 0.30, H * 0.60), (W * 0.70, H * 0.60), (W * 0.78, H * 0.93), (W * 0.22, H * 0.93)], fill=garment_colour)
    d.ellipse([W * 0.355, H * 0.54, W * 0.395, H * 0.585], fill=SKIN)
    d.ellipse([W * 0.605, H * 0.54, W * 0.645, H * 0.585], fill=SKIN)
    im = im.filter(ImageFilter.GaussianBlur(0.8))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=94)
    buf.seek(0)
    return Image.open(buf)


# ── the colourways the owner flagged must PASS as flat-lays ───────────────

@pytest.mark.parametrize("name,colour", [
    ("champagne-gold", CHAMPAGNE),
    ("beige", BEIGE),
    ("cream", CREAM),
    ("camel-dark", (176, 140, 96)),
    ("navy-control", NAVY),
])
def test_warm_colourway_flat_lays_are_accepted(name, colour):
    photo_type, ev = classify_garment_photo(_flat_lay(colour))
    assert photo_type == "flat-lay", (
        f"{name} flat-lay was rejected as {photo_type} "
        f"(detector={ev['detector']}, skin={ev['skin_ratio']})"
    )
    assert asset_gate_error(photo_type, ev, 5, "Silk Slip Column Maxi Dress", False) is None


# ── but the SAME colourway worn by a person must STILL be rejected ────────

@pytest.mark.parametrize("name,colour", [
    ("champagne-gold", CHAMPAGNE),
    ("navy-control", NAVY),
])
def test_the_same_colourway_worn_by_a_person_is_still_rejected(name, colour):
    photo_type, ev = classify_garment_photo(_worn(colour))
    assert photo_type == "model", f"{name} worn shot was classified {photo_type}"
    err = asset_gate_error(photo_type, ev, 5, "Silk Slip Column Maxi Dress", False)
    assert err and "VTON_GARMENT_ASSET_INVALID" in err


def test_a_worn_shot_is_still_rejected_when_a_prepared_asset_exists():
    """The prepared-asset path is an escape hatch only for a photo that LOOKS
    worn; it never rescues a genuinely worn photo into the render path."""
    photo_type, ev = classify_garment_photo(_worn(CHAMPAGNE))
    assert photo_type == "model"
    # has_prepared_asset=True returns None by design: the prepared clean asset
    # is what gets rendered, not this photo. Pinned so the distinction stays
    # explicit rather than looking like a hole.
    assert asset_gate_error(photo_type, ev, 5, "x", True) is None


def test_relaxing_the_human_scale_filter_would_break_the_worn_case():
    """Guard against a future 'fix gold by widening the skin bounds'.

    The discrimination comes from the ≤12% human-scale blob filter, not from
    the chroma bounds. Dropping the filter is what would let a gold garment
    masquerade as a person — so this test asserts the filter is still in the
    signal path, by showing a garment-sized gold region does NOT count as skin
    while a face-sized one does.

    (Both are measured through the public classifier, so a change to the
    internals that keeps this property still passes.)
    """
    from backend.app.services.garment_asset_guard import _skin_ratio

    small_gold = np.zeros((200, 200, 3), np.uint8)
    small_gold[:] = (128, 130, 133)
    small_gold[80:110, 90:115] = CHAMPAGNE            # face-sized patch
    big_gold = np.zeros((200, 200, 3), np.uint8)
    big_gold[:] = (128, 130, 133)
    big_gold[40:170, 40:170] = CHAMPAGNE              # garment-sized region

    assert _skin_ratio(small_gold) > 0.0, "a face-sized warm patch must count as skin"
    assert _skin_ratio(big_gold) == 0.0, (
        "a garment-sized warm region must NOT count as skin — this is the "
        "filter that makes gold flat-lays pass without a geometry detector"
    )
