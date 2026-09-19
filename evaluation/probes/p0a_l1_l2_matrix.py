"""P0-A: L1 hash -> L2 outcome matrix (analysis only, no new runs).

Reads evaluation/results/p0_repeated_runs/attempts.json and tabulates:
  * every distinct L1 output class (sha prefix), frequency,
  * the L2 outcome observed after each occurrence (worker verify verdict,
    pixel_change, color_shift) — the matrix answers whether L1 sample
    identity deterministically predicts L2 outcome at N=30,
  * per-attempt latency (for the P1 retry assessment).
Writes p0a_matrix.json (hashes + metrics only).
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "evaluation" / "results" / "p0_repeated_runs" / "attempts.json"
if not SRC.exists():
    print("ERROR: attempts.json not found — P0 probe has not finished.", file=sys.stderr)
    sys.exit(1)

data = json.loads(SRC.read_text())
attempts = data["attempts"]

classes = defaultdict(list)
for a in attempts:
    l1 = a.get("layer1")
    if not l1 or not l1.get("sha256"):
        classes["<L1_MISSING>"].append(a)
        continue
    classes[l1["sha256"][:8]].append(a)

rows = []
for sha8 in sorted(classes, key=lambda s: (-len(classes[s]), s)):
    atts = classes[sha8]
    outcomes = []
    for a in atts:
        l2 = a.get("layer2")
        v = (l2 or {}).get("verify") if l2 else None
        out = {
            "attempt": a["attempt"],
            "http": a.get("http"),
            "error_code": a.get("error_code"),
            "l2_sha8": (l2 or {}).get("sha256", "")[:8] if l2 and l2.get("sha256") else None,
            "l2_verify_PASS": v.get("PASS") if v else None,
            "pixel_change": (v or {}).get("metric_pixel_change") if v else None,
            "color_shift": (v or {}).get("metric_color_shift") if v else None,
            "elapsed_s": a.get("elapsed_s"),
        }
        outcomes.append(out)
    rows.append({
        "l1_sha8": sha8,
        "n_attempts": len(atts),
        "attempt_ids": [a["attempt"] for a in atts],
        "l2_outcomes": outcomes,
        "distinct_l2_shas": sorted({o["l2_sha8"] for o in outcomes if o["l2_sha8"]}),
        "l2_pass_count": sum(1 for o in outcomes if o["l2_verify_PASS"] is True),
        "l2_fail_count": sum(1 for o in outcomes if o["l2_verify_PASS"] is not True),
    })

print(f"total attempts: {len(attempts)}  distinct L1 classes: {len(rows)}")
print(f"{'L1':10} {'n':>2} {'attempts':22} {'L2pass':>6} {'L2fail':>6}  L2 outcomes (px / err)")
for r in rows:
    at = ",".join(str(x) for x in r["attempt_ids"])
    print(f"{r['l1_sha8']:10} {r['n_attempts']:>2} {at:22} {r['l2_pass_count']:>6} {r['l2_fail_count']:>6}")
    for o in r["l2_outcomes"]:
        px = f"{o['pixel_change']:.4f}" if isinstance(o.get("pixel_change"), (int, float)) else str(o.get("pixel_change"))
        cs = f"{o['color_shift']:.4f}" if isinstance(o.get("color_shift"), (int, float)) else str(o.get("color_shift"))
        print(f"           a{o['attempt']:02d} l2={o['l2_sha8'] or '-'} PASS={o['l2_verify_PASS']} px={px} cs={cs} err={o['error_code'] or '-'} {o['elapsed_s']}s")

# determinism test: within each L1 class, are ALL L2 outcomes identical?
for r in rows:
    verds = {o["l2_verify_PASS"] for o in r["l2_outcomes"]}
    shas = set(o["l2_sha8"] for o in r["l2_outcomes"] if o["l2_sha8"])
    if len(verds) > 1:
        r["l2_deterministic"] = False
        r["note"] = f"SAME L1 class produced DIFFERENT L2 verdicts {sorted(map(str, verds))}"
    else:
        r["l2_deterministic"] = True
        r["note"] = f"verdict={sorted(verds)} distinct_L2_bytes={len(shas)}"

print()
for r in rows:
    print(f"L1 {r['l1_sha8']}: deterministic={r['l2_deterministic']} — {r['note']}")

# latency summary (P1 input)
el = [a["elapsed_s"] for a in attempts if isinstance(a.get("elapsed_s"), (int, float))]
el.sort()
if el:
    n = len(el)
    print(f"\nlatency s: min={el[0]} med={el[n//2]} p90={el[int(n*0.9)]} max={el[-1]}")
ok = sum(1 for a in attempts if a.get("final_sha256"))
print(f"attempt-level success (final render produced): {ok}/{n}")

out = {"request": data.get("request"), "rows": rows,
       "latency_s": {"min": el[0] if el else None, "median": el[n//2] if el else None,
                     "p90": el[int(n * 0.9)] if el else None, "max": el[-1] if el else None},
       "success_count": ok, "total": n}
(SRC.parent / "p0a_matrix.json").write_text(json.dumps(out, indent=1))
print("WROTE", SRC.parent / "p0a_matrix.json")
