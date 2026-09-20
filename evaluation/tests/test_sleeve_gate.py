"""Regression tests — long-sleeve sleeve-transfer defect gate (Phase 1 §7).

Covers:
  1. _ciede2000_vec vs the scalar reference (known values, extreme L*, no NaN)
  2. lightness-conditioned ΔE removes a pure lightness shift (design property)
  3. garment_sleeve_drop geometry classifier on deterministic synthetic flat lays
  4. pure gate mapping logic
  5. Phase 0.5 catch-up: S_g001 (judge 10/10) fails the gate — SKIPs if the
     gitignored result renders are absent (fresh clone).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from vton_metrics import color_metrics
from vton_metrics.imaging import ciede2000, rgb_to_lab
from vton_metrics.color_metrics import _ciede2000_vec, region_delta_e_lightness_conditioned
from vton_metrics.sleeve_metrics import (
    garment_sleeve_drop, gate_status_from, _content_box)

EVAL_ROOT = Path(__file__).resolve().parent.parent


# ---------- 1. CIEDE2000 vector vs scalar ----------

def test_ciede2000_vec_matches_scalar():
    rng = np.random.default_rng(42)
    a = rng.uniform([0, -128, -128], [100, 128, 128], (25, 3))
    b = a + rng.uniform(-30, 30, (25, 3))
    vec = _ciede2000_vec(a, b)
    sca = np.array([ciede2000(x, y) for x, y in zip(a, b)])
    assert np.allclose(vec, sca, atol=1e-8)


def test_ciede2000_vec_extreme_l_no_nan():
    # L* near 0/100 previously produced NaN via the full-Sharma L2' sqrt term
    a = np.array([[1.0, 0, 0], [99.0, 1, -1], [18.0, 10, 10], [82.0, -10, -10]])
    b = np.array([[95.0, 5, -5], [5.0, -3, 3], [50.0, 0, 0], [50.0, 20, 20]])
    v = _ciede2000_vec(a, b)
    assert not np.isnan(v).any()
    assert (v >= 0).all()


def test_ciede2000_zero_for_identical():
    lab = np.array([[50.0, 12.3, -8.7]])
    assert _ciede2000_vec(lab, lab)[0] < 1e-9


# ---------- 2. lightness-conditioned ΔE ----------

def _synth_pair(tmp_path, shift_L: float):
    """Two garment-region pairs: identical hue/chroma, output shifted in L*."""
    arr = np.full((64, 64, 3), (70, 90, 140), dtype=np.uint8)
    ref = Image.fromarray(arr)
    # shift lightness by re-rendering the same hue with a luminance scale
    import colorsys
    r, g, b = 70 / 255, 90 / 255, 140 / 255
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l2 = min(0.98, max(0.02, l + shift_L))
    r2, g2, b2 = colorsys.hls_to_rgb(h, l2, s)
    out_arr = np.full((64, 64, 3), (int(r2 * 255), int(g2 * 255), int(b2 * 255)), dtype=np.uint8)
    out = Image.fromarray(out_arr)
    return ref, out


def test_lc_delta_e_reduces_pure_lightness_shift(tmp_path):
    ref, out = _synth_pair(tmp_path, shift_L=0.15)
    lc = region_delta_e_lightness_conditioned(out, (0, 0, 64, 64), ref, (0, 0, 64, 64), grid=32)
    assert lc["delta_e_raw_mean"] > 8.0, lc  # the uncorrected metric sees the shift
    assert lc["delta_e_lc_mean"] < lc["delta_e_raw_mean"] * 0.5, lc
    assert abs(lc["lightness_offset_dL"]) > 5.0, lc


def test_lc_delta_e_zero_for_identical(tmp_path):
    arr = np.full((48, 48, 3), (120, 60, 90), dtype=np.uint8)
    img = Image.fromarray(arr)
    lc = region_delta_e_lightness_conditioned(img, (0, 0, 48, 48), img, (0, 0, 48, 48), grid=32)
    assert lc["delta_e_lc_mean"] < 0.5, lc
    assert abs(lc["lightness_offset_dL"]) < 0.5


# ---------- 3. sleeve-drop geometry classifier ----------

def _flat_lay(tmp_path, name, long_sleeves: bool, horizontal: bool = False):
    """Deterministic synthetic garment flat lay on white background."""
    W, H = 400, 500
    img = Image.new("RGB", (W, H), (250, 250, 250))
    d = ImageDraw.Draw(img)
    color = (30, 30, 35)
    # torso: 140..260 x, 80..420 y
    d.rectangle([140, 80, 260, 420], fill=color)
    # shoulders
    d.polygon([(140, 80), (90, 100), (90, 130), (140, 150)], fill=color)
    d.polygon([(260, 80), (310, 100), (310, 130), (260, 150)], fill=color)
    if horizontal:
        # sleeves laid horizontally at shoulder height
        d.rectangle([10, 100, 90, 150], fill=color)
        d.rectangle([310, 100, 390, 150], fill=color)
    elif long_sleeves:
        # separated vertical sleeves alongside the torso (gap >= 8 px)
        d.rectangle([70, 100, 128, 420], fill=color)   # gap 128..140 = 12px
        d.rectangle([272, 100, 330, 420], fill=color)  # gap 260..272 = 12px
    else:
        # short sleeves: stubs ending mid-chest
        d.rectangle([70, 100, 128, 200], fill=color)
        d.rectangle([272, 100, 330, 200], fill=color)
    p = tmp_path / name
    img.save(p, "JPEG", quality=95)
    return p


def test_drop_long_sleeve_vertical(tmp_path):
    p = _flat_lay(tmp_path, "long.jpg", long_sleeves=True)
    r = garment_sleeve_drop(p)
    assert r["status"] == "OK" and r["sleeve_drop_ratio"] > 0.45, r
    assert r["is_long_sleeve_candidate"] is True


def test_drop_short_sleeve(tmp_path):
    p = _flat_lay(tmp_path, "short.jpg", long_sleeves=False)
    r = garment_sleeve_drop(p)
    assert r["sleeve_drop_ratio"] is not None
    assert r["is_long_sleeve_candidate"] is False, r


def test_drop_horizontal_sleeve(tmp_path):
    p = _flat_lay(tmp_path, "horiz.jpg", long_sleeves=True, horizontal=True)
    r = garment_sleeve_drop(p)
    assert r["is_long_sleeve_candidate"] is False, r  # no separated-vertical signature


def test_drop_empty_image(tmp_path):
    p = tmp_path / "empty.jpg"
    Image.new("RGB", (100, 100), (250, 250, 250)).save(p)
    assert garment_sleeve_drop(p)["status"] == "NO_CONTENT"


# ---------- 4. pure gate mapping ----------

def test_gate_mapping():
    assert gate_status_from(False, {"status": "OK", "overall": "SLEEVES_MISSING"}) == "N/A_SHORT_SLEEVE"
    assert gate_status_from(True, {"status": "OK", "overall": "SLEEVES_PRESENT"}) == "PASS"
    assert gate_status_from(True, {"status": "OK", "overall": "SLEEVES_PARTIAL"}) == "FAIL_SLEEVES_INCOMPLETE"
    assert gate_status_from(True, {"status": "OK", "overall": "SLEEVES_MISSING"}) == "FAIL_SLEEVES_INCOMPLETE"
    assert gate_status_from(True, {"status": "NO_POSE"}) == "NO_POSE"


# ---------- 5. Phase 0.5 catch-up (needs saved renders; skip on fresh clone) ----------

S_G001 = EVAL_ROOT / "results" / "outputs" / "S_g001-L1-g001.jpg"


@pytest.mark.skipif(not (S_G001.exists() and
                         (EVAL_ROOT / "fixtures" / "garments" / "g001.jpg").exists()),
                    reason="gitignored Phase 0.5 renders/fixtures not present")
def test_phase05_s_g001_catch_up_fails_sleeve_gate():
    """S_g001 was rated 10/10 by the VLM judge but is a sleeveless render of a
    long-sleeve flat lay (g001). The gate must flag it."""
    from vton_metrics.sleeve_metrics import sleeve_gate_report
    rep = sleeve_gate_report(EVAL_ROOT / "fixtures" / "persons" / "p001.jpg",
                             S_G001,
                             EVAL_ROOT / "fixtures" / "garments" / "g001.jpg")
    assert rep["expected_full_sleeves"] is True, rep["garment_sleeve_drop"]
    assert rep["gate_status"] == "FAIL_SLEEVES_INCOMPLETE", rep
