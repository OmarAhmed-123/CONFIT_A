"""Calibration analysis (Phase 0.5 §21).

Computes, per metric, over {known-good baseline samples} vs {known-bad
constructed samples}:
  - distributions: n, mean, std, min, p50, p95, max (good & bad)
  - AUC (direction-aware)
  - FPR / FNR at a grid of CANDIDATE operating points (thresholds UNFROZEN —
    these are operating-point characterizations, not frozen gates)
  - best-F1 candidate point + the FPR<=5% / FNR<=15% target-feasibility region
  - per-arm (category) stability on known-good: std across arms
  - Spearman correlation vs human scores when human_ratings.json exists
    (PENDING raters; field is reserved)

Writes results/calibration.json + calibration_metrics.csv.
"""
from __future__ import annotations

import csv
import json
import math
import time
from pathlib import Path

import numpy as np

EVAL_ROOT = Path(__file__).resolve().parent.parent
RESULTS = EVAL_ROOT / "results"

# metric direction: "high_good" = higher value means more like good
DIRECTION = {
    "identity_dinov2_face_cos": "high_good",
    "face_aligned_ssim": "high_good",
    "face_geo_mean_disp": "low_good",
    "landmark_mpjpe_norm": "low_good",
    "pose_mpjpe_torso_norm": "low_good",
    "garment_delta_e_mean": "low_good",
    "garment_delta_e_lc_mean": "low_good",
    "garment_lightness_residual_std": "low_good",
    # garment_lightness_offset is diagnostic-only (signed dL magnitude is a
    # relighting characteristic, not a defect signal) — excluded from gates.
    "garment_dominant_match": "high_good",
    "garment_histogram": "high_good",
    "texture_period_ok": "high_good",
    "dinov2_garment_cos": "high_good",
    "ocr_text_score": "high_good",
}


def _stats(vals: list[float]) -> dict:
    a = np.array(vals, dtype=float)
    return {
        "n": int(len(a)),
        "mean": round(float(a.mean()), 4),
        "std": round(float(a.std(ddof=1)), 4) if len(a) > 1 else 0.0,
        "min": round(float(a.min()), 4),
        "p50": round(float(np.percentile(a, 50)), 4),
        "p95": round(float(np.percentile(a, 95)), 4),
        "max": round(float(a.max()), 4),
    }


def _auc(scores_good: list[float], scores_bad: list[float]) -> float | None:
    """Rank-based AUC (Mann-Whitney U) with ties handled; 1.0 = perfect."""
    g = np.array(scores_good, dtype=float)
    b = np.array(scores_bad, dtype=float)
    if len(g) == 0 or len(b) == 0:
        return None
    allv = np.concatenate([g, b])
    ranks = _rankdata(allv)
    rg = ranks[:len(g)].sum()
    u = rg - len(g) * (len(g) + 1) / 2.0
    return float(u / (len(g) * len(b)))


def _rankdata(v: np.ndarray) -> np.ndarray:
    order = np.argsort(v, kind="mergesort")
    ranks = np.empty(len(v), dtype=float)
    i = 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def _fpr_fnr_at(scores_good, scores_bad, t: float, high_good: bool):
    """predict BAD if (high_good and s < t) or (low_good and s > t)."""
    def pred_bad(s):
        return s < t if high_good else s > t
    fp = sum(1 for s in scores_good if pred_bad(s))
    fn = sum(1 for s in scores_bad if not pred_bad(s))
    return (fp / len(scores_good)) if scores_good else None, (fn / len(scores_bad)) if scores_bad else None


def _spearman(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3:
        return None
    rx, ry = _rankdata(np.array(x)), _rankdata(np.array(y))
    mx, my = rx.mean(), ry.mean()
    cov = ((rx - mx) * (ry - my)).sum()
    den = math.sqrt(((rx - mx) ** 2).sum() * ((ry - my) ** 2).sum())
    return float(cov / den) if den > 0 else None


def main():
    off = json.loads((RESULTS / "baseline-20260915_offline_eval.json").read_text())
    kb_manifest = json.loads((RESULTS / "known_bad" / "manifest.json").read_text())
    good = [s for s in off["samples"] if s["structural"].get("face_present")]
    # known-bad: run the same metric extraction over KB images (imported on the fly)
    import sys
    sys.path.insert(0, str(EVAL_ROOT))
    bad = _extract_known_bad()

    human = None
    hp = RESULTS / "human_ratings.json"
    if hp.exists():
        human = json.loads(hp.read_text())

    metrics = {}
    for key, direction in DIRECTION.items():
        g_scores = [s["metrics"][key] for s in good if key in s["metrics"] and s["metrics"][key] is not None]
        b_scores = [s["metrics"][key] for s in bad if key in s.get("metrics", {}) and s["metrics"][key] is not None]
        if len(g_scores) < 2 or len(b_scores) < 1:
            metrics[key] = {"status": "INSUFFICIENT_DATA", "good": _stats(g_scores) if g_scores else None,
                            "bad": _stats(b_scores) if b_scores else None}
            continue
        # grid of candidate operating points: percentiles of combined distribution
        allv = np.array(g_scores + b_scores)
        grid = np.percentile(allv, [5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 75, 80, 85, 90, 95])
        high_good = direction == "high_good"
        ops = []
        best = None
        for t in grid:
            fpr, fnr = _fpr_fnr_at(g_scores, b_scores, float(t), high_good)
            tp_rate = 1 - fnr
            f1 = (2 * tp_rate * (1 - fpr) / (tp_rate + (1 - fpr) + 1e-12)) if (tp_rate + (1 - fpr)) > 0 else 0.0
            ops.append({"candidate_threshold": round(float(t), 4),
                        "FPR": round(fpr, 4), "FNR": round(fnr, 4),
                        "TPR": round(tp_rate, 4), "F1": round(f1, 4),
                        "meets_FPR_le_5pct": fpr <= 0.05, "meets_FNR_le_15pct": fnr <= 0.15})
        ops.sort(key=lambda d: -d["F1"])
        feasible = [o for o in ops if o["meets_FPR_le_5pct"] and o["meets_FNR_le_15pct"]]
        # per-arm stability on good
        arms = {}
        for s in good:
            if key in s["metrics"] and s["metrics"][key] is not None:
                arms.setdefault(s["arm"], []).append(s["metrics"][key])
        stability = {a: {"n": len(v), "std": round(float(np.std(v, ddof=1)), 4) if len(v) > 1 else 0.0}
                     for a, v in arms.items()}
        m = {
            "direction": direction,
            "good": _stats(g_scores),
            "bad": _stats(b_scores),
            "auc": _auc(g_scores, b_scores),
            "candidate_operating_points": ops,
            "best_F1_point": ops[0],
            "target_feasible_points": feasible,
            "arm_stability": stability,
        }
        if human is not None and key in human.get("correlation_inputs", {}):
            m["spearman_vs_human"] = _spearman(
                human["correlation_inputs"][key]["scores"],
                human["correlation_inputs"][key]["human_mean"])
        metrics[key] = m

    out = {
        "calibrated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "known_good_n": len(good),
        "known_bad_n": len(bad),
        "known_bad_labels": kb_manifest.get("known_bad_ids", []),
        "human_ratings": "PENDING (raters required)" if human is None else "present",
        "note": "ALL thresholds UNFROZEN. candidate_operating_points are operating-point characterizations only.",
        "metrics": metrics,
    }
    p = RESULTS / "calibration.json"
    p.write_text(json.dumps(out, indent=1))
    with open(RESULTS / "calibration_metrics.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "direction", "good_n", "good_mean", "good_std", "bad_mean", "bad_std",
                    "auc", "best_F1_threshold", "best_F1", "best_F1_FPR", "best_F1_FNR",
                    "n_feasible_target_points"])
        for k, m in metrics.items():
            if m.get("status") == "INSUFFICIENT_DATA":
                w.writerow([k, DIRECTION[k], m["good"]["n"] if m["good"] else 0, "", "",
                            m["bad"]["n"] if m["bad"] else 0, "", "INSUFFICIENT_DATA", "", "", "", ""])
            else:
                bf = m["best_F1_point"]
                w.writerow([k, m["direction"], m["good"]["n"], m["good"]["mean"], m["good"]["std"],
                            m["bad"]["mean"], m["bad"]["std"], m["auc"], bf["candidate_threshold"],
                            bf["F1"], bf["FPR"], bf["FNR"], len(m["target_feasible_points"])])
    print(f"WROTE {p} + calibration_metrics.csv (good={len(good)}, bad={len(bad)})")


def _extract_known_bad() -> list[dict]:
    """Run metric extraction over known-bad composites vs their source person.

    Each KB sample's metrics are computed the same way as baseline samples:
    face/pose vs ORIGINAL person; garment color/texture/OCR/dino vs the garment
    the sample CLAIMS to be (its source job's garment) — so a defect should move
    at least the metric family it corrupts.
    """
    import sys
    sys.path.insert(0, str(EVAL_ROOT))
    from PIL import Image
    from harness import run_offline_eval as roe
    import importlib
    importlib.reload(roe)
    M = roe.M
    rec = json.loads((RESULTS / "baseline_runs.json").read_text())
    jobs = {f"{j['outfit_id']}/L{j['order']}-{j['garment_id']}": j for j in rec["jobs"] if j.get("http") == 200}
    kbdir = RESULTS / "known_bad"
    out = []
    for p in sorted(kbdir.glob("KB*.jpg")):
        meta = json.loads((kbdir / (p.stem + ".json")).read_text())
        src = meta["source_output"]
        j = jobs.get(src)
        if not j:
            continue
        img = Image.open(p).convert("RGB")
        person = Image.open(EVAL_ROOT / "fixtures" / "persons" / f"{j['person_id']}.jpg").convert("RGB")
        gmanifest = {g["garment_id"]: g for g in json.loads((EVAL_ROOT / "fixtures" / "garment_manifest.json").read_text())}
        g = gmanifest[j["garment_id"]]
        gimg = Image.open(EVAL_ROOT / "fixtures" / "garments" / f"{g['garment_id']}.jpg").convert("RGB")
        ev = {"sample_id": meta["kb_id"], "arm": "KNOWN_BAD", "garment_id": j["garment_id"],
              "person_id": j["person_id"], "label": meta["label"],
              "metrics": {}, "structural": {"face_present": True}}
        fr = M["face"].face_report(person, img)
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
            ev["metrics"]["face_aligned_ssim"] = 0.0
        pr = M["pose"].pose_report(person, img)
        if pr.get("status") == "OK" and pr.get("mpjpe_torso_norm_raw") is not None:
            ev["metrics"]["pose_mpjpe_torso_norm"] = pr["mpjpe_torso_norm_raw"]
        region, rstatus = M["regions"].regions_from_pose(img, j["slot"])
        if rstatus == "OK":
            box = region["primary"]
            cb = roe.color_metrics_box(img, box, g)
            ev["metrics"]["garment_delta_e_mean"] = cb["delta_e"]["delta_e_mean"]
            ev["metrics"]["garment_dominant_match"] = cb["dominant"]["match_score"]
            gbox = roe.fixture_garment_box(EVAL_ROOT / "fixtures" / "garments" / f"{g['garment_id']}.jpg")
            ev["metrics"]["garment_histogram"] = M["color"].histogram_similarity(img, box, gimg, gbox)["score"]
            lc = M["color"].region_delta_e_lightness_conditioned(img, box, gimg, gbox)
            ev["metrics"]["garment_delta_e_lc_mean"] = lc["delta_e_lc_mean"]
            ev["metrics"]["garment_lightness_offset"] = lc["lightness_offset_dL"]
            ev["metrics"]["garment_lightness_residual_std"] = lc["lightness_residual_std"]
            tex = M["tex"].texture_report(img, box, roe.expected_period(g))
            if "period_check" in tex:
                ev["metrics"]["texture_period_ok"] = 1.0 if tex["period_check"]["period_ok"] else 0.0
            try:
                ev["metrics"]["dinov2_garment_cos"] = M["dino"].similarity_report(gimg, gbox, img, box)["cosine"]
            except Exception as e:
                ev["dinov2_error"] = str(e)[:120]
            if g.get("has_text"):
                ev["metrics"]["ocr_text_score"] = M["ocr"].text_fidelity(g["expected_text"], img, box,
                                                                         occluded=False)["score"]
        out.append(ev)
        print(f"  KB metrics: {meta['kb_id']} {meta['label']}", flush=True)
    return out


if __name__ == "__main__":
    main()
