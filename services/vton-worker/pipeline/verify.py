"""Coherent composite-output verification for the VTON worker.

The previous report presented GARMENT_VISIBLE_PASS and PIXEL_DIFF_PASS as a
single story while the two measured different things on different regions
(local garment color coverage vs global change fraction), which produced a
self-contradictory "PASS" alongside a failing paired check. This module
measures both metrics on the SAME garment-target region and PASS requires
EVERY metric to pass - one failing metric forces the combined verdict to
FAIL, never a partial pass.
"""
from PIL import Image
import numpy as np


def verify_composite_output(
    original: Image.Image,
    rendered: Image.Image,
    region: tuple = (0.30, 0.65, 0.10, 0.90),
    change_threshold: float = 0.10,
    color_delta: int = 15,
) -> dict:
    a = np.asarray(original.convert("RGB")).astype(np.int16)
    b = np.asarray(rendered.convert("RGB")).astype(np.int16)
    H, W, _ = a.shape
    y0, y1 = int(region[0] * H), int(region[1] * H)
    x0, x1 = int(region[2] * W), int(region[3] * W)
    ra, rb = a[y0:y1, x0:x1], b[y0:y1, x0:x1]

    changed = float((np.abs(ra - rb).max(axis=2) > 5).mean())

    coverage_in = float(((ra[..., 2] > ra[..., 0] + color_delta) &
                         (ra[..., 2] > ra[..., 1] + color_delta)).mean())
    coverage_out = float(((rb[..., 2] > rb[..., 0] + color_delta) &
                          (rb[..., 2] > rb[..., 1] + color_delta)).mean())
    color_shift = float(coverage_out - coverage_in)

    metric_pixel_change = changed >= change_threshold
    metric_color_shift = color_shift > 0.01
    return {
        "region": {"y0": y0, "y1": y1, "x0": x0, "x1": x1},
        "region_changed_fraction": round(changed, 4),
        "garment_region_coverage_in": round(float(coverage_in), 4),
        "garment_region_coverage_out": round(float(coverage_out), 4),
        "garment_color_shift": round(color_shift, 4),
        "metric_pixel_change": metric_pixel_change,
        "metric_color_shift": metric_color_shift,
        "PASS": bool(metric_pixel_change and metric_color_shift),
        "note": ("Both metrics measured on the same garment-target region; "
                 "PASS requires both."),
    }
