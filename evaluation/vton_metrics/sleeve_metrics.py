"""Sleeve-presence metrics (Phase 1 §7 — long-sleeve root-cause detection).

Root-cause context (measured 2026-09-15, see evaluation/results/rootsleeve_runs.json):
  The FASHN engine (fashn-vton-v1.5 @7c0f10af) clips garment sleeves whose
  geometry extends VERTICALLY far from the torso in the product image:
    90° vertical sleeves  -> rendered SLEEVELESS (torso re-textured, arms unchanged)
    45° raglan sleeves    -> rendered PARTIAL (upper arm only)
    0° horizontal sleeves -> rendered FULL (sleeves to wrist, pose-following)
  Mechanism (DERIVED): garment-to-body warp compresses sleeve geometry toward
  the shoulder anchor; transferred length shrinks with vertical sleeve drop.

This module provides the two measurement pieces for a structural,
garment-aware sleeve gate:
  1. garment_sleeve_drop  — how far sleeve content extends below the shoulder
     line in the product image (predicts which renders MUST show full arms).
  2. arm_coverage         — for a render, whether the person's arms were
     re-covered with the garment color (vs input) along shoulder->wrist.

Deterministic; CPU-only; MediaPipe Pose (Apache-2.0 model) + CIEDE2000.
Thresholds are CANDIDATE operating points — see calibration output, not frozen.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from .imaging import crop_box, rgb_to_lab, to_array
from .color_metrics import _ciede2000_vec

# MediaPipe Pose landmark indices
MP_LEFT_SH, MP_LEFT_EL, MP_LEFT_WR = 11, 13, 15
MP_RIGHT_SH, MP_RIGHT_EL, MP_RIGHT_WR = 12, 14, 16


def _content_mask(arr: np.ndarray) -> np.ndarray:
    """Content mask with adaptive threshold.

    Fixed threshold 30 (sum-abs channel diff from corner background) fails on
    low-contrast garments (e.g. white garment on white background, diff p99
    ~20). Adaptive: thr = max(8, min(30, 0.5 * p99(diff))).
    """
    d = np.abs(arr.astype(int) - arr[0, 0].astype(int)).sum(axis=2)
    thr = max(8.0, min(30.0, 0.5 * float(np.percentile(d, 99))))
    return d > thr


def _content_box(arr: np.ndarray) -> tuple[int, int, int, int] | None:
    m = _content_mask(arr)
    ys, xs = np.where(m)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def garment_sleeve_drop(garment_img) -> dict:
    """Vertical sleeve drop of a garment product image (deterministic, v2).

    Definition (cluster-separation based — v1's outer-band heuristic
    misfired on boxy T-shirts whose wide body fills the side bands):
      1. Content mask (adaptive threshold); content box.
      2. Shoulder line at 15% of content height.
      3. For each row below the shoulder line, find content runs. A row
         "has a separated sleeve" if there is a content run in the outer
         25% of the content width whose gap to the nearest torso run
         (a run overlapping the central 50%) is >= 6 px.
      4. sleeve_drop_ratio = (deepest such row - shoulder_y) / content height.

    Vertical long-sleeve flat lays (sleeves laid alongside the body with a
    background gap) -> ratio ~0.6-0.9. Horizontal-sleeve flat lays and boxy
    short-sleeve tees -> small. Candidate long-sleeve threshold: 0.45
    (UNFROZEN — validated against the 52-job measured set).
    """
    if isinstance(garment_img, (str, Path)):
        garment_img = Image.open(garment_img).convert("RGB")
    arr = to_array(garment_img)
    m_full = _content_mask(arr)
    ys, xs = np.where(m_full)
    if len(xs) == 0:
        return {"sleeve_drop_ratio": None, "status": "NO_CONTENT"}
    x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    m = m_full[y0:y1, x0:x1]
    h, w = m.shape
    shoulder_y = int(0.15 * h)
    mid_lo, mid_hi = int(0.25 * w), int(0.75 * w)
    outer_w = int(0.25 * w)
    min_gap = 6
    deepest = -1
    for y in range(shoulder_y, h):
        row = m[y]
        if not row.any():
            continue
        runs, in_run, start = [], False, 0
        for x in range(w + 1):
            if x < w and row[x] and not in_run:
                in_run, start = True, x
            elif x == w or (not row[x] and in_run):
                in_run = False
                runs.append((start, x - 1))
        if not runs:
            continue
        torso = [r for r in runs if r[0] < mid_hi and r[1] > mid_lo]
        if not torso:
            continue
        for (rs, re_) in runs:
            if rs < outer_w and re_ < mid_lo:
                if torso[0][0] - (re_ + 1) >= min_gap:
                    deepest = max(deepest, y)
            elif rs > mid_hi and re_ > w - 1 - outer_w:
                if (rs - 1) - torso[-1][1] >= min_gap:
                    deepest = max(deepest, y)
    if deepest < 0:
        return {"sleeve_drop_ratio": 0.0, "status": "NO_SEPARATED_SIDE",
                "content_box": [x0, y0, x1, y1]}
    ratio = max(0.0, (deepest - shoulder_y) / h)
    return {
        "sleeve_drop_ratio": round(ratio, 4),
        "is_long_sleeve_candidate": bool(ratio > 0.45),
        "deepest_separated_row": int(deepest),
        "content_box": [x0, y0, x1, y1],
        "status": "OK",
    }


def _pose_xy(img) -> np.ndarray | None:
    from .pose_metrics import pose_landmarks
    r = pose_landmarks(img)
    return r[0] if r else None


def _median_color(arr: np.ndarray, x: float, y: float, r: int = 5) -> np.ndarray:
    h, w = arr.shape[:2]
    x0, x1 = int(max(0, x - r)), int(min(w, x + r + 1))
    y0, y1 = int(max(0, y - r)), int(min(h, y + r + 1))
    return np.median(arr[y0:y1, x0:x1].reshape(-1, 3), axis=0)


def arm_coverage(person_img, out_img, garment_lab: np.ndarray) -> dict:
    """Was the person's arm re-covered with garment color in the output?

    Samples both arms at 55% and 85% of shoulder->wrist (upper-arm and
    forearm points). Per sample: d_input = ΔE2k(out, person) at the same
    pixel; d_garment = ΔE2k(out, garment dominant Lab).
    Per-arm verdict (candidate thresholds, UNFROZEN):
      PRESENT  if arm_changed AND arm_garment
      PARTIAL  if exactly one of (arm_changed, arm_garment)
      MISSING  otherwise
    arm_changed: max d_input over samples > 10
    arm_garment: min d_garment over samples < 12
    """
    from .color_metrics import _ciede2000_vec  # noqa: F401 (shared impl)
    if isinstance(person_img, (str, Path)):
        person_img = Image.open(person_img).convert("RGB")
    if isinstance(out_img, (str, Path)):
        out_img = Image.open(out_img).convert("RGB")
    pxy = _pose_xy(person_img)
    oxy = _pose_xy(out_img)
    if pxy is None or oxy is None:
        return {"status": "NO_POSE"}
    # Person fixture and VTON output are different canvases (768x1024 vs
    # 576x768, same aspect); each pose is in its own image's coordinates,
    # so samples stay in local coordinates.
    pa, oa = to_array(person_img), to_array(out_img)
    out_report = {"status": "OK", "arms": {}}
    n_present = n_partial = n_missing = 0
    for name, (sh, wr) in (
        ("left", (MP_LEFT_SH, MP_LEFT_WR)),
        ("right", (MP_RIGHT_SH, MP_RIGHT_WR)),
    ):
        samples = {}
        for t in (0.55, 0.85):
            x_in = pxy[sh, 0] + t * (pxy[wr, 0] - pxy[sh, 0])
            y_in = pxy[sh, 1] + t * (pxy[wr, 1] - pxy[sh, 1])
            x_out = oxy[sh, 0] + t * (oxy[wr, 0] - oxy[sh, 0])
            y_out = oxy[sh, 1] + t * (oxy[wr, 1] - oxy[sh, 1])
            c_out = rgb_to_lab(_median_color(oa, x_out, y_out)).reshape(1, 3)
            c_in = rgb_to_lab(_median_color(pa, x_in, y_in)).reshape(1, 3)
            c_g = np.tile(garment_lab[None, :], (1, 1))
            d_in = float(_ciede2000_vec(c_out, c_in)[0])
            d_g = float(_ciede2000_vec(c_out, c_g)[0])
            samples[f"t{t:.2f}"] = {
                "d_input": round(d_in, 2), "d_garment": round(d_g, 2),
                "out_xy": [round(float(x_out), 1), round(float(y_out), 1)],
            }
        changed = max(s["d_input"] for s in samples.values()) > 10.0
        garment = min(s["d_garment"] for s in samples.values()) < 12.0
        verdict = ("PRESENT" if (changed and garment)
                   else "PARTIAL" if (changed or garment)
                   else "MISSING")
        if verdict == "PRESENT":
            n_present += 1
        elif verdict == "PARTIAL":
            n_partial += 1
        else:
            n_missing += 1
        out_report["arms"][name] = {"samples": samples, "verdict": verdict}
    overall = ("SLEEVES_PRESENT" if n_present == 2
               else "SLEEVES_PARTIAL" if n_present + n_partial >= 1 and n_missing <= 1
               else "SLEEVES_MISSING")
    out_report["overall"] = overall
    return out_report


def gate_status_from(expected_full: bool, cov: dict) -> str:
    """Pure gate mapping (deterministic, unit-testable without pose models)."""
    if not expected_full:
        return "N/A_SHORT_SLEEVE"
    if cov.get("status") != "OK":
        return "NO_POSE"
    return "PASS" if cov.get("overall") == "SLEEVES_PRESENT" else "FAIL_SLEEVES_INCOMPLETE"


def sleeve_gate_report(person_img, out_img, garment_img, garment_lab: np.ndarray | None = None) -> dict:
    """Combined structural sleeve gate report for one render."""
    from .imaging import dominant_color
    drop = garment_sleeve_drop(garment_img)
    if garment_lab is None:
        if isinstance(garment_img, (str, Path)):
            gimg = Image.open(garment_img).convert("RGB")
        else:
            gimg = garment_img
        box = _content_box(to_array(gimg))
        crop = gimg if box is None else crop_box(gimg, box)
        d = dominant_color(crop, k=1)
        garment_lab = np.array(d[0]["lab"])
    cov = arm_coverage(person_img, out_img, garment_lab)
    expected_full = bool(drop.get("is_long_sleeve_candidate"))
    return {
        "garment_sleeve_drop": drop,
        "arm_coverage": cov,
        "expected_full_sleeves": expected_full,
        "gate_status": gate_status_from(expected_full, cov),
    }
