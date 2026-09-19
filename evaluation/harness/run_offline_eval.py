"""Offline metric evaluation over baseline outputs (Phase 0.5 §11-18).

For every successful chain step:
  - tier-1 garment region from pose + slot prior (regions.py)
  - color report (delta E, dominant colors, histogram) vs fixture ground truth
  - texture report (edge, spectrum, autocorrelation period vs fixture period)
  - OCR text fidelity where fixture has text (g009)
  - DINOv2 region similarity vs fixture garment region
  - face/pose identity metrics vs the ORIGINAL person (chain invariant)
  - occlusion state per layer (occlusion.py)
  - artifact proxies (artifacts.py)
  - evidence record (verdict.py) — NO frozen thresholds applied.

Outputs: results/<run_id>/offline_eval.json (+ .csv summary).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
from PIL import Image

EVAL_ROOT = Path(__file__).resolve().parent.parent
RESULTS = EVAL_ROOT / "results"
OUTPUTS = RESULTS / "outputs"

sys_path_fix = None


def _import_metrics():
    import sys
    sys.path.insert(0, str(EVAL_ROOT))
    from vton_metrics import artifacts, color_metrics, dino_metrics, face_metrics, occlusion, ocr_metrics, pose_metrics, regions, texture_metrics
    return dict(artifacts=artifacts, color=color_metrics, dino=dino_metrics, face=face_metrics,
                occ=occlusion, ocr=ocr_metrics, pose=pose_metrics, regions=regions, tex=texture_metrics)


M = _import_metrics()


def fixture_garment_box(gpath: Path) -> tuple:
    """Tight-ish content box of the garment fixture (non-background pixels)."""
    import numpy as np
    arr = np.asarray(Image.open(gpath).convert("RGB"))
    bg = arr[0, 0]
    mask = (np.abs(arr.astype(int) - bg.astype(int)).sum(axis=2) > 30)
    ys, xs = np.where(mask)
    if len(xs) == 0:
        w, h = Image.open(gpath).size
        return (0, 0, w, h)
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def expected_period(garment_manifest_entry: dict) -> int | None:
    pt = garment_manifest_entry.get("pattern_type")
    if pt in ("stripes", "check"):
        box = fixture_garment_box(OUTPUTS if False else EVAL_ROOT / "fixtures" / "garments" / f"{garment_manifest_entry['garment_id']}.jpg")
        img = Image.open(EVAL_ROOT / "fixtures" / "garments" / f"{garment_manifest_entry['garment_id']}.jpg")
        ac = M["tex"].local_autocorrelation(img, box)
        return ac.get("strongest_period")
    return None


def evaluate_run(run_id: str = "baseline-20260915") -> dict:
    rec = json.loads((RESULTS / "baseline_runs.json").read_text())
    gmanifest = {g["garment_id"]: g for g in
                 json.loads((EVAL_ROOT / "fixtures" / "garment_manifest.json").read_text())}
    pmanifest = {p["person_id"]: p for p in
                 json.loads((EVAL_ROOT / "fixtures" / "person_manifest.json").read_text())}
    results = []
    for job in rec["jobs"]:
        if job["http"] != 200 or not job.get("output_sha256"):
            continue
        out_path = OUTPUTS / f"{job['outfit_id']}-L{job['order']}-{job['garment_id']}.jpg"
        if not out_path.exists():
            continue
        img = Image.open(out_path).convert("RGB")
        person_path = EVAL_ROOT / "fixtures" / "persons" / f"{job['person_id']}.jpg"
        person = Image.open(person_path).convert("RGB")
        g = gmanifest[job["garment_id"]]
        gpath = EVAL_ROOT / "fixtures" / "garments" / f"{g['garment_id']}.jpg"
        gimg = Image.open(gpath).convert("RGB")

        ev = {"sample_id": f"{job['outfit_id']}/L{job['order']}", "arm": job["arm"],
              "garment_id": job["garment_id"], "person_id": job["person_id"],
              "output": str(out_path.relative_to(EVAL_ROOT)), "metrics": {},
              "structural": {"worker_success": True}}

        # ---- regions + occlusion
        region, rstatus = M["regions"].regions_from_pose(img, job["slot"])
        ev["region_status"] = rstatus
        if rstatus == "OK":
            box = region["primary"]
            in_img = M["occ"].region_in_image(box, img.size[0], img.size[1])
            state = M["occ"].classify(rstatus, in_img, occlusion_expected=False)
            ev["occlusion_states"] = {job["garment_id"]: state}
        else:
            box, state = None, "UNDETERMINED"
            ev["occlusion_states"] = {job["garment_id"]: state}

        # ---- face/pose identity (vs ORIGINAL person — chain invariant)
        fr = M["face"].face_report(person, img)
        ev["structural"]["face_present"] = fr.get("status") in ("OK",) and fr.get("face") is not None or fr.get("status") == "OK"
        if fr.get("status") == "OK":
            ev["metrics"]["face_aligned_ssim"] = fr["ssim"]["aligned_face_ssim"]
            ev["metrics"]["face_geo_mean_disp"] = fr["geometry_delta"]["mean_normalized_displacement"]
            ev["metrics"]["landmark_mpjpe_norm"] = fr["landmark_displacement"]["landmark_mpjpe_norm"]
            try:
                ev["metrics"]["identity_dinov2_face_cos"] = M["dino"].face_similarity(person, img)["cosine"]
            except Exception as e:
                ev["dinov2_face_error"] = str(e)[:120]
        elif fr.get("status") == "NO_FACE_IN_OUTPUT":
            ev["structural"]["face_present"] = False
        pr = M["pose"].pose_report(person, img)
        ev["structural"]["pose_present"] = pr.get("status") == "OK"
        if pr.get("status") == "OK":
            ev["metrics"]["pose_mpjpe_torso_norm"] = pr["mpjpe_torso_norm_raw"]

        # ---- garment fidelity (region-based)
        if box is not None:
            cb = color_metrics_box(img, box, g)
            ev["metrics"]["garment_delta_e_mean"] = cb["delta_e"]["delta_e_mean"]
            ev["metrics"]["garment_dominant_match"] = cb["dominant"]["match_score"]
            gbox = fixture_garment_box(gpath)
            ev["metrics"]["garment_histogram"] = M["color"].histogram_similarity(img, box, gimg, gbox)["score"]
            lc = M["color"].region_delta_e_lightness_conditioned(img, box, gimg, gbox)
            ev["metrics"]["garment_delta_e_lc_mean"] = lc["delta_e_lc_mean"]
            ev["metrics"]["garment_lightness_offset"] = lc["lightness_offset_dL"]
            ev["metrics"]["garment_lightness_residual_std"] = lc["lightness_residual_std"]
            tex = M["tex"].texture_report(img, box, expected_period(g))
            ev["metrics"]["texture_edge_density"] = tex["edge"]["edge_density"]
            if "period_check" in tex:
                ev["metrics"]["texture_period_ok"] = 1.0 if tex["period_check"]["period_ok"] else 0.0
            ev["metrics"]["dinov2_garment_cos"] = M["dino"].similarity_report(gimg, gbox, img, box)["cosine"]
            ev["artifacts"] = {
                "edge_anomaly": M["artifacts"].edge_anomaly(img, box, gimg, gbox),
                "blockiness": M["artifacts"].blockiness(img, box),
            }
            if g.get("has_text"):
                ev["metrics"]["ocr_text_score"] = M["ocr"].text_fidelity(g["expected_text"], img, box,
                                                                         occluded=(state in ("PARTIALLY_VISIBLE", "OCCLUDED_VERIFIED")))["score"]
            if g.get("has_logo"):
                # logo is non-text; DINOv2 + texture edge serve as proxy (documented)
                ev["metrics"]["logo_proxy_note"] = "logo=shape; covered by dinov2+edge (no invented detector)"
        fb = M["artifacts"].face_blur(img)
        if fb:
            ev["artifacts"]["face_blur"] = fb
        results.append(ev)
        print(f"evaluated {ev['sample_id']} state={state}", flush=True)

    out = {"run_id": run_id, "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "n_samples": len(results), "samples": results,
           "note": "thresholds UNFROZEN — evidence only; candidate operating points applied in calibrate.py"}
    p = RESULTS / f"{run_id}_offline_eval.json"
    p.write_text(json.dumps(out, indent=1))
    print(f"WROTE {p} n={len(results)}")
    return out


def color_metrics_box(img, box, g):
    return M["color"].garment_color_report(img, box, [g["dominant_color"]])


if __name__ == "__main__":
    import sys
    run_id = sys.argv[1] if len(sys.argv) > 1 else "baseline-20260915"
    evaluate_run(run_id)
