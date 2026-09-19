"""v2.3 sleeve-gate full-matrix regression (Phase 5, 2026-09-19).

Replays the ENTIRE measured 50-artifact calibration matrix
(evaluation/results/sleeve_signal_matrix.json; labels = AGENT VISUAL
INSPECTION, NOT HUMAN GROUND TRUTH) through the PRODUCTION decision
function ``evaluate_sleeves_sync`` and asserts the v2.3 decision table:

  * every measured true positive (sleeves present, old gate PASS) -> PASS
    (the anatomy channels must not over-refuse the measured TP population)
  * every measured false negative (sleeves present, old gate REFUSE)
    -> REFUSE (unchanged; the v2.3 channels only add refusals)
  * every measured drop (incl. class E + the independently constructed
    synthetic drops) and the short-sleeve-declared-long negative -> REFUSE

HARD SAFETY PROPERTY under test (P0-D):
  "A visibly incomplete long-sleeve render must never be delivered as an
   ordinary successful long-sleeve result."

The matrix rows carry the measured signal values (S1 coverage, S5
new-skin, S6 wrist-reach); this test re-measures through the production
code (no cached values in the decision path) and asserts statuses.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from PIL import Image

EVAL_ROOT = Path(__file__).resolve().parent.parent
REPO = EVAL_ROOT.parent
sys.path.insert(0, str(REPO))

from backend.app.services.vton_sleeve_gate import (  # noqa: E402
    ANATOMY_NEW_SKIN_REFUSE,
    ANATOMY_WRIST_REACH_REFUSE,
    evaluate_sleeves_sync,
)

MATRIX = EVAL_ROOT / "results" / "sleeve_signal_matrix.json"


def _rows():
    if not MATRIX.exists():
        pytest.skip("sleeve_signal_matrix.json not present (run evaluation/probes/sleeve_signal_probe.py)")
    return json.loads(MATRIX.read_text())["rows"]


def _expected_status(truth: str, old_gate: str) -> str:
    if truth in ("dropped", "dropped_synth", "short_declared_long"):
        return "REFUSE"
    if truth == "present":
        # old gate PASS -> v2.3 must keep PASS; old gate REFUSE -> stays REFUSE
        # (v2.3 is monotone: it cannot convert a refusal into a pass).
        return "PASS" if old_gate == "P" else "REFUSE"
    raise ValueError(f"unknown truth label: {truth}")


def test_matrix_has_full_phase5_population():
    rows = _rows()
    assert len(rows) >= 50, f"expected >= 50 measured rows, got {len(rows)}"
    truths = {r["truth"] for r in rows}
    assert "dropped" in truths and "dropped_synth" in truths
    assert any(r["case"] == "p4_j_arabic2_L1" for r in rows), "class-E row missing"
    # every row needs all three measured signals
    for r in rows:
        if "error" in r:
            continue
        b = r["best_arm"]
        assert "s1_coverage" in b and "s5_new_skin_outer" in b and "s6_wrist_reach" in b, r["case"]


@pytest.mark.parametrize("row", _rows(), ids=[r["case"] for r in _rows()])
def test_v23_decision_table_matches_measured_ground_truth(row):
    if "error" in row:
        pytest.skip(f"artifacts missing for {row['case']}")
    case = row["case"]
    # locate the artifact directory
    out_p = in_p = gar_p = None
    for d in (EVAL_ROOT / "results").iterdir():
        if not d.is_dir():
            continue
        cand_out = d / f"{case}.png"
        cand_in = d / f"{case}_input.png"
        cand_gar = d / f"{case}_garment.png"
        if cand_out.exists() and cand_in.exists() and cand_gar.exists():
            out_p, in_p, gar_p = cand_out, cand_in, cand_gar
            break
    assert out_p is not None, f"artifacts for {case} not found on disk"

    d = evaluate_sleeves_sync(
        slot_type="upper_inner", sleeve_length="long",
        output_img=Image.open(out_p).convert("RGB"),
        input_img=Image.open(in_p).convert("RGB"),
        garment_img=Image.open(gar_p).convert("RGB"),
    )
    expected = _expected_status(row["truth"], row["gate"])
    assert d["status"] == expected, (
        f"{case} (truth={row['truth']}, old gate={row['gate']}): expected "
        f"{expected}, got {d['status']} — coverage={d.get('coverage')} "
        f"anatomy={d.get('anatomy')}"
    )
    # on the PASS path, both anatomy channels must be inside their safe bounds
    if d["status"] == "PASS":
        assert d.get("anatomy"), "PASS decisions must carry anatomy provenance"
        ns = max(a["new_skin_outer"] for a in d["anatomy"].values())
        wz = max(a["wrist_reach"] for a in d["anatomy"].values())
        assert ns < ANATOMY_NEW_SKIN_REFUSE, (case, ns)
        assert wz >= ANATOMY_WRIST_REACH_REFUSE, (case, wz)


def test_class_e_row_measured_values_are_the_rejection_basis():
    """Provenance pin: the class-E row must show the measured values that
    justify the new-skin threshold (0.2992 >= 0.10 while every TP row is
    <= 0.0431), so a future threshold change cannot be silent."""
    rows = {r["case"]: r for r in _rows() if "error" not in r}
    e = rows["p4_j_arabic2_L1"]
    assert e["best_arm"]["s5_new_skin_outer"] >= ANATOMY_NEW_SKIN_REFUSE
    tps = [r for r in rows.values() if r["truth"] == "present" and r["gate"] == "P"]
    assert tps, "no TP rows in matrix"
    tp_max = max(r["best_arm"]["s5_new_skin_outer"] for r in tps)
    assert tp_max < ANATOMY_NEW_SKIN_REFUSE, tp_max
    tp_wz_min = min(r["best_arm"]["s6_wrist_reach"] for r in tps)
    assert tp_wz_min >= ANATOMY_WRIST_REACH_REFUSE, tp_wz_min
    drops = [r for r in rows.values()
             if r["truth"] in ("dropped", "dropped_synth")]
    for r in drops:
        # every drop must be rejected by at least one channel (or by
        # coverage alone, which the decision-table test asserts)
        b = r["best_arm"]
        assert (b["s1_coverage"] < 0.35
                or b["s5_new_skin_outer"] >= ANATOMY_NEW_SKIN_REFUSE
                or b["s6_wrist_reach"] < ANATOMY_WRIST_REACH_REFUSE), r["case"]
