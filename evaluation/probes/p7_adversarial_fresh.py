#!/usr/bin/env python3
"""P7 P1-D: FRESH adversarial cases for the frozen v2.4 gate.

10 freshly generated base renders (new persons, skin tones, garments,
backgrounds — none used to tune v2.4). For each base we construct:

  input_exposed      = base with BOTH arm bands filled skin-colored
                       (stands in for "person whose input already exposes
                       the forearms" — the Phase-6 FP class context)
  render_onearm      = base with the RIGHT band filled skin-colored
                       (asymmetric drop; left sleeve intact)
  render_bilateral   = base with the LOWER part of BOTH bands filled
                       skin-colored (bilateral crop to mid-forearm)

Gate runs (frozen production function, no monkeypatch):
  healthy:  output=base,              input=input_exposed  (expect PASS if bands align)
  onearm:   output=render_onearm,     input=input_exposed  (expect REFUSE — the v2.4 FP class, fresh arms)
  bilateral:output=render_bilateral,  input=input_exposed  (expect REFUSE)

Labels: AGENT VISUAL INSPECTION — NOT HUMAN GROUND TRUTH.

P8: JSON = measurements/statuses only; composite PNGs stay in results/
(gitignored), referenced by name.

Usage: python3 evaluation/probes/p7_adversarial_fresh.py
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from backend.app.services import vton_sleeve_gate as gate  # noqa: E402
from backend.app.services.vton_sleeve_gate import _rgb_to_lab, _is_skin_lab  # noqa: E402

OUT = REPO / "evaluation" / "results" / "p7_adversarial"
OUT.mkdir(parents=True, exist_ok=True)

BASES = [
    "p7d_dark_skin_white_lee", "p7d_light_skin_black_tee", "p7d_med_stripe_tee",
    "p7d_hijab_navy_tunic", "p7d_light_multicolor", "p7d_arms_raised",
    "p7d_plus_black", "p7d_light_burgundy", "p7d_med_gray_darkbg", "p7d_dark_beige",
]
# expected behavior (documented expectation, verified after the run)
EXPECT = {
    "p7d_arms_raised": {"healthy": "REFUSE (expected over-refusal: arms outside the fixed bands — safe direction)"},
}

BANDS = {"left": (0.52, 0.70, 0.40, 0.55), "right": (0.28, 0.46, 0.40, 0.55)}


def sample_skin(arr: np.ndarray) -> np.ndarray:
    """Median skin color from hand region, else face region."""
    h, w, _ = arr.shape
    for (y0, y1, x0, x1) in ((0.78, 0.92, 0.35, 0.65), (0.04, 0.16, 0.38, 0.62),
                             (0.60, 0.75, 0.30, 0.70),
                             # arms-raised: hands near the ears (both sides)
                             (0.06, 0.28, 0.15, 0.42), (0.06, 0.28, 0.58, 0.85)):
        patch = arr[int(h*y0):int(h*y1), int(w*x0):int(w*x1)].reshape(-1, 3)
        labs = [_rgb_to_lab(tuple(p)) for p in patch[::7]]
        skin = [p for p, lab in zip(patch[::7], labs) if _is_skin_lab(lab)]
        if len(skin) >= 20:
            return np.median(skin, axis=0).astype(np.uint8)
    raise RuntimeError("no skin-colored region found in the base image")


def fill_band(img: Image.Image, side: str, color, y_lo_frac: float = None) -> Image.Image:
    out = img.copy().convert("RGB")
    a = np.array(out)
    h, w, _ = a.shape
    fx0, fx1, fy0, fy1 = BANDS[side]
    y0 = int(h * (y_lo_frac if y_lo_frac is not None else fy0))
    a[y0:int(h*fy1), int(w*fx0):int(w*fx1)] = color
    return Image.fromarray(a)


def run(out_img, in_img, garment_img):
    d = gate.evaluate_sleeves_sync(slot_type="upper_inner", sleeve_length="long",
                                   output_img=out_img, input_img=in_img, garment_img=garment_img)
    cov = d.get("coverage") or {}
    anat = d.get("anatomy") or {}
    return {
        "status": d["status"], "reason": (d.get("reason") or "")[:280],
        "best_s1": max(cov.values()) if cov else None,
        "s5_max": max((v["new_skin_outer"] for v in anat.values()), default=None),
        "s5b_max": max((v["any_skin_outer"] for v in anat.values()), default=None),
        "s6_max": max((v["wrist_reach"] for v in anat.values()), default=None),
    }


def main():
    t0 = time.time()
    results = []
    for name in BASES:
        base_p = OUT / f"{name}.png"
        base = Image.open(base_p).convert("RGB")
        arr = np.array(base)
        skin = sample_skin(arr)
        exposed = fill_band(base, "left", skin)
        exposed = fill_band(exposed, "right", skin)
        onearm = fill_band(base, "right", skin)
        bilateral = fill_band(base, "left", skin, y_lo_frac=0.4825)
        bilateral = fill_band(bilateral, "right", skin, y_lo_frac=0.4825)
        # garment reference: torso+sleeve crop of the base (dominant color)
        h, w, _ = arr.shape
        garment = base.crop((int(w*0.28), int(h*0.22), int(w*0.72), int(h*0.55)))
        exposed.save(OUT / f"{name}_input_exposed.png")
        onearm.save(OUT / f"{name}_onearm.png")
        bilateral.save(OUT / f"{name}_bilateral_crop.png")

        rec = {"case": name,
               "skin_rgb_sampled": [int(v) for v in skin],
               "healthy": run(base, exposed, garment),
               "onearm_drop": run(onearm, exposed, garment),
               "bilateral_crop": run(bilateral, exposed, garment)}
        rec["note"] = EXPECT.get(name, {}).get("healthy", "healthy: PASS expected if bands align; defects: REFUSE required")
        results.append(rec)
        s = rec["healthy"]["status"]
        s1 = rec["onearm_drop"]["status"]
        s2 = rec["bilateral_crop"]["status"]
        print(f"{name:26s} healthy={s:6s} onearm={s1:6s} bilateral={s2:6s}")

    safety = [r["case"] for r in results
              if r["onearm_drop"]["status"] == "PASS" or r["bilateral_crop"]["status"] == "PASS"]
    out = {
        "gate_version": "v2.4 frozen (SLEEVE_GATE_V24_FROZEN_SPEC_2026-09-19.md)",
        "label_provenance": "AGENT VISUAL INSPECTION — NOT HUMAN GROUND TRUTH",
        "n_bases": len(results),
        "safety_violations": safety,
        "VERDICT": "SAFE" if not safety else "SLEEVE SAFETY = BLOCKED",
        "results": results,
        "elapsed_s": round(time.time() - t0, 1),
    }
    (OUT / "results.json").write_text(json.dumps(out, indent=1))
    print("safety violations:", safety or "none")
    print("VERDICT:", out["VERDICT"])


if __name__ == "__main__":
    main()
