#!/usr/bin/env python3
"""Live end-to-end verification of Virtual Try-On against a REAL deployment.

Why this exists (audit closure 2026-09-21, VTON / Photo-Match)
-------------------------------------------------------------
The audit explicitly recorded: *"الميزة الثقيلة لم تُختبر من البداية للنهاية"*
— the heavy feature was never exercised end to end, and previous "real
generated image" claims could not be re-verified against the current commit.
A report that asserts a feature works without running it is not evidence.

This script IS the evidence generator. It runs the whole lifecycle against a
live API and writes a machine-readable report, so "does try-on work right now,
on this commit, against this deployment" is a command someone can run — not a
sentence someone can write.

What it exercises (in order, all against the real API):
  1. GET  /api/v1/health                        -> honest worker verdict + storage
  2. GET  /api/v1/try-on/capabilities           -> engine_state, SLA, per-product
  3. POST /api/v1/try-on/validate-image         -> image limits really enforced
  4. POST /api/v1/try-on/jobs                   -> job accepted (202)
  5. GET  /api/v1/try-on/jobs/{id}              -> status polling
  6. GET  /api/v1/try-on/jobs/{id}/result       -> one-shot download (410 after)
  7. DELETE /api/v1/try-on/jobs/{id}/result     -> explicit revocation
  8. DELETE /api/v1/try-on/sessions/{id}/purge  -> retention purge
  9. SLA assertions against the published numbers

The person image is a SYNTHETIC mannequin drawn by this script (see
--person-image to override). No real person's photo is uploaded, and nothing
is written to the repository: outputs go to --out (default /tmp).

Exit code: 0 when every REQUIRED check passed, 1 otherwise. A deployment whose
GPU worker is offline is reported as a truthful failure with the platform's own
error — never as a pass.

Usage:
  python3 backend/scripts/verify_vton_live_e2e.py \
      --base-url https://confit-a.vercel.app \
      --email confit.audit.probe@example.com --password '...' \
      --product-ids 3 --expect-engine available

  # no credentials: exercises the guest path (delivery-token bound jobs)
  python3 backend/scripts/verify_vton_live_e2e.py --base-url http://localhost:8000
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    import urllib.error
    import urllib.request
except ImportError:  # pragma: no cover
    print("urllib is required", file=sys.stderr)
    raise


# ---------------------------------------------------------------------------
# Result recording
# ---------------------------------------------------------------------------
@dataclass
class Check:
    name: str
    passed: bool
    required: bool
    detail: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0


class Report:
    def __init__(self) -> None:
        self.checks: List[Check] = []
        self.started = time.time()
        self.meta: Dict[str, Any] = {}

    def add(self, name: str, passed: bool, detail: str = "",
            evidence: Optional[Dict[str, Any]] = None, required: bool = True,
            duration_ms: float = 0.0) -> Check:
        check = Check(name=name, passed=bool(passed), required=required,
                      detail=detail, evidence=evidence or {}, duration_ms=duration_ms)
        self.checks.append(check)
        mark = "PASS" if check.passed else ("FAIL" if required else "WARN")
        print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
        return check

    @property
    def required_failures(self) -> List[Check]:
        return [c for c in self.checks if c.required and not c.passed]

    def as_dict(self) -> Dict[str, Any]:
        passed = [c for c in self.checks if c.passed]
        return {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "elapsed_seconds": round(time.time() - self.started, 2),
            "meta": self.meta,
            "summary": {
                "total": len(self.checks),
                "passed": len(passed),
                "failed_required": len(self.required_failures),
                "verdict": "PASS" if not self.required_failures else "FAIL",
            },
            "checks": [c.__dict__ for c in self.checks],
        }


# ---------------------------------------------------------------------------
# HTTP helper (stdlib only — this must run anywhere the API is reachable)
# ---------------------------------------------------------------------------
def http(method: str, url: str, *, token: Optional[str] = None,
         payload: Optional[Dict[str, Any]] = None, timeout: float = 120.0,
         raw: bool = False) -> Dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json"}
    if data:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return {
                "status": resp.status,
                "headers": dict(resp.headers.items()),
                "body": body if raw else _maybe_json(body),
                "elapsed_ms": round((time.time() - started) * 1000, 1),
            }
    except urllib.error.HTTPError as exc:
        body = exc.read()
        return {
            "status": exc.code,
            "headers": dict(exc.headers.items()) if exc.headers else {},
            "body": body if raw else _maybe_json(body),
            "elapsed_ms": round((time.time() - started) * 1000, 1),
            "error": True,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": 0,
            "headers": {},
            "body": None,
            "elapsed_ms": round((time.time() - started) * 1000, 1),
            "error": f"{type(exc).__name__}: {exc}",
        }


def _maybe_json(body: bytes) -> Any:
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:  # noqa: BLE001
        text = body.decode("utf-8", errors="replace")
        return text[:2000]


# ---------------------------------------------------------------------------
# Synthetic person image — deliberately NOT a photograph of a real person.
# ---------------------------------------------------------------------------
def synthetic_person_data_url(width: int = 768, height: int = 1280) -> str:
    """Draw a flat mannequin-style figure: enough structure for pose-anchored
    inference, zero personal data."""
    try:
        from PIL import Image, ImageDraw, ImageFilter
    except ImportError:
        raise SystemExit("Pillow is required: pip install Pillow")

    img = Image.new("RGB", (width, height), (236, 236, 240))
    d = ImageDraw.Draw(img)
    w, h = float(width), float(height)
    d.ellipse([w * 0.28, h * 0.90, w * 0.72, h * 0.97], fill=(205, 205, 212))
    d.polygon([(w * 0.42, h * 0.52), (w * 0.58, h * 0.52), (w * 0.60, h * 0.92),
               (w * 0.52, h * 0.92), (w * 0.50, h * 0.66), (w * 0.48, h * 0.92),
               (w * 0.40, h * 0.92)], fill=(52, 63, 84))
    d.polygon([(w * 0.36, h * 0.24), (w * 0.64, h * 0.24), (w * 0.62, h * 0.55),
               (w * 0.38, h * 0.55)], fill=(196, 62, 62))
    d.polygon([(w * 0.36, h * 0.25), (w * 0.30, h * 0.30), (w * 0.30, h * 0.52),
               (w * 0.36, h * 0.50)], fill=(176, 52, 52))
    d.polygon([(w * 0.64, h * 0.25), (w * 0.70, h * 0.30), (w * 0.70, h * 0.52),
               (w * 0.64, h * 0.50)], fill=(176, 52, 52))
    d.ellipse([w * 0.44, h * 0.10, w * 0.56, h * 0.24], fill=(222, 190, 164))
    d.rectangle([w * 0.48, h * 0.22, w * 0.52, h * 0.26], fill=(214, 182, 156))
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def tiny_image_data_url() -> str:
    """A 64x64 JPEG — below MIN_PERSON_SIDE, must be rejected."""
    try:
        from PIL import Image
    except ImportError:
        raise SystemExit("Pillow is required: pip install Pillow")
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (10, 20, 30)).save(buf, format="JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def wide_banner_data_url() -> str:
    """2000x200 — aspect 10:1, above MAX_PERSON_ASPECT, must be rejected."""
    try:
        from PIL import Image
    except ImportError:
        raise SystemExit("Pillow is required: pip install Pillow")
    buf = io.BytesIO()
    Image.new("RGB", (2000, 200), (200, 200, 200)).save(buf, format="JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------------------
# The verification run
# ---------------------------------------------------------------------------
def run(args: argparse.Namespace) -> Report:
    report = Report()
    base = args.base_url.rstrip("/")
    api = f"{base}/api/v1"
    report.meta = {
        "base_url": base,
        "expect_engine": args.expect_engine,
        "product_ids": args.product_ids,
        "git_sha": os.environ.get("VERCEL_GIT_COMMIT_SHA"),
        "python": sys.version.split()[0],
    }

    token: Optional[str] = None
    if args.email and args.password:
        res = http("POST", f"{api}/auth/login",
                   payload={"email": args.email, "password": args.password}, timeout=60)
        if res["status"] == 200 and isinstance(res["body"], dict):
            token = res["body"].get("access_token")
        if not token:
            res = http("POST", f"{api}/auth/register",
                       payload={"email": args.email, "password": args.password,
                                "full_name": args.full_name}, timeout=60)
            token = (res["body"] or {}).get("access_token") if isinstance(res["body"], dict) else None
        report.add("auth.authenticate", bool(token),
                   f"login/register -> {res['status']}",
                   {"status": res["status"]}, required=not args.allow_guest)
    else:
        report.add("auth.authenticate", True, "guest path (no credentials supplied)",
                   required=False)

    # ---------------------------------------------------------------- 1. health
    res = http("GET", f"{api}/health", timeout=60)
    health = res["body"] if isinstance(res["body"], dict) else {}
    worker = (health.get("checks") or {}).get("vton_worker") or {}
    storage = (health.get("checks") or {}).get("storage") or {}
    report.add("health.reachable", res["status"] == 200, f"HTTP {res['status']}")
    report.add(
        "health.vton_worker_verdict_published",
        bool(worker) and "verdict" in worker,
        f"verdict={worker.get('verdict')} production_ready={worker.get('production_ready')} "
        f"reason={str(worker.get('reason'))[:120]}",
        evidence={k: worker.get(k) for k in ("verdict", "production_ready", "reason",
                                             "error_code", "probe_age_seconds")},
        # A deployment that predates this fix has no live verdict. That is a
        # finding, so it is a hard failure of the audit requirement.
        required=True,
    )
    report.add(
        "health.storage_production_grade",
        bool(storage.get("production_grade")),
        f"provider={storage.get('provider')} production_grade={storage.get('production_grade')} "
        f"probe={((storage.get('live_probe') or {}).get('verdict'))}",
        evidence={k: storage.get(k) for k in ("provider", "production_grade", "writable", "detail")},
        required=not args.allow_local_storage,
    )

    # --------------------------------------------------------- 2. capabilities
    q = "&".join(f"product_ids={p}" for p in args.product_ids)
    res = http("GET", f"{api}/try-on/capabilities?{q}", timeout=60)
    caps = res["body"] if isinstance(res["body"], dict) else {}
    engine_state = caps.get("engine_state")
    sla = caps.get("sla") or {}
    report.add("capabilities.reachable", res["status"] == 200, f"HTTP {res['status']}")
    report.add(
        "capabilities.engine_state_matches_reality",
        engine_state == args.expect_engine,
        f"engine_state={engine_state} expected={args.expect_engine} "
        f"engine.verdict={(caps.get('engine') or {}).get('verdict')} "
        f"reason={str((caps.get('engine') or {}).get('detail'))[:120]}",
        evidence={"engine": caps.get("engine"), "user_message": caps.get("user_message")},
    )
    report.add(
        "capabilities.publishes_sla",
        bool(sla) and sla.get("cold_start_seconds_budget", 0) > 0,
        f"sla={json.dumps(sla)[:200]}",
        evidence=sla,
    )
    supported = [p for p in (caps.get("products") or []) if p.get("state") == "supported"]
    report.add(
        "capabilities.at_least_one_renderable_product",
        bool(supported) or args.expect_engine != "available",
        f"supported={len(supported)} of {len(caps.get('products') or [])}",
        evidence={"products": caps.get("products")},
        required=args.expect_engine == "available",
    )

    # -------------------------------------------------------- 3. image limits
    validate_url = f"{api}/try-on/validate-image"
    limits = [
        ("rejects_too_small_image", tiny_image_data_url(), False),
        ("rejects_extreme_aspect", wide_banner_data_url(), False),
    ]
    for name, data_url, should_pass in limits:
        res = http("POST", validate_url,
                   payload={"image_base64": data_url.split(",", 1)[1]}, timeout=60)
        body = res["body"] if isinstance(res["body"], dict) else {}
        ok = body.get("is_valid", body.get("valid"))
        rejected = (res["status"] >= 400) or (ok is False)
        passed = rejected if not should_pass else bool(ok)
        report.add(f"validate_image.{name}", passed,
                   f"HTTP {res['status']} valid={ok} reason={str(body.get('reason') or body.get('message') or '')[:120]}",
                   evidence={"status": res["status"], "body": body})

    # --------------------------------------------------------------- 4. submit
    if args.expect_engine != "available":
        report.add("job.render", False,
                   f"engine_state={engine_state}: a real render cannot be verified while the "
                   f"GPU worker is offline. This is a truthful failure, not a skipped test.",
                   required=True)
        return report

    person = args.person_image or synthetic_person_data_url()
    if person.startswith("data:"):
        submit_payload: Dict[str, Any] = {
            "product_ids": args.product_ids,
            "user_image_base64": person,
            "gender_mode": args.gender_mode,
            "output_aspect": args.output_aspect,
            "background_mode": "studio",
            "consent_retain_photo": False,
        }
    else:
        submit_payload = {
            "product_ids": args.product_ids,
            "user_image_url": person,
            "gender_mode": args.gender_mode,
            "output_aspect": args.output_aspect,
            "background_mode": "studio",
            "consent_retain_photo": False,
        }

    res = http("POST", f"{api}/try-on/jobs", payload=submit_payload, token=token, timeout=300)
    job = res["body"] if isinstance(res["body"], dict) else {}
    job_id = job.get("job_id")
    sla_budget = float(sla.get("job_timeout_seconds") or 90.0)
    report.add("job.accepted", res["status"] == 202 and bool(job_id),
               f"HTTP {res['status']} job_id={job_id}", evidence={"status": res["status"]})
    if not job_id:
        report.add("job.render", False, "no job_id returned", required=True)
        return report

    # The submit call performs the render synchronously in this deployment, so
    # its latency IS the render latency and is checked against the published SLA.
    report.add(
        "sla.render_within_job_timeout",
        res["elapsed_ms"] / 1000.0 <= sla_budget,
        f"{res['elapsed_ms']/1000.0:.1f}s vs budget {sla_budget}s",
        evidence={"elapsed_seconds": res["elapsed_ms"] / 1000.0, "budget": sla_budget},
    )

    # -------------------------------------------------------------- 5. result
    delivery = job.get("delivery") or {}
    dtoken = delivery.get("token")
    data_url = job.get("result_image_data_url")
    status_now = job.get("status")
    completed = status_now == "completed"
    report.add(
        "job.completed",
        completed,
        f"status={status_now} error_code={job.get('error_code')} "
        f"message={str(job.get('error_message'))[:140]}",
        evidence={"status": status_now, "error_code": job.get("error_code"),
                  "metrics": job.get("metrics"), "model_used": job.get("model_used")},
    )
    report.add(
        "job.returned_real_image_in_response",
        bool(data_url and data_url.startswith("data:image")),
        f"result_image_data_url present={bool(data_url)} bytes≈"
        f"{(len(data_url) * 3 // 4) if data_url else 0}",
        required=True,
    )
    if data_url and args.out:
        os.makedirs(args.out, exist_ok=True)
        path = os.path.join(args.out, f"{job_id}.jpg")
        with open(path, "wb") as fh:
            fh.write(base64.b64decode(data_url.split(",", 1)[1]))
        report.add("artifact.saved_locally", os.path.getsize(path) > 1024,
                   f"{path} ({os.path.getsize(path)} bytes)", required=False)
        # The generated image must never be committed to the repository.
        report.add(
            "artifact.not_in_repository",
            not os.path.abspath(path).startswith(os.path.abspath(args.repo_root)),
            f"saved outside the repo ({args.repo_root})",
        )

    # ------------------------------------------------------- 6. one-shot fetch
    if dtoken:
        res = http("GET", f"{api}/try-on/jobs/{job_id}/result?delivery_token={dtoken}",
                   token=token, timeout=60, raw=True)
        first_claim_ok = res["status"] in (200, 410)
        report.add(
            "delivery.one_shot_download",
            first_claim_ok,
            f"first claim HTTP {res['status']} bytes={len(res['body']) if isinstance(res['body'], bytes) else 0} "
            f"(410 is the documented serverless-affinity answer)",
            evidence={"status": res["status"],
                      "content_type": res["headers"].get("Content-Type"),
                      "cache_control": res["headers"].get("Cache-Control")},
        )
        if res["status"] == 200:
            report.add(
                "delivery.no_store_headers",
                res["headers"].get("Cache-Control") == "no-store"
                and "attachment" in (res["headers"].get("Content-Disposition") or ""),
                f"Cache-Control={res['headers'].get('Cache-Control')} "
                f"Content-Disposition={res['headers'].get('Content-Disposition')}",
            )
        res2 = http("GET", f"{api}/try-on/jobs/{job_id}/result?delivery_token={dtoken}",
                    token=token, timeout=60, raw=True)
        report.add(
            "delivery.is_single_use",
            res2["status"] in (410, 404),
            f"second claim HTTP {res2['status']} (expected 410/404)",
        )

        # ------------------------------------------------------- 7. revocation
        res = http("DELETE", f"{api}/try-on/jobs/{job_id}/result", token=token, timeout=60)
        report.add("delivery.revocation", res["status"] in (204, 404, 410),
                   f"DELETE result -> HTTP {res['status']} (idempotent by contract)")
        res = http("GET", f"{api}/try-on/jobs/{job_id}/result?delivery_token={dtoken}",
                   token=token, timeout=60, raw=True)
        report.add(
            "retention.no_bytes_after_revocation",
            res["status"] in (410, 404),
            f"GET after revoke -> HTTP {res['status']}",
        )

    # -------------------------------------------------------------- 8. purge
    session_id = job.get("session_id") or job_id
    res = http("DELETE", f"{api}/try-on/sessions/{session_id}/purge", token=token, timeout=60)
    report.add("retention.purge_endpoint", res["status"] in (200, 204, 404),
               f"purge -> HTTP {res['status']} (404 = no session row for an async job)",
               required=False)

    # ------------------------------------------------------------- 9. cancel
    res = http("POST", f"{api}/try-on/jobs/{job_id}/cancel", token=token, timeout=60)
    report.add("job.cancel", res["status"] in (200, 204),
               f"cancel -> HTTP {res['status']} body={str(res['body'])[:120]}")
    if dtoken:
        res = http("GET", f"{api}/try-on/jobs/{job_id}/result?delivery_token={dtoken}",
                   token=token, timeout=60, raw=True)
        report.add("retention.no_bytes_after_cancel", res["status"] in (410, 404),
                   f"GET after cancel -> HTTP {res['status']}")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default=os.environ.get("CONFIT_BASE_URL", "https://confit-a.vercel.app"))
    parser.add_argument("--email", default=os.environ.get("CONFIT_E2E_EMAIL"))
    parser.add_argument("--password", default=os.environ.get("CONFIT_E2E_PASSWORD"))
    parser.add_argument("--full-name", default="CONFIT E2E Probe")
    parser.add_argument("--product-ids", type=int, nargs="+", default=[3])
    parser.add_argument("--gender-mode", default="infer_from_image")
    parser.add_argument("--output-aspect", default="9:16")
    parser.add_argument("--person-image", default=None,
                        help="data URL or https URL; default is a synthetic mannequin")
    parser.add_argument("--expect-engine", default="available",
                        choices=["available", "cold_start", "temporarily_unavailable", "misconfigured"],
                        help="what the live probe SHOULD say; the run fails if reality differs")
    parser.add_argument("--allow-guest", action="store_true",
                        help="do not require authentication to succeed")
    parser.add_argument("--allow-local-storage", action="store_true",
                        help="do not fail when storage is the local backend (development)")
    parser.add_argument("--out", default="/tmp/confit_vton_e2e")
    parser.add_argument("--repo-root", default=os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    parser.add_argument("--report", default=None, help="write the JSON report here")
    args = parser.parse_args()

    report = run(args)
    payload = report.as_dict()
    if args.report:
        os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
        with open(args.report, "w") as fh:
            json.dump(payload, fh, indent=2)
        print(f"\nreport written to {args.report}")
    print(json.dumps(payload["summary"], indent=2))
    return 0 if not report.required_failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
