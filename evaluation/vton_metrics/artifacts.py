"""Lightweight, deterministic artifact heuristics (Phase 0.5).

These are PROXY signals (EXPERIMENTAL by default), not validated detectors:
  - face_region_blur: Laplacian variance of the aligned face crop (sharpness).
  - edge_anomaly: Sobel magnitude tail (p99) in garment region vs reference.
  - blockiness: 8x8 DCT high-frequency energy proxy (compression/artifact).
No learned artifact model is claimed.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from .face_metrics import aligned_face_crop, geometry, landmarks
from .imaging import crop_box, to_array


def face_blur(img) -> dict | None:
    pts = landmarks(img)
    if pts is None:
        return None
    crop = aligned_face_crop(img, pts)
    g = crop.mean(axis=2)
    lap = ndimage.laplace(g)
    return {"face_laplacian_var": round(float(lap.var()), 2)}


def edge_anomaly(img, box, reference_img, reference_box) -> dict:
    def p99(box_, img_):
        g = to_array(crop_box(img_, box_).convert("L"))
        g = ndimage.sobel(g)
        return float(np.percentile(g, 99))
    a, b = p99(box, img), p99(reference_box, reference_img)
    return {
        "edge_p99_output": round(a, 2),
        "edge_p99_reference": round(b, 2),
        "edge_ratio": round(a / (b + 1e-6), 3),
    }


def blockiness(img, box) -> dict:
    crop = to_array(crop_box(img, box).convert("L")).astype(np.float64)
    if crop.shape[0] < 16 or crop.shape[1] < 16:
        return {"blockiness": None}
    h, w = crop.shape[:2]
    h8, w8 = h // 8 * 8, w // 8 * 8
    blk = crop[:h8, :w8].reshape(h8 // 8, 8, w8 // 8, 8).transpose(0, 2, 1, 3)
    # block-boundary discontinuity: mean |edge difference across 8px grid lines|
    ri = np.arange(7, h8, 8)
    ri = ri[ri + 1 < h8]
    vert = np.abs(crop[ri + 1, :w8].astype(float) - crop[ri, :w8].astype(float)).mean()
    ci = np.arange(7, w8, 8)
    ci = ci[ci + 1 < w8]
    horiz = np.abs(crop[:h8, ci + 1].astype(float) - crop[:h8, ci].astype(float)).mean()
    internal = np.abs(crop[1:, :].astype(float) - crop[:-1, :].astype(float)).mean()
    score = (float(vert) + float(horiz)) / (2.0 * (internal + 1e-6))
    return {"blockiness_ratio": round(float(score), 3)}
