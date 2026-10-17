"""Post-render QA gate for the CONFIT VTON worker (ghost-hands remediation).

WHY THIS EXISTS
---------------
The production "ghost hands" incident (2026-10): a catalog photo where a
model WEARS the garment was fed to the segmentation-free engine as a
``flat-lay``; the engine's garment conditioning therefore contained the
catalog model's hands/skin, and the render reproduced pale hands at the
user's waist. The pre-existing ``_verify_output`` gate only proves the
image *changed* (pixel-change / color-shift / stddev) — a contaminated
render changes plenty, so it passed as "completed".

This module adds the missing CONTENT checks, all pure numpy/PIL (+optional
cv2 for labeling speed), so they run on the GPU worker with no new model:

  * ``detect_new_skin_blobs``  — skin-coloured connected components present
    in the RENDER but absent from the PERSON input (ghost limbs / hands
    copied from the garment photo);
  * ``face_drift`` / ``background_drift`` — identity/background preservation
    scores (the user's face and scene must not be re-imagined);
  * ``qa_gate``                — single honest verdict consumed by
    ``_verify_output`` (a failed gate => ``PASS: False`` => the backend's
    canonical ``VTON_LAYER_NOT_APPLIED`` => truthful failure, never a
    silent bad image);
  * ``paste_back_identity``    — P2 compositing: feathered paste-back of the
    person's face band and outer background margin from the INPUT onto the
    render, so identity/scene stay pixel-faithful even when diffusion drifts.

Everything here is deterministic and unit-testable on CPU with synthetic
images (see tests/test_vton_qa.py).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

# --- skin detection (classic YCrCb bounds; deliberately conservative) -------
_CR = (133, 173)
_CB = (77, 127)


def _to_rgb_np(img) -> np.ndarray:
    if isinstance(img, Image.Image):
        img = img.convert("RGB")
    arr = np.asarray(img, dtype=np.uint8)
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError(f"expected RGB image, got shape {arr.shape}")
    return arr


def skin_mask(rgb: np.ndarray) -> np.ndarray:
    """Boolean skin mask via YCrCb chroma bounds (OpenCV-free)."""
    r = rgb[..., 0].astype(np.int16)
    g = rgb[..., 1].astype(np.int16)
    b = rgb[..., 2].astype(np.int16)
    # ITU-R BT.601 chroma (integer approx, good enough for QA thresholds)
    cr = 128 + ((r * 112 - g * 94 - b * 18) >> 8)
    cb = 128 + ((-r * 38 - g * 74 + b * 112) >> 8)
    return (cr >= _CR[0]) & (cr <= _CR[1]) & (cb >= _CB[0]) & (cb <= _CB[1])


def _dilate(mask: np.ndarray, k: int = 5) -> np.ndarray:
    if k <= 1:
        return mask
    try:
        import cv2

        kern = np.ones((k, k), np.uint8)
        return cv2.dilate(mask.astype(np.uint8), kern).astype(bool)
    except Exception:
        out = mask.copy()
        for _ in range(k // 2):
            out = out | np.roll(out, 1, 0) | np.roll(out, -1, 0) | np.roll(out, 1, 1) | np.roll(out, -1, 1)
        return out


def _label_blobs(mask: np.ndarray, min_area: int) -> List[int]:
    """Sizes (px) of connected components >= min_area. cv2 if available."""
    if not mask.any():
        return []
    try:
        import cv2

        n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
        return [int(stats[i, cv2.CC_STAT_AREA]) for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= min_area]
    except Exception:
        # Fallback: naive BFS (fine for unit-test sized images)
        sizes: List[int] = []
        seen = np.zeros_like(mask, bool)
        h, w = mask.shape
        for y in range(h):
            for x in range(w):
                if mask[y, x] and not seen[y, x]:
                    stack = [(y, x)]
                    seen[y, x] = True
                    size = 0
                    while stack:
                        cy, cx = stack.pop()
                        size += 1
                        for dy in (-1, 0, 1):
                            for dx in (-1, 0, 1):
                                ny, nx = cy + dy, cx + dx
                                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                                    seen[ny, nx] = True
                                    stack.append((ny, nx))
                    if size >= min_area:
                        sizes.append(size)
        return sizes


def detect_new_skin_blobs(
    person,
    rendered,
    *,
    min_area_frac: float = 0.004,
    tolerance_dilate: int = 7,
) -> Dict:
    """Skin blobs in RENDER that are NOT in the PERSON input.

    A segmentation-free render must not invent skin: hands/arms visible in
    the output but absent from the input are, with this pipeline's failure
    mode, copied from the garment photo's person (ghost limbs). Returns the
    blob count + the largest blob's area fraction for observability.
    """
    p = _to_rgb_np(person)
    r = _to_rgb_np(rendered)
    if r.shape[:2] != p.shape[:2]:
        # _verify_output already resizes rendered to person size; keep parity
        r = np.asarray(Image.fromarray(r).resize((p.shape[1], p.shape[0])), dtype=np.uint8)
    sp, sr = skin_mask(p), skin_mask(r)
    new = sr & ~_dilate(sp, tolerance_dilate)
    min_area = int(min_area_frac * p.shape[0] * p.shape[1])
    blobs = _label_blobs(new, max(24, min_area))
    total = p.shape[0] * p.shape[1]
    return {
        "new_skin_blobs": len(blobs),
        "largest_blob_frac": round((max(blobs) / total) if blobs else 0.0, 5),
    }


def _mean_abs_diff(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.abs(a.astype(np.int16) - b.astype(np.int16))) / 255.0)


def face_drift(person, rendered, band: Tuple[float, float] = (0.0, 0.30)) -> float:
    """Normalized mean-abs diff over the top face band (identity check)."""
    p = _to_rgb_np(person)
    r = _to_rgb_np(rendered)
    if r.shape[:2] != p.shape[:2]:
        r = np.asarray(Image.fromarray(r).resize((p.shape[1], p.shape[0])), dtype=np.uint8)
    h = p.shape[0]
    y0, y1 = int(band[0] * h), int(band[1] * h)
    return round(_mean_abs_diff(p[y0:y1], r[y0:y1]), 4)


def background_drift(person, rendered, margin_frac: float = 0.06) -> float:
    """Diff over the outer border margin (scene/background check)."""
    p = _to_rgb_np(person)
    r = _to_rgb_np(rendered)
    if r.shape[:2] != p.shape[:2]:
        r = np.asarray(Image.fromarray(r).resize((p.shape[1], p.shape[0])), dtype=np.uint8)
    h, w = p.shape[:2]
    my, mx = max(1, int(h * margin_frac)), max(1, int(w * margin_frac))
    zones = [
        (slice(0, my), slice(None)),
        (slice(h - my, h), slice(None)),
        (slice(None), slice(0, mx)),
        (slice(None), slice(w - mx, w)),
    ]
    diffs = [_mean_abs_diff(p[sy, sx], r[sy, sx]) for sy, sx in zones]
    return round(float(np.mean(diffs)), 4)


def qa_gate(
    person,
    rendered,
    garment=None,
    *,
    max_new_skin_blobs: int = 0,
    max_face_drift: float = 0.35,
    max_background_drift: float = 0.35,
) -> Dict:
    """Single honest QA verdict. ``PASS`` is exactly True or False."""
    skin = detect_new_skin_blobs(person, rendered)
    fd = face_drift(person, rendered)
    bd = background_drift(person, rendered)
    reasons: List[str] = []
    if skin["new_skin_blobs"] > max_new_skin_blobs:
        reasons.append(
            f"ghost_limb: {skin['new_skin_blobs']} skin blob(s) in render absent "
            f"from person input (largest {skin['largest_blob_frac']:.1%} of frame)"
        )
    if fd > max_face_drift:
        reasons.append(f"face_drift {fd:.3f} > {max_face_drift}")
    if bd > max_background_drift:
        reasons.append(f"background_drift {bd:.3f} > {max_background_drift}")
    return {
        "qa_PASS": not reasons,
        "ghost_skin_blobs": skin["new_skin_blobs"],
        "largest_ghost_blob_frac": skin["largest_blob_frac"],
        "face_drift": fd,
        "background_drift": bd,
        "qa_reasons": reasons,
    }


def paste_back_identity(
    person,
    rendered,
    *,
    face_band: Tuple[float, float] = (0.0, 0.26),
    feather_px: int = 24,
    bg_margin_frac: float = 0.04,
) -> Image.Image:
    """P2 compositing: copy the person's face band + outer background margin
    from INPUT onto the render with a feathered alpha, so identity and scene
    are pixel-faithful regardless of diffusion drift.

    Deterministic and mask-free (no parser needed): the face band and border
    margin are geometric priors that hold for the supported full-body
    9:16 person shots (see check_person_bytes aspect rules).
    """
    p = _to_rgb_np(person)
    r = _to_rgb_np(rendered)
    if r.shape[:2] != p.shape[:2]:
        r = np.asarray(Image.fromarray(r).resize((p.shape[1], p.shape[0])), dtype=np.uint8)
    h, w = p.shape[:2]
    alpha = np.zeros((h, w), np.float32)

    y1 = int(face_band[1] * h)
    alpha[0:y1, :] = 1.0
    my, mx = max(1, int(h * bg_margin_frac)), max(1, int(w * bg_margin_frac))
    alpha[0:my, :] = 1.0
    alpha[h - my:, :] = 1.0
    alpha[:, 0:mx] = 1.0
    alpha[:, w - mx:] = 1.0

    f = max(1, feather_px)
    # vertical feather below the face band
    for i in range(f):
        y = y1 + i
        if y < h:
            alpha[y, :] = np.maximum(alpha[y, :], 1.0 - (i + 1) / f)
    out = (p.astype(np.float32) * alpha[..., None] + r.astype(np.float32) * (1 - alpha[..., None])).astype(np.uint8)
    return Image.fromarray(out)


QA_SEED_LADDER = (42, 1337, 20261010)
