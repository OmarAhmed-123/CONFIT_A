"""Honest per-layer VTON verification aggregation — zero-GPU unit tests.

Root defect fixed here (confirmed from production ``confit-vton-worker-segfee``
logs): the FASHN worker returns HTTP 200 + an image even when a garment layer
was NOT effectively applied (``verify.PASS=False`` on a ``_l2``/``_l3`` job).
The backend previously dropped the per-layer verify outcome and reported the
result as a clean, fully-verified complete outfit — so a failed upper layer
(e.g. a blazer) was served as a false "complete outfit verified" success.

These tests pin the honest contract via the single source of truth
``aggregate_layer_verification`` used by BOTH the sync multi-render path and
the async job path:
  * a layer is "verified" ONLY when verify_pass is exactly True;
  * any layer with verify_pass != True => all_layers_verified is False and the
    layer appears in failed_layers;
  * an empty layer list is never "verified".

No GPU, no worker, no DB: the function is pure.
"""
from __future__ import annotations

import pytest

from backend.app.services.tryon_service import aggregate_layer_verification


def _layer(layer: int, slot: str, verify_pass, pixel_change=3.0, product_id=None):
    return {
        "layer": layer,
        "product_id": product_id,
        "slot_type": slot,
        "verify_pass": verify_pass,
        "metric_pixel_change": pixel_change,
    }


def test_all_layers_pass_is_fully_verified():
    meta = [
        _layer(1, "lower_body", True, product_id=1),
        _layer(2, "upper_body", True, product_id=2),
        _layer(3, "outer_jacket", True, product_id=3),
    ]
    agg = aggregate_layer_verification(meta)
    assert agg["all_layers_verified"] is True
    assert agg["layers_requested"] == 3
    assert agg["verified_layers"] == 3
    assert agg["layers_failed"] == 0
    assert agg["failed_layers"] == []


def test_failed_upper_layer_is_not_fully_verified():
    """The exact production scenario: bottom+top applied, blazer (_l2) not applied."""
    meta = [
        _layer(1, "lower_body", True, product_id=1),
        _layer(2, "outer_jacket", False, product_id=2),  # blazer NOT applied
    ]
    agg = aggregate_layer_verification(meta)
    assert agg["all_layers_verified"] is False
    assert agg["layers_failed"] == 1
    assert agg["verified_layers"] == 1
    assert len(agg["failed_layers"]) == 1
    assert agg["failed_layers"][0]["layer"] == 2
    assert agg["failed_layers"][0]["slot_type"] == "outer_jacket"
    assert agg["failed_layers"][0]["verify_pass"] is False


def test_null_verify_pass_counts_as_unverified():
    """A missing/None verify (worker did not return a PASS) must NOT be treated
    as verified — honest default is 'unconfirmed'."""
    meta = [
        _layer(1, "upper_body", None),
        _layer(2, "upper_body", None),
    ]
    agg = aggregate_layer_verification(meta)
    assert agg["all_layers_verified"] is False
    assert agg["layers_failed"] == 2


def test_falsy_zero_pixel_change_is_unverified():
    """verify_pass is the gate, not the metric — but a layer whose engine marked
    PASS False with 0 pixel change is clearly unapplied."""
    meta = [
        _layer(1, "upper_body", False, pixel_change=0.0),
    ]
    agg = aggregate_layer_verification(meta)
    assert agg["all_layers_verified"] is False
    assert agg["layers_failed"] == 1


def test_empty_layer_list_is_never_verified():
    agg = aggregate_layer_verification([])
    assert agg["all_layers_verified"] is False
    assert agg["layers_requested"] == 0
    assert agg["layers_failed"] == 0
    assert agg["failed_layers"] == []


def test_single_layer_pass():
    agg = aggregate_layer_verification([_layer(1, "upper_body", True)])
    assert agg["all_layers_verified"] is True
    assert agg["layers_failed"] == 0


def test_mixed_three_layers_one_failed():
    meta = [
        _layer(1, "upper_body", True, product_id=1),
        _layer(2, "upper_body", True, product_id=2),
        _layer(3, "outer_jacket", False, product_id=3),  # blazer fails
    ]
    agg = aggregate_layer_verification(meta)
    assert agg["all_layers_verified"] is False
    assert agg["layers_requested"] == 3
    assert agg["verified_layers"] == 2
    assert agg["layers_failed"] == 1
    assert [f["product_id"] for f in agg["failed_layers"]] == [3]
