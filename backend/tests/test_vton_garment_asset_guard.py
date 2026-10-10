"""CPU unit tests for the P0 garment-asset gate (ghost-hands remediation).

Synthetic catalog shots: a flat-lay (uniform backdrop + garment rect) vs an
on-model shot (skin head/hands + worn garment). No GPU, no network, no DB.
"""
import io

import numpy as np
import pytest
from PIL import Image

from backend.app.services.garment_asset_guard import (
    asset_gate_error,
    classify_garment_photo,
)

H, W = 400, 320
SKIN = (210, 170, 140)
NAVY = (27, 31, 59)
WHITE_BG = (245, 245, 245)


def _img(arr: np.ndarray) -> Image.Image:
    return Image.open(io.BytesIO(_bytes(arr)))


def _bytes(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _flat_lay() -> np.ndarray:
    img = np.zeros((H, W, 3), np.uint8)
    img[:] = WHITE_BG
    img[H // 4 : 3 * H // 4, W // 4 : 3 * W // 4] = NAVY  # garment on backdrop
    return img


def _on_model() -> np.ndarray:
    img = np.zeros((H, W, 3), np.uint8)
    img[:] = (120, 118, 110)  # busy street-ish backdrop, not uniform
    yy, xx = np.ogrid[:H, :W]
    head = ((yy - 60) ** 2 + (xx - W // 2) ** 2) <= 30**2
    img[head] = SKIN
    img[int(0.30 * H) :, W // 5 : 4 * W // 5] = NAVY       # worn jacket
    for cx in (W // 2 - 40, W // 2 + 40):                  # hands at waist
        blob = ((yy - int(0.62 * H)) ** 2) // 4 + (xx - cx) ** 2 <= 18**2
        img[blob] = SKIN
    return img


def test_classifier_flags_on_model_shot():
    photo_type, ev = classify_garment_photo(_img(_on_model()))
    assert photo_type == "model"
    assert ev["detector"] == "skin-ratio"
    assert ev["skin_ratio"] >= 0.015


def test_classifier_accepts_flat_lay():
    photo_type, ev = classify_garment_photo(_img(_flat_lay()))
    assert photo_type == "flat-lay"
    assert ev["detector"] == "background-uniformity"


def test_classifier_conservative_when_inconclusive():
    # busy two-colour checker backdrop (no uniform dominance, no skin chroma)
    img = np.zeros((H, W, 3), np.uint8)
    ys = (np.arange(H) // 8) % 2
    xs = (np.arange(W) // 8) % 2
    checker = (ys[:, None] ^ xs[None, :]).astype(bool)
    img[checker] = (0, 90, 0)
    img[~checker] = (90, 0, 90)
    img[H // 3 : 2 * H // 3, W // 4 : 3 * W // 4] = NAVY  # garment, no person
    photo_type, ev = classify_garment_photo(Image.fromarray(img))
    assert photo_type == "model"
    assert ev["detector"] == "conservative-default"


def test_gate_blocks_on_model_without_prepared_asset():
    _, ev = classify_garment_photo(_img(_on_model()))
    err = asset_gate_error("model", ev, 2, "Tuxedo Peak Lapel Evening Dinner Jacket", False)
    assert err and "VTON_GARMENT_ASSET_INVALID" in err and "ghost hands" in err


def test_gate_allows_flat_lay_and_prepared_assets():
    _, ev = classify_garment_photo(_img(_flat_lay()))
    assert asset_gate_error("flat-lay", ev, 1, "Blazer", False) is None
    assert asset_gate_error("model", ev, 2, "Tuxedo", True) is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
