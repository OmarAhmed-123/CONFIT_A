"""P7 sleeve false-refusal class analysis (Phase 3, 2026-09-16).

Quantifies the mechanism of each of the four over-refusal classes using the
Phase-2 saved renders (hermetic; no live calls):

  Class A — dark background / band geometry   (cal_03, 0.1897)
      band pixel composition: unchanged background vs garment-changed.
      control: cal_02 (same garment, light bg, PASS 0.4615).
  Class B — multicolor garment reference      (cal_07, 0.0689)
      sleeve pixels are the contrasting color block; measure their ΔE vs the
      single dominant-color reference.
  Class C — ΔE thin-margin blazer             (io_1 0.3297, io_3 0.3480)
      band loss decomposition: garment-colored-unchanged vs
      changed-not-garment-colored vs counted.
  Class D — pose-related low coverage         (cal_04, 0.1861)
      garment-colored-changed pixels that exist OUTSIDE the band boxes.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
import numpy as np
from PIL import Image

import backend.app.services.vton_sleeve_gate as sg

CAL = REPO / "evaluation" / "results" / "calibration_v22"
BANDS = sg.FOREARM_BANDS  # left (0.52,0.70,0.40,0.55), right (0.28,0.46,0.40,0.55)
DE_GARMENT = sg.DELTA_E_RADIUS  # 40
DE_CHANGE = 20.0

def band_arrays(img: Image.Image):
    arr = np.asarray(img.convert("RGB")).astype(float)
    h, w, _ = arr.shape
    out = {}
    for side, (fx0, fx1, fy0, fy1) in BANDS.items():
        out[side] = arr[int(h * fy0):int(h * fy1), int(w * fx0):int(w * fx1)]
    return arr, out

def full_band_mask(img: Image.Image):
    h, w = img.size[1], img.size[0]
    m = np.zeros((h, w), bool)
    for side, (fx0, fx1, fy0, fy1) in BANDS.items():
        m[int(h * fy0):int(h * fy1), int(w * fx0):int(w * fx1)] = True
    return m

def analyze(tag, out_p, in_p, gar_p, slot="upper_outer", sleeve="long"):
    out_img = Image.open(out_p).convert("RGB")
    in_img = Image.open(in_p).convert("RGB")
    if in_img.size != out_img.size:  # mirror the gate's own resize behavior
        in_img = in_img.resize(out_img.size)
    ref = sg.garment_dominant_lab(Image.open(gar_p).convert("RGB"))
    out_arr, out_bands = band_arrays(out_img)
    _, in_bands = band_arrays(in_img)
    per_band = {}
    for side in BANDS:
        ob, ib = out_bands[side], in_bands[side]
        olab = sg._rgb_array_to_lab(ob) if hasattr(sg, "_rgb_array_to_lab") else None
        # per-pixel lab via the gate's scalar converter is too slow; vectorize:
        res = {}
        o = ob.reshape(-1, 3)
        i = ib.reshape(-1, 3)
        labs_o = np.array([sg._rgb_to_lab(p) for p in o[::3]])
        labs_i = np.array([sg._rgb_to_lab(p) for p in i[::3]])
        d_gar = np.sqrt(((labs_o - np.array(ref)) ** 2).sum(axis=1))
        d_chg = np.sqrt(((labs_o - labs_i) ** 2).sum(axis=1))
        n = len(o[::3])
        res["n_samples"] = int(n)
        res["garment_colored"] = round(float((d_gar <= DE_GARMENT).mean()), 4)
        res["changed"] = round(float((d_chg > DE_CHANGE).mean()), 4)
        res["counted"] = round(float(((d_gar <= DE_GARMENT) & (d_chg > DE_CHANGE)).mean()), 4)
        res["garment_colored_unchanged"] = round(float(((d_gar <= DE_GARMENT) & (d_chg <= DE_CHANGE)).mean()), 4)
        res["changed_not_garment"] = round(float(((d_gar > DE_GARMENT) & (d_chg > DE_CHANGE)).mean()), 4)
        per_band[side] = res
    full = full_band_mask(out_img)
    oa = np.asarray(out_img.convert("RGB")).reshape(-1, 3)
    ia = np.asarray(in_img.convert("RGB")).reshape(-1, 3)
    fm = full.reshape(-1)
    outside = ~fm
    if outside.sum() > 0:
        lo = np.array([sg._rgb_to_lab(p) for p in oa[outside][::7]])
        li = np.array([sg._rgb_to_lab(p) for p in ia[outside][::7]])
        dgo = np.sqrt(((lo - np.array(ref)) ** 2).sum(axis=1))
        dco = np.sqrt(((lo - li) ** 2).sum(axis=1))
        outside_stats = {
            "garment_colored_changed_frac_of_image": round(
                float(((dgo <= DE_GARMENT) & (dco > DE_CHANGE)).mean()), 5),
        }
    else:
        outside_stats = {}
    return {"tag": tag, "ref_lab": [round(v, 1) for v in ref],
            "bands": per_band, "outside": outside_stats}

R = {}
R["class_A_dark_bg"] = analyze("cal_03", CAL / "cal_03_L1.png", CAL / "cal_03_L1_input.png", CAL / "cal_03_L1_garment.png")
R["class_A_control_light_bg"] = analyze("cal_02", CAL / "cal_02_L1.png", CAL / "cal_02_L1_input.png", CAL / "cal_02_L1_garment.png")
R["class_B_multicolor"] = analyze("cal_07", CAL / "cal_07_L1.png", CAL / "cal_07_L1_input.png", CAL / "cal_07_L1_garment.png")
R["class_C_thin_margin_io1"] = analyze("io_1", CAL / "io_1_L2.png", CAL / "io_1_L2_input.png", CAL / "io_1_L2_garment.png")
R["class_C_thin_margin_io3"] = analyze("io_3", CAL / "io_3_L2.png", CAL / "io_3_L2_input.png", CAL / "io_3_L2_garment.png")
R["class_D_pose"] = analyze("cal_04", CAL / "cal_04_L1.png", CAL / "cal_04_L1_input.png", CAL / "cal_04_L1_garment.png")
R["class_D_control_arms_down"] = analyze("cal_05", CAL / "cal_05_L1.png", CAL / "cal_05_L1_input.png", CAL / "cal_05_L1_garment.png")

(CAL / "class_analysis.json").write_text(json.dumps(R, indent=1))
for tag, r in R.items():
    bl = r["bands"]["left"]; br = r["bands"]["right"]
    print(f"{tag:28} ref={r['ref_lab']}")
    print(f"   L counted={bl['counted']} gc_unch={bl['garment_colored_unchanged']} chg_notgar={bl['changed_not_garment']}   "
          f"R counted={br['counted']} gc_unch={br['garment_colored_unchanged']} chg_notgar={br['changed_not_garment']}   "
          f"outside_gc_chg={r['outside'].get('garment_colored_changed_frac_of_image')}")
print("WROTE", CAL / "class_analysis.json")
