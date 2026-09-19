"""Phase 1 §8 — person onboarding probe.

Renders each new person (p011+) with a reference garment (g003 navy sweater,
short-sleeve flat lay) and runs the local structural battery on the render:
face presence, pose presence, region status, occlusion state, face/pose
metrics, AdaFace identity cosine (eval-only), garment region color.
Purpose: verify the expanded fixture set works end-to-end BEFORE matrix runs
(detection failures on new demographics = findings, not surprises).
Writes results/person_onboarding_probe.json + outputs/onboarding/*.jpg
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
OUT_DIR = RESULTS / "outputs" / "onboarding"
OUT_DIR.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(EVAL_ROOT))

from PIL import Image  # noqa: E402

from harness.rootsleeve_root_cause import data_uri, load_env, load_urls, run_one  # noqa: E402

GARMENT = "g003"  # navy sweater (short-sleeve flat lay, drop 0.0)


def main():
    env = load_env()
    token = env["VTON_EVAL_ADMIN_TOKEN"]
    urls = load_urls()
    import re
    persons = sorted(
        (EVAL_ROOT / "fixtures" / "persons").glob("p0*.jpg"),
        key=lambda p: p.stem,
    )
    persons = [p for p in persons if re.fullmatch(r"p\d{3}", p.stem)]
    new = [p for p in persons if int(p.stem[1:]) >= 11]
    rows = []
    for pp in new:
        pid = pp.stem
        job_id = f"OB-{pid}-{GARMENT}"
        res = run_one(urls["process"], token, job_id, data_uri(pp),
                      EVAL_ROOT / "fixtures" / "garments" / f"{GARMENT}.jpg", "upper_inner")
        row = {"job_id": job_id, "person": pid, "garment": GARMENT,
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
            # ---- local structural battery
            from harness import run_offline_eval as roe
            M = roe.M
            fr = M["face"].face_report(Image.open(pp), img)
            row["face_present"] = fr.get("status") == "OK"
            if row["face_present"]:
                row["face_ssim"] = fr["ssim"]["aligned_face_ssim"]
                row["face_geo_disp"] = fr["geometry_delta"]["mean_normalized_displacement"]
            pr = M["pose"].pose_report(Image.open(pp), img)
            row["pose_present"] = pr.get("status") == "OK"
            if row["pose_present"]:
                row["pose_mpjpe"] = pr.get("mpjpe_torso_norm_raw")
            region, rstatus = M["regions"].regions_from_pose(img, "upper_inner")
            row["region_status"] = rstatus
            if rstatus == "OK":
                in_img = M["occ"].region_in_image(region["primary"], img.size[0], img.size[1])
                row["occlusion"] = M["occ"].classify(rstatus, in_img, occlusion_expected=False)
            try:
                from vton_metrics.adaface_eval import identity_cosine
                idr = identity_cosine(Image.open(pp), img)
                row["adaface_cos"] = idr["adaface_ir101"].get("cosine")
            except Exception as e:  # noqa: BLE001
                row["adaface_error"] = str(e)[:120]
        else:
            row["error"] = str(b)[:200]
        rows.append(row)
        print(f"{job_id} http={res['http']} face={row.get('face_present')} "
              f"pose={row.get('pose_present')} region={row.get('region_status')} "
              f"adaface={row.get('adaface_cos')}", flush=True)
        (RESULTS / "person_onboarding_probe.json").write_text(json.dumps(
            {"test": "person_onboarding_probe", "date": "2026-09-15",
             "garment": GARMENT, "jobs": rows}, indent=1))
    print("DONE", len(rows), "persons")


if __name__ == "__main__":
    main()
