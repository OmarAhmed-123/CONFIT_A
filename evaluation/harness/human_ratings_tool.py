"""Human rating tool (Phase 0.5 §19).

Console tool for human raters. NOT automated — a human operates it.
Usage:
  python3 evaluation/harness/human_ratings_tool.py --rater R1 \
      --samples "S_g001/L1-g001,KB01_wrong_garment"
For each sample the rater sees image paths (opens them in viewer) and enters
8 dimension scores (0-10) + defect checkboxes.

Output: evaluation/results/human_ratings_raw.json
Schema per entry: {rater_id, sample_id, scores: {D1..D8}, defects: [], notes, rated_at}
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

EVAL_ROOT = Path(__file__).resolve().parent.parent
RESULTS = EVAL_ROOT / "results"
OUTPUTS = RESULTS / "outputs"
KB = RESULTS / "known_bad"
FIX_PERSONS = EVAL_ROOT / "fixtures" / "persons"
FIX_GARMENTS = EVAL_ROOT / "fixtures" / "garments"

DIMS = ["D1_identity", "D2_facial", "D3_garment", "D4_layering",
        "D5_artifacts_inv", "D6_hair", "D7_pose", "D8_realism"]
DEFECTS = ["wrong_garment", "missing_garment", "shifted_garment", "wrong_color",
           "lost_pattern", "lost_text_logo", "face_distortion", "identity_change",
           "hair_change", "pose_change", "layer_order_error", "phantom_garment",
           "partial_layer_drop", "seam_artifacts", "skin_texture_artifacts",
           "limb_artifacts", "other"]


def sample_images(sample_id: str) -> dict[str, Path]:
    if sample_id.startswith("KB"):
        kb = sample_id.replace("/", "_")
        return {"output": KB / f"{kb}.jpg"}
    oid, rest = sample_id.split("/", 1)
    order, gid = rest.split("-", 1)
    return {"output": OUTPUTS / f"{oid}-L{order}-{gid}.jpg"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rater", required=True)
    ap.add_argument("--samples", required=True, help="comma-separated sample ids")
    ap.add_argument("--interactive", action="store_true",
                    help="prompt per-dimension scores in terminal")
    args = ap.parse_args()

    out_path = RESULTS / "human_ratings_raw.json"
    existing = json.loads(out_path.read_text()) if out_path.exists() else {"ratings": []}

    for sid in [s.strip() for s in args.samples.split(",") if s.strip()]:
        imgs = sample_images(sid)
        print(f"\n=== Sample {sid} ===")
        print("Open and study these images, then score:")
        for k, p in imgs.items():
            print(f"  [{k}] {p}")
        if not args.interactive:
            print("  (use --interactive to enter scores in terminal)")
            continue
        scores = {}
        for d in DIMS:
            while True:
                v = input(f"  {d} (0-10, n=not-applicable): ").strip()
                if v in {str(i) for i in range(11)} | {"n"}:
                    scores[d] = None if v == "n" else int(v)
                    break
                print("  invalid; enter 0-10 or n")
        defects = input("  defects (comma-separated from checklist, or 'none'): ").strip()
        defects = [] if defects in ("", "none") else [x.strip() for x in defects.split(",")]
        notes = input("  notes (optional): ").strip()
        entry = {"rater_id": args.rater, "sample_id": sid, "scores": scores,
                 "defects": defects, "notes": notes,
                 "rated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        existing["ratings"].append(entry)
        out_path.write_text(json.dumps(existing, indent=1))
        print("  saved.")
    print(f"\nTotal ratings on file: {len(existing['ratings'])}")


if __name__ == "__main__":
    main()
