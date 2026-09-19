"""Pose consistency metrics (Phase 0.5).

MediaPipe Pose Landmarker (33 landmarks, Apache-2.0 model). Normalizes by
torso length (shoulder-midpoint to hip-midpoint) and reports MPJPE after
IOD-equivalent (torso) normalization + optional Procrustes alignment.
Deterministic.
"""
from __future__ import annotations

import numpy as np

from .face_metrics import WEIGHTS_DIR
from .imaging import to_array

SH_L, SH_R, HIP_L, HIP_R = 11, 12, 23, 24
N_POSE = 33


def _pose_landmarker():
    from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions
    try:
        from mediapipe.tasks import BaseOptions
    except ImportError:
        from mediapipe.tasks.python import BaseOptions
    model = WEIGHTS_DIR / "pose_landmarker_lite.task"
    if not model.exists():
        raise FileNotFoundError(f"pose_landmarker_lite.task missing; run evaluation/scripts/fetch_mediapipe_models.py")
    opts = PoseLandmarkerOptions(base_options=BaseOptions(model_asset_path=str(model)),
                                 num_poses=1, min_pose_detection_confidence=0.35)
    return PoseLandmarker.create_from_options(opts)


def pose_landmarks(img) -> tuple[np.ndarray, np.ndarray] | None:
    import mediapipe as mp
    arr = to_array(img)
    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=arr.astype(np.uint8))
    res = _pose_landmarker().detect(mp_img)
    if not res.pose_landmarks:
        return None
    lm = res.pose_landmarks[0]
    h, w = arr.shape[:2]
    xy = np.array([[p.x * w, p.y * h] for p in lm], dtype=np.float64)
    vis = np.array([p.visibility for p in lm], dtype=np.float64)
    return xy, vis


def _normalize(xy: np.ndarray) -> np.ndarray:
    sh = (xy[SH_L] + xy[SH_R]) / 2.0
    hip = (xy[HIP_L] + xy[HIP_R]) / 2.0
    torso = np.linalg.norm(sh - hip)
    if torso < 1e-6:
        raise ValueError("degenerate torso length")
    return (xy - sh) / torso


def procrustes(src: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """Align src to ref via similarity transform (scale+rot+translate)."""
    mu_s, mu_r = src.mean(axis=0), ref.mean(axis=0)
    cs, cr = src - mu_s, ref - mu_r
    H = cr.T @ cs
    U, _, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(U @ Vt))
    D = np.diag([1.0, d])
    R = U @ D @ Vt  # column-vector convention; row-vector use: pts @ R.T
    s = (R @ cs.T @ cr).trace() / ((cs.T @ cs).trace() + 1e-12)
    return (src - mu_s) @ R.T * s + mu_r


def pose_report(img_ref, img_out) -> dict:
    r1 = pose_landmarks(img_ref)
    if r1 is None:
        return {"status": "NO_POSE_IN_REFERENCE"}
    r2 = pose_landmarks(img_out)
    if r2 is None:
        return {"status": "NO_POSE_IN_OUTPUT"}
    xy1, vis1 = r1
    xy2, vis2 = r2
    n1, n2 = _normalize(xy1), _normalize(xy2)
    vis_ok = (vis1[:N_POSE] > 0.5) & (vis2[:N_POSE] > 0.5)
    raw = np.linalg.norm(n1[:N_POSE] - n2[:N_POSE], axis=1)
    aligned = procrustes(n1, n2)
    al_d = np.linalg.norm(aligned[:N_POSE] - n2[:N_POSE], axis=1)
    out = {"status": "OK"}
    if vis_ok.any():
        out["mpjpe_torso_norm_raw"] = round(float(raw[vis_ok].mean()), 4)
        out["mpjpe_torso_norm_procrustes"] = round(float(al_d[vis_ok].mean()), 4)
        out["n_visible_landmarks"] = int(vis_ok.sum())
    else:
        out["mpjpe_torso_norm_raw"] = None
        out["mpjpe_torso_norm_procrustes"] = None
        out["n_visible_landmarks"] = 0
    return out
