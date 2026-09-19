"""P0 sleeve-fix: candidate anatomical-signal measurement harness (hermetic).

For every labeled sleeve artifact triple (output, input, garment) in the
existing calibration sets, measures:

  S1  existing changed garment-color coverage (per side band, best-arm)
  S2  cuff presence: in the wrist zone (bottom 25% of each band), fraction
      of outer-65% columns where >=50% of zone pixels are
      changed garment-colored (a long-sleeve cuff flanks the wrist)
  S3  sleeve reach: deepest relative y in-band (0..1) with changed
      garment-colored pixels in the outer 65% of the band
  S4  NEW-SKIN: fraction of band pixels that are skin-colored in the OUTPUT
      AND changed vs the input (newly exposed skin = dropped-sleeve evidence;
      pre-existing bare skin is unchanged and does NOT count)
  S5  new-skin restricted to the outer 65% (arm side, excludes torso edge)

Output: sleeve_signal_matrix.json (measurements only) + printed table.
No production code touched; labels come from the agent-inspection records in
Parts 3-4 of the report (AGENT VISUAL INSPECTION - NOT HUMAN GROUND TRUTH).
"""
import io
import json
import math
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from PIL import Image
from backend.app.services.vton_sleeve_gate import (
    _rgb_to_lab, garment_dominant_lab, FOREARM_BANDS, DELTA_E_RADIUS,
    FOREARM_CHANGE_THRESHOLD,
)

RES = REPO / "evaluation" / "results"

# label: (case, layer, truth, gate) — truth: present/dropped; gate: P/R/N
# from Parts 3-4 of the authoritative report (agent inspection).
CASES = [
    # --- Part 3 calibration_v22 (cal_XX) ---
    ("calibration_v22", "cal_01", "L1", "present", "P"),
    ("calibration_v22", "cal_02", "L1", "present", "P"),
    ("calibration_v22", "cal_03", "L1", "present", "R"),   # class A dark bg FN
    ("calibration_v22", "cal_04", "L1", "present", "R"),   # class D pose FN
    ("calibration_v22", "cal_05", "L1", "present", "P"),
    ("calibration_v22", "cal_06", "L1", "dropped", "R"),   # synthetic drop TN
    ("calibration_v22", "cal_07", "L1", "present", "R"),   # class B FN
    ("calibration_v22", "cal_09", "L1", "present", "P"),
    ("calibration_v22", "cal_13", "L1", "present", "P"),
    # --- Part 3 phase3_sleeve_batch ---
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
    ("phase3_sleeve_batch", "io_gray_I", "L2", "present", "R"),  # blazer outer
    # --- AT-15 reconciliation ---
    ("at15_reconciliation", "m0_repro", "L2", "present", "R"),
    # --- Phase 4 p4_fresh_batch ---
    ("p4_fresh_batch", "p4_j_tunic", "L1", "present", "P"),
    ("p4_fresh_batch", "p4_j_arabic2", "L1", "dropped", "P"),   # CLASS E FP
    ("p4_fresh_batch", "p4_k_rust", "L1", "present", "P"),
    ("p4_fresh_batch", "p4_k_black", "L1", "present", "P"),
    ("p4_fresh_batch", "p5_l_gray", "L1", "present", "P"),
    ("p4_fresh_batch", "p5_m_blazer", "L1", "present", "R"),
    ("p4_fresh_batch", "p5_m_io", "L1", "present", "R"),
    ("p4_fresh_batch", "p5_l_tpb", "L1", "present", "P"),
    # --- Phase 5 P0-C new artifacts (agent inspection 2026-09-19) ---
    ("p0c_sleeve_calibration", "p0c_k_white", "L1", "present", "R"),
    ("p0c_sleeve_calibration", "p0c_f_white", "L1", "present", "R"),
    ("p0c_sleeve_calibration", "p0c_m_black", "L1", "present", "R"),
    ("p0c_sleeve_calibration", "p0c_e_rust", "L1", "present", "R"),
    ("p0c_sleeve_calibration", "p0c_a_pattern", "L1", "present", "R"),
    ("p0c_sleeve_calibration", "p0c_g_short", "L1", "short_declared_long", "R"),
    ("p0c_sleeve_calibration", "p0c_d_gray", "L1", "present", "P"),
    ("p0c_sleeve_calibration", "p0c_l_black", "L1", "present", "P"),
    # --- Phase 3/4 rows completed from the n=39 matrix (labels per report) ---
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

# skin window (CIE-Lab) — MUST match vton_sleeve_gate.SKIN_LAB_WINDOW
# (v2.3, calibrated 2026-09-19; see that constant's comment for the full
# measured provenance: cohort reference tones + J/L hand/forearm + class-E
# forearm inside; rendered rust / terracotta / burgundy / brick / mustard /
# purple / beige / olive / navy / black / white outside).
SKIN = {"l": (25.0, 85.0), "a": (7.0, 25.0), "b": (7.0, 31.0)}

def is_skin(lab):
    return (SKIN["l"][0] <= lab[0] <= SKIN["l"][1]
            and SKIN["a"][0] <= lab[1] <= SKIN["a"][1]
            and SKIN["b"][0] <= lab[2] <= SKIN["b"][1])

def band_stats(out: Image.Image, inp: Image.Image, ref, outer_frac=0.65, wrist_frac=0.35):
    """Per side band: S1 coverage, S2 cuff, S3 reach, S4 new-skin, S5 new-skin
    outer, S6 wrist-reach (changed garment fraction in wrist-zone outer)."""
    ow, oh = out.size
    if inp.size != (ow, oh):
        inp = inp.resize((ow, oh))
    px = out.convert("RGB").load()
    pi = inp.convert("RGB").load()
    res = {}
    for side, (fx0, fx1, fy0, fy1) in FOREARM_BANDS.items():
        x0, x1 = int(ow * fx0), int(ow * fx1)
        y0, y1 = int(oh * fy0), int(oh * fy1)
        bw = x1 - x0
        x_outer0 = x0 + int(bw * (1 - outer_frac))  # outer 65% start (arm side: right for left-side band?)
        # side 'left' = person's left = image RIGHT (x 0.52-0.70): outer = high x
        # side 'right' = person's right = image LEFT (x 0.28-0.46): outer = low x
        if side == "left":
            outer_cols = range(x_outer0, x1)
        else:
            outer_cols = range(x0, x_outer0)
        n = close = 0
        new_skin = new_skin_outer = 0
        n_outer = 0
        reach = 0.0
        # S2: wrist zone = bottom 25% of band; per outer column, >=50% zone px are changed garment-colored
        z0 = y0 + int((y1 - y0) * 0.75)
        col_cuff = {}
        wy0 = y0 + int((y1 - y0) * (1 - wrist_frac))  # S6 wrist-zone top
        n_wz = gz = 0
        for yy in range(y0, y1, 2):
            rel_y = (yy - y0) / max(1, (y1 - y0))
            for xx in range(x0, x1, 2):
                o = _rgb_to_lab(px[xx, yy])
                i = _rgb_to_lab(pi[xx, yy])
                e_g = math.sqrt(sum((a - b) ** 2 for a, b in zip(o, ref)))
                e_c = math.sqrt(sum((a - b) ** 2 for a, b in zip(o, i)))
                ing = e_g <= DELTA_E_RADIUS
                chg = e_c > FOREARM_CHANGE_THRESHOLD
                n += 1
                if ing and chg:
                    close += 1
                    if rel_y > reach:
                        reach = rel_y
                if is_skin(o) and chg:
                    new_skin += 1
                    if xx in outer_cols:
                        new_skin_outer += 1
                if xx in outer_cols:
                    n_outer += 1
                    if z0 <= yy < y1:
                        c, t = col_cuff.get(xx, (0, 0))
                        col_cuff[xx] = (c + (1 if ing and chg else 0), t + 1)
                    if yy >= wy0:
                        n_wz += 1
                        if ing and chg:
                            gz += 1
        res[side] = {
            "s1_coverage": round(close / n, 4) if n else 0.0,
            "s2_cuff_cols": (lambda cc: round(sum(1 for c, t in cc.values() if t and c / t >= 0.5) / len(cc), 4) if cc else 0.0)(col_cuff),
            "s3_reach": round(reach, 3),
            "s4_new_skin": round(new_skin / n, 4) if n else 0.0,
            "s5_new_skin_outer": round(new_skin_outer / n_outer, 4) if n_outer else 0.0,
            "s6_wrist_reach": round(gz / n_wz, 4) if n_wz else 0.0,
        }
    return res

ROWS = []
for dirname, case, layer, truth, gate in CASES:
    d = RES / dirname
    out_p = d / f"{case}_{layer}.png"
    in_p = d / f"{case}_{layer}_input.png"
    gar_p = d / f"{case}_{layer}_garment.png"
    row = {"case": f"{case}_{layer}", "truth": truth, "gate": gate}
    if not (out_p.exists() and in_p.exists() and gar_p.exists()):
        row["error"] = "missing artifacts"
        ROWS.append(row)
        continue
    out = Image.open(out_p).convert("RGB")
    inp = Image.open(in_p).convert("RGB")
    gar = Image.open(gar_p).convert("RGB")
    ref = garment_dominant_lab(gar)
    row["ref_lab"] = [round(v, 1) for v in ref]
    row.update(band_stats(out, inp, ref))
    row["best_arm"] = {k: max(row[s][k] for s in ("left", "right")) for k in
                       ("s1_coverage", "s2_cuff_cols", "s3_reach", "s4_new_skin",
                        "s5_new_skin_outer", "s6_wrist_reach")}
    ROWS.append(row)

print(f"{'case':22} {'truth':8} {'gate':4} {'S1':>7} {'S2cuff':>7} {'S3rch':>6} {'S4nsw':>6} {'S5nso':>6}")
for r in ROWS:
    if "error" in r:
        print(f"{r['case']:22} {r['truth']:8} {r['gate']:4} MISSING ARTIFACTS")
        continue
    b = r["best_arm"]
    print(f"{r['case']:22} {r['truth']:8} {r['gate']:4} {b['s1_coverage']:7.4f} {b['s2_cuff_cols']:7.4f} "
          f"{b['s3_reach']:6.3f} {b['s4_new_skin']:6.4f} {b['s5_new_skin_outer']:6.4f}")

out_path = REPO / "evaluation" / "results" / "sleeve_signal_matrix.json"
out_path.write_text(json.dumps({"skin_window": SKIN, "rows": ROWS}, indent=1))
print("WROTE", out_path)
