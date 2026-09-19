"""Phase 1 §7 supplement — TRUE short-sleeve control (g011 polo, short sleeves).

The original 'controls' (g001/g002) turned out to be full-length-sleeve flat
lays (fixture defect, see ROOT_CAUSE_LONG_SLEEVE.md), so the control class was
invalid. g011 (light blue polo) is a verified short-sleeve flat lay.
3 jobs: g011 x p001/p007/p010.
Writes results/rootsleeve_control_g011.json + outputs/rootsleeve/RS-g011-*.jpg
"""
from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path

EVAL_ROOT = Path(__file__).resolve().parent.parent
RESULTS = EVAL_ROOT / "results"
OUT_DIR = RESULTS / "outputs" / "rootsleeve"
OUT_DIR.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(EVAL_ROOT))

from harness.rootsleeve_root_cause import data_uri, load_env, load_urls, run_one  # noqa: E402
from vton_metrics.sleeve_metrics import (  # noqa: E402
    arm_coverage, garment_sleeve_drop, _content_box)
from vton_metrics.imaging import dominant_color, to_array  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402


def main():
    env = load_env()
    token = env["VTON_EVAL_ADMIN_TOKEN"]
    urls = load_urls()
    gdir = EVAL_ROOT / "fixtures" / "garments"
    gimg = Image.open(gdir / "g011.jpg").convert("RGB")
    box = _content_box(to_array(gimg))
    crop = gimg if box is None else gimg.crop(box)
    lab = np.array(dominant_color(crop, k=1)[0]["lab"])
    drop = garment_sleeve_drop(gimg)
    rows = []
    for pid in ("p001", "p007", "p010"):
        job_id = f"RS-g011-{pid}-shortcontrol"
        res = run_one(urls["process"], token, job_id,
                      data_uri(EVAL_ROOT / "fixtures" / "persons" / f"{pid}.jpg"),
                      gdir / "g011.jpg", "upper_inner")
        row = {"job_id": job_id, "garment": "g011", "person": pid,
               "kind": "shortcontrol", "http": res["http"], "wall_s": res["wall_s"]}
        b = res["body"]
        if res["http"] == 200 and isinstance(b, dict) and b.get("rendered_image_data_url"):
            import io
            out_b64 = b["rendered_image_data_url"].split(",", 1)[-1]
            outp = OUT_DIR / f"{job_id}.jpg"
            Image.open(io.BytesIO(base64.b64decode(out_b64))).convert("RGB").save(outp, "JPEG", quality=95)
            row["output"] = str(outp.relative_to(EVAL_ROOT))
            row["verify"] = b.get("verify")
            row["pixel_change"] = (b.get("verify") or {}).get("metric_pixel_change")
            cov = arm_coverage(Image.open(f"evaluation/fixtures/persons/{pid}.jpg"),
                               Image.open(outp), lab)
            row["sleeve_drop_ratio"] = drop.get("sleeve_drop_ratio")
            row["arm_overall"] = cov.get("overall")
            row["arms"] = {a: v["verdict"] for a, v in cov.get("arms", {}).items()}
        else:
            row["error"] = str(b)[:200]
        rows.append(row)
        print(f"{job_id} http={res['http']} wall={res['wall_s']}s arm={row.get('arm_overall')}", flush=True)
    out = {"test": "rootsleeve_true_short_sleeve_control", "date": "2026-09-15",
           "garment_sleeve_drop": drop, "jobs": rows}
    p = RESULTS / "rootsleeve_control_g011.json"
    p.write_text(json.dumps(out, indent=1))
    print("WROTE", p)


if __name__ == "__main__":
    main()
