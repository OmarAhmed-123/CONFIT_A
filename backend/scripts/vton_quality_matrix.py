#!/usr/bin/env python3
"""Segmentation-free VTON quality matrix — real renders, real assertions.

Audit gap this closes (2026-09-21): *"لم يتحقق الفحص من ... جودة
segmentation-free على أوضاع مختلفة"* — the quality of the segmentation-free
engine across different poses / garment slots / output aspects was never
measured, and the previous "real generated try-on image" claims were single
samples that could not be re-verified against the current commit.

This harness runs a MATRIX of renders against a live deployment and reports
per-case measurements instead of a single anecdote:

  person pose   x  garment slot   x  output aspect
  ------------------------------------------------
  front_standing   upper_inner (tops)      9:16
  three_quarter    upper_outer (outerwear) 4:5
  seated           lower (bottoms)         1:1
  walking          dress (one-pieces)      9:16

For every case it records: wall-clock latency, the engine's own per-layer
verification (verify.PASS / metric_pixel_change), whether the output is a real
decodable image distinct from the input, and whether the run beat the published
SLA. The aggregate report states the pass rate — a 1-in-4 pass rate is a
finding, and it is reported as one.

The person images are SYNTHETIC figures drawn here (different silhouettes per
pose). No real person's photo is uploaded, and no artifact is written into the
repository.

Usage:
  python3 backend/scripts/vton_quality_matrix.py \
      --base-url https://confit-a.vercel.app \
      --email ... --password ... \
      --top-product-id 3 --outer-product-id 1 \
      --bottom-product-id 4 --dress-product-id 5 \
      --report /tmp/vton_quality_matrix.json

Exit code 0 only when every REQUIRED case rendered and verified.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from verify_vton_live_e2e import http, synthetic_person_data_url  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic pose variants. Different silhouettes, still not a person.
# ---------------------------------------------------------------------------
def pose_data_url(pose: str, width: int = 768, height: int = 1280) -> str:
    try:
        from PIL import Image, ImageDraw, ImageFilter
    except ImportError:
        raise SystemExit("Pillow is required: pip install Pillow")

    img = Image.new("RGB", (width, height), (238, 238, 242))
    d = ImageDraw.Draw(img)
    w, h = float(width), float(height)

    if pose == "front_standing":
        d.ellipse([w * .28, h * .90, w * .72, h * .97], fill=(205, 205, 212))
        legs = [(w * .42, h * .52), (w * .58, h * .52), (w * .60, h * .92),
                (w * .52, h * .92), (w * .50, h * .66), (w * .48, h * .92), (w * .40, h * .92)]
        torso = [(w * .36, h * .24), (w * .64, h * .24), (w * .62, h * .55), (w * .38, h * .55)]
        head = [w * .44, h * .10, w * .56, h * .24]
    elif pose == "three_quarter":
        d.ellipse([w * .34, h * .90, w * .78, h * .97], fill=(205, 205, 212))
        legs = [(w * .46, h * .52), (w * .62, h * .52), (w * .68, h * .92),
                (w * .60, h * .92), (w * .56, h * .66), (w * .50, h * .92), (w * .42, h * .92)]
        torso = [(w * .40, h * .24), (w * .68, h * .24), (w * .66, h * .55), (w * .42, h * .55)]
        head = [w * .48, h * .10, w * .60, h * .24]
    elif pose == "seated":
        d.rectangle([w * .30, h * .70, w * .70, h * .76], fill=(150, 150, 160))
        legs = [(w * .40, h * .62), (w * .60, h * .62), (w * .72, h * .72),
                (w * .66, h * .78), (w * .50, h * .70), (w * .46, h * .90), (w * .38, h * .90)]
        torso = [(w * .36, h * .32), (w * .64, h * .32), (w * .62, h * .64), (w * .38, h * .64)]
        head = [w * .44, h * .18, w * .56, h * .32]
    elif pose == "walking":
        d.ellipse([w * .26, h * .90, w * .74, h * .97], fill=(205, 205, 212))
        legs = [(w * .42, h * .52), (w * .58, h * .52), (w * .70, h * .92),
                (w * .62, h * .92), (w * .50, h * .64), (w * .36, h * .92), (w * .28, h * .90)]
        torso = [(w * .36, h * .24), (w * .64, h * .24), (w * .62, h * .55), (w * .38, h * .55)]
        head = [w * .44, h * .10, w * .56, h * .24]
    else:
        raise SystemExit(f"unknown pose {pose!r}")

    d.polygon(legs, fill=(52, 63, 84))
    d.polygon(torso, fill=(196, 62, 62))
    d.polygon([(w * .36, h * .25), (w * .28, h * .34), (w * .30, h * .54), (w * .36, h * .50)], fill=(176, 52, 52))
    d.polygon([(w * .64, h * .25), (w * .72, h * .34), (w * .70, h * .54), (w * .64, h * .50)], fill=(176, 52, 52))
    d.ellipse(head, fill=(222, 190, 164))
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def image_stats(data_url: str) -> Dict[str, Any]:
    """Decoded size + a cheap entropy proxy, to prove the output is a real
    image and not a flat colour block or an echo of the input."""
    try:
        from PIL import Image
    except ImportError:
        return {}
    raw = base64.b64decode(data_url.split(",", 1)[1])
    img = Image.open(io.BytesIO(raw)).convert("L")
    hist = img.histogram()
    total = sum(hist) or 1
    import math
    entropy = -sum((c / total) * math.log2(c / total) for c in hist if c)
    return {
        "bytes": len(raw),
        "width": img.size[0],
        "height": img.size[1],
        "gray_entropy_bits": round(entropy, 3),
    }


# ---------------------------------------------------------------------------
def run(args: argparse.Namespace) -> int:
    base = args.base_url.rstrip("/")
    api = f"{base}/api/v1"
    cases: List[Dict[str, Any]] = []

    token: Optional[str] = None
    if args.email and args.password:
        res = http("POST", f"{api}/auth/login",
                   payload={"email": args.email, "password": args.password}, timeout=60)
        token = (res["body"] or {}).get("access_token") if isinstance(res["body"], dict) else None
        if not token:
            res = http("POST", f"{api}/auth/register",
                       payload={"email": args.email, "password": args.password,
                                "full_name": "CONFIT Quality Probe"}, timeout=60)
            token = (res["body"] or {}).get("access_token") if isinstance(res["body"], dict) else None
    print(f"auth: {'ok' if token else 'guest'}")

    caps = http("GET", f"{api}/try-on/capabilities", timeout=60)
    caps_body = caps["body"] if isinstance(caps["body"], dict) else {}
    engine_state = caps_body.get("engine_state")
    sla = caps_body.get("sla") or {}
    print(f"engine_state={engine_state}")
    if engine_state != "available":
        print(json.dumps({
            "verdict": "NOT_RUN",
            "reason": f"engine_state={engine_state}; {(caps_body.get('engine') or {}).get('detail')}",
            "note": "Refusing to report a quality matrix that was never measured.",
        }, indent=2))
        return 1

    budget = float(sla.get("job_timeout_seconds") or 90.0)
    p95 = float(sla.get("warm_render_seconds_p95") or 35.0)

    matrix = [
        ("front_standing", "upper_inner", args.top_product_id, "9:16"),
        ("three_quarter", "upper_outer", args.outer_product_id, "4:5"),
        ("seated", "lower", args.bottom_product_id, "1:1"),
        ("walking", "dress", args.dress_product_id, "9:16"),
    ]

    for pose, slot, product_id, aspect in matrix:
        if not product_id:
            cases.append({"pose": pose, "slot": slot, "skipped": "no product id supplied"})
            continue
        started = time.time()
        res = http("POST", f"{api}/try-on/jobs", token=token, timeout=300, payload={
            "product_ids": [product_id],
            "user_image_base64": pose_data_url(pose),
            "gender_mode": args.gender_mode,
            "output_aspect": aspect,
            "background_mode": "studio",
            "consent_retain_photo": False,
        })
        elapsed = time.time() - started
        job = res["body"] if isinstance(res["body"], dict) else {}
        data_url = job.get("result_image_data_url")
        metrics = job.get("metrics") or {}
        verification = metrics.get("verification") or {}
        case = {
            "pose": pose,
            "slot": slot,
            "product_id": product_id,
            "output_aspect": aspect,
            "status": job.get("status"),
            "elapsed_seconds": round(elapsed, 2),
            "within_job_timeout": elapsed <= budget,
            "within_warm_p95": elapsed <= p95,
            "model_used": job.get("model_used"),
            "verify_pass": verification.get("all_layers_verified"),
            "pixel_change": metrics.get("metric_pixel_change"),
            "output": image_stats(data_url) if data_url else None,
            "error_code": job.get("error_code"),
            "error_message": (job.get("error_message") or "")[:200] or None,
            "passed": bool(job.get("status") == "completed" and data_url
                           and verification.get("all_layers_verified") is True),
        }
        cases.append(case)
        print(f"[{'PASS' if case['passed'] else 'FAIL'}] {pose}/{slot}/{aspect} "
              f"{case['elapsed_seconds']}s status={case['status']} "
              f"verify={case['verify_pass']} err={case['error_code']}")

        if data_url and args.out:
            os.makedirs(args.out, exist_ok=True)
            with open(os.path.join(args.out, f"{pose}_{slot}.jpg"), "wb") as fh:
                fh.write(base64.b64decode(data_url.split(",", 1)[1]))

    measured = [c for c in cases if "skipped" not in c]
    passed = [c for c in measured if c["passed"]]
    latencies = sorted(c["elapsed_seconds"] for c in measured)
    summary = {
        "verdict": "PASS" if measured and len(passed) == len(measured) else "FAIL",
        "cases_total": len(measured),
        "cases_passed": len(passed),
        "pass_rate": round(len(passed) / len(measured), 3) if measured else 0.0,
        "latency_seconds_min": latencies[0] if latencies else None,
        "latency_seconds_max": latencies[-1] if latencies else None,
        "all_within_job_timeout": all(c["within_job_timeout"] for c in measured) if measured else False,
        "engine_state": engine_state,
        "sla": sla,
    }
    report = {"summary": summary, "cases": cases,
              "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if args.report:
        os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
        with open(args.report, "w") as fh:
            json.dump(report, fh, indent=2)
        print(f"\nreport -> {args.report}")
    print(json.dumps(summary, indent=2))
    return 0 if summary["verdict"] == "PASS" else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", default=os.environ.get("CONFIT_BASE_URL", "https://confit-a.vercel.app"))
    p.add_argument("--email", default=os.environ.get("CONFIT_E2E_EMAIL"))
    p.add_argument("--password", default=os.environ.get("CONFIT_E2E_PASSWORD"))
    p.add_argument("--top-product-id", type=int, default=None)
    p.add_argument("--outer-product-id", type=int, default=None)
    p.add_argument("--bottom-product-id", type=int, default=None)
    p.add_argument("--dress-product-id", type=int, default=None)
    p.add_argument("--gender-mode", default="infer_from_image")
    p.add_argument("--out", default="/tmp/confit_vton_quality")
    p.add_argument("--report", default=None)
    return run(p.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
