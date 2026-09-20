"""Verdict logic tests (Phase 0.5 §28): candidate operating points, structural."""
from __future__ import annotations

from vton_metrics.verdict import Evidence, verdicts_at_candidate_points


def _ev():
    e = Evidence(sample_id="t1", arm="SINGLE")
    e.metrics["face_aligned_ssim"] = 0.91
    e.metrics["garment_delta_e_mean"] = 8.2
    e.metrics["ocr_text_score"] = None
    e.structural["face_present"] = True
    e.structural["pose_present"] = True
    e.structural["worker_success"] = True
    return e


def test_verdicts_high_good():
    pts = {"face_aligned_ssim": {"op": ">=", "value": 0.85}}
    v = verdicts_at_candidate_points(_ev(), pts)
    assert v["face_aligned_ssim"]["pass"] is True
    assert v["face_aligned_ssim"]["value"] == 0.91


def test_verdicts_low_good_fail():
    pts = {"garment_delta_e_mean": {"op": "<=", "value": 5.0}}
    v = verdicts_at_candidate_points(_ev(), pts)
    assert v["garment_delta_e_mean"]["pass"] is False


def test_missing_metric_is_none():
    pts = {"ocr_text_score": {"op": ">=", "value": 0.5}}
    v = verdicts_at_candidate_points(_ev(), pts)
    assert v["ocr_text_score"]["pass"] is None
    assert v["ocr_text_score"]["value"] is None


def test_structural_failure_is_not_threshold():
    e = _ev()
    e.structural["face_present"] = False
    v = verdicts_at_candidate_points(e, {})
    assert v["structural_face_present"]["pass"] is False
    assert v["structural_face_present"]["candidate_op"] == "structural"


def test_candidate_op_echoed_not_frozen():
    pts = {"face_aligned_ssim": {"op": ">=", "value": 0.7}}
    v = verdicts_at_candidate_points(_ev(), pts)
    assert v["face_aligned_ssim"]["candidate_op"] == {"op": ">=", "value": 0.7}
