"""Garment color fidelity metrics (Phase 0.5 — NOT a single embedding score).

Three complementary, license-clean signals:
  1. delta_e_mean / delta_e_p95   — CIEDE2000 between expected garment color and
     measured region color (mean + tail).
  2. dominant_color_match         — nearest-neighbor check of measured dominant
     colors against expected color set.
  3. histogram_similarity         — channel histogram intersection (shape/color mix).

All region-based: expects (img, box, expected_color_lab or hex). Deterministic.
"""
from __future__ import annotations

import numpy as np

from .imaging import (crop_box, dominant_color, hex2rgb, histogram,
                      histogram_intersection, lab_to_rgb_hex_lab, rgb_to_lab,
                      to_array)


def region_color_delta_e(img, box: tuple[int, int, int, int], expected_hex: str) -> dict:
    crop = crop_box(img, box)
    arr = to_array(crop) / 255.0
    lab = rgb_to_lab(arr).reshape(-1, 3)
    exp = lab_to_rgb_hex_lab(expected_hex)
    de = np.array([_de2k(l, exp) for l in lab[:: max(1, len(lab) // 4096)]])  # subsample for speed
    de.sort()
    return {
        "metric": "garment_color_delta_e",
        "expected_hex": expected_hex,
        "delta_e_mean": round(float(de.mean()), 3),
        "delta_e_p50": round(float(de[int(0.5 * (len(de) - 1))]), 3),
        "delta_e_p95": round(float(de[int(0.95 * (len(de) - 1))]), 3),
        "n_samples": int(len(de)),
    }


def _de2k(lab: np.ndarray, ref: np.ndarray) -> float:
    from .imaging import ciede2000
    return ciede2000(lab, ref)


def _ciede2000_vec(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    """Vectorized CIEDE2000 over (N,3) Lab arrays.

    Mirrors imaging.ciede2000 (the repo's scalar reference implementation)
    exactly, including its dLp = L2 - L1 simplification (the full Sharma
    L2' term's sqrt argument goes negative for L* < ~18 or > ~82 -> NaN).
    """
    L1, a1, b1 = lab1[:, 0], lab1[:, 1], lab1[:, 2]
    L2, a2, b2 = lab2[:, 0], lab2[:, 1], lab2[:, 2]
    C1 = np.hypot(a1, b1)
    C2 = np.hypot(a2, b2)
    Cbar = (C1 + C2) / 2.0
    Cbar7 = Cbar ** 7
    G = 0.5 * (1.0 - np.sqrt(Cbar7 / (Cbar7 + 25.0 ** 7)))
    a1p = (1.0 + G) * a1
    a2p = (1.0 + G) * a2
    C1p = np.hypot(a1p, b1)
    C2p = np.hypot(a2p, b2)
    dCp = C1p - C2p
    dLp = L2 - L1
    hp1 = np.mod(np.degrees(np.arctan2(b1, a1p)), 360.0)
    hp2 = np.mod(np.degrees(np.arctan2(b2, a2p)), 360.0)
    big = np.abs(hp1 - hp2) > 180.0
    hp1 = np.where(big, hp1 + 360.0, hp1)
    hbar = (hp1 + hp2) / 2.0
    hbar = np.where(big, hbar - 360.0, hbar)
    dhp = hp2 - hp1
    dhp = np.where(np.abs(dhp) > 180.0, dhp - 360.0 * np.sign(dhp), dhp)
    dth = 2.0 * np.sqrt(C1p * C2p) * np.sin(np.radians(dhp) / 2.0)
    T = (1.0 - 0.17 * np.cos(np.radians(hbar - 30.0)) + 0.24 * np.cos(np.radians(2.0 * hbar))
         + 0.32 * np.cos(np.radians(3.0 * hbar + 6.0)) - 0.20 * np.cos(np.radians(4.0 * hbar - 63.0)))
    Cbarp = (C1p + C2p) / 2.0
    Cbarp7 = Cbarp ** 7
    RC = 2.0 * np.sqrt(Cbarp7 / (Cbarp7 + 25.0 ** 7))
    dTheta = 30.0 * np.exp(-((hbar - 275.0) / 25.0) ** 2)
    RT = -RC * np.sin(np.radians(2.0 * dTheta))
    Lbar = (L1 + L2) / 2.0
    SL = 1.0 + 0.015 * (Lbar - 50.0) ** 2 / np.sqrt(20.0 + (Lbar - 50.0) ** 2)
    SC = 1.0 + 0.045 * Cbarp
    SH = 1.0 + 0.015 * Cbarp * T
    de = np.sqrt((dLp / SL) ** 2 + (dCp / SC) ** 2 + (dth / SH) ** 2
                 + RT * (dCp / SC) * (dth / SH))
    return de


def region_delta_e_lightness_conditioned(img, box: tuple[int, int, int, int],
                                         ref_img, ref_box: tuple[int, int, int, int],
                                         grid: int = 128) -> dict:
    """Paired, lightness-conditioned garment color fidelity (Phase 1 §6).

    Motivation (measured Phase 0.5): raw CIEDE2000 vs the product-photo color
    carried a systematic ~ΔE 24 lightness bias (AUC 0.437 — REJECTED). The
    VTON output is consistently lighter/darker than the studio product photo
    (relighting), which a hue/chroma comparison should not penalize.

    Method (deterministic):
      1. Resample both regions onto a common grid×grid (nearest-neighbor).
      2. Convert to CIELAB (D65).
      3. Estimate the global lightness offset dL = mean(L_out) - mean(L_ref).
      4. Correct the output L* by -dL, then compute per-pixel CIEDE2000.

    Reports: corrected mean/p50/p95 ΔE (primary), raw mean ΔE (context),
    lightness offset magnitude, and residual L* std after correction
    (non-uniform shading / occlusion artifacts).

    Limitation: whole-box pairing without per-pixel warping; residual local
    misalignment (pose/warp differences, occluders in-box) inflates both raw
    and corrected ΔE. The garment content box of the product photo may include
    studio background pixels in the corners — a common mode that cancels in
    good/bad ranking but not in absolute values.
    """
    a = to_array(crop_box(img, box).resize((grid, grid), 0)) / 255.0
    b = to_array(crop_box(ref_img, ref_box).resize((grid, grid), 0)) / 255.0
    la = rgb_to_lab(a).reshape(-1, 3)
    lb = rgb_to_lab(b).reshape(-1, 3)
    dL = float(la[:, 0].mean() - lb[:, 0].mean())
    la_corr = la.copy()
    la_corr[:, 0] -= dL
    de_raw = _ciede2000_vec(la, lb)
    de_lc = _ciede2000_vec(la_corr, lb)
    resid = la_corr[:, 0] - lb[:, 0]
    de_raw.sort()
    de_lc.sort()
    return {
        "metric": "garment_delta_e_lightness_conditioned",
        "grid": grid,
        "lightness_offset_dL": round(dL, 3),
        "delta_e_raw_mean": round(float(de_raw.mean()), 3),
        "delta_e_lc_mean": round(float(de_lc.mean()), 3),
        "delta_e_lc_p50": round(float(de_lc[int(0.5 * (len(de_lc) - 1))]), 3),
        "delta_e_lc_p95": round(float(de_lc[int(0.95 * (len(de_lc) - 1))]), 3),
        "lightness_residual_std": round(float(resid.std(ddof=1)), 3),
        "n_samples": int(len(la)),
    }


def dominant_color_match(img, box: tuple[int, int, int, int], expected_hexes: list[str], k: int = 3) -> dict:
    crop = crop_box(img, box)
    doms = dominant_color(crop, k=k)
    exp_labs = [lab_to_rgb_hex_lab(h) for h in expected_hexes]
    matches = []
    for d in doms:
        lab = np.array(d["lab"])
        dists = [float(np.linalg.norm(lab - e)) for e in exp_labs]
        best = int(np.argmin(dists))
        matches.append({"measured_hex": d["hex"], "measured_lab": d["lab"], "fraction": d["fraction"],
                        "nearest_expected": expected_hexes[best], "lab_distance": round(dists[best], 3),
                        "is_expected": bool(dists[best] < 12.0)})  # 12 Lab units ~= clearly same hue family
    return {
        "metric": "garment_dominant_color",
        "dominant_colors": doms,
        "match_score": round(float(np.mean([m["is_expected"] for m in matches])), 3),
        "per_color": matches,
    }


def histogram_similarity(img, box: tuple[int, int, int, int], reference_img, reference_box: tuple[int, int, int, int], bins: int = 16) -> dict:
    a = histogram(crop_box(img, box), bins=bins)
    b = histogram(crop_box(reference_img, reference_box), bins=bins)
    return {
        "metric": "garment_histogram_intersection",
        "score": round(histogram_intersection(a, b), 4),
    }


def garment_color_report(img, box, expected_hexes: list[str], reference_img=None, reference_box=None) -> dict:
    rep = {
        "region_box": list(box),
        "delta_e": region_color_delta_e(img, box, expected_hexes[0]),
        "dominant": dominant_color_match(img, box, expected_hexes),
    }
    if reference_img is not None and reference_box is not None:
        rep["histogram"] = histogram_similarity(img, box, reference_img, reference_box)
    return rep
