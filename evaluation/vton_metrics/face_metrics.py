"""Identity-preservation metrics (Phase 0.5) — PROXY indicators, not a validated
face-recognition system.

Components:
  1. MediaPipe Face Landmarker (Apache-2.0): 478 landmarks -> eye/nose/mouth
     geometry (interocular distance, eye height/width, mouth width, jaw width,
     nose length), all normalized by interocular distance (IOD).
     -> normalized landmark displacement (mean/max L2, IOD-normalized)
  2. Key-point-aligned face-crop SSIM (scale by IOD, center on eye midpoint).
  3. DINOv2 ViT-B/14 (Apache-2.0) face-crop embedding cosine — DRIFT PROXY ONLY.

No OpenAI CLIP (license excludes deployed use), no InsightFace (NC weights).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .imaging import crop_box, downscale_to, to_array

WEIGHTS_DIR = Path(__file__).resolve().parent.parent / "weights_local"

EYE_L = [33, 133]          # left eye corners (L/R per MediaPipe convention)
EYE_R = [362, 263]
NOSE_TIP = 1
NOSE_ROOT = 6
MOUTH_L, MOUTH_R = 61, 291
JAW_L, JAW_R = 172, 4
EYE_TOP, EYE_BOT = 159, 145   # vertical span
BROW_L, BROW_R = 70, 300


def _landmarker():
    from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions
    try:
        from mediapipe.tasks import BaseOptions
    except ImportError:
        from mediapipe.tasks.python import BaseOptions

    model = WEIGHTS_DIR / "face_landmarker.task"
    if not model.exists():
        raise FileNotFoundError(
            f"face_landmarker.task missing at {model}; run evaluation/scripts/fetch_mediapipe_models.py")
    opts = FaceLandmarkerOptions(base_options=BaseOptions(model_asset_path=str(model)),
                                 num_faces=1, min_face_detection_confidence=0.35)
    return FaceLandmarker.create_from_options(opts)


def _detect_in(mp_img, side: int, x0: int, y0: int) -> list[np.ndarray] | None:
    """Run the landmarker on a square crop of side `side` at (x0, y0);
    map landmarks back to full-image coordinates."""
    res = _landmarker().detect(mp_img)
    if not res.face_landmarks:
        return None
    pts = res.face_landmarks[0]
    return [np.array([p.x * side + x0, p.y * side + y0]) for p in pts]


def _face_search_box(arr: np.ndarray) -> tuple[int, int, int] | None:
    """Pose-guided face search box (deterministic two-stage localization).

    The face landmarker only reliably detects faces that occupy a large part of
    the frame; full-body images have small faces. Pose landmark 0 (nose) +
    shoulder width give a face-sized search box. Returns (x0, y0, side) or None.
    """
    from .pose_metrics import pose_landmarks
    try:
        res = pose_landmarks(_PIL(arr) if isinstance(arr, np.ndarray) else arr)
    except Exception:
        return None
    if res is None:
        return None
    xy, vis = res
    if vis[0] <= 0.4 or vis[11] <= 0.4 or vis[12] <= 0.4:
        return None
    nose = xy[0]
    sh_w = float(np.linalg.norm(xy[11] - xy[12]))
    side = int(1.6 * sh_w)
    cx, cy = int(nose[0]), int(nose[1] - 0.30 * side)
    x0 = max(0, cx - side // 2)
    y0 = max(0, cy - side // 2)
    # keep the box inside the image
    h, w = arr.shape[:2]
    if x0 + side > w:
        x0 = max(0, w - side)
    if y0 + side > h:
        y0 = max(0, h - side)
    if side < 64:
        side = min(w, h, 64)
        x0 = max(0, cx - side // 2)
        y0 = max(0, cy - side // 2)
    return x0, y0, side


def _PIL(arr: np.ndarray):
    from PIL import Image
    return Image.fromarray(arr.astype(np.uint8))


def landmarks(img) -> list[np.ndarray] | None:
    """Return 478 (x, y) pixel landmarks for the face, or None.

    Two-stage: (1) pose-guided face-sized crop upscaled to 512 (deterministic),
    (2) full-image fallback. Pure function of the image.
    """
    import mediapipe as mp
    from .imaging import load_image
    arr = to_array(img) if not isinstance(img, (str, Path)) else to_array(load_image(img))
    if arr is None:
        return None
    mp_img_cls = lambda a: mp.Image(image_format=mp.ImageFormat.SRGB, data=a.astype(np.uint8))
    # stage 1: pose-guided crop
    box = _face_search_box(arr)
    if box is not None:
        x0, y0, side = box
        crop = arr[y0:y0 + side, x0:x0 + side]
        crop_img = _PIL(crop).resize((512, 512))
        # normalized coords on the 512 crop -> crop px (side) -> full image (+x0, +y0)
        got = _detect_in(mp_img_cls(to_array(crop_img)), side, x0, y0)
        if got is not None:
            return got
    # stage 2: full-image fallback (non-square safe mapping)
    res = _landmarker().detect(mp_img_cls(arr))
    if not res.face_landmarks:
        return None
    h, w = arr.shape[:2]
    return [np.array([p.x * w, p.y * h]) for p in res.face_landmarks[0]]


def _to_np_img(img):
    return img


def geometry(pts: list[np.ndarray]) -> dict:
    iol = np.linalg.norm(pts[EYE_L[0]] - pts[EYE_L[1]])
    ior = np.linalg.norm(pts[EYE_R[0]] - pts[EYE_R[1]])
    iod = float((iol + ior) / 2.0)
    if iod < 1e-6:
        raise ValueError("degenerate face geometry")
    d = lambda a, b: float(np.linalg.norm(pts[a] - pts[b]))
    return {
        "iod": iod,
        "eye_width_left": d(*EYE_L) / iod,
        "eye_width_right": d(*EYE_R) / iod,
        "eye_height": d(EYE_TOP, EYE_BOT) / iod,
        "eye_aspect": (d(EYE_TOP, EYE_BOT) / iod) / ((d(*EYE_L) + d(*EYE_R)) / 2.0 / iod),
        "mouth_width": d(MOUTH_L, MOUTH_R) / iod,
        "jaw_width": d(JAW_L, JAW_R) / iod,
        "nose_length": d(NOSE_ROOT, NOSE_TIP) / iod,
        "brow_span": d(BROW_L, BROW_R) / iod,
        "eye_midpoint": ((pts[EYE_L[0]] + pts[EYE_L[1]] + pts[EYE_R[0]] + pts[EYE_R[1]]) / 4.0).tolist(),
    }


def geometry_delta(g1: dict, g2: dict) -> dict:
    keys = ["eye_width_left", "eye_width_right", "eye_height", "eye_aspect",
            "mouth_width", "jaw_width", "nose_length", "brow_span"]
    deltas = {k: round(abs(g1[k] - g2[k]), 4) for k in keys}
    vals = list(deltas.values())
    return {
        "per_property": deltas,
        "mean_normalized_displacement": round(float(np.mean(vals)), 4),
        "max_normalized_displacement": round(float(np.max(vals)), 4),
    }


def landmark_displacement(pts1: list[np.ndarray], pts2: list[np.ndarray]) -> dict:
    """IOD-normalized, eye-midpoint-centered L2 displacement over all 478 landmarks.

    Scale- and translation-invariant (each face normalized by its OWN IOD and
    centered on its own eye midpoint). Not rotation-invariant (documented).
    """
    g1, g2 = geometry(pts1), geometry(pts2)
    iod1, iod2 = g1["iod"], g2["iod"]
    m1 = np.array(g1["eye_midpoint"])
    m2 = np.array(g2["eye_midpoint"])
    p1 = (np.array(pts1) - m1) / iod1
    p2 = (np.array(pts2) - m2) / iod2
    d = np.linalg.norm(p1 - p2, axis=1)
    return {
        "landmark_mpjpe_norm": round(float(d.mean()), 4),
        "landmark_mpjpe_p95_norm": round(float(np.percentile(d, 95)), 4),
        "landmark_max_norm": round(float(d.max()), 4),
        "n_landmarks": int(len(d)),
    }


def aligned_face_crop(img, pts: list[np.ndarray], scale: float = 1.0) -> np.ndarray:
    """Center on eye midpoint, side = 3.2 * IOD * scale, axis-aligned (no rotation)."""
    from .imaging import load_image
    if isinstance(img, (str, Path)):
        img = load_image(img)
    mid = np.array(geometry(pts)["eye_midpoint"])
    iod = geometry(pts)["iod"]
    half = 1.6 * iod * scale
    x0, y0 = int(mid[0] - half), int(mid[1] - half)
    box = (x0, y0, x0 + int(2 * half), y0 + int(2 * half))
    crop = crop_box(img, box)
    crop = crop.resize((160, 160), 0)  # fixed size for SSIM/embedding comparability
    return to_array(crop)


def aligned_ssim(img1, pts1, img2, pts2) -> dict:
    from skimage.metrics import structural_similarity
    c1 = aligned_face_crop(img1, pts1)
    c2 = aligned_face_crop(img2, pts2)
    v = structural_similarity(c1, c2, channel_axis=2, data_range=255.0)
    return {"aligned_face_ssim": round(float(v), 4)}


def face_report(img_ref, img_out) -> dict:
    """Full face-preservation report between input person and VTON output."""
    pts_ref = landmarks(img_ref)
    if pts_ref is None:
        return {"status": "NO_FACE_IN_REFERENCE", "face": None}
    rep = {"status": "OK"}
    rep["reference_geometry"] = {k: (round(v, 4) if isinstance(v, float) else v)
                                  for k, v in geometry(pts_ref).items() if k != "eye_midpoint"}
    pts_out = landmarks(img_out)
    if pts_out is None:
        rep["status"] = "NO_FACE_IN_OUTPUT"
        rep["face"] = None
        return rep
    rep["output_geometry"] = {k: (round(v, 4) if isinstance(v, float) else v)
                              for k, v in geometry(pts_out).items() if k != "eye_midpoint"}
    rep["geometry_delta"] = geometry_delta(geometry(pts_ref), geometry(pts_out))
    rep["landmark_displacement"] = landmark_displacement(pts_ref, pts_out)
    rep["ssim"] = aligned_ssim(img_ref, pts_ref, img_out, pts_out)
    return rep
