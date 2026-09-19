"""P6 P5: fresh dynamic local + global batch — NEW runtime inputs.

Cohort (generated 2026-09-19, never used in any prior phase):
  person_p5l_hijab  hijab, white LS input        (local: modest)
  person_p5l_arabic green tee input              (local: Arabic text)
  person_p5l_deep   deep-skin man, gray tee      (local: skin tone)
  person_p5l_fair   fair-skin woman, beige tee   (local: skin tone)
  person_p5g_plus   plus-size, white tank        (global: body type)
  person_p5g_darkbg navy tee, DARK background    (global: lighting)
  person_p5g_tank   tanned man, white tank       (global: exposed arms)

Cases (N=2 independent worker calls each; unique job_id per call):
  L1 p5l_hijab_moderest   modest tunic, LS
  L2 p5l_hijab_dress      one-piece dress
  L3 p5l_arabic_text      Arabic-text tee, short  [EasyOCR text]
  L4 p5l_deep_rust        rust LS
  L5 p5l_fair_white       white LS
  L6 p5l_fair_pattern     patterned LS
  G1 p5g_plus_black       black LS over tank input (old-skin live condition)
  G2 p5g_darkbg_black     black LS on dark bg (dark-on-dark)
  G3 p5g_tank_text        text tee, short         [EasyOCR text]
  G4 p5g_tank_logo_chain  L1 short tee -> L2 logo blazer (inner+outer)
  G5 p5g_plus_topbottom   tee + joggers in ONE call (true multi-garment)

Per render: http/latency, worker verify, sleeve gate (LS cases),
lower-region diff (G5), EasyOCR text preservation (L3/G3), input+output
sha256 (P8: hashes + metrics only). Identity = NOT MEASURED (ArcFace
weights license-gated P7; DINOv2 weights unavailable in this environment)
— reported as NOT VERIFIED, no proxy substituted as identity evidence.
Labels: AGENT VISUAL INSPECTION — NOT HUMAN GROUND TRUTH.
"""
import base64
import hashlib
import json
import re
import sys
import time
import uuid
from pathlib import Path

import httpx
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

urls = (REPO / "evaluation" / ".eval_urls").read_text().split()
env_text = (REPO / "evaluation" / ".eval_env").read_text()
token = re.search(r"^VTON_EVAL_ADMIN_TOKEN=(.+)$", env_text, re.M).group(1).strip()
PROCESS_URL = urls[1]
HEADERS = {"X-VTON-Admin": token, "Content-Type": "application/json"}

P5 = REPO / "evaluation" / "dyninputs_p5"
FRESH = REPO / "evaluation" / "dyninputs_fresh"
LOCAL = REPO / "evaluation" / "dyninputs" / "local"
GLOBAL = REPO / "evaluation" / "dyninputs" / "global"
OUT = REPO / "evaluation" / "results" / "p5_dynamic_fresh"
OUT.mkdir(parents=True, exist_ok=True)

def b64(p: Path) -> str:
    return base64.b64encode(p.read_bytes()).decode()

def worker_call(person: Path, garments, n: int, tag: str):
    """garments: list of (path, slot, sleeve). Returns render info."""
    job = f"p5_{tag}_n{n}_{uuid.uuid4().hex[:8]}"
    payload = {
        "job_id": job,
        "user_image_base64_or_url": "data:image/jpeg;base64," + b64(person),
        "garments": [
            {"product_id": f"{job}_{i}", "slot_type": slot,
             "sleeve_length": sleeve, "image_base64": "data:image/jpeg;base64," + b64(g)}
            for i, (g, slot, sleeve) in enumerate(garments)
        ],
        "gender_mode": "infer_from_image", "output_aspect": "9:16",
    }
    t0 = time.time()
    try:
        r = httpx.post(PROCESS_URL, json=payload, headers=HEADERS, timeout=900)
    except Exception as e:
        return {"http": None, "error": f"{type(e).__name__}: {e}", "elapsed_s": round(time.time() - t0, 1)}
    el = round(time.time() - t0, 1)
    if r.status_code != 200:
        return {"http": r.status_code, "error": r.text[:400], "elapsed_s": el}
    d = r.json()
    rend = d.get("rendered_image_data_url", "")
    raw = base64.b64decode(rend.split(",", 1)[1]) if rend.startswith("data:") else b""
    (OUT / f"{job}.png").write_bytes(raw)
    return {"http": 200, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
            "verify": d.get("verify"), "raw_path": f"{job}.png", "elapsed_s": el}

def lower_region_diff(out_raw: bytes, in_path: Path):
    """P0-B signal: fraction of bottom-55% x center-60% pixels changed > 8/255
    (engine-applied evidence for lower-slot garments)."""
    import io
    import numpy as np
    a = np.array(Image.open(io.BytesIO(out_raw)).convert("L")).astype(int)
    b = np.array(Image.open(in_path).convert("L"))
    if b.shape != a.shape:
        b = np.array(Image.open(in_path).convert("L").resize((a.shape[1], a.shape[0])))
    h, w = a.shape
    reg_a = a[int(h * 0.45):, int(w * 0.20):int(w * 0.80)]
    reg_b = b[int(h * 0.45):, int(w * 0.20):int(w * 0.80)]
    return round(float((np.abs(reg_a - reg_b) > 8).mean()), 5)

def ocr_text(img_path: Path, lang: str = "en"):
    """Single-language EasyOCR in a SUBPROCESS: the sandbox has 2GB RAM and
    loading two language models OOMs (measured: ['ar','en'] -> SIGKILL 137;
    single-language readers fit). 'ar' may still OOM under memory pressure —
    the error is then recorded, not hidden."""
    import subprocess
    code = (
        "import warnings; warnings.filterwarnings('ignore'); import easyocr, json, sys\n"
        "r = easyocr.Reader([%r], gpu=False, verbose=False)\n"
        "res = r.readtext(sys.argv[1])\n"
        "print(json.dumps([t[1] for t in res if t[2] >= 0.4]))\n" % lang
    )
    try:
        p = subprocess.run([sys.executable, "-c", code, str(img_path)],
                           capture_output=True, text=True, timeout=300)
        if p.returncode != 0:
            return {"error": f"exit {p.returncode}: {p.stderr.strip()[-200:]}"}
        import json as _json
        return _json.loads(p.stdout.strip().splitlines()[-1])
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:200]}"}

from backend.app.services.vton_sleeve_gate import evaluate_sleeves_sync  # noqa: E402

CASES = [
    # tag, person, garments [(path, slot, sleeve)], ls_gate, extra
    ("L1", "p5l_hijab_moderest", P5 / "person_p5l_hijab.jpg", [(FRESH / "garment_modest_tunic.jpg", "upper_inner", "long")], True, {}),
    ("L2", "p5l_hijab_dress", P5 / "person_p5l_hijab.jpg", [(LOCAL / "garment_local_dress.jpg", "dress", "long")], True, {}),
    ("L3", "p5l_arabic_text", P5 / "person_p5l_arabic.jpg", [(LOCAL / "garment_local_arabic_tee.jpg", "upper_inner", "short")], False, {"ocr": True, "ocr_lang": "ar"}),
    ("L4", "p5l_deep_rust", P5 / "person_p5l_deep.jpg", [(FRESH / "garment_rust_longsleeve.jpg", "upper_inner", "long")], True, {}),
    ("L5", "p5l_fair_white", P5 / "person_p5l_fair.jpg", [(FRESH / "garment_white_longsleeve.jpg", "upper_inner", "long")], True, {}),
    ("L6", "p5l_fair_pattern", P5 / "person_p5l_fair.jpg", [(FRESH / "garment_patterned_ls.jpg", "upper_inner", "long")], True, {}),
    ("G1", "p5g_plus_black", P5 / "person_p5g_plus.jpg", [(FRESH / "garment_black_longsleeve.jpg", "upper_inner", "long")], True, {}),
    ("G2", "p5g_darkbg_black", P5 / "person_p5g_darkbg.jpg", [(FRESH / "garment_black_longsleeve.jpg", "upper_inner", "long")], True, {}),
    ("G3", "p5g_tank_text", P5 / "person_p5g_tank.jpg", [(GLOBAL / "garment_global_text_tee.jpg", "upper_inner", "short")], False, {"ocr": True}),
    ("G4", "p5g_tank_logo_chain", P5 / "person_p5g_tank.jpg", [(FRESH / "garment_short_sleeve_tee.jpg", "upper_inner", "short")], False, {"chain": GLOBAL / "garment_global_logo_blazer.jpg"}),
    ("G5", "p5g_plus_topbottom", P5 / "person_p5g_plus.jpg", [(FRESH / "garment_short_sleeve_tee.jpg", "upper_inner", "short"), (FRESH / "garment_black_joggers.jpg", "lower", "none")], False, {"lower": True}),
]

def _gate_fingerprint() -> dict:
    """Record the EXACT frozen gate version + commit + constants at run time
    (Phase 7 P5: do not reuse pre-v2.4 results as current verification)."""
    import subprocess
    import backend.app.services.vton_sleeve_gate as g
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                                capture_output=True, text=True).stdout.strip()
    except Exception:
        commit = "unknown"
    return {
        "gate_version": "v2.4 (frozen: SLEEVE_GATE_V24_FROZEN_SPEC_2026-09-19.md)",
        "git_commit": commit,
        "constants": {
            "S1_pass": g.FOREARM_PASS_THRESHOLD,
            "S1_fail": g.FOREARM_FAIL_THRESHOLD,
            "S5_new_skin_refuse": g.ANATOMY_NEW_SKIN_REFUSE,
            "S5b_any_skin_refuse": g.ANATOMY_ANY_SKIN_REFUSE,
            "S6_wrist_reach_refuse": g.ANATOMY_WRIST_REACH_REFUSE,
            "delta_e_radius": g.DELTA_E_RADIUS,
            "change_threshold": g.FOREARM_CHANGE_THRESHOLD,
        },
    }


def main():
    RESULTS = {"cohort": sorted(p.name for p in P5.glob("person_*.jpg")),
               "gate": _gate_fingerprint(),
               "note": "P5 fresh dynamic batch, NEW runtime inputs (2026-09-19). "
                       "N=2 = two independent worker calls per case "
                       "(within-instance determinism check via sha compare). "
                       "IDENTITY = NOT MEASURED (ArcFace license-gated P7; "
                       "DINOv2 weights unavailable) — NOT VERIFIED, no proxy. "
                       "Labels: AGENT VISUAL INSPECTION, NOT HUMAN GROUND TRUTH. "
                       "Results are valid only for the recorded gate version/commit.",
               "cases": {}}
    for cid, tag, person, garments, ls_gate, extra in CASES:
        rec = {"person": person.name, "garments": [g.name for g, _, _ in garments],
               "renders": []}
        for n in (1, 2):
            info = worker_call(person, garments, n, tag)
            r = {k: info.get(k) for k in ("http", "elapsed_s", "sha256", "error", "verify", "raw_path")}
            if info.get("http") == 200 and info.get("raw"):
                raw = info["raw"]
                if ls_gate:
                    d = evaluate_sleeves_sync(slot_type=garments[0][1], sleeve_length=garments[0][2],
                                              output_img=Image.open(OUT / info["raw_path"]).convert("RGB"),
                                              input_img=Image.open(person).convert("RGB"),
                                              garment_img=Image.open(garments[0][0]).convert("RGB"))
                    r["sleeve_gate"] = {k: d.get(k) for k in ("status", "coverage", "anatomy", "reason")}
                if extra.get("lower"):
                    r["lower_region_changed_frac"] = lower_region_diff(raw, person)
            if extra.get("ocr") and info.get("http") == 200:
                lang = extra.get("ocr_lang", "en")
                r["ocr_input_garment"] = ocr_text(garments[0][0], lang)
                r["ocr_render"] = ocr_text(OUT / info["raw_path"], lang) if info.get("raw_path") else None
            # chain: L2 = logo blazer over the L1 output
            if extra.get("chain") and info.get("http") == 200 and info.get("raw_path"):
                l2 = worker_call(OUT / info["raw_path"], [(extra["chain"], "upper_outer", "long")], n, f"{tag}_L2")
                r2 = {k: l2.get(k) for k in ("http", "elapsed_s", "sha256", "error", "verify")}
                if l2.get("http") == 200 and l2.get("raw_path"):
                    d2 = evaluate_sleeves_sync(slot_type="upper_outer", sleeve_length="long",
                                               output_img=Image.open(OUT / l2["raw_path"]).convert("RGB"),
                                               input_img=Image.open(OUT / info["raw_path"]).convert("RGB"),
                                               garment_img=Image.open(extra["chain"]).convert("RGB"))
                    r2["sleeve_gate"] = {k: d2.get(k) for k in ("status", "coverage", "anatomy", "reason")}
                r["L2_logo_blazer"] = r2
            rec["renders"].append(r)
        # determinism: N=2 sha compare
        shas = [r.get("sha256") for r in rec["renders"]]
        rec["deterministic_within_instance"] = (len(set(s for s in shas if s)) == 1)
        RESULTS["cases"][cid] = rec
        st = [f"{r.get('http')}/{r.get('sleeve_gate', {}).get('status', '-')}({r.get('elapsed_s')}s)" for r in rec["renders"]]
        print(f"{cid} {tag:22} " + "  ".join(st), flush=True)

    (OUT / "results.json").write_text(json.dumps(RESULTS, indent=1, default=str))
    print("WROTE", OUT / "results.json")

if __name__ == "__main__":
    main()
