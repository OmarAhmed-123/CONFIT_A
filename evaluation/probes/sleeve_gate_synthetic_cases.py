"""Synthetic negative/control cases for the sleeve gate v2.2 calibration
(2026-09-16, Phase 2, P1/P5). Builds defect-simulated and control cases from
REAL captured renders (cal_01: fresh dark blazer on fresh person A) plus pure
synthetic constructions, and scores each with the gate's own probe at change
thresholds {15,20,25,30}.

Hypothesis under test:
  "garment-colored AND changed-vs-input" distinguishes an actually applied
  sleeve from an unchanged dark region that only resembles the garment color.

Cases:
  neg_drop_sim       both forearm bands restored to INPUT pixels (sleeves gone)
  neg_partial_sim    inner half of one band restored to input (partial drop)
  neg_distort_sim    garment-colored patch painted in the WRONG band location
  neg_no_apply       the layer INPUT itself as "output" (nothing applied)
  ctrl_unchanged_gc  both bands garment-colored in input AND output (unchanged)
  ctrl_changed_gc    input bands skin, output bands garment (constructed POS)
  ctrl_skin_unchanged input bands skin, output bands skin (no garment anywhere)

Outputs: evaluation/results/calibration_v22/synthetic_*.png + synthetic_results.json
"""
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "evaluation"))
os_chdir = REPO
import os
os.chdir(os_chdir)

from PIL import Image
import backend.app.services.vton_sleeve_gate as gate_mod

OUTDIR = REPO / "evaluation" / "results" / "calibration_v22"
OUTDIR.mkdir(parents=True, exist_ok=True)
BANDS = gate_mod.FOREARM_BANDS  # left (0.52,0.70,0.40,0.55), right (0.28,0.46,0.40,0.55)

base_out = Image.open(OUTDIR / "cal_01_L1.png").convert("RGB")
base_in = Image.open(OUTDIR / "cal_01_L1_input.png").convert("RGB")
garment_img = Image.open(OUTDIR / "cal_01_L1_garment.png").convert("RGB")
ref = gate_mod.garment_dominant_lab(garment_img)
print("garment ref lab:", [round(v, 1) for v in ref])

W, H = base_out.size
po, pi = base_out.load(), base_in.load()

def _lab_to_rgb(lab):
    L, a, b = lab
    fy = (L + 16) / 116.0
    fx = a / 500.0 + fy
    fz = fy - b / 200.0
    def _finv(f):
        # inverse of f(t)=t^(1/3) [t>delta] else 7.787t+16/116
        return f ** 3 if f > 0.2008 else (f - 16 / 116) / 7.787
    yv = _finv(fy)
    xv = _finv(fx) * 0.95047
    zv = _finv(fz) * 1.08883
    r = xv * 3.2406 + yv * -1.5372 + zv * -0.4986
    g = xv * -0.9689 + yv * 1.8758 + zv * 0.0415
    bb = xv * 0.0557 + yv * -0.2040 + zv * 1.0570
    def _gam(c):
        c = max(0.0, min(1.0, c))
        return int(255 * ((1.055 * c ** (1 / 2.4)) - 0.055) if c > 0.0030394 else int(255 * 12.92 * c))
    return (_gam(r), _gam(g), _gam(bb))

GARMENT_RGB = _lab_to_rgb(ref)
SKIN = (224, 178, 140)
WHITE = (245, 245, 245)

def paint_band(img_px, fx0, fx1, fy0, fy1, color):
    for y in range(int(H * fy0), int(H * fy1)):
        for x in range(int(W * fx0), int(W * fx1)):
            img_px[x, y] = color

def restore_from_input(dst_px, fx0, fx1, fy0, fy1, source_px):
    for y in range(int(H * fy0), int(H * fy1)):
        for x in range(int(W * fx0), int(W * fx1)):
            dst_px[x, y] = source_px[x, y]

def score(output_img, input_img, garment=garment_img):
    refv = gate_mod.garment_dominant_lab(garment)
    scores = {}
    orig = gate_mod.FOREARM_CHANGE_THRESHOLD
    try:
        for t in (15.0, 20.0, 25.0, 30.0):
            gate_mod.FOREARM_CHANGE_THRESHOLD = t
            scores[str(t)] = gate_mod.forearm_garment_coverage(output_img, input_img, refv)
    finally:
        gate_mod.FOREARM_CHANGE_THRESHOLD = orig
    d = gate_mod.evaluate_sleeves_sync(
        slot_type="upper_outer", sleeve_length="long",
        output_img=output_img, input_img=input_img, garment_img=garment)
    return {"ref_lab": [round(v, 1) for v in refv], "sweep": scores,
            "best_20": max(scores["20.0"].values()),
            "gate_status": d["status"], "gate_reason": str(d["reason"])[:180]}

CASES = {}

# --- neg_drop_sim: both bands back to input pixels ---------------------------
img = base_out.copy(); px = img.load()
for side, (fx0, fx1, fy0, fy1) in BANDS.items():
    restore_from_input(px, fx0, fx1, fy0, fy1, pi)
img.save(OUTDIR / "synthetic_neg_drop_sim.png")
CASES["neg_drop_sim"] = {"truth": "NEG (sleeves absent by construction)",
                         "note": "both bands restored to person-A input pixels on the real cal_01 render",
                         **score(img, base_in)}

# --- neg_partial_sim: inner half of the right band (x 0.28-0.37) -------------
img = base_out.copy(); px = img.load()
restore_from_input(px, 0.28, 0.37, 0.40, 0.55, pi)
img.save(OUTDIR / "synthetic_neg_partial_sim.png")
CASES["neg_partial_sim"] = {"truth": "NEG (partial drop: ~half of right arm bare)",
                            "note": "x 0.28-0.37 of right band restored to input",
                            **score(img, base_in)}

# --- neg_distort_sim: garment-colored square at wrong band location ----------
img = base_out.copy(); px = img.load()
paint_band(px, 0.52, 0.57, 0.40, 0.445, GARMENT_RGB)
img.save(OUTDIR / "synthetic_neg_distort_sim.png")
CASES["neg_distort_sim"] = {"truth": "NEG (garment color present but geometry wrong: 0.52-0.57 x 0.40-0.445 patch)",
                            "note": "garment-colored patch in the band corner, not on the arm",
                            **score(img, base_in)}

# --- neg_no_apply: input as output -------------------------------------------
CASES["neg_no_apply"] = {"truth": "NEG (nothing applied)",
                         "note": "layer input image used as the output (no garment applied)",
                         **score(base_in, base_in)}

# --- controls: constructed images ---------------------------------------------
def constructed(band_color_out, band_color_in, torso=(120, 120, 120)):
    out_img = Image.new("RGB", (W, H), WHITE)
    in_img = Image.new("RGB", (W, H), WHITE)
    poo, pii = out_img.load(), in_img.load()
    paint_band(poo, 0.30, 0.70, 0.28, 0.40, torso)
    paint_band(pii, 0.30, 0.70, 0.28, 0.40, torso)
    for side, (fx0, fx1, fy0, fy1) in BANDS.items():
        paint_band(poo, fx0, fx1, fy0, fy1, band_color_out)
        paint_band(pii, fx0, fx1, fy0, fy1, band_color_in)
    return out_img, in_img

# ctrl_unchanged_gc: garment-colored in input AND output (unchanged)
o, i = constructed(GARMENT_RGB, GARMENT_RGB)
o.save(OUTDIR / "synthetic_ctrl_unchanged_gc_out.png"); i.save(OUTDIR / "synthetic_ctrl_unchanged_gc_in.png")
CASES["ctrl_unchanged_gc"] = {"truth": "NEG-control (garment-colored, UNCHANGED vs input — the L1-tan-skirt / dark-trouser class)",
                              "note": "constructed: both bands garment-colored in input and output",
                              **score(o, i)}
# ctrl_changed_gc: skin in input, garment in output (applied sleeve)
o, i = constructed(GARMENT_RGB, SKIN)
o.save(OUTDIR / "synthetic_ctrl_changed_gc_out.png"); i.save(OUTDIR / "synthetic_ctrl_changed_gc_in.png")
CASES["ctrl_changed_gc"] = {"truth": "POS-control (garment-colored AND changed — applied sleeve)",
                            "note": "constructed: skin input bands, garment output bands",
                            **score(o, i)}
# ctrl_skin_unchanged: skin in both (no garment at all)
o, i = constructed(SKIN, SKIN)
o.save(OUTDIR / "synthetic_ctrl_skin_unchanged_out.png"); i.save(OUTDIR / "synthetic_ctrl_skin_unchanged_in.png")
CASES["ctrl_skin_unchanged"] = {"truth": "NEG-control (no garment color anywhere)",
                                "note": "constructed: skin bands in input and output",
                                **score(o, i)}

res = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
       "base_render": "cal_01 (fresh dark blazer on fresh person A, live 2026-09-16)",
       "cases": CASES}
(OUTDIR / "synthetic_results.json").write_text(json.dumps(res, indent=1, default=str))
for k, v in CASES.items():
    print(f"{k:22} truth={v['truth'][:34]:34} best_20={v['best_20']:.4f} gate={v['gate_status']}", flush=True)
print("WROTE", OUTDIR / "synthetic_results.json")
