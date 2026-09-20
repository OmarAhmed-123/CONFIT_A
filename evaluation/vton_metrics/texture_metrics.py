"""Texture & pattern structure metrics (Phase 0.5).

Complements color: detects whether a pattern (stripes/check/floral/plain)
survives try-on in terms of (a) edge structure, (b) spatial frequency
(spectral centroid), (c) local correlation texture. Deterministic,
license-clean (scipy/skimage only).
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from .imaging import crop_box, to_array


def _gray(img):
    return to_array(crop_box(img, (0, 0, img.size[0], img.size[1]))) if False else to_array(img)


def edge_structure(img, box: tuple[int, int, int, int]) -> dict:
    crop = crop_box(img, box).convert("L").resize((128, 128))
    g = to_array(crop)
    gx = ndimage.sobel(g, axis=1)
    gy = ndimage.sobel(g, axis=0)
    mag = np.hypot(gx, gy)
    theta = np.arctan2(gy, gx)
    # 8-bin orientation histogram of strong edges
    strong = mag > mag.mean()
    hist = np.zeros(8)
    bins = (np.linspace(-np.pi, np.pi, 9))
    idx = np.digitize(theta[strong].ravel(), bins) - 1
    idx = idx[(idx >= 0) & (idx < 8)]
    if len(idx):
        hist += np.bincount(idx, minlength=8)
        hist /= hist.sum()
    return {
        "metric": "texture_edge_structure",
        "edge_density": round(float((mag > 30).mean()), 4),
        "orientation_entropy": round(float(_entropy(hist)), 4),
        "orientation_hist": [round(float(x), 4) for x in hist],
    }


def _entropy(p):
    p = p[p > 0]
    return float(-(p * np.log2(p)).sum())


def spectral_centroid(img, box: tuple[int, int, int, int]) -> dict:
    """Normalized dominant spatial frequency (higher = finer texture)."""
    crop = crop_box(img, box).convert("L").resize((128, 128))
    g = to_array(crop)
    g = g - g.mean()
    F = np.fft.fftshift(np.abs(np.fft.fft2(g)))
    F = F / (F.max() + 1e-12)
    h, w = F.shape
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot(yy - h / 2, xx - w / 2)
    max_r = r.max()
    weights = r / max_r
    return {
        "metric": "texture_spectral_centroid",
        "centroid": round(float((F * weights).sum()), 5),
    }


def _ac_curve(g: np.ndarray, axis: int, max_lag: int) -> np.ndarray:
    """Normalized autocorrelation along `axis` (0=vertical, 1=horizontal)."""
    g = g - g.mean(axis=axis, keepdims=True)
    ac = np.zeros(max_lag)
    for lag in range(1, max_lag):
        a = np.take(g, range(0, g.shape[axis] - lag), axis=axis)
        b = np.take(g, range(lag, g.shape[axis]), axis=axis)
        denom = np.sqrt((a * a).sum() * (b * b).sum()) + 1e-12
        ac[lag - 1] = (a * b).sum() / denom
    return ac


def local_autocorrelation(img, box: tuple[int, int, int, int], max_lag: int = 40) -> dict:
    """Axis-aware normalized autocorrelation — period detection for stripes/checks.

    Computes both axes; the axis with the stronger peak amplitude is reported
    (vertical stripes -> horizontal-axis period). Deterministic.
    """
    crop = crop_box(img, box).convert("L").resize((128, 128))
    g = to_array(crop)
    acs = {0: _ac_curve(g, 0, max_lag), 1: _ac_curve(g, 1, max_lag)}

    def peaks_of(ac):
        peaks = []
        for i in range(1, max_lag - 1):
            if ac[i] > ac[i - 1] and ac[i] >= ac[i + 1] and ac[i] > 0.15:
                peaks.append({"lag": int(i + 1), "value": round(float(ac[i]), 4)})
        peaks.sort(key=lambda d: -d["value"])
        return peaks

    best_axis, best_peaks = None, []
    for axis in (1, 0):  # horizontal axis first (vertical stripes are common)
        pk = peaks_of(acs[axis])
        if not best_peaks or (pk and (not best_peaks or pk[0]["value"] > best_peaks[0]["value"])):
            best_axis, best_peaks = axis, pk
    return {
        "metric": "texture_autocorrelation",
        "axis": "horizontal" if best_axis == 1 else "vertical",
        "strongest_period": best_peaks[0]["lag"] if best_peaks else None,
        "strongest_period_value": best_peaks[0]["value"] if best_peaks else 0.0,
        "n_significant_peaks": len(best_peaks),
        "peaks": best_peaks[:3],
        "ac_vertical": [round(float(x), 3) for x in acs[0][:8]],
        "ac_horizontal": [round(float(x), 3) for x in acs[1][:8]],
    }


def period_match(expected_period: int | None, measured: dict, tolerance: int = 4) -> dict:
    """Compare measured dominant period against fixture ground truth (stripes/checks)."""
    if expected_period is None:
        return {"period_ok": None, "note": "no expected period (plain garment)"}
    got = measured.get("strongest_period")
    return {
        "period_ok": (got is not None and abs(got - expected_period) <= tolerance) if got is not None else False,
        "expected_period": expected_period,
        "measured_period": got,
    }


def texture_report(img, box, expected_period: int | None = None) -> dict:
    edge = edge_structure(img, box)
    spec = spectral_centroid(img, box)
    ac = local_autocorrelation(img, box)
    rep = {"edge": edge, "spectrum": spec, "autocorrelation": ac}
    if expected_period is not None:
        rep["period_check"] = period_match(expected_period, ac)
    return rep
