"""Person-framing gate: is there a full body in this photo?

The customer upload path had no framing check at all. A customer could upload a
head-and-shoulders portrait and receive a render with a garment smeared over a
face, with the per-layer gate reporting success — that gate verifies the GARMENT,
and nothing on the person side asked whether a body was in the frame.

WHY THIS RUNS ON THE GPU WORKER
-------------------------------
The decision needs DWPose, which already runs as the first stage of the render
pipeline on the worker. Two consequences:

  * the Vercel/serverless bundle gains no dependency (this module imports numpy
    only, and never leaves the worker image);
  * a refusal costs one pose pass (measured 0.40-0.70 s on 4 CPU cores,
    0.6-0.7 s on the A10G path it replaces) instead of the diffusion ladder
    (~18 s per seed, three seeds, measured on the A10G).

WHY KEYPOINTS AND NOT PIXELS
----------------------------
The obvious serverless heuristics were measured and rejected before this was
written:

    signal                                   legitimate cluttered-bg full body
    head-width fraction                      37.7%  (looks like a bust)
    YCrCb face/skin blob                     no blob at all on an obvious
                                             portrait; 95.9% on that same photo

Any threshold that separated the studio fixtures refused that real photo, and it
would have refused it most often for people photographing themselves at home and
for people with darker skin tones. A DWPose keypoint is a position: it carries no
colour and no background statistics, so the demographic bias of the pixel
alternatives cannot enter this decision. ``test_the_gate_is_geometric_only``
pins that structurally.

WHAT THE REAL MODEL ACTUALLY RETURNS (measured, 2026-10-25)
-----------------------------------------------------------
This module was first written against the COCO-18 convention and the unit tests
passed, but the *real* detector output refused to cooperate — the gate accepted a
head-and-shoulders portrait. Running the actual model over a corpus
(``scripts/dwpose_framing_probe.py``) showed two things a synthetic test could
never have told us:

  1. **The returned order is OpenPose-18, not COCO-18.** ``wholebody.py`` remaps
     mmpose columns before ``DWposeDetector.__call__`` slices ``candidate[:, :18]``,
     so index 9 is the right KNEE and indices 14-17 are eyes/ears. Read as COCO,
     the eyes and ears of a portrait landed in the "leg" slots, which is exactly
     why the bust passed.
  2. **``bodies.subset`` is not a confidence array.** ``__call__`` overwrites it
     with ``int(18*person + keypoint)`` for every point above
     ``KEYPOINT_VISIBILITY_THRESHOLD`` and ``-1`` for the rest. The real
     confidences are discarded inside ``wholebody.py``. So a ">= 0.3" test on
     that array is meaningless, and — the dangerous case — the sentinel for a
     visible NOSE is the integer 0, which a naive confidence threshold reads as
     invisible.

Both are handled below, and ``tests/test_vton_framing.py`` replays the captured
real model output so this cannot silently regress.

THE RULE
--------
Accept when a head keypoint AND at least one knee-or-ankle keypoint are visible.

DWPose has already applied its own 0.3 visibility threshold by the time we see
the data, so "visible" here means "the model was at least 30% confident", not
"the coordinate was present".

The asymmetry is deliberate: refusing a legitimate full-body photo is a worse
error than accepting an odd one, because it blocks a paying customer with no
recourse. So the rule asks only "is any part of the leg line visible?", accepts a
single confident ankle (occlusion is normal), accepts a photo cropped at the
shoes (knees visible) and accepts a seated customer. It does not require both
ankles, a particular aspect ratio, a minimum height span, or a vertical ordering
of joints — a seated person's knees are often level with their hips, and none of
those thresholds could be calibrated without production traffic. Measured
residual risk: a bust on which DWPose confidently hallucinates a knee would pass;
that did not happen on any of the seven corpus images, and it is recorded in the
phase report rather than papered over with an uncalibrated extra threshold.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Tuple

import numpy as np

#: The code the backend and the UI already use for an unusable person image.
FRAMING_INVALID_CODE = "VTON_PERSON_FRAMING_INVALID"

#: DWPose's own visibility threshold (KEYPOINT_VISIBILITY_THRESHOLD in the
#: vendored fork). Points below it arrive as -1, so this value only matters for
#: callers that pass raw confidence arrays (the tests do; the worker does not).
KEYPOINT_CONFIDENCE = 0.3

# OpenPose-18 body keypoints — the order the vendored DWPose actually returns
# (verified against the model's own output on 2026-10-25; see module docstring).
OPENPOSE_NOSE = 0
OPENPOSE_NECK = 1
OPENPOSE_HEAD = frozenset({0, 14, 15, 16, 17})      # nose, eyes, ears
OPENPOSE_SHOULDERS = frozenset({2, 5})
OPENPOSE_ELBOWS = frozenset({3, 6})
OPENPOSE_WRISTS = frozenset({4, 7})
OPENPOSE_HIPS = frozenset({8, 11})
OPENPOSE_KNEES = frozenset({9, 12})
OPENPOSE_ANKLES = frozenset({10, 13})
OPENPOSE_LEG_LINE = frozenset({9, 10, 12, 13})     # knees + ankles

_LOWER_BODY_MESSAGE = (
    "VTON_PERSON_FRAMING_INVALID: this photo does not show the whole body. "
    "A try-on needs a full-length photo — head to feet, standing, arms slightly "
    "away from your body — so the garment can be fitted to your actual figure. "
    "Please upload a full-body photo."
)
_NO_PERSON_MESSAGE = (
    "VTON_PERSON_FRAMING_INVALID: we could not find a person in this photo. "
    "Please upload a clear, full-length photo of yourself, head to feet, on a "
    "plain background if possible."
)


def _as_candidates(candidate: Any, subset: Any) -> Tuple[np.ndarray, np.ndarray]:
    """Normalise DWPose's varying shapes to ``(people, 18, 2)`` and ``(people, 18)``.

    Shapes observed from the real model: ``(18, 2)`` for a single person,
    ``(1, 18, 2)`` after ``_find_best_candidate``, and *empty 1-D arrays* when
    nobody is in frame.
    """
    cand = np.asarray(candidate, dtype=np.float32)
    score = np.asarray(subset, dtype=np.float32)
    if cand.ndim == 2 and cand.shape[-1] == 2:
        cand = cand[None, ...]
    if score.ndim == 1:
        score = score[None, ...]
    if cand.ndim != 3 or score.ndim != 2 or cand.size == 0 or score.size == 0:
        return np.zeros((0, 18, 2), np.float32), np.zeros((0, 18), np.float32)
    return cand[:, :18], score[:, :18]


def _is_visible(value: float, person: int, keypoint: int, min_confidence: float) -> bool:
    """Both visibility conventions, decided per point.

    The worker receives the fork's sentinel encoding (``18*person + keypoint``, or
    -1); the tests hand in raw confidences (0..1, or -1). Accept either, but never
    mistake the sentinel for a low score: a visible nose is exactly ``0``.
    """
    if value < 0:
        return False
    if int(value) == 18 * person + keypoint and float(value).is_integer():
        return True
    return value >= min_confidence


def _visible_points(
    pose: Mapping[str, Any], min_confidence: float = KEYPOINT_CONFIDENCE
) -> Dict[int, Tuple[float, float]]:
    """Keypoints of the most complete person, as ``{index: (x, y)}`` in 0..1.

    Multiple candidates appear when several people are in frame. The renderer
    dresses one person — the best-scoring candidate — so the framing question is
    asked about that candidate only, never an average of the crowd.
    """
    bodies = (pose or {}).get("bodies") or {}
    cand, score = _as_candidates(bodies.get("candidate"), bodies.get("subset"))

    best: Dict[int, Tuple[float, float]] = {}
    best_key: Tuple[int, float] = (-1, -1.0)
    for person in range(cand.shape[0]):
        points: Dict[int, Tuple[float, float]] = {}
        total = 0.0
        for keypoint in range(cand.shape[1]):
            x, y = float(cand[person, keypoint, 0]), float(cand[person, keypoint, 1])
            raw = float(score[person, keypoint])
            if x < 0.0 or y < 0.0:            # the fork zeroes absent positions to -1
                continue
            if not _is_visible(raw, person, keypoint, min_confidence):
                continue
            points[keypoint] = (x, y)
            total += raw
        key = (len(points), total)
        if key > best_key:
            best, best_key = points, key
    return best


def pose_from_dwpose_output(output: Mapping[str, Any]) -> Dict[int, Tuple[float, float]]:
    """Reduce a DWPose result to ``{keypoint index: (x, y)}`` for visible points.

    Convenience wrapper over :func:`_visible_points` with no confidence floor of
    its own: the model has already applied its 0.3 threshold.
    """
    return _visible_points(output, min_confidence=0.0)


def _lowest_region(visible: Iterable[int]) -> str:
    """Name the lowest body region seen, for the operator-facing evidence."""
    seen = set(visible)
    if seen & OPENPOSE_LEG_LINE:
        return "legs"
    if seen & OPENPOSE_HIPS:
        return "hips"
    if seen & (OPENPOSE_WRISTS | OPENPOSE_ELBOWS):
        return "arms"
    if seen & OPENPOSE_SHOULDERS:
        return "shoulders"
    if seen & OPENPOSE_HEAD:
        return "head"
    return "none"


def assess_person_framing(
    pose: Mapping[str, Any], min_confidence: float = KEYPOINT_CONFIDENCE
) -> Dict[str, Any]:
    """Decide whether a person image is usable for a full-body try-on.

    Returns ``{"full_body": bool, "code": str | None, "message": str | None,
    "evidence": {...}}``. Geometry only — see the module docstring.
    """
    visible = _visible_points(pose, min_confidence)
    regions = sorted(visible)
    has_head = bool(visible.keys() & OPENPOSE_HEAD)
    has_legs = bool(visible.keys() & OPENPOSE_LEG_LINE)

    evidence: Dict[str, Any] = {
        "keypoints_visible": regions,
        "lowest_region": _lowest_region(regions),
        "has_head": has_head,
        "has_leg_line": has_legs,
        "confidence_floor": min_confidence,
    }

    if not visible:
        evidence["reason"] = "no_person_detected"
        return {"full_body": False, "code": FRAMING_INVALID_CODE,
                "message": _NO_PERSON_MESSAGE, "evidence": evidence}

    if not has_head:
        evidence["reason"] = "no_head_keypoint"
        return {"full_body": False, "code": FRAMING_INVALID_CODE,
                "message": _NO_PERSON_MESSAGE, "evidence": evidence}

    if not has_legs:
        # A head and torso with nothing below the hips: a bust or a waist-up
        # crop. This is the input that used to produce a garment on a face.
        evidence["reason"] = "no_leg_keypoints"
        return {"full_body": False, "code": FRAMING_INVALID_CODE,
                "message": _LOWER_BODY_MESSAGE, "evidence": evidence}

    return {"full_body": True, "code": None, "message": None, "evidence": evidence}
