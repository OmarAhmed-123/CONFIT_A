#!/usr/bin/env python3
"""Build ARTIFACT_MANIFEST.json + LABELING_SHEET_rater{1,2,3}.csv +
UNBLINDING_SHEET.csv for the human calibration package (P6).

P8 hygiene: manifest stores PATHS + SHA256 + metadata only — no image
payloads, no credentials. display_order = fixed-seed shuffle (recorded).
"""
import csv
import hashlib
import json
import random
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RES = REPO / "evaluation" / "results"
FRESH = REPO / "evaluation" / "dyninputs_fresh"
SEED = 20260919
OUT = REPO / "evaluation" / "human_calibration"

def sha(p: Path):
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except Exception:
        return None

def rel(p: Path):
    try:
        return str(p.relative_to(REPO))
    except Exception:
        return str(p)

items = []

# ---------- Type S: 50-row matrix artifacts ----------
matrix = json.loads((RES / "sleeve_signal_matrix.json").read_text())
probe = (REPO / "evaluation" / "probes" / "sleeve_signal_probe.py").read_text()
S_DIRS = {}
for m in re.finditer(r'\("(\w+)",\s*"(\w+)",\s*"(\w+)"', probe):
    S_DIRS[f"{m.group(2)}_{m.group(3)}"] = m.group(1)

v24 = {r["case"]: r for r in json.loads((RES / "p6_sleeve_v24.json").read_text())["rows"]}
CORE_S = {
    # decision-critical: thin-margin, borderline partial, asymmetric FPs,
    # class-E, synthetic drops, pose/over-refusal rows
    "cal_01_L1", "cal_03_L1", "cal_04_L1", "cal_05_L1", "p4_j_arabic2_L1",
    "m1_light_trousers_L2", "m3_arms_raised_L2", "m5_dark_inner_L2",
    "p0c_synth_partial_krust_L1", "sc_crop_B_L1", "sc_tank_C_L1",
}
for r in matrix["rows"]:
    case = r["case"]
    d = S_DIRS.get(case)
    v = v24.get(case, {})
    # v2.3 = coverage( max S1>=0.35 ) AND max S5<0.10 AND max S6>=0.05  (measured)
    # v2.4 = v2.3 AND max any-skin < 0.15                              (measured)
    v23_status = ("PASS" if v.get("v23") else "REFUSE") if v else "n/a"
    v24_status = ("PASS" if (v.get("v23") and max(v["s5b"].values()) < 0.15) else "REFUSE") if v else "n/a"
    it = {
        "item_id": f"S_{case}", "type": "S", "case": case,
        "truth_label_agent": r["truth"],
        "gate_verdict_v23": v23_status,
        "gate_verdict_v24": v24_status,
        "gate_at_creation_historical": {"P": "PASS", "R": "REFUSE", "X": "n/a"}[r["gate"]],
        "core": case in CORE_S,
        "note": "50-row matrix artifact (Phase 3-5 cohorts; agent-labeled)",
    }
    if d:
        rp, ip, gp = RES / d / f"{case}.png", RES / d / f"{case}_input.png", RES / d / f"{case}_garment.png"
        it["render"], it["input"], it["garment_ref"] = rel(rp), rel(ip), rel(gp)
        it["sha256"] = {"render": sha(rp), "input": sha(ip), "garment_ref": sha(gp)}
    items.append(it)

# ---------- Type S: 7 adversarial composites (6 defects + base control) ----------
ADV = RES / "p6_sleeve_adversarial"
adv = json.loads((ADV / "results.json").read_text())
for name, rec in adv["cases"].items():
    it = {
        "item_id": f"S_{name}", "type": "S", "case": name,
        "truth_label_agent": "dropped",
        "gate_verdict_v23": "PASS" if name in ("adv_onearm", "adv_onearm_full") else "REFUSE",
        "gate_verdict_v24": "REFUSE",
        "core": name in ("adv_onearm", "adv_onearm_full", "adv_wristgap"),
        "note": "Phase-6 adversarial composite on cal_02 base (input tank top, arms exposed; agent-labeled)",
    }
    rp, ip, gp = (ADV / f"{name}.png",
                  RES / "calibration_v22" / "cal_02_L1_input.png",
                  RES / "calibration_v22" / "cal_02_L1_garment.png")
    it["render"], it["input"], it["garment_ref"] = rel(rp), rel(ip), rel(gp)
    it["sha256"] = {"render": sha(rp), "input": sha(ip), "garment_ref": sha(gp)}
    items.append(it)
# note: cal_02_L1 (the composites' healthy base) is already in the 50-row
# matrix and is labeled there — no duplicate item is added.

# ---------- Type S: Phase-7 P1-D fresh adversarial items ----------
# 10 fresh bases (never used to tune any rule) + 10 one-arm composites +
# 10 bilateral-crop composites. Label provenance: AGENT VISUAL INSPECTION
# (two bases were visually re-labeled as 3/4-sleeve defect renders).
ADV7 = RES / "p7_adversarial"
P1D = [
    # (name, kind, truth, core)
    ("p7d_dark_skin_white_lee", "base", "present", False),
    ("p7d_light_skin_black_tee", "base", "short_declared_long", True),   # 3/4 sleeves (visual)
    ("p7d_med_stripe_tee", "base", "present", False),
    ("p7d_hijab_navy_tunic", "base", "present", False),
    ("p7d_light_multicolor", "base", "present", False),
    ("p7d_arms_raised", "base", "present", False),
    ("p7d_plus_black", "base", "short_declared_long", True),             # sleeves to below-elbow (visual)
    ("p7d_light_burgundy", "base", "present", False),
    ("p7d_med_gray_darkbg", "base", "present", False),
    ("p7d_dark_beige", "base", "present", False),
]
for name, kind, truth, core in P1D:
    it = {
        "item_id": f"S_p7_{name}{'_' + kind if kind != 'base' else ''}",
        "type": "S", "case": name, "p1d_kind": kind,
        "truth_label_agent": truth,
        "gate_verdict_v23": ("n/a (fresh, pre-v2.4)" if kind == "base"
                              else "PASS — the v2.3 false-pass class on fresh arms (S1 0.54-0.99, S5 ~0)" if kind == "onearm"
                              else "REFUSE (measured)"),
        "gate_verdict_v24": {"p7d_light_skin_black_tee": "REFUSE (correct: 3/4 sleeves, s5b 0.356)",
                              "p7d_plus_black": "REFUSE (correct: sleeves to below-elbow, s5b 0.326)"}.get(name) or ("PASS" if (kind == "base" and truth == "present") else "REFUSE (measured, s5b 1.0)"),
        "core": core,
        "note": ("Phase-7 P1-D fresh base render (agent-labeled)" if kind == "base"
                 else "Phase-7 P1-D synthetic composite on a fresh base (forearm region replaced with the subject's skin color; paint edges visible; agent-labeled)"),
        "composition": f"Phase-7 P1-D {kind} on {name}",
    }
    if kind == "base":
        rp = ADV7 / f"{name}.png"
        it["render"], it["input"] = rel(rp), rel(rp)
        it["garment_ref"] = rel(rp)  # garment visible on the subject
    elif kind == "onearm":
        rp, ip = ADV7 / f"{name}_onearm.png", ADV7 / f"{name}_input_exposed.png"
        it["render"], it["input"], it["garment_ref"] = rel(rp), rel(ip), rel(ADV7 / f"{name}.png")
    else:
        rp, ip = ADV7 / f"{name}_bilateral_crop.png", ADV7 / f"{name}_input_exposed.png"
        it["render"], it["input"], it["garment_ref"] = rel(rp), rel(ip), rel(ADV7 / f"{name}.png")
    it["sha256"] = {"render": sha(Path(it["render"])), "input": sha(Path(it["input"])), "garment_ref": sha(Path(it["garment_ref"]))}
    items.append(it)

# ---------- Type L: 7 low-contrast P0 cases ----------
lc = json.loads((RES / "p6_lowcontrast" / "results.json").read_text())
LC_GAR = {
    "A-E": FRESH / "garment_navy_wool_trousers.jpg",
    "B": FRESH / "garment_charcoal_trousers.jpg",
    "C": FRESH / "garment_beige_chino.jpg",
    "D": FRESH / "garment_navy_wool_trousers.jpg",
    "F": FRESH / "garment_navy_patterned_trousers.jpg",
    "G": FRESH / "garment_navy_wool_trousers.jpg",
    "H": FRESH / "garment_navy_skirt.jpg",
}
LC_META = {
    "A-E": "person I (navy joggers) -> navy wool trousers",
    "B": "person I (navy joggers) -> charcoal trousers",
    "C": "person I (navy joggers) -> beige chinos",
    "D": "person C (cream chinos) -> navy wool trousers",
    "F": "person I (navy joggers) -> navy patterned trousers",
    "G": "person K (gray wide chinos) -> navy slim (wool) trousers",
    "H": "person A (denim) -> navy skirt",
}
base = RES / "p6_lowcontrast"
for c in lc["cases"]:
    cid = c["id"]
    passed = bool(c["l2"]["verify"].get("PASS"))
    rp, ip, gp = base / f"raw_{cid}_l2.png", base / f"raw_{cid}_l1.png", LC_GAR[cid]
    it = {
        "item_id": f"L_{cid}", "type": "L", "case": cid,
        "composition": LC_META[cid],
        "truth_label_agent": "applied" if passed else "not_applied",
        "gate_verdict_v23": "PASS" if passed else "REFUSE",
        "gate_verdict_v24": "PASS" if passed else "REFUSE",
        "verify_pixel_change": c["l2"]["verify"].get("metric_pixel_change"),
        "verify_color_shift": c["l2"]["verify"].get("metric_color_shift"),
        "core": True,
        "note": "Phase-6 P0 low-contrast matrix (direct worker; exact L1 bytes as L2 input)",
    }
    it["render"], it["input"], it["garment_ref"] = rel(rp), rel(ip), rel(gp)
    it["sha256"] = {"render": sha(rp), "input": sha(ip), "garment_ref": sha(gp)}
    items.append(it)

# ---------- display order (fixed seed) ----------
random.seed(SEED)
order = list(range(len(items)))
random.shuffle(order)
for new_pos, old_pos in enumerate(order):
    items[old_pos]["display_order"] = new_pos + 1
items.sort(key=lambda x: x["display_order"])
# Phase 7 P6: blinded presentation — raters see only opaque blind_id + type
# (no case names: "S_adv_onearm" would reveal the defect class; person and
# garment identities stay in the unblinding sheet only)
for i, it in enumerate(items):
    it["blind_id"] = f"item-{i+1:02d}"


manifest = {
    "seed": SEED,
    "n": len(items),
    "n_type_S": sum(1 for i in items if i["type"] == "S"),
    "n_type_L": sum(1 for i in items if i["type"] == "L"),
    "core_set_size": sum(1 for i in items if i.get("core")),
    "core_set": [i["item_id"] for i in items if i.get("core")],
    "hygiene": "P8: paths + sha256 + metadata only; no image payloads, no credentials",
    "items": items,
}
(OUT / "ARTIFACT_MANIFEST.json").write_text(json.dumps(manifest, indent=1))

for rater in (1, 2, 3):
    with open(OUT / f"LABELING_SHEET_rater{rater}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["blind_id", "type", "primary", "confidence_1_5", "notes"])
        for it in items:
            w.writerow([it["blind_id"], it["type"], "", "", ""])

with open(OUT / "UNBLINDING_SHEET.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["blind_id", "item_id", "type", "case", "truth_label_agent",
                "gate_verdict_v23", "gate_verdict_v24", "render_path"])
    for it in items:
        w.writerow([it["blind_id"], it["item_id"], it["type"], it["case"], it["truth_label_agent"],
                    it.get("gate_verdict_v23", ""), it.get("gate_verdict_v24", ""),
                    it.get("render", "")])

missing = [i["item_id"] for i in items if not i.get("sha256", {}).get("render")]
print(f"manifest: n={len(items)} (S={manifest['n_type_S']}, L={manifest['n_type_L']}), core={manifest['core_set_size']}")
print("missing render hashes:", missing or "none")
