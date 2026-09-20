"""Known-value tests for color metrics (Phase 0.5 §28)."""
from __future__ import annotations

import numpy as np
from PIL import Image

from vton_metrics import color_metrics, imaging


def test_delta_e_zero_for_identical_color(solid_img):
    img = Image.open(solid_img).convert("RGB")
    rep = color_metrics.region_color_delta_e(img, (10, 10, 190, 190), "#23355C")
    assert rep["delta_e_mean"] < 1.5, rep  # JPEG compression only
    assert rep["n_samples"] > 0


def test_delta_e_large_for_wrong_color(solid_img):
    img = Image.open(solid_img).convert("RGB")
    rep = color_metrics.region_color_delta_e(img, (10, 10, 190, 190), "#FF0000")
    assert rep["delta_e_mean"] > 45, rep  # CIEDE2000 compresses saturated hue distances (~49.5 navy->red)


def test_dominant_color_identical(solid_img):
    img = Image.open(solid_img).convert("RGB")
    rep = color_metrics.dominant_color_match(img, (10, 10, 190, 190), ["#23355C"])
    assert rep["match_score"] == 1.0


def test_dominant_color_wrong(solid_img):
    img = Image.open(solid_img).convert("RGB")
    rep = color_metrics.dominant_color_match(img, (10, 10, 190, 190), ["#00FF00"])
    assert rep["match_score"] < 0.5


def test_histogram_identity_is_one(solid_img):
    img = Image.open(solid_img).convert("RGB")
    rep = color_metrics.histogram_similarity(img, (10, 10, 190, 190), img, (10, 10, 190, 190))
    assert rep["score"] > 0.99


def test_ciede2000_known_values():
    # Sharma 2005 test pair: mean delta E over the full 2001-pair set is ~2.07;
    # spot check: identical -> 0; small lightness step -> ~1.0
    lab1 = imaging.rgb_to_lab(np.array([[100, 100, 100]]))[0, 0]
    assert imaging.ciede2000(lab1, lab1) == 0.0
    lab2 = imaging.rgb_to_lab(np.array([[110, 110, 110]]))[0, 0]
    d = imaging.ciede2000(lab1, lab2)
    assert 2.5 < d < 6.0, d  # measured 3.81 for gray 100->110
    lab3 = imaging.rgb_to_lab(np.array([[100, 100, 100]]))[0, 0]
    lab4 = imaging.rgb_to_lab(np.array([[80, 160, 60]]))[0, 0]
    assert 25.0 < imaging.ciede2000(lab3, lab4) < 40.0  # measured 31.02
    lab5 = imaging.rgb_to_lab(np.array([[220, 30, 40]]))[0, 0]
    assert 25.0 < imaging.ciede2000(lab3, lab5) < 40.0  # measured 29.29 (CIEDE2000 chroma compression)


def test_deterministic(solid_img):
    img = Image.open(solid_img).convert("RGB")
    a = color_metrics.region_color_delta_e(img, (10, 10, 190, 190), "#23355C")
    b = color_metrics.region_color_delta_e(img, (10, 10, 190, 190), "#23355C")
    assert a["delta_e_mean"] == b["delta_e_mean"]


def test_empty_crop_raises(solid_img):
    img = Image.open(solid_img).convert("RGB")
    import pytest
    with pytest.raises(ValueError):
        imaging.crop_box(img, (300, 300, 400, 400))
