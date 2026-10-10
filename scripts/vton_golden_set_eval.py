#!/usr/bin/env python3
"""Golden-set evaluator for the VTON ghost-hands remediation.

Runs a matrix of (person x garment) cases against a DEPLOYED worker and
measures, per case and in aggregate:

  * success rate            — HTTP 200 + verify.PASS
  * ghost-hand rate         — vton_qa.detect_new_skin_blobs on the result
  * face / background drift — vton_qa identity-preservation scores
  * latency                 — wall time per render

The SAME script measures BEFORE (currently deployed worker) and AFTER
(redeployed fix branch), so improvement claims come from measured numbers,
never from eyeballing. Credentials come from the environment ONLY
(VTON_WORKER_ADMIN_TOKEN); nothing secret is ever written to the report.

Usage:
  export VTON_WORKER_PROCESS_URL=https://...-2c912d.modal.run
  export VTON_WORKER_ADMIN_TOKEN=...   # from your local .env, never committed
  python3 scripts/vton_golden_set_eval.py --out reports/golden_BEFORE.json
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
from pathlib import Path

import httpx
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "services" / "vton-worker"))
from vton_qa import background_drift, detect_new_skin_blobs, face_drift  # noqa: E402

DEFAULT_CASES = [
    # label, garment path-or-url, expected photo type (informational)
    ("on-model tuxedo (incident repro)", str(REPO.parent / "uploads/tuxedo_catalog.jpg"), "model"),
    ("flat-lay navy garment", str(REPO / "services/vton-worker/_demo_inputs/garment_navy.png"), "flat-lay"),
]
DEFAULT_PERSON = str(REPO / "services/vton-worker/_demo_inputs/person.png")


def _b64(path_or_url: str) -> str:
    if path_or_url.startswith("http"):
        r = httpx.get(path_or_url, timeout=30, follow_redirects=True)
        r.raise_for_status()
        raw = r.content
    else:
        raw = Path(path_or_url).read_bytes()
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--process-url", default=os.environ.get("VTON_WORKER_PROCESS_URL", ""))
    ap.add_argument("--person", default=DEFAULT_PERSON)
    ap.add_argument("--out", default="reports/golden_set.json")
    ap.add_argument("--seeds-note", default="")
    args = ap.parse_args()

    token = os.environ.get("VTON_WORKER_ADMIN_TOKEN", "")
    if not args.process_url or not token:
        print("VTON_WORKER_PROCESS_URL and VTON_WORKER_ADMIN_TOKEN must be set (env only).", file=sys.stderr)
        return 2

    person_b64 = _b64(args.person)
    person_img = Image.open(io.BytesIO(base64.b64decode(person_b64.split(",", 1)[1])))

    results = []
    for label, garment, expected in DEFAULT_CASES:
        t0 = time.time()
        try:
            resp = httpx.post(
                args.process_url,
                json={
                    "job_id": f"golden_{int(t0)}",
                    "user_image_base64_or_url": person_b64,
                    "garments": [{"slot_type": "upper_outer", "image_base64": _b64(garment)}],
                    "gender_mode": "infer_from_image",
                    "output_aspect": "9:16",
                },
                headers={"X-VTON-Admin": token},
                timeout=180,
            )
            latency = round(time.time() - t0, 1)
            if resp.status_code != 200:
                results.append({"case": label, "expected": expected, "http": resp.status_code,
                                "success": False, "latency_s": latency,
                                "detail": resp.text[:300]})
                continue
            data = resp.json()
            rendered = data["rendered_image_data_url"].split(",", 1)[1]
            rendered_img = Image.open(io.BytesIO(base64.b64decode(rendered))).convert("RGB").resize(person_img.size)
            skin = detect_new_skin_blobs(person_img, rendered_img)
            results.append({
                "case": label, "expected": expected, "http": 200,
                "success": bool((data.get("verify") or {}).get("PASS")),
                "worker_verify_pass": (data.get("verify") or {}).get("PASS"),
                "worker_qa": (data.get("verify") or {}).get("qa"),
                "ghost_skin_blobs_measured": skin["new_skin_blobs"],
                "face_drift_measured": face_drift(person_img, rendered_img),
                "background_drift_measured": background_drift(person_img, rendered_img),
                "latency_s": latency,
            })
        except Exception as e:  # noqa: BLE001
            results.append({"case": label, "expected": expected, "success": False,
                            "latency_s": round(time.time() - t0, 1), "detail": f"{type(e).__name__}: {e}"[:300]})

    n = len(results) or 1
    agg = {
        "success_rate": round(sum(1 for r in results if r.get("success")) / n, 3),
        "ghost_hand_rate": round(
            sum(1 for r in results if r.get("ghost_skin_blobs_measured", 0) > 0) / n, 3
        ),
        "mean_latency_s": round(sum(r.get("latency_s", 0) for r in results) / n, 1),
    }
    out = {"aggregate": agg, "cases": results, "note": args.seeds_note}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2))
    print(json.dumps(agg, indent=2))
    print(f"written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
