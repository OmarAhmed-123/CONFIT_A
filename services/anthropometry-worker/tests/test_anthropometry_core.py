"""Feature 05 core tests — REAL vendored models, honest refusals, disclosures.

These tests load the actual Bayesian-ridge bundles (male.pkl/female.pkl) and
the real vendored pipeline, including the acceptance check mandated by the
feature design: the repository's own demo_landmarks.json must reproduce its
published measurements through the worker's exact model path.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "vendor" / "landmarks2anthropometry" / "upstream"))

import anthropometry_core as core
import landmark_mapping as lm
from test_landmark_mapping import synth_person  # shared synthetic A-pose


# ── the vendored demo acceptance check (feature design requirement) ─────────
DEMO_README = {  # published output of estimate_measurements.py on the demo
    "Ankle Circumference (mm)": 262.04, "Arm Length (Shoulder to Elbow) (mm)": 341.65,
    "Arm Length (Shoulder to Wrist) (mm)": 682.76, "Arm Length (Spine to Wrist) (mm)": 875.01,
    "Chest Circumference (mm)": 1011.42, "Crotch Height (mm)": 756.22,
    "Head Circumference (mm)": 571.57, "Hip Circ Max Height (mm)": 858.80,
    "Hip Circumference, Maximum (mm)": 1089.39, "Neck Base Circumference (mm)": 492.71,
    "Stature (mm)": 1751.95,
}


def test_vendor_demo_reproduces_published_measurements_through_worker_path():
    """The repo's demo cloud through the worker's exact predict path
    (process_landmarks scale=1 on the mm cloud, normalize=False) must
    reproduce the published README values — proving the vendored models and
    the invocation path are intact."""
    demo = json.load(open(core.vendor_dir() / "data" / "demo_landmarks.json"))
    cloud_mm = {k: [c * 1000 for c in v] for k, v in demo.items()}  # m -> mm
    out = core._predict_all(cloud_mm, "male")
    for name, expected in DEMO_README.items():
        assert out[name] == pytest.approx(expected, abs=1.0), name


# ── happy path on a synthetic frontal A-pose ────────────────────────────────
def test_estimate_happy_path_male():
    resp = core.estimate(synth_person(), [1.0] * 33, "male")
    assert resp["status"] == "completed"
    assert resp["measurement_method"] == "ai_estimate"
    assert resp["quality"] in ("full", "partial")
    # every one of the 11 model outputs is accounted for: kept or excluded
    kept_model = [m for m in resp["measurements"] if m["source"] == "model"]
    excluded_model = [e for e in resp["excluded"] if e["name"].endswith("(mm)")]
    assert len(kept_model) + len(excluded_model) == 11
    # direct geometry always ships in full
    sources = {m["name"]: m["source"] for m in resp["measurements"]}
    for name in ("Stature", "Inseam (Hip to Ankle)", "Arm Length (Shoulder to Elbow)",
                 "Arm Length (Shoulder to Wrist)"):
        assert sources[name] == "direct_geometry"
    # the model's own stature entry is present and labeled as model output
    assert sources.get("Stature (mm)") == "model" or any(
        e["name"] == "Stature (mm)" for e in resp["excluded"])
    # every entry carries mm + cm
    for m in resp["measurements"]:
        assert m["value_cm"] == pytest.approx(m["value_mm"] / 10.0, abs=0.11)
    # synthetic is a 1.75m-proportioned adult: plausibility gates passed
    stature = next(m["value_mm"] for m in resp["measurements"] if m["name"] == "Stature")
    assert 1500 < stature < 1900
    # every kept measurement passes the anatomical bounds
    for m in resp["measurements"]:
        assert not lm.plausibility_check({m["name"]: m["value_mm"]}), m["name"]


def test_estimate_happy_path_female_uses_female_bundle():
    """The female bundle loads and is actually exercised. On the (male-
    proportioned) synthetic cloud some female regressors land outside the
    anatomical envelope — that must surface as transparent exclusions, never
    as fabricated values or a crash."""
    resp = core.estimate(synth_person(), [1.0] * 33, "female")
    assert resp["status"] == "completed"
    assert resp["quality"] in ("full", "partial", "geometry_only")
    resp_m = core.estimate(synth_person(), [1.0] * 33, "male")
    fem = {m["name"]: m["value_mm"] for m in resp["measurements"] if m["source"] == "model"}
    fem_excl = {e["name"] for e in resp["excluded"]}
    mal = {m["name"]: m["value_mm"] for m in resp_m["measurements"] if m["source"] == "model"}
    # the female bundle produced output (kept or excluded) for every measurement
    assert len(fem) + len(fem_excl) == 11
    # and it actually differs from the male bundle where both kept values
    assert any(abs(fem[k] - mal[k]) > 0.5 for k in fem if k in mal)


def test_quality_partial_lists_excluded_measurements_transparently():
    """A model output outside the anatomical range is excluded and REPORTED,
    while direct geometry still ships."""
    mp = synth_person()
    real = core._predict_all(lm.build_caesar_cloud(np.asarray(mp)), "male")
    def fake_predict(cloud, sex):
        out = dict(real)
        out["Ankle Circumference (mm)"] = 90.0  # impossible → must be excluded
        return out
    orig = core._predict_all
    core._predict_all = fake_predict
    try:
        resp = core.estimate(mp, [1.0] * 33, "male")
    finally:
        core._predict_all = orig
    assert resp["quality"] == "partial"
    assert any(e["name"] == "Ankle Circumference (mm)" and e["reason"] == "outside_anatomical_range"
               for e in resp["excluded"])
    names = {m["name"] for m in resp["measurements"]}
    assert "Ankle Circumference (mm)" not in names
    assert "Stature" in names and "Inseam (Hip to Ankle)" in names  # geometry always ships


def test_mandatory_disclosures_present():
    resp = core.estimate(synth_person(), [1.0] * 33, "male")
    assert resp["accuracy_note"] == "±2-3 cm"
    assert "±2-3 cm" in resp["disclaimer"]
    assert resp["landmark_source"] == "mediapipe_pose_world_approx"
    assert resp["model"]["license"] == "unlicensed-research-only"
    assert resp["model"]["commercial"] is False
    assert resp["model"]["vendor_commit"] == "de2df48dd428dce457339141c709d7510e0e6f2b"
    assert resp["engine"] == "landmarks2anthropometry_visapp2024_cpu"
    assert "pose_quality" in resp and "scale_calibration" in resp


# ── honest refusals ─────────────────────────────────────────────────────────
def test_refuses_invalid_sex():
    with pytest.raises(core.EstimationRefused) as e:
        core.estimate(synth_person(), [1.0] * 33, "other")
    assert e.value.code == "INPUT_INVALID"


def test_refuses_no_pose():
    with pytest.raises(core.EstimationRefused) as e:
        core.estimate(np.zeros((5, 3)), None, "male")
    assert e.value.code == "NO_USABLE_POSE"


def test_refuses_low_visibility():
    vis = [1.0] * 33
    vis[lm.MP["right_heel"]] = 0.1
    with pytest.raises(core.EstimationRefused) as e:
        core.estimate(synth_person(), vis, "male")
    assert e.value.code == "NO_USABLE_POSE"
    assert "full-body" in e.value.message or "visible" in e.value.message


def test_refuses_out_of_envelope_pose():
    with pytest.raises(core.EstimationRefused) as e:
        core.estimate(synth_person(bent_arms=True), [1.0] * 33, "male")
    assert e.value.code == "POSE_OUT_OF_ENVELOPE"
    assert "arms" in e.value.message
    assert "pose_quality" in e.value.details


def test_refuses_yawed_pose():
    with pytest.raises(core.EstimationRefused) as e:
        core.estimate(synth_person(yaw_deg=40), [1.0] * 33, "male")
    assert e.value.code == "POSE_OUT_OF_ENVELOPE"


# ── height calibration ──────────────────────────────────────────────────────
def test_height_hint_calibrates_scale_and_is_disclosed():
    resp = core.estimate(synth_person(), [1.0] * 33, "male", height_cm=175.0)
    assert resp["scale_calibration"]["applied"] is True
    assert resp["scale_calibration"]["source"] == "user_reported_height"
    assert resp["scale_calibration"]["reported_height_cm"] == 175.0
    # after calibration the direct stature must match the reported height
    stature = next(m["value_mm"] for m in resp["measurements"] if m["name"] == "Stature")
    assert stature == pytest.approx(1750.0, abs=5.0)


def test_height_hint_out_of_range_refused():
    with pytest.raises(core.EstimationRefused) as e:
        core.estimate(synth_person(), [1.0] * 33, "male", height_cm=300.0)
    assert e.value.code == "INPUT_INVALID"


def test_height_hint_conflicting_with_photo_refused():
    # reporting 210cm for a photo that reads ~168cm => factor ~1.25 > band
    with pytest.raises(core.EstimationRefused) as e:
        core.estimate(synth_person(), [1.0] * 33, "male", height_cm=225.0)
    assert e.value.code == "SCALE_MISMATCH"


# ── plausibility gate ───────────────────────────────────────────────────────
def test_implausible_geometry_is_a_hard_refusal(monkeypatch):
    """If the OBSERVED geometry itself is impossible the photo is unusable —
    refuse the whole request rather than ship an impossible body."""
    def fake_direct(wl):
        return {"Stature": 900.0, "Inseam (Hip to Ankle)": 700.0,
                "Arm Length (Shoulder to Elbow)": 300.0,
                "Arm Length (Shoulder to Wrist)": 600.0}
    monkeypatch.setattr(lm, "direct_geometry_measurements", fake_direct)
    with pytest.raises(core.EstimationRefused) as e:
        core.estimate(synth_person(), [1.0] * 33, "male")
    assert e.value.code == "IMPLAUSIBLE_RESULT"
    assert "Stature" in e.value.details["failed_measurements"]


# ── scale invariance of the whole pipeline ─────────────────────────────────
def test_pipeline_scales_with_body_size():
    r1 = core.estimate(synth_person(scale=1.0), [1.0] * 33, "male")
    r2 = core.estimate(synth_person(scale=1.1), [1.0] * 33, "male")
    s1 = next(m["value_mm"] for m in r1["measurements"] if m["name"] == "Stature")
    s2 = next(m["value_mm"] for m in r2["measurements"] if m["name"] == "Stature")
    assert s2 == pytest.approx(s1 * 1.1, rel=0.02)
