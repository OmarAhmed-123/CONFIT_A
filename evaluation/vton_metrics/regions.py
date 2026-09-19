"""Tier-1 REQUIRED deterministic garment-region estimation (Phase 0.5, §17).

Method: MediaPipe pose keypoints + slot/category anatomical priors + image
bounding boxes. NO heavy segmentation, NO NC fashion parsers.
Tier-2 (SAM2) is EXPERIMENTAL offline-only, default OFF — not implemented in
this package on purpose (see LICENSE_AUDIT / METRICS.md).

Boxes are (x0, y0, x1, y1) ints, clipped to image bounds.
"""
from __future__ import annotations

import numpy as np

from .imaging import to_array

# MediaPipe pose landmark ids
SH_L, SH_R = 11, 12
ELB_L, ELB_R = 13, 14
WR_L, WR_R = 15, 16
HIP_L, HIP_R = 23, 24
KNEE_L, KNEE_R = 25, 26
ANK_L, ANK_R = 27, 28
NOSE = 0


def _box(x0, y0, x1, y1, w, h):
    x0, y0 = max(0, int(x0)), max(0, int(y0))
    x1, y1 = min(w, int(x1)), min(h, int(y1))
    return (x0, y0, x1, y1) if x1 > x0 and y1 > y0 else None


def regions_from_pose(img, slot: str) -> tuple[dict, str]:
    """Estimate garment region box(es) for a slot from pose + priors.

    Returns (regions, status) where status in {OK, NO_POSE, NO_BOX}.
    regions: {"primary": box, "secondary": box|None}
    """
    from .pose_metrics import pose_landmarks
    res = pose_landmarks(img)
    if res is None:
        return {}, "NO_POSE"
    xy, vis = res
    w, h = img.size
    get = lambda i: xy[i] if vis[i] > 0.4 else None
    sh_l, sh_r = get(SH_L), get(SH_R)
    hip_l, hip_r = get(HIP_L), get(HIP_R)
    knee_l, knee_r = get(KNEE_L), get(KNEE_R)
    wr_l, wr_r = get(WR_L), get(WR_R)
    nose = get(NOSE)

    if sh_l is None or sh_r is None or hip_l is None or hip_r is None:
        return {}, "NO_BOX"

    sh_mid = (sh_l + sh_r) / 2
    hip_mid = (hip_l + hip_r) / 2
    shoulder_span = np.linalg.norm(sh_l - sh_r)
    torso = np.linalg.norm(sh_mid - hip_mid)

    if slot in ("upper_inner", "upper_outer"):
        # outer garment: slightly wider box (covers layering extent)
        pad = 0.28 * shoulder_span if slot == "upper_outer" else 0.15 * shoulder_span
        top = (nose if nose is not None else sh_mid)
        primary = _box(sh_mid[0] - shoulder_span * 0.75 - pad, top[1] + 0.15 * torso,
                       sh_mid[0] + shoulder_span * 0.75 + pad, hip_mid[1] + 0.08 * torso, w, h)
        secondary = None
    elif slot == "lower":
        knee = (knee_l + knee_r) / 2 if (knee_l is not None and knee_r is not None) else hip_mid + 1.1 * (hip_mid - sh_mid)
        primary = _box(hip_mid[0] - shoulder_span * 0.55, hip_mid[1] - 0.1 * torso,
                       hip_mid[0] + shoulder_span * 0.55, knee[1] + 0.5 * torso, w, h)
        secondary = None
    elif slot == "dress":
        knee = (knee_l + knee_r) / 2 if (knee_l is not None and knee_r is not None) else hip_mid + 1.1 * (hip_mid - sh_mid)
        primary = _box(sh_mid[0] - shoulder_span * 0.8, (nose if nose is not None else sh_mid)[1] + 0.15 * torso,
                       sh_mid[0] + shoulder_span * 0.8, knee[1] + 0.6 * torso, w, h)
        secondary = None
    else:
        return {}, "NO_BOX"

    if primary is None:
        return {}, "NO_BOX"
    return {"primary": primary, "secondary": secondary}, "OK"


def face_region(img, margin: float = 0.35) -> tuple[dict, str]:
    """Face crop box from MediaPipe face landmarks (for identity metrics)."""
    from .face_metrics import landmarks, geometry
    pts = landmarks(img)
    if pts is None:
        return {}, "NO_FACE"
    g = geometry(pts)
    iod = g["iod"]
    mid = np.array(g["eye_midpoint"])
    w, h = img.size
    half = (1.6 + margin) * iod
    box = _box(mid[0] - half, mid[1] - half, mid[0] + half, mid[1] + half, w, h)
    if box is None:
        return {}, "NO_FACE"
    return {"primary": box}, "OK"
