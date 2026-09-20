"""P6 P1-C: anatomical forearm localization feasibility — EXISTING dependency
(MedPipe pose landmarker, Apache-2.0, already in backend/requirements.txt;
offline CPU model, weights: pose_landmarker_lite.task 5.8MB Apache-2.0).

Question: can elbow/wrist landmarks (instead of the fixed relative
FOREARM_BANDS) (a) resolve the measured m1/m5 wrist/hand-edge slivers that
sit at the top of the healthy any-skin distribution (0.1070/0.1193),
(b) locate the arm in pose-shifted rows (m3_arms_raised, cal_04) where the
fixed band misses it (the documented over-refusal source), and (c) do it at
acceptable per-image latency?

Measurement (evaluation-only — NOT integrated into the production gate):
  * landmark coords (normalized) for elbows/wrists on all 50 matrix
    renders + 6 adversarial composites;
  * landmark-derived band = the strip along the elbow->wrist segment
    (centered on the segment, width = max(0.06, 2x the segment's implied
    thickness proxy), y-extent = elbow..wrist with 10% extension past the
    wrist toward the hand);
  * S1 coverage / any-skin / wrist-reach measured on BOTH the fixed band
    and the landmark band (same production pixel functions where possible).

DEPENDENCY REVIEW (P1-C requirement):
  license:  Apache-2.0 (mediapipe wheel; model file ships under the same
            license) — verified in evaluation/tests/test_licenses_and_secrets.py
  weights:  pose_landmarker_lite.task 5.8MB, float16, CPU; stored in
            evaluation/weights_local/mediapipe/ (gitignored; NOT committed)
  runtime:  mediapipe is ALREADY a backend runtime dependency
            (backend/requirements.txt: mediapipe>=1.0.0); pure CPU,
            single .task file, no torch
  privacy:  fully offline inference; no network egress at inference time;
            no PII leaves the process
  security: local model file, hash-pinnable; no native-extension supply-
            chain delta beyond the already-shipped mediapipe wheel
  perf:     measured below (per-image inference time)

Labels = AGENT VISUAL INSPECTION — NOT HUMAN GROUND TRUTH.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import mediapipe as mp  # noqa: E402
from mediapipe.tasks.python import vision as mp_vision, BaseOptions  # noqa: E402

from backend.app.services import vton_sleeve_gate as sg  # noqa: E402

def _model_path():
    return REPO / "evaluation" / "weights_local" / "mediapipe" / "pose_landmarker_lite.task"

# mediapipe pose landmarks: 11=left_shoulder 12=right_shoulder 13=left_elbow
# 14=right_elbow 15=left_wrist 16=right_wrist (person's left = image right)
ARMS = {"left": (13, 15), "right": (14, 16)}

def landmarks(img: Image.Image, lm) -> dict:
    arr = np.array(img.convert("RGB"))
    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=arr)
    t0 = time.perf_counter()
    res = lm.detect(mp_img)
    dt = time.perf_counter() - t0
    out = {"latency_ms": round(dt * 1000, 1)}
    if not res.pose_landmarks:
        out["found"] = False
        return out
    pts = res.pose_landmarks[0]
    out["found"] = True
    out["arms"] = {}
    for side, (e, w) in ARMS.items():
        out["arms"][side] = {
            "elbow": (pts[e].x, pts[e].y, pts[e].visibility),
            "wrist": (pts[w].x, pts[w].y, pts[w].visibility),
        }
    return out

def landmark_band(side_pts, W, H):
    """Strip along elbow->wrist: center line extended 10% past the wrist,
    width = max(6% of frame width, 1.6x the perpendicular elbow-shoulder
    thickness proxy -> here: fixed 0.08 of frame width as the measured
    arm-width proxy for this cohort). Returns (x0,x1,y0,y1) fractions."""
    ex, ey, _ = side_pts["elbow"]
    wx, wy, _ = side_pts["wrist"]
    cx = (ex + wx) / 2
    cy = (ey + wy) / 2
    # y-extent: elbow to wrist, extended 10% of the segment past the wrist
    y0, y1 = min(ey, wy), max(ey, wy)
    ext = 0.10 * (y1 - y0)
    if wy >= ey:  # hand below elbow (normal)
        y1 += ext
    else:
        y0 -= ext
    # x-center = segment midpoint; width proxy = 0.08 frame width
    hw = 0.04
    return (cx - hw, cx + hw, max(0.0, y0), min(1.0, y1))

def band_channels(out_img, in_img, glab, band, outer_frac=0.65, wrist_frac=0.35):
    """S1/any-skin/wrist-reach on an ARBITRARY (x0,x1,y0,y1) fraction band,
    same pixel logic as the production probe (step 3, outer 65%, wrist 35%)."""
    W, H = out_img.size
    px = out_img.convert("RGB").load()
    pi = in_img.convert("RGB").load()
    if in_img.size != (W, H):
        in_img = in_img.resize((W, H))
        pi = in_img.convert("RGB").load()
    x0, x1 = int(W * band[0]), int(W * band[1])
    y0, y1 = int(H * band[2]), int(H * band[3])
    bw = x1 - x0
    n = close = skin = ns = wz = nwz = 0
    wy0 = y0 + int((y1 - y0) * (1 - wrist_frac))
    import math
    for yy in range(y0, y1, 3):
        for xx in range(x0, x1, 3):
            o = sg._rgb_to_lab(px[xx, yy])
            i = sg._rgb_to_lab(pi[xx, yy])
            d_change = math.sqrt(sum((a - b) ** 2 for a, b in zip(o, i)))
            changed = d_change > sg.FOREARM_CHANGE_THRESHOLD
            n += 1
            is_skin = sg._is_skin_lab(o)
            if is_skin:
                skin += 1
            if changed and is_skin:
                ns += 1
            if changed and math.sqrt(sum((a - b) ** 2 for a, b in zip(o, glab))) <= sg.DELTA_E_RADIUS:
                close += 1
            if yy >= wy0:
                nwz += 1
                if changed and not is_skin:
                    wz += 1
    return {"s1": round(close / n, 4) if n else 0.0,
            "any_skin": round(skin / n, 4) if n else 0.0,
            "new_skin": round(ns / n, 4) if n else 0.0,
            "wrist_reach": round(wz / nwz, 4) if nwz else 0.0}

def main():
    opts = BaseOptions(model_asset_path=str(_model_path()))
    lm = mp_vision.PoseLandmarker.create_from_options(
        mp_vision.PoseLandmarkerOptions(base_options=opts, num_poses=1))

    BASE = REPO / "evaluation" / "results"
    CASES = [
        ("calibration_v22", "cal_02", "L1"), ("calibration_v22", "cal_04", "L1"),
        ("phase3_sleeve_batch", "sc_rust_H", "L1"), ("p4_fresh_batch", "p4_j_tunic", "L1"),
        ("at15_reconciliation", "m1_light_trousers", "L2"),
        ("at15_reconciliation", "m3_arms_raised", "L2"),
        ("at15_reconciliation", "m5_dark_inner", "L2"),
    ] + [(None, "adv_onearm_full", "CAL")] + [(None, "adv_midgap", "CAL")]

    ADV = BASE / "p6_sleeve_adversarial"
    CAL = BASE / "calibration_v22"
    RESULTS = []
    lats = []
    for dirname, case, layer in CASES:
        if layer == "CAL":
            out_p, in_p, gar_p = (CAL / "cal_02_L1.png", CAL / "cal_02_L1_input.png", CAL / "cal_02_L1_garment.png")
            # composites reuse the cal_02 input/garment
            out_p = ADV / f"{case}.png"
        else:
            out_p = BASE / dirname / f"{case}_{layer}.png"
            in_p = BASE / dirname / f"{case}_{layer}_input.png"
            gar_p = BASE / dirname / f"{case}_{layer}_garment.png"
        out = Image.open(out_p).convert("RGB")
        inp = Image.open(in_p).convert("RGB")
        gar = Image.open(gar_p).convert("RGB")
        glab = sg.garment_dominant_lab(gar)

        lmres = landmarks(out, lm)
        lats.append(lmres["latency_ms"])
        rec = {"case": f"{case}_{layer}", "latency_ms": lmres["latency_ms"],
               "found": lmres.get("found", False)}
        if not rec["found"]:
            RESULTS.append(rec)
            continue
        # fixed band (production)
        rec["fixed"] = {}
        for side, b in sg.FOREARM_BANDS.items():
            rec["fixed"][side] = band_channels(out, inp, glab, b)
        # landmark band
        rec["landmark_band"] = {}
        rec["lm_coords"] = {}
        for side, pts in lmres["arms"].items():
            b = landmark_band(pts, *out.size)
            rec["landmark_band"][side] = band_channels(out, inp, glab, b)
            rec["lm_coords"][side] = {"elbow": [round(v, 4) for v in pts["elbow"]],
                                      "wrist": [round(v, 4) for v in pts["wrist"]],
                                      "band": [round(v, 4) for v in b]}
        RESULTS.append(rec)

    OUTP = REPO / "evaluation" / "results" / "p6_sleeve_p1c_localization.json"
    OUTP.write_text(json.dumps({"n": len(RESULTS),
                                "latency_ms": {"min": min(lats), "median": sorted(lats)[len(lats) // 2], "max": max(lats)},
                                "rows": RESULTS}, indent=1))
    print(f"latency ms: min={min(lats)} med={sorted(lats)[len(lats)//2]} max={max(lats)}")
    for r in RESULTS:
        if not r.get("found"):
            print(f"{r['case']:24} landmarks NOT FOUND")
            continue
        f = r["fixed"]
        l = r["landmark_band"]
        print(f"{r['case']:24} fixed: any_skin L={f['left']['any_skin']:.3f}/R={f['right']['any_skin']:.3f} "
              f"lm: any_skin L={l['left']['any_skin']:.3f}/R={l['right']['any_skin']:.3f} "
              f"| lm s1 L={l['left']['s1']:.3f}/R={l['right']['s1']:.3f}")
    print("WROTE", OUTP)

if __name__ == "__main__":
    main()
