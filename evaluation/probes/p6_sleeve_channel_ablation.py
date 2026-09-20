"""P6 P1-A: sleeve-gate channel ablation — confusion matrices.

Replays the 50-row Phase-5 matrix (per-row channel values + agent
labels; AGENT VISUAL INSPECTION — NOT HUMAN GROUND TRUTH) under four
decision rules and reports TP/TN/FP/FN + rates + margins:

  V1  S1 coverage >= 0.35                          (the pre-v2.3 gate)
  V2  S1 >= 0.35 AND S5 new-skin-outer < 0.10
  V3  S1 >= 0.35 AND S6 wrist-reach >= 0.05
  V4  S1 >= 0.35 AND S5 < 0.10 AND S6 >= 0.05      (production v2.3)

Best-arm S1 matches production; S5/S6 here are read from the best-arm
record (a replay approximation on cached Phase-5 measurements).
Production uses MAX across both arms for every channel — the
authoritative per-arm table is evaluation/results/p6_sleeve_v24.json
and the live re-execution p7_v24_full_matrix.json.
"""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
M = REPO / "evaluation" / "results" / "sleeve_signal_matrix.json"
data = json.loads(M.read_text())

ROWS = [r for r in data["rows"] if "error" not in r]
T1, T5, T6 = 0.35, 0.10, 0.05

def rules(r):
    s1 = r["best_arm"]["s1_coverage"]
    s5 = r["best_arm"]["s5_new_skin_outer"]
    s6 = r["best_arm"]["s6_wrist_reach"]
    return {
        "V1": s1 >= T1,
        "V2": s1 >= T1 and s5 < T5,
        "V3": s1 >= T1 and s6 >= T6,
        "V4": s1 >= T1 and s5 < T5 and s6 >= T6,
    }

out = {}
REFUSE_TRUTHS = ("dropped", "dropped_synth", "short_declared_long")
for v in ("V1", "V2", "V3", "V4"):
    tp = tn = fp = fn = 0
    fp_cases, fn_cases = [], []
    for r in ROWS:
        pred = rules(r)[v]
        should_refuse = r["truth"] in REFUSE_TRUTHS
        if pred and not should_refuse:
            tp += 1
        elif pred and should_refuse:
            fp += 1
            fp_cases.append(r["case"])
        elif not pred and should_refuse:
            tn += 1
        else:
            fn += 1
            fn_cases.append(r["case"])
    n = len(ROWS)
    out[v] = {
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "tpr": round(tp / max(tp + fn, 1), 4),
        "fnr": round(fn / max(tp + fn, 1), 4),
        "tnr": round(tn / max(tn + fp, 1), 4),
        "fpr": round(fp / max(tn + fp, 1), 4),
        "precision": round(tp / max(tp + fp, 1), 4),
        "recall": round(tp / max(tp + fn, 1), 4),
        "accuracy": round((tp + tn) / n, 4),
        "fp_cases": fp_cases,
        "fn_cases": fn_cases,
    }

# margins under V4
margins = {"present_pass": [], "refuse_expected_refused": []}
for r in ROWS:
    d = rules(r)
    s1 = r["best_arm"]["s1_coverage"]
    s5 = r["best_arm"]["s5_new_skin_outer"]
    s6 = r["best_arm"]["s6_wrist_reach"]
    should_refuse = r["truth"] in REFUSE_TRUTHS
    if d["V4"] and not should_refuse:
        margins["present_pass"].append({
            "case": r["case"],
            "s1_minus_tau": round(s1 - T1, 4),
            "tau5_minus_s5": round(T5 - s5, 4),
            "s6_minus_tau": round(s6 - T6, 4),
        })
    if not d["V4"] and should_refuse:
        margins["refuse_expected_refused"].append({
            "case": r["case"],
            "truth": r["truth"],
            "s5_minus_tau": round(s5 - T5, 4) if s5 >= T5 else None,
            "tau6_minus_s6": round(T6 - s6, 4) if s6 < T6 else None,
            "tau1_minus_s1": round(T1 - s1, 4) if s1 < T1 else None,
        })

for v, o in out.items():
    print(f"{v}: TP={o['tp']} TN={o['tn']} FP={o['fp']} FN={o['fn']} "
          f"TPR={o['tpr']} FPR={o['fpr']} TNR={o['tnr']} P={o['precision']} "
          f"R={o['recall']} acc={o['accuracy']}")
    if o["fp_cases"]:
        print(f"   FP cases: {o['fp_cases']}")
    if o["fn_cases"]:
        print(f"   FN cases: {o['fn_cases']}")

thinnest = sorted(margins["present_pass"], key=lambda m: min(
    m["s1_minus_tau"], m["tau5_minus_s5"], m["s6_minus_tau"]))[:3]
print("thinnest-TP margins (V4):", json.dumps(thinnest, indent=1))
worst_drops = sorted(margins["refuse_expected_refused"], key=lambda m: max(
    m["s5_minus_tau"] or -1, m["tau6_minus_s6"] or -1, m["tau1_minus_s1"] or -1),
    reverse=True)[:3]
print("thinnest drop-rejection margins (V4):", json.dumps(worst_drops, indent=1))

(REPO / "evaluation" / "results" / "p6_sleeve_ablation.json").write_text(json.dumps(
    {"note": "P1-A channel ablation on the 50-row Phase-5 matrix; labels are "
             "AGENT VISUAL INSPECTION — NOT HUMAN GROUND TRUTH",
     "thresholds": {"S1": T1, "S5": T5, "S6": T6},
     "rules": {"V1": "S1", "V2": "S1+S5", "V3": "S1+S6", "V4": "S1+S5+S6 (production v2.3)"},
     "results": out, "margins_v4": margins}, indent=1))
print("WROTE p6_sleeve_ablation.json")
