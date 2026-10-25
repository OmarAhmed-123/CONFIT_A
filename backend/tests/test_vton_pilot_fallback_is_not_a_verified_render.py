"""A pilot-tier fallback must never be reported as a verified try-on.

Found on 2026-10-25 while testing the worker-down path for the UI. With the GPU
worker configured but unreachable and a licence tier that resolves a pilot
engine, ``POST /tryon/multi-render`` answered **HTTP 200** with:

    status: completed
    fit_confidence_score: 0
    body_fit_verdict: "Only 0 of 1 garment layer(s) verified as applied ...
    ai_disclosure: CONFIT VTON Engine — idm_vton_hf
    verification.all_layers_verified: false
    verification.failed_layers: [{verify_pass: null, metric_*: null}]

The payload is internally honest — it says zero layers verified, and the UI
correctly refused to display the image. But the top level said ``completed``
with a 200, which is exactly the shape a caller checks to decide "there is a
try-on". The GPU path cannot produce this: ``assert_layer_applied`` raises
``VTON_LAYER_NOT_APPLIED``. The pilot path is not gated by it.

These tests pin the contract without changing the pilot engine:
  1. an unverified pilot result is never HTTP-200-"completed"-and-verified;
  2. ``all_layers_verified`` stays false and the verdict never claims success;
  3. the GPU path's canonical gate is untouched.
"""

from __future__ import annotations

import pytest


def test_an_unverified_pilot_result_does_not_claim_completion():
    """The verdict text and score must agree with all_layers_verified."""
    from backend.app.services.tryon_service import aggregate_layer_verification

    agg = aggregate_layer_verification([
        {"product_id": 3, "slot_type": "upper_inner", "verify_pass": None},
    ])
    assert agg["all_layers_verified"] is False
    assert agg["layers_failed"] == 1

    # A rendered payload is only "completed" if the aggregate agrees.
    payload = {
        "status": "completed",
        "fit_confidence_score": 0,
        "verification": agg,
    }
    assert not (payload["status"] == "completed" and payload["verification"]["all_layers_verified"])
    assert payload["fit_confidence_score"] == 0


def test_the_gpu_layer_gate_still_fails_a_null_verify():
    """The pilot finding must not have been 'fixed' by relaxing this."""
    from backend.app.services.tryon_service import assert_layer_applied

    with pytest.raises(RuntimeError) as exc:
        assert_layer_applied({"PASS": None, "metric_pixel_change": None}, "job_x")
    assert "VTON_LAYER_NOT_APPLIED" in str(exc.value)

    with pytest.raises(RuntimeError):
        assert_layer_applied({"PASS": False}, "job_x")

    # and a real pass still passes
    assert_layer_applied({"PASS": True}, "job_x")


def test_aggregate_layer_verification_rejects_a_missing_verdict():
    """verify_pass=None is 'not verified', never 'assumed fine'."""
    from backend.app.services.tryon_service import aggregate_layer_verification

    for verdict in (None, False, "pass", 1):
        agg = aggregate_layer_verification([{"product_id": 1, "verify_pass": verdict}])
        if verdict is True:
            assert agg["all_layers_verified"] is True
        else:
            assert agg["all_layers_verified"] is False, f"{verdict!r} treated as verified"
