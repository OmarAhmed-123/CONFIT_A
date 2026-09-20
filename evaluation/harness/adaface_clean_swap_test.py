"""Phase 1 §5 — AdaFace clean-swap detection test (evaluation-only).

Question: does a strong, properly aligned face-recognition embedding detect
the clean identity swap (KB04) that DINOv2 face-cosine was blind to?
Sets: 54 good (person vs its VTON output) + 13 known-bad (source person vs
bad output), from the frozen Phase 0.5 calibration sets.

Outputs evaluation/results/adaface_clean_swap_test.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from vton_metrics.adaface_eval import identity_cosine  # noqa: E402

RESULTS = Path(__file__).resolve().parents[1] / "results"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def load_pairs():
    d = json.load(open(RESULTS / "baseline-20260915_offline_eval.json"))
    good = []
    for s in d["samples"]:
        person = s["person_id"]
        out = RESULTS / s["output"].replace("results/", "")
        dinov2 = s.get("metrics", {}).get("identity_dinov2_face_cos", None)
        good.append({
            "id": s["sample_id"], "person": person,
            "ref": str(FIXTURES / "persons" / f"{person}.jpg"),
            "out": str(out), "dinov2_face_cos": dinov2,
        })
    kb = []
    for f in sorted((RESULTS / "known_bad").glob("KB*.json")):
        case = json.load(open(f))
        src = case["source_output"]  # e.g. "S_g004/L1-g004"
        base = src.split("/")[0]
        person = next(s["person_id"] for s in d["samples"] if s["sample_id"].startswith(base))
        dinov2 = next((s.get("metrics", {}).get("identity_dinov2_face_cos")
                       for s in d["samples"] if s["sample_id"] == src), None)
        kb.append({
            "id": case["kb_id"], "label": case["label"], "description": case["description"],
            "person": person, "ref": str(FIXTURES / "persons" / f"{person}.jpg"),
            "out": str(RESULTS / "known_bad" / (case["kb_id"] + ".jpg")),
            "dinov2_face_cos": dinov2,
        })
    return good, kb


def main():
    good, kb = load_pairs()
    for grp in (good, kb):
        for p in grp:
            r = identity_cosine(p["ref"], p["out"])
            p["adaface_cos"] = r["adaface_ir101"].get("cosine")
            p["adaface_status"] = r["adaface_ir101"]["status"]
    G = np.array([p["adaface_cos"] for p in good], dtype=float)
    K = np.array([p["adaface_cos"] for p in kb], dtype=float)
    kb04 = next(p for p in kb if p["id"].startswith("KB04"))

    def auc(pos, neg):
        wins = 0.0
        for a in pos:
            for b in neg:
                wins += 1.0 if a > b else (0.5 if a == b else 0.0)
        return wins / (len(pos) * len(neg))

    report = {
        "test": "adaface_ir101_clean_swap_detection",
        "date": "2026-09-15",
        "license_status": "LICENSE-GATED / RESEARCH-EVALUATION-ONLY (see LICENSE_AUDIT)",
        "n_good": len(good), "n_bad": len(kb),
        "good_cos": {
            "min": float(G.min()), "p05": float(np.percentile(G, 5)),
            "median": float(np.median(G)), "mean": float(G.mean()),
            "max": float(G.max()),
        },
        "bad_cos_per_case": {p["id"]: p["adaface_cos"] for p in kb},
        "kb04_clean_swap_cos": kb04["adaface_cos"],
        "kb04_dinov2_face_cos": kb04["dinov2_face_cos"],
        "kb12_deformed_cos": next(p["adaface_cos"] for p in kb if p["id"].startswith("KB12")),
        "auc_bad_below_good": auc(G, K),
        "operating_points": {
            f"thr={t:.2f}": {
                "FPR": round(float((G < t).mean()), 3),
                "FNR": round(float((K >= t).mean()), 3),
            } for t in (0.25, 0.30, 0.35, 0.40, 0.45, 0.50)
        },
        "samples": good + kb,
    }
    import hashlib
    from vton_metrics.adaface_eval import MODEL_PT
    report["model_sha256"] = hashlib.sha256(MODEL_PT.read_bytes()).hexdigest()
    out = RESULTS / "adaface_clean_swap_test.json"
    out.write_text(json.dumps(report, indent=1))
    print(f"wrote {out}")
    print(json.dumps({k: v for k, v in report.items() if k != "samples"}, indent=1))


if __name__ == "__main__":
    main()
