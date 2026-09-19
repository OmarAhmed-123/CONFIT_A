"""P1 retry assessment — EVALUATION ONLY (analysis of P0 sequence data).

No production code change. Answers, from the measured 30-attempt sequence
(one fixed logical request), whether bounded retry is a legitimate
mitigation for this combination:

  * first-attempt success rate
  * sequential recovery: P(success within k attempts) computed FROM THE
    ACTUAL SEQUENCE (sliding window of k consecutive attempts), NOT from
    an i.i.d. assumption — the worker's L1 sampling is lumpy (clusters),
    so independence is not assumed
  * best/worst case latency for k attempts
  * added compute per retry (2 worker inferences per attempt: L1 + L2)
  * residual failure after k attempts (sequence-based)
  * per-L1-class pass rate (which L1 samples carry the passes)

Output: p1_retry_assessment.json (metrics only).
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "evaluation" / "results" / "p0_repeated_runs" / "attempts.json"
if not SRC.exists():
    print("ERROR: attempts.json missing — run P0 probe first.", file=sys.stderr)
    sys.exit(1)

data = json.loads(SRC.read_text())
att = data["attempts"]
n = len(att)
succ = [bool(a.get("final_sha256")) for a in att]
el = [a.get("elapsed_s") for a in att if isinstance(a.get("elapsed_s"), (int, float))]

# L1 class per attempt + its L2 outcome
l1seq = []
for a in att:
    l1 = a.get("layer1") or {}
    l2 = a.get("layer2") or {}
    v = l2.get("verify") or {}
    l1seq.append({"l1": (l1.get("sha256") or "")[:8],
                  "pass": v.get("PASS") is True,
                  "err": a.get("error_code"),
                  "px": v.get("metric_pixel_change")})

def window_success(k):
    """success within k consecutive attempts, sliding over the real sequence."""
    wins = 0
    total = 0
    for i in range(0, n - k + 1):
        total += 1
        if any(succ[i:i + k]):
            wins += 1
    return wins, total

out = {"n_attempts": n,
       "first_attempt_success": sum(succ),
       "first_attempt_rate": round(sum(succ) / n, 3),
       "windows": {},
       "latency_s": {"min": min(el), "median": sorted(el)[len(el)//2],
                     "max": max(el), "sum": round(sum(el), 1)}}
for k in (2, 3, 5):
    w, t = window_success(k)
    out["windows"][f"within_{k}"] = {"windows": t, "recovered": w,
                                     "rate": round(w / t, 3) if t else None,
                                     "residual_failure": round(1 - w / t, 3) if t else None,
                                     "worst_case_latency_s": round(k * max(el), 1),
                                     "expected_added_inferences_per_recovered": None}

# per-L1-class pass rates
byclass = {}
for x in l1seq:
    c = byclass.setdefault(x["l1"], {"n": 0, "pass": 0, "attempts": []})
    c["n"] += 1
    c["pass"] += int(x["pass"])
    c["attempts"].append({"l2_pass": x["pass"], "px": x["px"], "err": x["err"]})
out["per_l1_class"] = {k: {**v, "pass_rate": round(v["pass"] / v["n"], 3)} for k, v in byclass.items()}

# run-length structure (lumpiness) — pass/fail runs in the sequence
runs = []
prev = None
for i, s in enumerate(succ):
    if s != prev:
        runs.append([i + 1, int(s), 1])
        prev = s
    else:
        runs[-1][2] += 1
out["sequence_runs"] = runs

# added compute: every retry = +1 full attempt (L1+L2 inferences); on a
# recovered run, all preceding failed attempts in the window are wasted.
out["compute_note"] = ("each attempt = 2 GPU inferences (L1 top + L2 bottom); "
                       "a recovered k-window wastes up to (k-1) full attempts "
                       "of compute; no caching benefit between attempts was "
                       "observed beyond byte-identical worker output caches")

print(json.dumps({k: v for k, v in out.items() if k != "per_l1_class"}, indent=1))
for c, v in out["per_l1_class"].items():
    print(f"L1 {c}: {v['pass']}/{v['n']} pass")
    for a in v["attempts"]:
        print(f"    l2_pass={a['l2_pass']} px={a['px']} err={a['err']}")

(SRC.parent / "p1_retry_assessment.json").write_text(json.dumps(out, indent=1))
print("WROTE", SRC.parent / "p1_retry_assessment.json")
