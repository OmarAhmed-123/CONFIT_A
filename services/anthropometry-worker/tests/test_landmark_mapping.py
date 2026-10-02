"""Feature 05 unit tests — landmark mapping (no MediaPipe, no model, no torch).

The synthetic A-pose generator encodes the REAL MediaPipe world-landmark
convention verified on a live photo: x = subject's LEFT is POSITIVE, y is
DOWN, z is negative toward the camera (subject front).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

# vendored model package (for LANDMARKS_ORDER, the source of truth)
VENDOR = Path(__file__).resolve().parents[3] / "vendor" / "landmarks2anthropometry" / "upstream"
sys.path.insert(0, str(VENDOR))

import landmark_mapping as lm


# ── synthetic frontal A-pose (metres, MediaPipe world-landmark axes) ────────
def synth_person(scale: float = 1.0, yaw_deg: float = 0.0, bent_arms: bool = False,
                 tilt_deg: float = 0.0, h: float = 1.75) -> np.ndarray:
    th = np.radians(yaw_deg)
    tl = np.radians(tilt_deg)
    P: dict = {}

    def setp(name: str, x: float, y: float, z: float) -> None:
        # yaw about the vertical (y) axis
        xr = x * math.cos(th) + z * math.sin(th)
        zr = -x * math.sin(th) + z * math.cos(th)
        # shoulder tilt: rotate shoulder/elbow/wrist x/y
        if name in ("left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
                    "left_wrist", "right_wrist"):
            xr2 = xr * math.cos(tl) - y * math.sin(tl)
            y2 = xr * math.sin(tl) + y * math.cos(tl)
            xr, y = xr2, y2
        P[name] = np.array([xr * scale, y * scale, zr * scale])

    # MediaPipe convention (verified on live data): +x = subject's LEFT,
    # and the subject FRONT is NEGATIVE z (toward the camera; heel z>0).
    setp("nose", 0, -h + 0.12, -0.08)
    setp("left_eye_outer", 0.03, -h + 0.10, -0.04)
    setp("right_eye_outer", -0.03, -h + 0.10, -0.04)
    setp("left_eye_inner", 0.015, -h + 0.10, -0.04)
    setp("left_eye", 0.022, -h + 0.10, -0.04)
    setp("right_eye_inner", -0.015, -h + 0.10, -0.04)
    setp("right_eye", -0.022, -h + 0.10, -0.04)
    setp("left_ear", 0.08, -h + 0.15, 0.02)
    setp("right_ear", -0.08, -h + 0.15, 0.02)
    setp("mouth_left", 0.02, -h + 0.18, -0.05)
    setp("mouth_right", -0.02, -h + 0.18, -0.05)
    setp("left_shoulder", 0.18, -h + 0.26, 0.0)
    setp("right_shoulder", -0.18, -h + 0.26, 0.0)
    if bent_arms:  # elbows out, forearms forward (hands-on-hips-like, 90°)
        setp("left_elbow", 0.18, -h + 0.56, 0.0)
        setp("right_elbow", -0.18, -h + 0.56, 0.0)
        setp("left_wrist", 0.02, -h + 0.56, -0.12)
        setp("right_wrist", -0.02, -h + 0.56, -0.12)
    else:          # relaxed, slightly abducted
        setp("left_elbow", 0.22, -h + 0.56, -0.01)
        setp("right_elbow", -0.22, -h + 0.56, -0.01)
        setp("left_wrist", 0.25, -h + 0.87, -0.02)
        setp("right_wrist", -0.25, -h + 0.87, -0.02)
    setp("left_index", 0.26, -h + 0.97, -0.03)
    setp("right_index", -0.26, -h + 0.97, -0.03)
    setp("left_pinky", 0.24, -h + 0.96, -0.02)
    setp("right_pinky", -0.24, -h + 0.96, -0.02)
    setp("left_thumb", 0.28, -h + 0.95, -0.04)
    setp("right_thumb", -0.28, -h + 0.95, -0.04)
    setp("left_hip", 0.09, -h + 0.80, 0.0)
    setp("right_hip", -0.09, -h + 0.80, 0.0)
    setp("left_knee", 0.09, -h + 1.25, -0.01)
    setp("right_knee", -0.09, -h + 1.25, -0.01)
    setp("left_ankle", 0.09, -h + 1.68, 0.0)
    setp("right_ankle", -0.09, -h + 1.68, 0.0)
    setp("left_heel", 0.09, -h + 1.75, 0.04)
    setp("right_heel", -0.09, -h + 1.75, 0.04)
    setp("left_foot_index", 0.09, -h + 1.72, -0.12)
    setp("right_foot_index", -0.09, -h + 1.72, -0.12)
    arr = np.zeros((33, 3))
    for name, idx in lm.MP.items():
        arr[idx] = P[name]
    return arr


# ── validate_pose ────────────────────────────────────────────────────────────
def test_validate_pose_rejects_wrong_shape():
    with pytest.raises(lm.LandmarkMappingError):
        lm.validate_pose(np.zeros((10, 3)))


def test_validate_pose_rejects_nonfinite():
    bad = synth_person()
    bad[11] = [np.nan, 0, 0]
    with pytest.raises(lm.LandmarkMappingError):
        lm.validate_pose(bad)


def test_validate_pose_rejects_low_visibility_key_joints():
    mp = synth_person()
    vis = [1.0] * 33
    vis[lm.MP["left_ankle"]] = 0.2
    with pytest.raises(lm.LandmarkMappingError, match="full-body"):
        lm.validate_pose(mp, vis)


# ── build_caesar_cloud ──────────────────────────────────────────────────────
def test_cloud_has_exactly_the_caesar_names():
    cloud = lm.build_caesar_cloud(synth_person())
    from landmark_utils import LANDMARKS_ORDER  # vendored source of truth
    assert set(cloud.keys()) == set(LANDMARKS_ORDER)


def test_cloud_structure_is_anatomically_ordered():
    cloud = lm.build_caesar_cloud(synth_person())
    # left/right never crossed on any mirrored pair
    for base in ("Acromion", "Trochanterion", "ASIS", "PSIS", "Humeral Lateral Epicn"):
        assert cloud[f"Lt. {base}"][0] > cloud[f"Rt. {base}"][0], base
    # back points behind front points (CAESAR +y = back)
    assert cloud["Lt. PSIS"][1] > cloud["Lt. ASIS"][1]
    assert cloud["Nuchale"][1] > cloud["Substernale"][1]
    assert cloud["Lt. Knee Crease"][1] > cloud["Substernale"][1] - 400  # behind torso front
    # vertical ordering: head above sternum above crotch above heel
    assert cloud["Sellion"][2] > cloud["Substernale"][2]
    assert cloud["Substernale"][2] > cloud["Crotch"][2]
    assert cloud["Crotch"][2] > cloud["Lt. Calcaneous, Post."][2]
    # symmetric constructions are symmetric
    assert abs(cloud["Lt. Acromion"][0] + cloud["Rt. Acromion"][0]) < 1e-6


def test_cloud_scales_linearly_with_body_scale():
    c1 = lm.build_caesar_cloud(synth_person(scale=1.0))
    c2 = lm.build_caesar_cloud(synth_person(scale=1.1))
    for name in ("Lt. Acromion", "Substernale", "Crotch", "Lt. ASIS"):
        for axis in range(3):
            if c1[name][axis]:
                assert c2[name][axis] == pytest.approx(c1[name][axis] * 1.1, rel=1e-3), name


def test_cloud_values_are_in_mm():
    cloud = lm.build_caesar_cloud(synth_person())
    # shoulder width (widened to CAESAR proportions) ~ 0.796 * torso ≈ 0.35 m
    sh_w = abs(cloud["Lt. Acromion"][0] - cloud["Rt. Acromion"][0])
    assert 250 < sh_w < 500  # mm, human range
    stature_span = cloud["Nuchale"][2] - cloud["Lt. Calcaneous, Post."][2]
    assert 1400 < stature_span < 2000  # mm


def test_cloud_rejects_degenerate_input():
    with pytest.raises(lm.LandmarkMappingError):
        lm.build_caesar_cloud(np.zeros((33, 3)))


def test_flip_x_mirrors_the_cloud():
    c = lm.build_caesar_cloud(synth_person())
    cf = lm.build_caesar_cloud(synth_person(), flip_x=True)
    assert cf["Lt. Acromion"][0] == pytest.approx(c["Lt. Acromion"][0])
    assert cf["Lt. Acromion"][0] > cf["Rt. Acromion"][0]  # still not crossed


# ── direct geometry ──────────────────────────────────────────────────────────
def test_direct_geometry_matches_synthetic_truth():
    geo = lm.direct_geometry_measurements(synth_person())
    # crown = ear line (h-0.15) + 0.5*ear_w (0.08) above; heels at h-1.75
    # -> stature = 1.75 - 0.15 + 0.08 = 1.68 m
    assert geo["Stature"] == pytest.approx(1680, abs=15)
    # hips at h-0.80, ankles at h-1.68
    assert geo["Inseam (Hip to Ankle)"] == pytest.approx(880, abs=10)
    # shoulder (0.18, h-0.26) -> elbow (0.22, h-0.56) -> wrist (0.25, h-0.87)
    assert geo["Arm Length (Shoulder to Elbow)"] == pytest.approx(303, abs=8)
    assert geo["Arm Length (Shoulder to Wrist)"] == pytest.approx(614, abs=10)


def test_direct_geometry_scales_linearly():
    g1 = lm.direct_geometry_measurements(synth_person())
    g2 = lm.direct_geometry_measurements(synth_person(scale=1.1))
    assert g2["Stature"] == pytest.approx(g1["Stature"] * 1.1, rel=1e-3)
    assert g2["Inseam (Hip to Ankle)"] == pytest.approx(g1["Inseam (Hip to Ankle)"] * 1.1, rel=1e-3)


# ── pose quality / envelope ─────────────────────────────────────────────────
def test_frontal_pose_passes_envelope():
    lm.check_pose_envelope(lm.pose_quality(synth_person()))  # no raise


@pytest.mark.parametrize("kw,match", [
    (dict(yaw_deg=35), "face the camera"),
    (dict(bent_arms=True), "arms"),
    (dict(tilt_deg=25), "level"),
])
def test_out_of_envelope_poses_are_refused_with_guidance(kw, match):
    with pytest.raises(lm.LandmarkMappingError, match=match):
        lm.check_pose_envelope(lm.pose_quality(synth_person(**kw)))


# ── plausibility ────────────────────────────────────────────────────────────
def test_plausibility_flags_impossible_values():
    bad = lm.plausibility_check({"Stature (mm)": 900, "Chest Circumference (mm)": 2200})
    assert "Stature (mm)" in bad and "Chest Circumference (mm)" in bad


def test_plausibility_passes_adult_ranges():
    ok = {"Stature (mm)": 1750, "Hip Circumference, Maximum (mm)": 950, "Stature": 1750}
    assert lm.plausibility_check(ok) == []


# ── calibration constants are the demo's real anatomy ───────────────────────
def test_calibration_constants_match_demo_frame():
    # shoulder/trochanter width ratios derived from the vendored demo subject
    assert lm.SHOULDER_W_FRAC == pytest.approx(0.437 / 0.549, abs=1e-3)
    assert lm.TROCHANTER_W_FRAC == pytest.approx(0.381 / 0.549, abs=1e-3)


def test_widening_preserves_already_caesar_width_girdles():
    """If observed joints are already at CAESAR width, widen() is a no-op."""
    mp = synth_person()
    # widen the synthetic shoulders to CAESAR width first
    cloud = lm.build_caesar_cloud(mp)
    sh_w = abs(cloud["Lt. Acromion"][0] - cloud["Rt. Acromion"][0]) / 1000
    cur = float(np.linalg.norm(mp[lm.MP["left_shoulder"]] - mp[lm.MP["right_shoulder"]]))
    if cur < sh_w:
        out = (sh_w - cur) / 2
        d = mp[lm.MP["left_shoulder"]] - mp[lm.MP["right_shoulder"]]
        u = d / np.linalg.norm(d)
        mp[lm.MP["left_shoulder"]] += u * out
        mp[lm.MP["right_shoulder"]] -= u * out
    cloud2 = lm.build_caesar_cloud(mp)
    # acromion positions barely move (no further widening needed)
    assert abs(cloud2["Lt. Acromion"][0] - cloud["Lt. Acromion"][0]) < 5  # mm
