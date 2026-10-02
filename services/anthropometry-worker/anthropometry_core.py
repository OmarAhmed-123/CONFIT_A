"""Feature 05 core — estimation logic, pure of Modal/MediaPipe/FastAPI.

Given 33 MediaPipe world landmarks (+visibilities), the vendored
Landmarks2Anthropometry Bayesian-ridge models, and an optional user-reported
height, produce the honest measurement response consumed by the CONFIT
backend. Everything that can fail honestly (no pose, bad pose, implausible
output) raises ``EstimationRefused`` with a machine-readable code + guidance.

The vendored package (MIT-free: LICENSE is null upstream → research-only
pilot tier, surfaced in every response) is imported from VENDOR_DIR:
  * local tests/development: <repo>/vendor/landmarks2anthropometry/upstream
  * Modal runtime:           /root/l2a (image bakes the files in)
"""
from __future__ import annotations

import contextlib
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

_HERE = Path(__file__).resolve().parent


def vendor_dir() -> Path:
    env = os.environ.get("CONFIT_ANTHROPOMETRY_VENDOR_DIR", "").strip()
    if env:
        return Path(env)
    local = _HERE.parents[1] / "vendor" / "landmarks2anthropometry" / "upstream"
    if local.exists():
        return local
    return Path("/root/l2a")  # Modal runtime


def _ensure_vendor_importable() -> None:
    vd = str(vendor_dir())
    if vd not in sys.path:
        sys.path.insert(0, vd)


@contextlib.contextmanager
def _vendor_cwd():
    """The vendored loader uses repo-relative paths (models/*.pkl), so model
    loading must run with cwd=vendor; restore the caller's cwd after."""
    prev = os.getcwd()
    try:
        os.chdir(vendor_dir())
        yield
    finally:
        try:
            os.chdir(prev)
        except OSError:
            pass


class EstimationRefused(ValueError):
    """Honest refusal: pose/quality/implausibility problems, never garbage."""

    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


# The product-mandated accuracy disclosure (±2-3 cm), shown with EVERY
# measurement set regardless of source.
ACCURACY_NOTE = "±2-3 cm"
DISCLAIMER = (
    "AI-estimated measurements are approximate (±2-3 cm) and derived from a "
    "single photo. For medical or tailoring-critical purposes, measure directly."
)
LANDMARK_SOURCE = "mediapipe_pose_world_approx"
ENGINE = "landmarks2anthropometry_visapp2024_cpu"

_model_cache: Dict[str, Any] = {}


def load_models() -> Dict[str, Any]:
    """Load both vendored Bayesian-ridge bundles (cached per process)."""
    _ensure_vendor_importable()
    from estimate_measurements import load_model  # vendored

    for sex in ("male", "female"):
        if sex not in _model_cache:
            with _vendor_cwd():
                _model_cache[sex] = load_model(sex)
    return _model_cache


def _predict_all(cloud: Dict[str, Sequence[float]], sex: str) -> Dict[str, float]:
    """Run the vendored per-measurement regressors on a CAESAR cloud (mm).

    Uses process_landmarks(scale=1, normalize_viewpoint=False): the cloud is
    already in mm and in the CAESAR canonical frame by construction; the
    vendor's align_vectors normalization is deliberately skipped (it is an
    identity for canonical clouds but can pick degenerate rotations on
    near-symmetric input — verified against the vendored demo: predictions
    with normalize=False reproduce the README numbers exactly).
    """
    _ensure_vendor_importable()
    from estimate_measurements import estimate_measurements  # vendored
    from landmark_utils import process_landmarks  # vendored
    from measurement_utils import MEASUREMENTS_ORDER  # vendored

    models = load_models()
    # normalize_viewpoint=False: no relative-path loads inside the vendor code.
    processed = process_landmarks(dict(cloud), 1, False)
    preds = estimate_measurements(models[sex], processed)
    return {m: round(float(preds[i].item()), 1) for i, m in enumerate(MEASUREMENTS_ORDER)}


# Height hints outside adult range are refused rather than silently ignored.
HEIGHT_HINT_CM_RANGE = (120.0, 230.0)
# mp monocular scale can drift; a calibration factor outside this band means
# the photo/pose is too far off for an honest reading even with a hint.
SCALE_CALIBRATION_RANGE = (0.80, 1.25)

# Model-vs-observed consistency: when the same quantity exists in both, a
# model value this far from the observed geometry is excluded (the observed
# geometry is the ground truth of the photo; the model extrapolates from it).
MODEL_VS_GEOMETRY_TOLERANCE = 0.15

# Human body proportion bands (value / stature). Direct-geometry measurements
# outside these bands (with 20% headroom) indicate MediaPipe proportion
# errors (e.g. squashed arms) and are excluded transparently rather than
# shipped under the ±2-3 cm note.
PROPORTION_BANDS = {
    "Arm Length (Shoulder to Elbow)": (0.135, 0.235),
    "Arm Length (Shoulder to Wrist)": (0.340, 0.540),
    "Inseam (Hip to Ankle)": (0.360, 0.580),
}


def estimate(mp_world_landmarks: Sequence[Sequence[float]],
             visibilities: Optional[Sequence[float]],
             sex: str,
             height_cm: Optional[float] = None,
             skip_envelope_check: bool = False) -> Dict[str, Any]:
    """Full honest estimation pipeline. Returns the worker response body.

    Raises EstimationRefused (code, message, details) on any honest failure.
    """
    import landmark_mapping as lm

    if sex not in ("male", "female"):
        raise EstimationRefused("INPUT_INVALID", "sex must be 'male' or 'female'")

    t0 = time.time()
    wl = np.asarray(mp_world_landmarks, dtype=np.float64)
    try:
        lm.validate_pose(wl, visibilities)
    except lm.LandmarkMappingError as e:
        raise EstimationRefused("NO_USABLE_POSE", str(e), {"landmarks": len(wl) if wl is not None else 0})

    quality = lm.pose_quality(wl)
    if not skip_envelope_check:
        try:
            lm.check_pose_envelope(quality)
        except lm.LandmarkMappingError as e:
            raise EstimationRefused("POSE_OUT_OF_ENVELOPE", str(e), {"pose_quality": quality})

    # Optional user-height calibration of the monocular scale (disclosed).
    scale_calibration = None
    if height_cm is not None:
        if not (HEIGHT_HINT_CM_RANGE[0] <= height_cm <= HEIGHT_HINT_CM_RANGE[1]):
            raise EstimationRefused("INPUT_INVALID",
                                    f"height_cm must be {HEIGHT_HINT_CM_RANGE[0]:.0f}-{HEIGHT_HINT_CM_RANGE[1]:.0f}")
        direct = lm.direct_geometry_measurements(wl)
        factor = (height_cm * 10.0) / direct["Stature"]
        if not (SCALE_CALIBRATION_RANGE[0] <= factor <= SCALE_CALIBRATION_RANGE[1]):
            raise EstimationRefused(
                "SCALE_MISMATCH",
                "photo proportions disagree with the reported height by more than 25% — "
                "please retake the photo (full body, upright, camera at chest height)",
                {"pose_quality": quality, "implied_factor": round(factor, 3)})
        wl = wl * factor
        scale_calibration = {
            "applied": True,
            "source": "user_reported_height",
            "factor": round(factor, 4),
            "reported_height_cm": height_cm,
        }
    else:
        scale_calibration = {"applied": False, "source": "mediapipe_monocular_scale"}

    try:
        cloud = lm.build_caesar_cloud(wl)
    except lm.LandmarkMappingError as e:
        raise EstimationRefused("NO_USABLE_POSE", str(e), {"pose_quality": quality})

    t_model = time.time()
    try:
        model_out = _predict_all(cloud, sex)
    except lm.LandmarkMappingError as e:
        raise EstimationRefused("NO_USABLE_POSE", str(e))
    except Exception as e:  # unpickle/predict failures etc. — never fabricate
        raise EstimationRefused("MODEL_FAILED", f"{type(e).__name__}: {str(e)[:200]}")
    model_s = round(time.time() - t_model, 3)

    direct_out = lm.direct_geometry_measurements(wl)

    # ── assemble: direct geometry always; model measurements only where they
    # pass the per-measurement plausibility bounds. Excluded model outputs are
    # reported transparently — never silently dropped, never forced through.
    # (Verified on real photos: MediaPipe's monocular world landmarks squashed
    # body proportions toward its canonical model — absolute scale is only
    # observable via the user's reported height, and the vendored linear
    # regressors go out of distribution on approximated clouds. The honest
    # product returns what survives scrutiny and labels the rest.)
    measurements: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []

    # 1) per-measurement anatomical bounds for the model output
    for name, value_mm in model_out.items():
        if lm.plausibility_check({name: value_mm}):
            excluded.append({"name": name, "value_mm": value_mm,
                             "reason": "outside_anatomical_range"})
        else:
            measurements.append({
                "name": name, "value_mm": value_mm, "value_cm": round(value_mm / 10.0, 1),
                "source": "model",
            })

    # 2) model-vs-observed consistency on shared quantities (the observed
    #    geometry is the ground truth of the photo; the model extrapolates).
    by_name = {m["name"]: m for m in measurements}
    shared = {
        "Stature (mm)": direct_out.get("Stature"),
        "Arm Length (Shoulder to Elbow) (mm)": direct_out.get("Arm Length (Shoulder to Elbow)"),
        "Arm Length (Shoulder to Wrist) (mm)": direct_out.get("Arm Length (Shoulder to Wrist)"),
    }
    for model_name, direct_value in shared.items():
        if model_name in by_name and direct_value:
            m = by_name[model_name]
            if abs(m["value_mm"] - direct_value) / direct_value > MODEL_VS_GEOMETRY_TOLERANCE:
                measurements.remove(m)
                excluded.append({"name": model_name, "value_mm": m["value_mm"],
                                 "reason": "inconsistent_with_observed_geometry"})

    # 3) direct geometry: always observed, but proportion-sanity-checked.
    stature_direct = direct_out.get("Stature") or 0.0
    for name, value_mm in direct_out.items():
        entry = {
            "name": name, "value_mm": value_mm, "value_cm": round(value_mm / 10.0, 1),
            "source": "direct_geometry",
        }
        band = PROPORTION_BANDS.get(name)
        if band and stature_direct:
            lo, hi = band[0] * 0.8 * stature_direct, band[1] * 1.2 * stature_direct
            if not (lo <= value_mm <= hi):
                excluded.append({"name": name, "value_mm": value_mm,
                                 "reason": "outside_body_proportion_band"})
                continue
        measurements.append(entry)

    # Direct geometry is the observed truth: if the observed body itself is
    # anatomically impossible the photo is unusable — a hard refusal (never
    # ship an impossible body). The stature anchor is mandatory.
    bad_direct = lm.plausibility_check(direct_out)
    if bad_direct or not any(m["name"] == "Stature" for m in measurements):
        raise EstimationRefused(
            "IMPLAUSIBLE_RESULT",
            "the photo produced anatomically implausible measurements — please retake "
            "it (full body in frame, upright, facing the camera, arms relaxed)",
            {"failed_measurements": bad_direct or ["Stature"], "pose_quality": quality})

    if any(m["source"] == "model" for m in measurements) and excluded:
        result_quality = "partial"
    elif not any(m["source"] == "model" for m in measurements):
        result_quality = "geometry_only"
    else:
        result_quality = "full"

    total_s = round(time.time() - t0, 3)
    return {
        "status": "completed",
        "sex": sex,
        "quality": result_quality,
        "measurements": measurements,
        "measurement_count": len(measurements),
        "excluded": excluded,
        "excluded_count": len(excluded),
        "measurement_method": "ai_estimate",
        "accuracy_note": ACCURACY_NOTE,
        "disclaimer": DISCLAIMER,
        "landmark_source": LANDMARK_SOURCE,
        "pose_quality": quality,
        "scale_calibration": scale_calibration,
        "engine": ENGINE,
        "model": {
            "name": "Landmarks2Anthropometry (VISAPP 2024, Bayesian ridge per measurement)",
            "paper": "Coja et al., Landmarks2Anthropometry: 3D Landmark Detection for "
                     "Anthropometric Measurement Estimation, VISAPP 2024",
            "vendor_commit": "de2df48dd428dce457339141c709d7510e0e6f2b",
            "landmark_detector": "mediapipe pose_landmarker_heavy (Apache-2.0)",
            "license": "unlicensed-research-only",
            "commercial": False,
        },
        "timings": {"total_seconds": total_s, "model_seconds": model_s},
    }
