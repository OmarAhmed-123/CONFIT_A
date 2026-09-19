"""P6 P1-B: adversarial composites on the cal_02 base.

Base: cal_02_L1 (Phase-3 render, agent-labeled 'present', gate PASS:
S1 0.4619 / S5 0.0019 / S6 0.2294). Its INPUT wears a white TANK TOP —
arms fully exposed in the input — the condition that defeats S5's
"new skin" semantics: any skin the engine exposes is ALSO present in
the input (delta-E ~0), so S5 sees zero NEW skin no matter what drops.

Composites (input arm pixels pasted over the rendered sleeves):
  adv_crop     sleeve ends at mid-bicep        (expect REFUSE: S1+S6)
  adv_elbow    sleeve ends at the elbow        (expect REFUSE: S1+S6)
  adv_midgap   upper sleeve + CUFF present,
               bare mid-forearm gap on both arms
               (P1-B target: S1 ~0.47, S5 = 0 (OLD skin), S6 ~0.49
                -> potential FALSE PASS of a visibly incomplete render)
  adv_onearm   person's RIGHT sleeve fully dropped, left intact
               (tests S5 max-arm logic on asymmetric drops with OLD skin)
  adv_wristgap upper sleeve present, cuff/wrist bare on both arms
               (wrist zone ~49% fabric -> S6 passes?)

All composites evaluated through PRODUCTION evaluate_sleeves_sync with
the real cal_02 input + garment. Labels: AGENT VISUAL INSPECTION —
NOT HUMAN GROUND TRUTH. Synthetic composites (pasted input pixels),
not engine outputs.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

OUT = REPO / "evaluation" / "results" / "p6_sleeve_adversarial"
OUT.mkdir(parents=True, exist_ok=True)
CAL = REPO / "evaluation" / "results" / "calibration_v22"
BASE = CAL / "cal_02_L1.png"
INPUT = CAL / "cal_02_L1_input.png"
GAR = CAL / "cal_02_L1_garment.png"

# forearm bands — must match vton_sleeve_gate.FOREARM_BANDS
BANDS = {"left": (0.52, 0.70, 0.40, 0.55), "right": (0.28, 0.46, 0.40, 0.55)}

def paste_arm(render: Image.Image, inp: Image.Image, side: str, y_cut: float, y_end: float) -> Image.Image:
    out = render.copy()
    W, H = render.size
    ix0, ix1, _, _ = BANDS[side]
    x0, x1 = int((ix0 + 0.015) * W), int((ix1 - 0.015) * W)
    ya, yb = int(y_cut * H), int(y_end * H)
    out.paste(inp.crop((x0, ya, x1, yb)), (x0, ya))
    return out

def both(render, inp, y_cut, y_end):
    return paste_arm(paste_arm(render, inp, "left", y_cut, y_end), inp, "right", y_cut, y_end)

def main():
    render = Image.open(BASE).convert("RGB")
    inp = Image.open(INPUT).convert("RGB").resize(render.size, Image.LANCZOS)
    gar = Image.open(GAR).convert("RGB")

    from backend.app.services.vton_sleeve_gate import evaluate_sleeves_sync

    cases = {
        "adv_crop":     lambda r: both(r, inp, 0.30, 0.72),
        "adv_elbow":    lambda r: both(r, inp, 0.40, 0.72),
        "adv_midgap":   lambda r: both(r, inp, 0.42, 0.50),
        "adv_onearm":   lambda r: paste_arm(r, inp, "right", 0.40, 0.72),
        "adv_wristgap": lambda r: both(r, inp, 0.50, 0.62),
    }

    RESULTS = {
        "base": {
            "file": "cal_02_L1.png",
            "input": "cal_02_L1_input.png (white TANK TOP — arms exposed in input)",
            "note": "Phase-3 render, agent-labeled present; sleeves fully to wrists",
        },
        "note": ("P1-B adversarial composites (input pixels pasted over rendered "
                 "sleeves). AGENT VISUAL INSPECTION — NOT HUMAN GROUND TRUTH. "
                 "Synthetic composites, not engine outputs."),
        "cases": {},
    }

    dbase = evaluate_sleeves_sync(slot_type="upper_inner", sleeve_length="long",
                                  output_img=render, input_img=inp, garment_img=gar)
    RESULTS["base"]["gate"] = {k: dbase.get(k) for k in ("status", "coverage", "anatomy", "reason")}
    print("BASE gate:", dbase["status"], dbase.get("coverage"), dbase.get("anatomy"), flush=True)

    for name, fn in cases.items():
        comp = fn(render)
        (OUT / f"{name}.png").save if False else comp.save(OUT / f"{name}.png")
        d = evaluate_sleeves_sync(slot_type="upper_inner", sleeve_length="long",
                                  output_img=comp, input_img=inp, garment_img=gar)
        rec = {k: d.get(k) for k in ("status", "coverage", "anatomy", "reason")}
        RESULTS["cases"][name] = {"file": f"{name}.png", **rec}
        print(f"{name}: {d['status']} cov={d.get('coverage')} anat={d.get('anatomy')}", flush=True)

    # contact sheet for visual inspection
    sheets = [render] + [Image.open(OUT / f"{n}.png").convert("RGB") for n in cases]
    cols = 3
    cw, ch = 260, 400
    rows = (len(sheets) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (cw + 10), rows * (ch + 24)), (255, 255, 255))
    from PIL import ImageDraw
    dr = ImageDraw.Draw(sheet)
    labels = ["BASE (good)"] + list(cases)
    for i, (im, lab) in enumerate(zip(sheets, labels)):
        t = im.copy(); t.thumbnail((cw, ch))
        x, y = (i % cols) * (cw + 10), (i // cols) * (ch + 24)
        sheet.paste(t, (x, y + 22))
        dr.text((x, y + 4), lab, fill=(0, 0, 0))
    sheet.save(OUT / "contact_sheet.png")

    (OUT / "results.json").write_text(json.dumps(RESULTS, indent=1, default=str))
    print("WROTE", OUT / "results.json")

if __name__ == "__main__":
    main()
