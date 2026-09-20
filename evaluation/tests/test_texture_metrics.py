"""Known-value tests for texture metrics (Phase 0.5 §28)."""
from __future__ import annotations

from PIL import Image

from vton_metrics import texture_metrics


def test_stripe_period_detected(stripe_img):
    img = Image.open(stripe_img).convert("RGB")
    # region: full image; stripes are 20px wide in original 200px -> after resize
    # to 128 the period scales to ~12.8 px
    ac = texture_metrics.local_autocorrelation(img, (0, 0, 200, 200), max_lag=40)
    assert ac["strongest_period"] is not None
    # 40px period in 200px space -> 40*128/200 = 25.6px in 128px space
    assert abs(ac["strongest_period"] - 26) <= 3, ac


def test_plain_image_no_period(solid_img):
    img = Image.open(solid_img).convert("RGB")
    ac = texture_metrics.local_autocorrelation(img, (0, 0, 200, 200), max_lag=24)
    assert ac["strongest_period"] is None
    assert ac["n_significant_peaks"] == 0


def test_period_match_logic():
    ok = texture_metrics.period_match(13, {"strongest_period": 14}, tolerance=4)
    assert ok["period_ok"] is True
    bad = texture_metrics.period_match(13, {"strongest_period": 40}, tolerance=4)
    assert bad["period_ok"] is False
    na = texture_metrics.period_match(None, {"strongest_period": 13})
    assert na["period_ok"] is None


def test_edge_density_higher_for_stripes(stripe_img, solid_img):
    s = texture_metrics.edge_structure(Image.open(stripe_img).convert("RGB"), (0, 0, 200, 200))
    p = texture_metrics.edge_structure(Image.open(solid_img).convert("RGB"), (0, 0, 200, 200))
    assert s["edge_density"] > p["edge_density"] * 5


def test_deterministic(stripe_img):
    img = Image.open(stripe_img).convert("RGB")
    a = texture_metrics.local_autocorrelation(img, (0, 0, 200, 200))
    b = texture_metrics.local_autocorrelation(img, (0, 0, 200, 200))
    assert a == b
