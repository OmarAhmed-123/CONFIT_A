#!/usr/bin/env python3
"""P7 P1: FULL v2.4 regression matrix on the frozen production gate.

Runs `evaluate_sleeves_sync` (the exact production function, imported —
no monkeypatch) on:
  * all 50 matrix-row artifacts (Phase 2/3/4/5 cohorts),
  * the 6 Phase-6 adversarial composites (on the cal_02 base),
and asserts every row against the frozen v2.4 decision table.

Outputs (P8: measurements + statuses only):
  evaluation/results/p7_v24_full_matrix.json
    - per case: per-arm channels, verdict, reason, truth, expected, match
    - defect-safety split: every dropped/short_declared_long row REFUSE?
    - valid-render acceptance split: present rows REFUSED (over-refusal),
      each one listed
    - named-artifact mapping (Phase 7 P1 list) -> case id + result

Usage: python3 evaluation/probes/p7_v24_full_matrix.py
"""
import json
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from PIL import Image  # noqa: E402
from backend.app.services import vton_sleeve_gate as gate  # noqa: E402

RES = REPO / "evaluation" / "results"
ADV = RES / "p6_sleeve_adversarial"

# case -> dir (from the original probe's CASES list)
PROBE_SRC = (REPO / "evaluation" / "probes" / "sleeve_signal_probe.py").read_text()
CASE_DIR = {}
for m in re.finditer(r'\("(\w+)",\s*"(\w+)",\s*"(\w+)"', PROBE_SRC):
    CASE_DIR[f"{m.group(2)}_{m.group(3)}"] = m.group(1)


def run_case(case: str, render_p: Path, input_p: Path, garment_p: Path) -> dict:
    out = {"case": case, "files": {"render": str(render_p.name), "input": str(input_p.name),
                                   "garment": str(garment_p.name)}}
    if not (render_p.exists() and input_p.exists() and garment_p.exists()):
        out.update(status="MISSING_FILES", reason="artifact absent (gitignored after sandbox reset?)")
        return out
    try:
        d = gate.evaluate_sleeves_sync(
            slot_type="upper_inner", sleeve_length="long",
            output_img=Image.open(render_p).convert("RGB"),
            input_img=Image.open(input_p).convert("RGB"),
            garment_img=Image.open(garment_p).convert("RGB"),
        )
        cov = d.get("coverage") or {}
        anat = d.get("anatomy") or {}
        out.update(
            status=d["status"], reason=(d.get("reason") or "")[:300],
            coverage= cov,
            per_arm={
                "s1": cov,
                "s5_new_skin": {k: v["new_skin_outer"] for k, v in anat.items()},
                "s5b_any_skin": {k: v["any_skin_outer"] for k, v in anat.items()},
                "s6_wrist_reach": {k: v["wrist_reach"] for k, v in anat.items()},
            },
        )
        return out
    except Exception as e:  # noqa: BLE001
        out.update(status="ERROR", reason=f"{type(e).__name__}: {str(e)[:200]}")
        return out


def main():
    t0 = time.time()
    matrix = json.loads((RES / "sleeve_signal_matrix.json").read_text())
    adv = json.loads((ADV / "results.json").read_text())
    rows = []
    for r in matrix["rows"]:
        case = r["case"]
        d = CASE_DIR.get(case)
        if not d:
            continue
        base = RES / d
        rows.append((case, r["truth"], base / f"{case}.png", base / f"{case}_input.png", base / f"{case}_garment.png"))
    for name in adv["cases"]:
        rows.append((name, "dropped", ADV / f"{name}.png",
                     RES / "calibration_v22" / "cal_02_L1_input.png",
                     RES / "calibration_v22" / "cal_02_L1_garment.png"))

    results = []
    for case, truth, rp, ip, gp in rows:
        rec = run_case(case, rp, ip, gp)
        rec["truth_agent"] = truth
        results.append(rec)

    # ---- frozen expected table: v2.4 = v2.3 AND max(s5b) < 0.15 (measured) ----
    v24 = {x["case"]: x for x in json.loads((RES / "p6_sleeve_v24.json").read_text())["rows"]}
    for rec in results:
        case = rec["case"]
        v = v24.get(case)
        if v:
            rec["expected_status"] = "PASS" if (v["v23"] and max(v["s5b"].values()) < 0.15) else "REFUSE"
        elif rec["status"] == "MISSING_FILES":
            rec["expected_status"] = "n/a"
        else:
            rec["expected_status"] = None  # composite not in v24 json (all are, actually)
        if rec["expected_status"] in ("PASS", "REFUSE"):
            rec["match"] = rec["status"] == rec["expected_status"]

    ok = [r for r in results if r.get("match") is True]
    mism = [r for r in results if r.get("match") is False]
    missing = [r["case"] for r in results if r["status"] == "MISSING_FILES"]
    errors = [r["case"] for r in results if r["status"] == "ERROR"]

    # ---- split 1: defect safety ----
    DROP = {"dropped", "dropped_synth", "short_declared_long"}
    defect_rows = [r for r in results if r["truth_agent"] in DROP and r["status"] in ("PASS", "REFUSE")]
    defect_passed = [r["case"] for r in defect_rows if r["status"] == "PASS"]
    # ---- split 2: valid-render acceptance (over-refusal) ----
    present_rows = [r for r in results if r["truth_agent"] == "present" and r["status"] in ("PASS", "REFUSE")]
    overrefused = []
    for r in present_rows:
        if r["status"] == "REFUSE":
            ca = r.get("per_arm", {})
            overrefused.append({
                "case": r["case"],
                "reason_kind": ("s1_coverage" if "NOT VERIFIED" in r.get("reason", "") or "NOT present" in r.get("reason", "")
                                else "anatomy:" + (
                                    "new_skin" if "new-skin" in r.get("reason", "")
                                    else "any_skin" if "exposed forearm skin" in r.get("reason", "")
                                    else "wrist_reach")),
                "best_s1": max((ca.get("s1") or {}).values()) if ca.get("s1") else None,
                "s5_max": max((ca.get("s5_new_skin") or {}).values()) if ca.get("s5_new_skin") else None,
                "s5b_max": max((ca.get("s5b_any_skin") or {}).values()) if ca.get("s5b_any_skin") else None,
                "s6_max": max((ca.get("s6_wrist_reach") or {}).values()) if ca.get("s6_wrist_reach") else None,
            })

    out = {
        "gate_version": "v2.4 frozen (SLEEVE_GATE_V24_FROZEN_SPEC_2026-09-19.md)",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "n_rows": len(results),
        "matched_frozen_table": len(ok),
        "mismatches": mism,
        "missing_files": missing,
        "errors": errors,
        "defect_safety": {
            "definition": "no row with truth in {dropped, dropped_synth, short_declared_long} may PASS",
            "defect_rows": len(defect_rows),
            "defect_rows_passing": defect_passed,
            "VERDICT": "SAFE" if not defect_passed else "SLEEVE SAFETY = BLOCKED",
        },
        "valid_render_acceptance": {
            "definition": "present rows REFUSED = over-refusal (usability defect, documented)",
            "present_rows": len(present_rows),
            "over_refused": len(overrefused),
            "over_refusal_list": overrefused,
        },
        "rows": results,
        "elapsed_s": round(time.time() - t0, 1),
    }
    RES.mkdir(parents=True, exist_ok=True)
    (RES / "p7_v24_full_matrix.json").write_text(json.dumps(out, indent=1))
    print(f"rows={len(results)} matched_frozen={len(ok)} mismatches={[m['case'] for m in mism]} "
          f"missing={len(missing)} errors={len(errors)}")
    print(f"defect rows={len(defect_rows)} passing={defect_passed} -> {out['defect_safety']['VERDICT']}")
    print(f"present rows={len(present_rows)} over-refused={len(overrefused)}: "
          f"{[o['case'] for o in overrefused]}")


if __name__ == "__main__":
    main()
