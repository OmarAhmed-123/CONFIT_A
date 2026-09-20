"""Evidence + verdict assembly (Phase 0.5, §10/§21).

CRITICAL: thresholds are UNFROZEN. This module NEVER hard-fails a sample with
fixed production thresholds. It assembles per-metric evidence values and
computes verdicts ONLY against explicitly supplied candidate operating points
(candidate dicts), which are used to characterize operating curves — they are
not frozen gates. The only hard, non-threshold verdicts are:
  - NO_FACE_IN_OUTPUT / NO_POSE_IN_OUTPUT  -> structural failure (not a threshold)
  - garment request rejected by worker     -> failure (not a threshold)
Everything else is reported as evidence + candidate-op verdicts with the
operating point echoed, so calibration (ROC/FPR/FNR) can happen offline.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

METRIC_KEYS = [
    "identity_dinov2_face_cos", "face_aligned_ssim", "face_geo_mean_disp",
    "landmark_mpjpe_norm", "pose_mpjpe_torso_norm",
    "garment_delta_e_mean", "garment_dominant_match", "garment_histogram",
    "texture_edge_density_delta", "texture_period_ok", "dinov2_garment_cos",
    "ocr_text_score",
]


@dataclass
class Evidence:
    sample_id: str
    arm: str
    metrics: dict = field(default_factory=dict)
    structural: dict = field(default_factory=dict)   # NO_FACE etc.
    occlusion_states: dict = field(default_factory=dict)
    artifacts: dict = field(default_factory=dict)


def get(ev: Evidence, key: str):
    return ev.metrics.get(key)


def verdicts_at_candidate_points(ev: Evidence, candidate_points: dict) -> dict:
    """candidate_points: {metric_key: {"op": ">=", "value": x, ...}}.

    Returns {metric_key: {"pass": bool, "value": v, "candidate_op": {...}}}
    for every metric with a finite value. Pure function of (evidence, points).
    """
    out = {}
    for key, spec in candidate_points.items():
        v = get(ev, key)
        if v is None:
            out[key] = {"pass": None, "value": None, "candidate_op": spec}
            continue
        op, thr = spec["op"], spec["value"]
        p = v >= thr if op == ">=" else v <= thr
        out[key] = {"pass": bool(p), "value": v, "candidate_op": spec}
    # structural failures are non-threshold
    for k in ("face_present", "pose_present", "worker_success"):
        ok = ev.structural.get(k, False)
        out.setdefault("structural_" + k, {"pass": bool(ok), "value": ok, "candidate_op": "structural"})
    return out
