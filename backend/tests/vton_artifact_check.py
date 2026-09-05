"""Deterministic VTON output artifact check (pose + hand duplication).

Purpose
-------
The reported production failure mode is *anatomical duplication / pose
transfer*: a person uploaded with a specific pose (e.g. hands on the waist,
arms crossed) comes back with **extra hands/arms**, or with the body pose of
the *garment/model* photo instead of the *uploaded person*. This module
measures, on an image pair (``person`` vs ``result``):

* the **hand count** in each image  -> an *increase* means duplicated hands;
* the **body-pose keypoint drift** between the two  -> large drift or a
  left/right wrist swap means the pose was not preserved (pose transfer).

It is intentionally **not** wired into the live production API request path
(MediaPipe models would add cold-start latency and weight to the serverless
function). It is used for:

1. deterministic automated regression tests
   (``backend/tests/test_vton_pose_artifact_regression.py``);
2. a standalone acceptance validator — run it against a real production
   ``person`` image and the ``rendered`` result data-URL and read the JSON
   verdict.

``python -m backend.app.services.vton_artifact_check \
    --person person.jpg --result result_data_url_or_path [--json out.json]``

Honesty
-------
The pose/hand models are heuristics. A ``PASS`` means "no duplication or
pose-transfer signal above threshold was detected", NOT a guarantee of
perfect anatomical fidelity. Final visual acceptance also requires the
documented human-review step (see the closure report). The module returns
every measured value so a reviewer can audit the numbers.
"""

from __future__ import annotations

import base64
import io
import json
import os
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple

def _resolve_model_dir() -> str:
    """Locate ``backend/cv_models/``. Honours ``VTON_CV_MODEL_DIR``; otherwise
    walks up from this file trying the layouts this module has lived in
    (backend/tests/ and legacy backend/app/services/)."""
    env = os.environ.get("VTON_CV_MODEL_DIR")
    if env:
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    for _ in range(4):
        cand = os.path.join(here, "cv_models")
        if os.path.isdir(cand):
            return cand
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    raise FileNotFoundError(
        "cv_models/ not found (set VTON_CV_MODEL_DIR to the directory "
        "containing hand_landmarker.task / pose_landmarker_lite.task)")


_DEFAULT_MODEL_DIR = _resolve_model_dir()


# ── image loading ──────────────────────────────────────────────────────────
def load_image(src: "str | bytes"):
    """Load a PIL image from a file path, a ``data:`` URL, raw base64, or
    raw bytes. Raises ValueError on undecodable input (never returns None)."""
    from PIL import Image

    if isinstance(src, bytes):
        try:
            img = Image.open(io.BytesIO(src))
            return img.convert("RGB")
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"cannot decode image bytes: {e}") from e

    s = str(src).strip()
    if s.startswith("data:"):
        if "," not in s:
            raise ValueError("malformed data URL")
        b64 = s.split(",", 1)[1]
        try:
            raw = base64.b64decode(b64)
            return Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"cannot decode data URL image: {e}") from e

    if os.path.exists(s):
        try:
            return Image.open(s).convert("RGB")
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"cannot open image file {s!r}: {e}") from e

    # Last resort: treat as raw base64.
    try:
        raw = base64.b64decode(s)
        return Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"cannot decode image source: {e}") from e


def _to_mp(img):
    import numpy as np
    import mediapipe as mp

    return mp.Image(image_format=mp.ImageFormat.SRGB, data=np.array(img))


# ── detectors (lazy model load) ────────────────────────────────────────────
_HAND_MODEL = "hand_landmarker.task"
_POSE_MODEL = "pose_landmarker_lite.task"

# Body joints used for the pose-drift signal (COCO-indexed in MediaPipe's
# 33-point pose). Upper body + hips where a try-on garment is applied.
_POSE_JOINTS = [0, 11, 12, 13, 14, 15, 16, 23, 24]
_L_WRIST, _R_WRIST = 15, 16


def count_hands(img, model_dir: str = _DEFAULT_MODEL_DIR, min_conf: float = 0.2):
    """Return (hand_count, [(wrist_x, wrist_y), ...]) for an RGB image."""
    from mediapipe.tasks import python as mpp
    from mediapipe.tasks.python import vision

    model = os.path.join(model_dir, _HAND_MODEL)
    if not os.path.exists(model):
        raise FileNotFoundError(f"hand landmarker model missing: {model}")
    with vision.HandLandmarker.create_from_options(
        vision.HandLandmarkerOptions(
            base_options=mpp.BaseOptions(model_asset_path=model),
            num_hands=8,
            min_hand_detection_confidence=min_conf,
        )
    ) as hl:
        res = hl.detect(_to_mp(img))
    wrists = [(round(lm[0].x, 3), round(lm[0].y, 3)) for lm in res.hand_landmarks]
    return len(res.hand_landmarks), wrists


def pose_keypoints(img, model_dir: str = _DEFAULT_MODEL_DIR):
    """Return a list of 33 (x, y, visibility) tuples, or None if no pose."""
    from mediapipe.tasks import python as mpp
    from mediapipe.tasks.python import vision

    model = os.path.join(model_dir, _POSE_MODEL)
    if not os.path.exists(model):
        raise FileNotFoundError(f"pose landmarker model missing: {model}")
    with vision.PoseLandmarker.create_from_options(
        vision.PoseLandmarkerOptions(
            base_options=mpp.BaseOptions(model_asset_path=model)
        )
    ) as pl:
        res = pl.detect(_to_mp(img))
    if not res.pose_landmarks:
        return None
    return [(lm.x, lm.y, lm.visibility) for lm in res.pose_landmarks[0]]


def _mean_joint_drift(person_kp, result_kp, joints: List[int]) -> float:
    """Mean normalized L1 drift over joints visible in the PERSON image.

    We anchor visibility on the person image (the authoritative pose
    reference) so occluded-by-garment joints in the result do not deflate
    the drift.
    """
    deltas = []
    for i in joints:
        px, py, pvis = person_kp[i]
        if pvis <= 0.5:
            continue
        rx, ry, _ = result_kp[i]
        deltas.append(abs(px - rx) + abs(py - ry))
    if not deltas:
        return 0.0
    return sum(deltas) / len(deltas)


def _wrist_swapped(person_kp, result_kp) -> bool:
    """True if the left/right wrist ordering is mirrored between the two
    images (a strong pose-transfer / wrong-body-reference signal)."""
    pl, pr = person_kp[_L_WRIST], person_kp[_R_WRIST]
    rl, rr = result_kp[_L_WRIST], result_kp[_R_WRIST]
    if min(pl[2], pr[2]) < 0.5 or min(rl[2], rr[2]) < 0.5:
        return False
    person_l_left_of_r = pl[0] < pr[0]
    result_l_left_of_r = rl[0] < rr[0]
    return person_l_left_of_r != result_l_left_of_r


# ── the comparison ─────────────────────────────────────────────────────────
@dataclass
class ArtifactReport:
    person_hands: int
    result_hands: int
    hand_count_delta: int
    person_wrists: List[Tuple[float, float]] = field(default_factory=list)
    result_wrists: List[Tuple[float, float]] = field(default_factory=list)
    pose_detected_person: bool = False
    pose_detected_result: bool = False
    pose_drift: Optional[float] = None
    wrist_swapped: Optional[bool] = None
    verdict: str = "UNKNOWN"  # PASS | WARN | FAIL
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# Thresholds (normalized L1, averaged over visible joints). Calibrated so a
# clean re-encode of the same pose is ~0.0 and a mirrored (pose-transferred)
# body is ~0.08. Real same-pose renders sit well under FAIL.
DRIFT_WARN = 0.05
DRIFT_FAIL = 0.07


def compare_person_and_result(
    person_img,
    result_img,
    model_dir: str = _DEFAULT_MODEL_DIR,
    drift_warn: float = DRIFT_WARN,
    drift_fail: float = DRIFT_FAIL,
) -> ArtifactReport:
    ph, pw = count_hands(person_img, model_dir)
    rh, rw = count_hands(result_img, model_dir)
    report = ArtifactReport(
        person_hands=ph,
        result_hands=rh,
        hand_count_delta=rh - ph,
        person_wrists=pw,
        result_wrists=rw,
    )

    # 1. Duplicated anatomy: extra hands in the result. The hand counter can
    # miss occluded hands (arms behind the back, hands in pockets); an
    # "extra" is only meaningful relative to a detected baseline.
    if ph >= 1 and report.hand_count_delta > 0:
        report.reasons.append(
            f"EXTRA_HANDS: result has {rh} hands vs person {ph} "
            f"(duplicated hand/arm artifact)"
        )
    elif ph >= 1 and report.hand_count_delta < -1:
        report.reasons.append(
            f"MISSING_HANDS: result has {rh} hands vs person {ph} "
            "(more than one hand lost — inspect)"
        )
    elif ph == 0 and rh >= 2:
        report.reasons.append(
            f"UNVERIFIABLE_HANDS: no hands detected in the person image but "
            f"{rh} in the result — hand-count check inconclusive, review"
        )

    # 2. Pose preservation.
    pk = pose_keypoints(person_img, model_dir)
    rk = pose_keypoints(result_img, model_dir)
    report.pose_detected_person = pk is not None
    report.pose_detected_result = rk is not None
    if pk is not None and rk is not None:
        drift = _mean_joint_drift(pk, rk, _POSE_JOINTS)
        report.pose_drift = round(drift, 4)
        report.wrist_swapped = _wrist_swapped(pk, rk)
        if report.wrist_swapped:
            report.reasons.append(
                "POSE_SWAP: left/right wrists are mirrored between person and "
                "result — pose/body reference not preserved"
            )
        if drift >= drift_fail:
            report.reasons.append(
                f"POSE_DRIFT_FAIL: body-pose drift {drift:.3f} >= {drift_fail} — "
                "result pose differs from the uploaded person (pose transfer?)"
            )
        elif drift >= drift_warn:
            report.reasons.append(
                f"POSE_DRIFT_WARN: body-pose drift {drift:.3f} >= {drift_warn} — "
                "review pose preservation"
            )

    # Verdict: any FAIL-class reason -> FAIL; else any reason -> WARN; else PASS.
    fail_markers = ("EXTRA_HANDS", "POSE_SWAP", "POSE_DRIFT_FAIL")
    if any(any(m in r for m in fail_markers) for r in report.reasons):
        report.verdict = "FAIL"
    elif report.reasons:
        report.verdict = "WARN"
    else:
        report.verdict = "PASS"
    return report


# ── CLI ────────────────────────────────────────────────────────────────────
def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="VTON pose/hand artifact check")
    ap.add_argument("--person", required=True, help="person image (path / data URL / base64)")
    ap.add_argument("--result", required=True, help="result image (path / data URL / base64)")
    ap.add_argument("--models", default=_DEFAULT_MODEL_DIR)
    ap.add_argument("--json", default=None, help="write the JSON report here")
    args = ap.parse_args(argv)

    person = load_image(args.person)
    result = load_image(args.result)
    report = compare_person_and_result(person, result, model_dir=args.models)
    out = json.dumps(report.to_dict(), indent=2)
    if args.json:
        with open(args.json, "w") as f:
            f.write(out + "\n")
    print(out)
    return {"PASS": 0, "WARN": 0, "FAIL": 2}[report.verdict]


if __name__ == "__main__":
    raise SystemExit(main())
