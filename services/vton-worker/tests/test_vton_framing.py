"""The customer-upload framing gate, decided from DWPose keypoints.

WHY THIS EXISTS
---------------
Until now only the *registry* avatars were framing-checked. A real customer could
upload a head-and-shoulders portrait and get a render with a garment smeared over
a face — the same meaningless-100% failure that the avatar fix closed on the demo
path. That is the gap between "real for a demo" and "real for a customer".

WHY POSE AND NOT PIXELS
-----------------------
The obvious serverless check — head width, face-blob size, subject/background
contrast — was measured and rejected: a legitimate cluttered-background full-body
photo scored 37.7% "head width" (indistinguishable from a bust) and a YCrCb skin
blob was absent entirely on an obvious portrait. Thresholds that separated the
studio fixtures would have refused real customers, and the failure would have
landed hardest on people photographing themselves at home and people with darker
skin tones.

DWPose keypoints carry none of that. A keypoint is a position, not a colour, and
not a background. There is no term in this module that can see skin tone or
clutter — that is why the bias check below is structural, not statistical.

WHY IT MUST RUN BEFORE DIFFUSION
--------------------------------
DWPose is the first stage of the render pipeline anyway. Running it on its own
turns a refusal into ~1-2 s of GPU instead of 18-60 s (one MMDiT pass per seed
in the QA ladder). The tests at the bottom pin that ordering.
"""

from __future__ import annotations

import numpy as np
import pytest

from vton_framing import (
    KEYPOINT_CONFIDENCE,
    FRAMING_INVALID_CODE,
    OPENPOSE_ANKLES,
    OPENPOSE_HEAD,
    OPENPOSE_KNEES,
    OPENPOSE_LEG_LINE,
    assess_person_framing,
    pose_from_dwpose_output,
)


# ── helpers: build a DWPose-shaped output from visible keypoints ──────────

def _pose(visible: dict[int, tuple[float, float]], hidden=(),
          confidence: float = 0.9) -> dict:
    """A DWPose detector output: `bodies.candidate` (normalised x,y) + scores.

    Hidden keypoints are marked exactly the way DWPose marks them: coordinate
    -1 and score -1.
    """
    cand = np.full((1, 18, 2), -1.0, dtype=np.float32)
    score = np.full((1, 18), -1.0, dtype=np.float32)
    for idx, (x, y) in visible.items():
        if idx in hidden:
            continue
        cand[0, idx] = (x, y)
        score[0, idx] = confidence
    return {"bodies": {"candidate": cand, "subset": score},
            "hands": np.zeros((1, 21, 2)), "faces": np.zeros((1, 68, 2))}


def _standing_full_body(**kw) -> dict:
    """A standing adult, head to feet, filling a portrait frame."""
    # OpenPose-18 order, the one the vendored DWPose actually returns.
    return _pose({
        0: (0.50, 0.09),                       # nose
        14: (0.48, 0.08), 15: (0.52, 0.08),    # eyes
        16: (0.46, 0.09), 17: (0.54, 0.09),    # ears
        1: (0.50, 0.19),                       # neck
        2: (0.42, 0.20), 5: (0.58, 0.20),      # shoulders
        3: (0.38, 0.32), 6: (0.62, 0.32),      # elbows
        4: (0.36, 0.44), 7: (0.64, 0.44),      # wrists
        8: (0.44, 0.48), 11: (0.56, 0.48),     # hips
        9: (0.44, 0.66), 12: (0.56, 0.66),     # knees
        10: (0.44, 0.87), 13: (0.56, 0.87),    # ankles
    }, **kw)


# ── accept: the case that must never be refused ──────────────────────────

def test_a_standing_full_body_is_accepted():
    verdict = assess_person_framing(_pose({
        0: (0.5, 0.09), 14: (0.48, 0.08), 15: (0.52, 0.08),
        2: (0.42, 0.20), 5: (0.58, 0.20),
        8: (0.44, 0.48), 11: (0.56, 0.48),
        9: (0.44, 0.66), 12: (0.56, 0.66),
        10: (0.44, 0.87), 13: (0.56, 0.87),
    }))
    assert verdict["full_body"] is True
    assert verdict["code"] is None


def test_a_full_body_cropped_at_the_shoes_is_accepted():
    """Knees visible, feet out of frame: a real customer photo, still dressable.

    Refusing here would be a false reject on an otherwise perfect input, which
    is the failure mode this gate must not have.
    """
    v = assess_person_framing(_pose({
        0: (0.5, 0.12), 2: (0.42, 0.24), 5: (0.58, 0.24),
        8: (0.44, 0.52), 11: (0.56, 0.52),
        9: (0.44, 0.74), 12: (0.56, 0.74),
    }))
    assert v["full_body"] is True


def test_a_seated_customer_with_knees_visible_is_accepted():
    v = assess_person_framing(_pose({
        0: (0.5, 0.20), 2: (0.40, 0.32), 5: (0.58, 0.32),
        8: (0.44, 0.55), 11: (0.56, 0.55),
        9: (0.70, 0.58), 12: (0.72, 0.62),
        10: (0.80, 0.74),
    }))
    assert v["full_body"] is True


def test_only_one_confident_ankle_is_enough():
    """Occlusion is normal. Requiring both ankles refuses real photos."""
    v = assess_person_framing(_pose({
        0: (0.5, 0.10), 2: (0.42, 0.22), 5: (0.58, 0.22),
        8: (0.44, 0.50), 11: (0.56, 0.50),
        10: (0.44, 0.88),                    # right ankle only
    }))
    assert v["full_body"] is True


# ── refuse: the failure this gate exists for ─────────────────────────────

def test_a_head_and_shoulders_portrait_is_refused_with_the_honest_code():
    v = assess_person_framing(_pose({
        0: (0.50, 0.35), 14: (0.47, 0.33), 15: (0.53, 0.33),
        16: (0.44, 0.35), 17: (0.56, 0.35),
        2: (0.36, 0.62), 5: (0.64, 0.62),
    }))
    assert v["full_body"] is False
    assert v["code"] == FRAMING_INVALID_CODE
    assert "full-body" in v["message"].lower() or "full body" in v["message"].lower()
    # the evidence says what was actually seen, for the operator
    assert v["evidence"]["lowest_region"] == "shoulders"


def test_a_waist_up_photo_is_refused():
    v = assess_person_framing(_pose({
        0: (0.5, 0.18), 2: (0.38, 0.42), 5: (0.62, 0.42),
        3: (0.30, 0.58), 6: (0.70, 0.58),
        4: (0.26, 0.74), 7: (0.74, 0.74),
    }))
    assert v["full_body"] is False
    assert v["evidence"]["lowest_region"] in ("shoulders", "arms")


def test_a_photo_with_no_detectable_person_is_refused():
    v = assess_person_framing(_pose({}))
    assert v["full_body"] is False
    assert v["code"] == FRAMING_INVALID_CODE
    assert v["evidence"]["reason"] == "no_person_detected"


def test_low_confidence_keypoints_below_the_hip_do_not_rescue_a_bust():
    """A weak guess at a knee must not be treated as a body.

    This is the anti-false-positive direction: without the confidence floor, a
    portrait with one low-confidence ankle guess would pass as a full body and
    re-open the meaningless render.
    """
    pose = _pose({0: (0.50, 0.30), 2: (0.36, 0.60), 5: (0.64, 0.60)},
                 confidence=0.9)
    # inject a *weak* knee far below, the way a detector hallucinates
    pose["bodies"]["candidate"][0, 9] = (0.45, 0.93)
    pose["bodies"]["subset"][0, 9] = KEYPOINT_CONFIDENCE * 0.5
    v = assess_person_framing(pose)
    assert v["full_body"] is False


def test_keypoints_marked_hidden_by_dwpose_are_not_counted():
    """DWPose zeroes the coordinate for invisible points; -1 must not read as
    a (normalised) position at the origin."""
    pose = _pose({0: (0.5, 0.30), 2: (0.36, 0.60), 5: (0.64, 0.60)})
    pose["bodies"]["candidate"][0, 10] = (-1.0, -1.0)
    pose["bodies"]["subset"][0, 10] = 0.95   # score high, position absent
    v = assess_person_framing(pose)
    assert v["full_body"] is False


# ── the bias check: structural, because the gate has no colour input ─────

def test_the_gate_is_geometric_only():
    """No skin, colour, or background term may enter this decision.

    Measured reason: the pixel alternatives refused a legitimate
    cluttered-background full-body photo (37.7% "head width") and found no skin
    blob at all on an obvious portrait. Any reintroduction of those signals
    re-introduces that bias, so the refusal is structural here: the function
    takes pose geometry and nothing else.
    """
    import inspect

    params = set(inspect.signature(assess_person_framing).parameters)
    assert params == {"pose", "min_confidence"}, (
        f"assess_person_framing grew a parameter: {sorted(params)}. A colour, "
        f"skin or background input here would reintroduce the demographic bias "
        f"that this design exists to avoid."
    )


def test_a_cluttered_background_full_body_is_accepted():
    """The bias case, expressed as geometry.

    A cluttered room and a plain studio backdrop differ only in pixels, and this
    decision has no access to pixels — so the same keypoints give the same
    verdict. Pinned so the reasoning is visible rather than assumed.
    """
    keypoints = {
        0: (0.50, 0.10), 2: (0.41, 0.22), 5: (0.59, 0.22),
        8: (0.44, 0.50), 11: (0.56, 0.50),
        9: (0.44, 0.68), 12: (0.56, 0.68),
        10: (0.44, 0.88), 13: (0.56, 0.88),
    }
    assert assess_person_framing(_pose(keypoints))["full_body"] is True


# ── adapter: DWPose output shape ─────────────────────────────────────────

def test_pose_from_dwpose_output_normalises_the_candidate_and_scores():
    cand = np.full((1, 18, 2), -1.0, dtype=np.float32)
    score = np.full((1, 18), -1.0, dtype=np.float32)
    cand[0, 0] = (0.5, 0.1); score[0, 0] = 0.88
    cand[0, 15] = (0.44, 0.9); score[0, 15] = 0.71
    out = {"bodies": {"candidate": cand, "subset": score}}

    points = pose_from_dwpose_output(out)
    assert points[0] == pytest.approx((0.5, 0.1))
    assert points[15] == pytest.approx((0.44, 0.9))
    assert 1 not in points        # score -1 -> not present
    assert 5 not in points        # coordinate -1 -> not present


def test_pose_from_dwpose_output_survives_multiple_candidates():
    """DWPose returns every candidate when several people are in frame; the
    framing question is about the person the renderer will use, i.e. the
    first/best candidate, never an average of the crowd."""
    cand = np.full((2, 18, 2), -1.0, dtype=np.float32)
    score = np.full((2, 18), -1.0, dtype=np.float32)
    cand[0, 0] = (0.5, 0.1); score[0, 0] = 0.9
    cand[1, 0] = (0.2, 0.8); score[1, 0] = 0.4
    points = pose_from_dwpose_output({"bodies": {"candidate": cand, "subset": score}})
    assert points[0] == pytest.approx((0.5, 0.1))


def test_the_head_region_matches_the_order_the_model_really_returns():
    """OpenPose-18: nose 0, eyes 14/15, ears 16/17.

    The first version of this module assumed COCO-18 (eyes 1/2, ears 3/4) and the
    real model then placed a portrait's EYES in the "leg" slots — which is how a
    bust passed. The order is pinned here so it cannot drift back.
    """
    assert OPENPOSE_HEAD == frozenset({0, 14, 15, 16, 17})
    assert OPENPOSE_KNEES == frozenset({9, 12})
    assert OPENPOSE_ANKLES == frozenset({10, 13})
    assert OPENPOSE_LEG_LINE == frozenset({9, 10, 12, 13})


# ── the refusal must be cheap: it happens before diffusion ───────────────

def test_the_worker_gates_framing_before_it_calls_render():
    """Ordering is the cost guarantee.

    The QA seed ladder runs one MMDiT pass per seed (~18 s each on the A10G).
    A refusal that happened after `engine.render(...)` would cost the full
    render; the gate must run first, so `render` is never reached for a
    refused input.
    """
    from pathlib import Path

    src = Path(__file__).resolve().parents[1].joinpath("modal_app_segfee.py").read_text()
    raw = src[src.index("def process("):]
    # Ignore comments: the gate's own rationale mentions render(), and comments
    # must not be able to satisfy (or break) a check about executed order.
    body = "\n".join(line.split("#", 1)[0] for line in raw.splitlines())

    gate = body.find("_enforce_person_framing(")
    render = body.find("self.engine.render(")
    assert gate != -1, "the worker no longer runs the framing gate"
    assert render != -1
    assert gate < render, (
        "_enforce_person_framing must run BEFORE self.engine.render(): a refusal "
        "after the diffusion pass costs the full render"
    )
    # ...and that helper is the one that raises the honest code.
    helper = src[src.index("def _enforce_person_framing("):]
    assert "assess_person_framing" in helper
    assert "VTON_PERSON_FRAMING_INVALID" in helper or 'verdict["code"]' in helper
    assert '"diffusion_performed": False' in helper


class _StubEngine:
    """Stands in for the GPU engine: records whether a render was attempted."""

    def __init__(self, pose):
        self._pose = pose
        self.render_calls = 0
        self.pose_calls = 0

    def detect_person_pose(self, person_image):
        self.pose_calls += 1
        return self._pose

    def render(self, **kwargs):  # pragma: no cover - must never be reached
        self.render_calls += 1
        raise AssertionError("render() ran on a refused input — the gate is too late")


def _load_worker_module():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "modal_app_segfee.py"
    spec = importlib.util.spec_from_file_location("modal_app_segfee_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # `modal` and fastapi import cleanly; no GPU work at import
    return module


def test_a_bust_is_refused_without_ever_calling_render():
    from fastapi import HTTPException

    worker = _load_worker_module()
    engine = _StubEngine(_pose({
        0: (0.50, 0.35), 14: (0.47, 0.33), 15: (0.53, 0.33),
        2: (0.36, 0.62), 5: (0.64, 0.62),          # shoulders only
    }))
    with pytest.raises(HTTPException) as excinfo:
        worker._enforce_person_framing(engine, object())

    exc = excinfo.value
    assert exc.status_code == 422
    assert exc.detail["error"]["code"] == FRAMING_INVALID_CODE
    assert exc.detail["error"]["diffusion_performed"] is False
    assert exc.detail["error"]["evidence"]["lowest_region"] == "shoulders"
    assert isinstance(exc.detail["error"]["pose_check_seconds"], float)
    assert engine.render_calls == 0, "a refused upload must spend no diffusion"
    assert engine.pose_calls == 1


def test_a_full_body_is_not_refused_and_reaches_the_renderer():
    worker = _load_worker_module()
    engine = _StubEngine(_standing_full_body())
    worker._enforce_person_framing(engine, object())   # must not raise
    assert engine.render_calls == 0        # the gate itself never renders
    assert engine.pose_calls == 1


def test_a_pose_model_failure_is_not_disguised_as_a_framing_refusal():
    """A broken gate must not tell the customer to retake a good photo."""
    from fastapi import HTTPException

    worker = _load_worker_module()

    class _BrokenEngine:
        def detect_person_pose(self, _): raise RuntimeError("weights missing")

    with pytest.raises(HTTPException) as excinfo:
        worker._enforce_person_framing(_BrokenEngine(), object())
    assert excinfo.value.status_code == 500
    assert excinfo.value.detail["error"]["code"] == "INFERENCE_FAILED"
    assert excinfo.value.detail["error"]["code"] != FRAMING_INVALID_CODE


# ── the encoding the real model returns ──────────────────────────────────

def test_a_visible_nose_is_not_mistaken_for_an_invisible_point():
    """`bodies.subset` holds int(18*person + keypoint), so a visible NOSE is 0.

    A naive `score >= 0.3` test reads that 0 as "not visible" and would refuse a
    perfectly framed photo of anyone whose nose is the only head point kept.
    """
    cand = np.full((1, 18, 2), -1.0, dtype=np.float32)
    sub = np.full((1, 18), -1.0, dtype=np.float32)
    cand[0, 0] = (0.5, 0.10)            # nose
    sub[0, 0] = 0.0                     # the sentinel for keypoint 0 of person 0
    cand[0, 10] = (0.45, 0.90)          # ankle
    sub[0, 10] = 10.0
    v = assess_person_framing({"bodies": {"candidate": cand, "subset": sub}})
    assert v["full_body"] is True
    assert v["evidence"]["has_head"] is True


def _real_output():
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parent / "fixtures" / "dwpose_real_output.json"
    return json.loads(path.read_text())["images"]


@pytest.mark.parametrize("name", sorted(_real_output()))
def test_captured_real_dwpose_output_is_judged_correctly(name):
    """Replay of the actual model, not a synthetic ideal.

    Every row was produced by running the vendored DWPose over a real image on
    2026-10-25 (`scripts/dwpose_framing_probe.py`) and stored verbatim. The
    portrait and the waist-up crop are the two that the first (COCO-ordered)
    implementation wrongly accepted.
    """
    row = _real_output()[name]
    pose = {
        "bodies": {
            "candidate": np.asarray([row["candidate"]], dtype=np.float32),
            "subset": np.asarray([row["subset"]], dtype=np.float32),
        }
    }
    verdict = assess_person_framing(pose)
    assert verdict["full_body"] is row["expected_full_body"], (
        f"{name}: expected full_body={row['expected_full_body']}, got "
        f"{verdict['full_body']} (reason={verdict['evidence'].get('reason')})"
    )
    if not row["expected_full_body"]:
        assert verdict["code"] == FRAMING_INVALID_CODE
