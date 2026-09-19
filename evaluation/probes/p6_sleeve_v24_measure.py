"""P6 P1-B: redesign measurement for sleeve gate v2.4.

Measured v2.3 structural defects (2026-09-19, adversarial composites on
cal_02 — input wears a TANK TOP, arms exposed):
  * adv_onearm / adv_onearm_full PASS: a fully dropped sleeve on ONE arm
    is carried past all three channels by the INTACT arm, because every
    channel is aggregated with max() (best arm).
  * S5 (new_skin_outer) is structurally blind to drops on inputs that
    already expose the arm: the exposed skin is UNCHANGED vs the input
    (measured new_skin_outer = exactly 0.0 on the dropped arm).

Candidate v2.4 (generic — no fixture/garment/person exceptions):
  v2.4a  per-arm AND for S1 and S6 (a long-sleeve garment must cover BOTH
         arms to the wrist; one intact arm may not carry the verdict)
         + S5 as today (max-arm).
  v2.4b  v2.4a + S5 replaced by S5b: fraction of the outer forearm band
         that is human-skin-colored IN THE OUTPUT, whether or not it is
         new relative to the input. A verified long sleeve leaves NO skin
         in the outer band; any exposed forearm (old or new) fails it.

Re-measures all 50 matrix rows (production channel functions, same grid)
+ the 7 adversarial composites. Confusion matrices + thin margins.
Labels = AGENT VISUAL INSPECTION — NOT HUMAN GROUND TRUTH.
"""
import json
import math
import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from backend.app.services.vton_sleeve_gate import (  # noqa: E402
    ANATOMY_NEW_SKIN_REFUSE,
    ANATOMY_OUTER_FRACTION,
    ANATOMY_WRIST_FRACTION,
    ANATOMY_WRIST_REACH_REFUSE,
    FOREARM_BANDS,
    FOREARM_PASS_THRESHOLD,
    _is_skin_lab,
    _rgb_to_lab,
    forearm_anatomy_probes,
    forearm_garment_coverage,
    garment_dominant_lab,
)

BASE_DIR = REPO / "evaluation" / "results"
CASES = [
    ("calibration_v22", "cal_01", "L1", "present", "P"),
    ("calibration_v22", "cal_02", "L1", "present", "P"),
    ("calibration_v22", "cal_03", "L1", "present", "R"),
    ("calibration_v22", "cal_04", "L1", "present", "R"),
    ("calibration_v22", "cal_05", "L1", "present", "P"),
    ("calibration_v22", "cal_06", "L1", "dropped", "R"),
    ("calibration_v22", "cal_07", "L1", "present", "R"),
    ("calibration_v22", "cal_09", "L1", "present", "P"),
    ("calibration_v22", "cal_13", "L1", "present", "P"),
    ("phase3_sleeve_batch", "sc_white", "L1", "present", "R"),
    ("phase3_sleeve_batch", "sc_gray_D", "L1", "present", "R"),
    ("phase3_sleeve_batch", "loc_tunic_F", "L1", "present", "P"),
    ("phase3_sleeve_batch", "loc_arabic2_F", "L1", "present", "R"),
    ("phase3_sleeve_batch", "sc_crop_B", "L1", "dropped", "R"),
    ("phase3_sleeve_batch", "sc_tank_C", "L1", "dropped", "R"),
    ("phase3_sleeve_batch", "sc_black_I", "L1", "present", "R"),
    ("phase3_sleeve_batch", "sc_dress_G", "L1", "present", "P"),
    ("phase3_sleeve_batch", "sc_rust_H", "L1", "present", "P"),
    ("phase3_sleeve_batch", "sc_rust_I", "L1", "present", "P"),
    ("phase3_sleeve_batch", "io_gray_I", "L2", "present", "R"),
    ("at15_reconciliation", "m0_repro", "L2", "present", "R"),
    ("p4_fresh_batch", "p4_j_tunic", "L1", "present", "P"),
    ("p4_fresh_batch", "p4_j_arabic2", "L1", "dropped", "P"),
    ("p4_fresh_batch", "p4_k_rust", "L1", "present", "P"),
    ("p4_fresh_batch", "p4_k_black", "L1", "present", "P"),
    ("p4_fresh_batch", "p5_l_gray", "L1", "present", "P"),
    ("p4_fresh_batch", "p5_m_blazer", "L1", "present", "R"),
    ("p4_fresh_batch", "p5_m_io", "L1", "present", "R"),
    ("p4_fresh_batch", "p5_l_tpb", "L1", "present", "P"),
    ("p0c_sleeve_calibration", "p0c_k_white", "L1", "present", "R"),
    ("p0c_sleeve_calibration", "p0c_f_white", "L1", "present", "R"),
    ("p0c_sleeve_calibration", "p0c_m_black", "L1", "present", "R"),
    ("p0c_sleeve_calibration", "p0c_e_rust", "L1", "present", "R"),
    ("p0c_sleeve_calibration", "p0c_a_pattern", "L1", "present", "R"),
    ("p0c_sleeve_calibration", "p0c_g_short", "L1", "short_declared_long", "R"),
    ("p0c_sleeve_calibration", "p0c_d_gray", "L1", "present", "P"),
    ("p0c_sleeve_calibration", "p0c_l_black", "L1", "present", "P"),
    ("calibration_v22", "cal_08", "L1", "present", "P"),
    ("calibration_v22", "cal_10", "L1", "short_declared_long", "R"),
    ("calibration_v22", "tpb_4", "L1", "present", "P"),
    ("calibration_v22", "io_1", "L2", "present", "R"),
    ("calibration_v22", "io_3", "L2", "present", "R"),
    ("at15_reconciliation", "m1_light_trousers", "L2", "present", "P"),
    ("at15_reconciliation", "m2_dark_bg", "L2", "present", "P"),
    ("at15_reconciliation", "m3_arms_raised", "L2", "present", "R"),
    ("at15_reconciliation", "m4_diff_person", "L2", "present", "R"),
    ("at15_reconciliation", "m5_dark_inner", "L2", "present", "P"),
    ("p4_fresh_batch", "p0c_synth_partial_krust", "L1", "dropped_synth", "X"),
    ("p4_fresh_batch", "p0c_synth_full_jtunic", "L1", "dropped_synth", "X"),
    ("p4_fresh_batch", "p0c_synth_full_lgray", "L1", "dropped_synth", "X"),
]
ADV_DIR = REPO / "evaluation" / "results" / "p6_sleeve_adversarial"
CAL = REPO / "evaluation" / "results" / "calibration_v22"
ADV_CASES = [
    (CAL / "cal_02_L1.png", CAL / "cal_02_L1_input.png", CAL / "cal_02_L1_garment.png", "present", "BASE_cal02"),
] + [(ADV_DIR / f"{n}.png", CAL / "cal_02_L1_input.png", CAL / "cal_02_L1_garment.png", "dropped", f"adv_{n}")
     for n in ("adv_crop", "adv_elbow", "adv_midgap", "adv_onearm", "adv_onearm_full", "adv_wristgap")]
# note: composite filenames already carry the adv_ prefix
ADV_CASES = [ADV_CASES[0]] + [(ADV_DIR / f"{n}.png", CAL / "cal_02_L1_input.png",
                                CAL / "cal_02_L1_garment.png", "dropped", n)
                               for n in ("adv_crop", "adv_elbow", "adv_midgap",
                                         "adv_onearm", "adv_onearm_full", "adv_wristgap")]


def s5b_any_skin_outer(out: Image.Image) -> dict:
    """Fraction of the outer forearm band that is skin-colored in the
    OUTPUT (whether or not new vs the input). Same grid/geometry as the
    production anatomy probe (step 3, outer 65% of each band)."""
    out_w, out_h = out.size
    px = out.convert("RGB").load()
    res = {}
    for side, (fx0, fx1, fy0, fy1) in FOREARM_BANDS.items():
        x0, x1 = int(out_w * fx0), int(out_w * fx1)
        y0, y1 = int(out_h * fy0), int(out_h * fy1)
        bw = x1 - x0
        xo = x0 + int(bw * (1 - ANATOMY_OUTER_FRACTION)) if side == "left" else x0
        x1o = x1 if side == "left" else x0 + int(bw * (1 - ANATOMY_OUTER_FRACTION))
        n = hit = 0
        for yy in range(y0, y1, 3):
            for xx in range(xo, x1o, 3):
                n += 1
                if _is_skin_lab(_rgb_to_lab(px[xx, yy])):
                    hit += 1
        res[side] = round(hit / n, 4) if n else 0.0
    return res


def verdicts(c1, s5, s5b, s6):
    """c1/s5/s5b/s6 are per-arm dicts {left,right}."""
    v23 = (max(c1.values()) >= FOREARM_PASS_THRESHOLD
           and max(s5.values()) < ANATOMY_NEW_SKIN_REFUSE
           and max(s6.values()) >= ANATOMY_WRIST_REACH_REFUSE)
    v24a = (min(c1.values()) >= FOREARM_PASS_THRESHOLD
            and max(s5.values()) < ANATOMY_NEW_SKIN_REFUSE
            and min(s6.values()) >= ANATOMY_WRIST_REACH_REFUSE)
    v24b = (min(c1.values()) >= FOREARM_PASS_THRESHOLD
            and max(s5b.values()) < ANATOMY_NEW_SKIN_REFUSE
            and min(s6.values()) >= ANATOMY_WRIST_REACH_REFUSE)
    return v23, v24a, v24b


ROWS = []
for dirname, case, layer, truth, gate in CASES:
    base = BASE_DIR / dirname / f"{case}_{layer}.png"
    inp = BASE_DIR / dirname / f"{case}_{layer}_input.png"
    gar = BASE_DIR / dirname / f"{case}_{layer}_garment.png"
    if not (base.exists() and inp.exists() and gar.exists()):
        print(f"MISSING {base} / {inp} / {gar}")
        continue
    out = Image.open(base).convert("RGB")
    i = Image.open(inp).convert("RGB")
    g = Image.open(gar).convert("RGB")
    glab = garment_dominant_lab(g)
    c1 = forearm_garment_coverage(out, i, glab)
    anat = forearm_anatomy_probes(out, i, glab)
    s5 = {k: anat[k]["new_skin_outer"] for k in anat}
    s6 = {k: anat[k]["wrist_reach"] for k in anat}
    s5b = s5b_any_skin_outer(out)
    v23, v24a, v24b = verdicts(c1, s5, s5b, s6)
    ROWS.append({"case": f"{case}_{layer}", "truth": truth, "gate": gate,
                 "c1": c1, "s5": s5, "s5b": s5b, "s6": s6,
                 "v23": v23, "v24a": v24a, "v24b": v24b})

for p, ip, gp, truth, label in ADV_CASES:
    out = Image.open(p).convert("RGB")
    i = Image.open(ip).convert("RGB")
    g = Image.open(gp).convert("RGB")
    glab = garment_dominant_lab(g)
    c1 = forearm_garment_coverage(out, i, glab)
    anat = forearm_anatomy_probes(out, i, glab)
    s5 = {k: anat[k]["new_skin_outer"] for k in anat}
    s6 = {k: anat[k]["wrist_reach"] for k in anat}
    s5b = s5b_any_skin_outer(out)
    v23, v24a, v24b = verdicts(c1, s5, s5b, s6)
    ROWS.append({"case": label, "truth": truth, "gate": ("P" if truth == "present" else "X"),
                 "c1": c1, "s5": s5, "s5b": s5b, "s6": s6,
                 "v23": v23, "v24a": v24a, "v24b": v24b})

REFUSE_TRUTHS = ("dropped", "dropped_synth", "short_declared_long")

def matrix(rows, key):
    tp = tn = fp = fn = 0
    fp_c, fn_c = [], []
    for r in rows:
        pred = r[key]
        sr = r["truth"] in REFUSE_TRUTHS
        if pred and not sr:
            tp += 1
        elif pred and sr:
            fp += 1
            fp_c.append(r["case"])
        elif not pred and sr:
            tn += 1
        else:
            fn += 1
            fn_c.append(r["case"])
    n = len(rows)
    return {"tp": tp, "tn": tn, "fp": fp, "fn": fn,
            "tpr": round(tp / max(tp + fn, 1), 4),
            "fpr": round(fp / max(tn + fp, 1), 4),
            "tnr": round(tn / max(tn + fp, 1), 4),
            "precision": round(tp / max(tp + fp, 1), 4),
            "accuracy": round((tp + tn) / n, 4),
            "fp_cases": fp_c, "fn_cases": fn_c}

MATRIX = {"v23_production": matrix(ROWS, "v23"),
          "v24a_perarm_AND_s5max": matrix(ROWS, "v24a"),
          "v24b_perarm_AND_s5b": matrix(ROWS, "v24b")}

# margins (thin ones)
margins = {"v24b_pass_min_margins": [], "v24b_refuse_reasons": []}
for r in ROWS:
    c1lo = min(r["c1"].values())
    s5bhi = max(r["s5b"].values())
    s6lo = min(r["s6"].values())
    if r["v24b"]:
        margins["v24b_pass_min_margins"].append({
            "case": r["case"], "truth": r["truth"],
            "c1min_minus_0.35": round(c1lo - 0.35, 4),
            "0.10_minus_s5bmax": round(0.10 - s5bhi, 4),
            "s6min_minus_0.05": round(s6lo - 0.05, 4),
        })
    elif r["truth"] not in REFUSE_TRUTHS:
        why = []
        if c1lo < 0.35:
            why.append(f"c1min={c1lo:.4f}")
        if s5bhi >= 0.10:
            why.append(f"s5bmax={s5bhi:.4f}")
        if s6lo < 0.05:
            why.append(f"s6min={s6lo:.4f}")
        margins["v24b_refuse_reasons"].append({"case": r["case"], "truth": r["truth"], "why": why,
                                               "c1": r["c1"], "s5b": r["s5b"], "s6": r["s6"]})

OUTP = REPO / "evaluation" / "results" / "p6_sleeve_v24.json"
OUTP.write_text(json.dumps({"n": len(ROWS), "matrix": MATRIX,
                            "margins": margins,
                            "rows": ROWS}, indent=1, default=str))
print(f"n={len(ROWS)}")
for k, m in MATRIX.items():
    print(f"{k}: TP={m['tp']} TN={m['tn']} FP={m['fp']} FN={m['fn']} "
          f"TNR={m['tnr']} FPR={m['fpr']} P={m['precision']} acc={m['accuracy']}")
    if m["fp_cases"]:
        print(f"   FP: {m['fp_cases']}")
print("WROTE", OUTP)
