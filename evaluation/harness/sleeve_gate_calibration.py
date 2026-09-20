"""Phase 1 §7 — run the sleeve gate over all 52 saved root-cause renders.

Deterministic, CPU-only (re-reads saved renders from rootsleeve_runs.json).
Writes evaluation/results/sleeve_gate_calibration.json with per-job sleeve
drop, arm coverage samples, gate status, and aggregate separation tables.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

from vton_metrics.imaging import dominant_color, to_array  # noqa: E402
from vton_metrics.sleeve_metrics import (  # noqa: E402
    arm_coverage, garment_sleeve_drop, _content_box)

EVAL = Path(__file__).resolve().parents[1]
RESULTS = EVAL / "results"
FIX = EVAL / "fixtures"


def garment_lab(gid: str):
    gimg = Image.open(FIX / "garments" / f"{gid}.jpg").convert("RGB")
    box = _content_box(to_array(gimg))
    crop = gimg if box is None else gimg.crop(box)
    return gimg, np_array_lab(crop)


def np_array_lab(crop):
    d = dominant_color(crop, k=1)
    import numpy as np
    return np.array(d[0]["lab"])


def main():
    runs = json.loads((RESULTS / "rootsleeve_runs.json").read_text())
    drops = {}
    rows = []
    for j in runs["jobs"]:
        if j["http"] != 200:
            continue
        gid, pid = j["garment"], j["person"]
        if gid not in drops:
            gimg, lab = garment_lab(gid)
            drops[gid] = (garment_sleeve_drop(gimg), lab)
        drop, lab = drops[gid]
        person = Image.open(FIX / "persons" / f"{pid}.jpg").convert("RGB")
        out = Image.open(RESULTS / j["output"].replace("results/", ""))
        cov = arm_coverage(person, out, lab)
        expected = bool(drop.get("is_long_sleeve_candidate"))
        gate = ("N/A_SHORT_SLEEVE" if not expected else
                ("PASS" if cov.get("overall") == "SLEEVES_PRESENT" else "FAIL_SLEEVES_INCOMPLETE")
                if cov.get("status") == "OK" else "NO_POSE")
        rows.append({
            "job_id": j["job_id"], "garment": gid, "person": pid, "kind": j["kind"],
            "sleeve_drop_ratio": drop.get("sleeve_drop_ratio"),
            "expected_full_sleeves": expected,
            "arm_overall": cov.get("overall"),
            "arm_detail": {a: v["verdict"] for a, v in cov.get("arms", {}).items()},
            "samples": cov.get("arms", {}),
            "pixel_change": j.get("pixel_change"),
            "gate_status": gate,
        })
    by_g = {}
    for r in rows:
        by_g.setdefault(r["garment"], []).append(r)
    summary = {g: {
        "n": len(v),
        "sleeve_drop_ratio": v[0]["sleeve_drop_ratio"],
        "expected_full_sleeves": v[0]["expected_full_sleeves"],
        "gate_counts": {s: sum(1 for x in v if x["gate_status"] == s) for s in
                        set(x["gate_status"] for x in v)},
        "arm_overall_counts": {s: sum(1 for x in v if x["arm_overall"] == s) for s in
                               set(x["arm_overall"] for x in v)},
    } for g, v in sorted(by_g.items())}
    out = {
        "test": "sleeve_gate_calibration",
        "date": "2026-09-15",
        "source": "rootsleeve_runs.json (52 jobs, rendered 2026-09-15)",
        "thresholds": {"arm_changed": "max d_input > 10", "arm_garment": "min d_garment < 12",
                       "long_sleeve_drop": "> 0.45",
                       "note": "CANDIDATE operating points, UNFROZEN — calibration evidence only"},
        "per_garment": summary,
        "jobs": rows,
    }
    p = RESULTS / "sleeve_gate_calibration.json"
    p.write_text(json.dumps(out, indent=1))
    print(f"WROTE {p}")
    for g, s in summary.items():
        print(f"  {g}: drop={s['sleeve_drop_ratio']} expected_full={s['expected_full_sleeves']} "
              f"arms={s['arm_overall_counts']} gate={s['gate_counts']}")


if __name__ == "__main__":
    main()
