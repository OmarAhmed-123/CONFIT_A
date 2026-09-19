"""Phase 1 §10/§12 — local-market Arabic + mixed-text OCR evaluation.

Renders: g120 (Arabic) x p001/p007, g121 (mixed en+ar) x p010.
Measures OCR fidelity per language on the VTON output (English and Arabic
measured SEPARATELY; mixed under the combined reader — no cross-language
assumption), plus the English control g009 ('STUDIO 2026') x p001.
Writes results/arabic_ocr_eval.json + outputs/arabic_ocr/*.jpg
"""
from __future__ import annotations

import base64
import io
import json
import sys
import time
from pathlib import Path

EVAL_ROOT = Path(__file__).resolve().parent.parent
RESULTS = EVAL_ROOT / "results"
OUT_DIR = RESULTS / "outputs" / "arabic_ocr"
OUT_DIR.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(EVAL_ROOT))

from PIL import Image  # noqa: E402

from harness.rootsleeve_root_cause import data_uri, load_env, load_urls, run_one  # noqa: E402
from vton_metrics.ocr_metrics import text_fidelity  # noqa: E402
from vton_metrics.sleeve_metrics import _content_box  # noqa: E402
from vton_metrics.imaging import to_array  # noqa: E402

PLAN = [
    ("g120", "p001", "ar", [("ar", "القاهرة")]),
    ("g120", "p007", "ar", [("ar", "القاهرة")]),
    ("g121", "p010", "mixed", [("en", "CONFIT 2026"), ("ar", "القاهرة")]),
    ("g009", "p001", "en_control", [("en", "STUDIO 2026")]),
]


def main():
    env = load_env()
    token = env["VTON_EVAL_ADMIN_TOKEN"]
    urls = load_urls()
    gdir = EVAL_ROOT / "fixtures" / "garments"
    rows = []
    for gid, pid, kind, checks in PLAN:
        job_id = f"AO-{gid}-{pid}-{kind}"
        res = run_one(urls["process"], token, job_id,
                      data_uri(EVAL_ROOT / "fixtures" / "persons" / f"{pid}.jpg"),
                      gdir / f"{gid}.jpg", "upper_inner")
        row = {"job_id": job_id, "garment": gid, "person": pid, "kind": kind,
               "http": res["http"], "wall_s": res["wall_s"]}
        b = res["body"]
        if res["http"] == 200 and isinstance(b, dict) and b.get("rendered_image_data_url"):
            out_b64 = b["rendered_image_data_url"].split(",", 1)[-1]
            outp = OUT_DIR / f"{job_id}.jpg"
            img = Image.open(io.BytesIO(base64.b64decode(out_b64))).convert("RGB")
            img.save(outp, "JPEG", quality=95)
            row["output"] = str(outp.relative_to(EVAL_ROOT))
            row["verify"] = b.get("verify")
            row["pixel_change"] = (b.get("verify") or {}).get("metric_pixel_change")
            gimg = Image.open(gdir / f"{gid}.jpg").convert("RGB")
            box = _content_box(to_array(gimg))
            # map the garment content box onto the rendered torso region:
            # use the pose-derived primary region from the offline-eval path
            from harness import run_offline_eval as roe
            region, rstatus = roe.M["regions"].regions_from_pose(img, "upper_inner")
            rbox = region["primary"] if rstatus == "OK" else box
            row["region_status"] = rstatus
            row["ocr"] = {}
            for lang, exp in checks:
                r = text_fidelity(exp, img, rbox, langs=(lang,))
                row["ocr"][lang] = {
                    "expected": exp,
                    "detected_joined": r["detected_joined"],
                    "exact_match": r["exact_match"],
                    "word_overlap": r["word_overlap"],
                    "score": r["score"],
                    "confidence_max": max((d["confidence"] for d in r["detected"]), default=0.0),
                    "n_detected": len(r["detected"]),
                    "regime": r["regime"],
                }
        else:
            row["error"] = str(b)[:200]
        rows.append(row)
        print(f"{job_id} http={res['http']} wall={res['wall_s']}s "
              f"ocr={ {k: v.get('score') for k, v in row.get('ocr', {}).items()} }", flush=True)
        (RESULTS / "arabic_ocr_eval.json").write_text(json.dumps(
            {"test": "local_market_arabic_ocr", "date": "2026-09-15", "jobs": rows}, indent=1))
    (RESULTS / "arabic_ocr_eval.json").write_text(json.dumps(
        {"test": "local_market_arabic_ocr", "date": "2026-09-15",
         "note": "English/Arabic measured separately; mixed via combined reader",
         "jobs": rows}, indent=1))
    print("DONE", len(rows), "jobs")


if __name__ == "__main__":
    main()
