"""Load test for the wardrobe stylist endpoints (P5).

Two modes — both bounded, neither ever sends uncontrolled traffic to IBM:

* ``--mode mocked`` (default): the backend under test must be running with
  ``WATSONX_URL``/``WATSONX_IAM_URL`` pointed at ``scripts/load/watsonx_double.py``.
  Measures OUR code path (auth, closet load, prompt build, validation,
  persistence) under concurrency with realistic simulated model latency.
* ``--mode live``: a SMALL, sequential-ish probe against real watsonx.ai
  (``--requests`` capped at 12, ``--vus`` capped at 2). Each request costs
  money; the cap is enforced in code, not by convention.

Each virtual user (VU) registers its own account (so the per-token 40/hour
limiter applies per VU exactly as it would in production), uploads a small
closet via the JSON items endpoint, then loops:
  POST /wardrobe/outfit-recommendation → (every 5th) POST /wardrobe/outfits
and finally GET /wardrobe/outfits once.

Targets (pre-defined; see docs/qa/LOAD_TEST_STYLIST.md):
  mocked  : error rate < 1 %, p95 < model_latency + 1.5 s, p99 < model_latency + 3 s, 0 5xx from our code
  live    : error rate 0 %, p95 < 15 s, honest provenance on every answer

Output: a JSON report (``--out``) with throughput, p50/p95/p99 per endpoint,
status histogram, retries observed (from ``fallback_reason``/429s) and the
PASS/FAIL verdict per target.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
import uuid
from collections import Counter, defaultdict
from typing import Any

import httpx

LIVE_MAX_REQUESTS = 12
LIVE_MAX_VUS = 2

CLOSET = [
    {"title": "White Oxford Shirt", "category": "Tops", "subcategory": "Oxford Shirt", "color_name": "White", "color_hex": "#FFFFFF"},
    {"title": "Navy Crew Knit", "category": "Tops", "subcategory": "Knit", "color_name": "Navy", "color_hex": "#1F2A44"},
    {"title": "Stone Chinos", "category": "Bottoms", "subcategory": "Chinos", "color_name": "Beige", "color_hex": "#C9B99A"},
    {"title": "Dark Denim", "category": "Bottoms", "subcategory": "Jeans", "color_name": "Indigo", "color_hex": "#2C3E6B"},
    {"title": "Brown Loafers", "category": "Footwear", "subcategory": "Loafers", "color_name": "Brown", "color_hex": "#5B3A1E"},
    {"title": "White Sneakers", "category": "Footwear", "subcategory": "Sneakers", "color_name": "White", "color_hex": "#F5F5F5"},
    {"title": "Camel Overcoat", "category": "Outerwear", "subcategory": "Overcoat", "color_name": "Camel", "color_hex": "#B98B5E"},
    {"title": "Leather Belt", "category": "Accessories", "subcategory": "Belt", "color_name": "Brown", "color_hex": "#4A2E14"},
]


def pct(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    k = max(0, min(len(s) - 1, round((p / 100.0) * (len(s) - 1))))
    return s[k]


class Collector:
    def __init__(self) -> None:
        self.lat: dict[str, list[float]] = defaultdict(list)
        self.status: dict[str, Counter] = defaultdict(Counter)
        self.sources: Counter = Counter()
        self.fallback_reasons: Counter = Counter()
        self.rejected_refs = 0
        self.errors: list[dict[str, Any]] = []
        self.t0 = time.perf_counter()
        self.t1 = self.t0

    def record(self, ep: str, seconds: float, status: int, body: Any = None) -> None:
        self.lat[ep].append(seconds)
        self.status[ep][status] += 1
        if ep == "recommend" and isinstance(body, dict):
            if "source" in body:
                self.sources[f"{body.get('source')}|ai={body.get('ai_generated')}|{body.get('model_id')}"] += 1
            if body.get("fallback_reason"):
                self.fallback_reasons[str(body["fallback_reason"])[:80]] += 1
            self.rejected_refs += len(body.get("rejected_references") or [])
        if status >= 400 and len(self.errors) < 40:
            self.errors.append({"endpoint": ep, "status": status, "body": (json.dumps(body)[:300] if body is not None else None)})

    def report(self, mode: str, targets: dict[str, float]) -> dict[str, Any]:
        wall = max(1e-6, self.t1 - self.t0)
        total = sum(sum(c.values()) for c in self.status.values())
        failures = sum(n for c in self.status.values() for s, n in c.items() if s >= 500)
        client_4xx = sum(n for c in self.status.values() for s, n in c.items() if 400 <= s < 500)
        rec = self.lat.get("recommend", [])
        out: dict[str, Any] = {
            "mode": mode,
            "wall_seconds": round(wall, 2),
            "requests_total": total,
            "throughput_rps": round(total / wall, 2),
            "server_errors_5xx": failures,
            "client_errors_4xx": client_4xx,
            "error_rate_5xx": round(failures / total, 4) if total else None,
            "per_endpoint": {
                ep: {
                    "n": len(v),
                    "p50_s": round(pct(v, 50), 3), "p95_s": round(pct(v, 95), 3), "p99_s": round(pct(v, 99), 3),
                    "mean_s": round(statistics.fmean(v), 3) if v else None, "max_s": round(max(v), 3) if v else None,
                    "status": dict(sorted(self.status[ep].items())),
                }
                for ep, v in self.lat.items()
            },
            "recommendation_provenance": dict(self.sources),
            "fallback_reasons": dict(self.fallback_reasons),
            "rejected_model_references_total": self.rejected_refs,
            "sample_errors": self.errors,
        }
        verdict = {}
        if rec:
            verdict["p95_recommend_under_target"] = pct(rec, 95) < targets["p95_s"]
            verdict["p99_recommend_under_target"] = pct(rec, 99) < targets["p99_s"]
        verdict["error_rate_under_target"] = (failures / total if total else 0) < targets["error_rate"]
        verdict["no_5xx_from_our_code"] = failures == 0
        out["targets"] = targets
        out["verdict"] = verdict
        out["pass"] = all(verdict.values())
        return out


async def register_users(base: str, n: int, col: Collector) -> list[str]:
    """Registration is rate-limited 5/min per IP in the app (by design). Pace
    sign-ups accordingly so the measured phase starts with every VU signed in;
    this phase is excluded from the timing window."""
    tokens: list[str] = []
    async with httpx.AsyncClient(base_url=base, timeout=30.0) as c:
        for i in range(n):
            for attempt in range(6):
                email = f"load_{uuid.uuid4().hex[:10]}@confit.io"
                r = await c.post("/api/v1/auth/register", json={"email": email, "password": "Password123!", "full_name": f"Load VU {i}"})
                if r.status_code == 201:
                    tokens.append(r.json()["access_token"])
                    break
                if r.status_code == 429:
                    wait = float((r.json().get("error", {}).get("details", {}) or {}).get("retry_after_seconds", 60)) if r.headers.get("content-type", "").startswith("application/json") else 60.0
                    print(f"[setup] registration rate-limited after {len(tokens)} users; sleeping {wait:.0f}s", file=sys.stderr)
                    await asyncio.sleep(wait + 0.5)
                    continue
                col.record("register", 0.0, r.status_code, r.text[:200])
                break
    return tokens


async def vu(idx: int, base: str, n_requests: int, col: Collector, language: str, think_s: float, token: str) -> None:
    async with httpx.AsyncClient(base_url=base, timeout=90.0) as c:
        h = {"Authorization": f"Bearer {token}"}
        for it in CLOSET:
            payload = {**it, "pattern": "Solid", "image_url": f"https://cdn.example.com/{uuid.uuid4().hex}.jpg",
                       "occasions": ["Smart Casual", "Casual"], "seasonality": "All-Season"}
            t = time.perf_counter()
            r = await c.post("/api/v1/wardrobe/items", json=payload, headers=h)
            col.record("add_item", time.perf_counter() - t, r.status_code)
        previous: list[int] = []
        for k in range(n_requests):
            body = {"occasion": ["Smart Casual", "Casual", "Business", "Evening"][k % 4], "time_of_day": "evening",
                    "season": "autumn", "location": "Cairo", "style_preferences": ["relaxed"], "previous_item_ids": previous,
                    "language": language}
            t = time.perf_counter()
            try:
                r = await c.post("/api/v1/wardrobe/outfit-recommendation", json=body, headers=h)
                data = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text
            except httpx.HTTPError as exc:
                col.record("recommend", time.perf_counter() - t, 599, {"transport": str(exc)[:120]})
                continue
            col.record("recommend", time.perf_counter() - t, r.status_code, data)
            if r.status_code == 200 and isinstance(data, dict):
                previous = [i["wardrobe_item_id"] for i in data.get("items", [])][:6]
                if k % 5 == 0 and data.get("items"):
                    save = {
                        "title": data["title"], "occasion": data["occasion"], "summary": data["summary"],
                        "items": [{"wardrobe_item_id": i["wardrobe_item_id"], "reason": i["reason"]} for i in data["items"]],
                        "styling_notes": data.get("styling_notes", []), "limitations": data.get("limitations", []),
                        "missing_categories": data.get("missing_categories", []), "context": data.get("context", {}),
                        "source": data["source"], "ai_generated": data["ai_generated"],
                        "model_id": data.get("model_id"), "prompt_version": data.get("prompt_version"),
                    }
                    t = time.perf_counter()
                    r2 = await c.post("/api/v1/wardrobe/outfits", json=save, headers=h)
                    col.record("save_outfit", time.perf_counter() - t, r2.status_code)
            if think_s:
                await asyncio.sleep(think_s)
        t = time.perf_counter()
        r = await c.get("/api/v1/wardrobe/outfits", headers=h)
        col.record("list_outfits", time.perf_counter() - t, r.status_code)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--mode", choices=["mocked", "live"], default="mocked")
    ap.add_argument("--vus", type=int, default=10)
    ap.add_argument("--requests", type=int, default=20, help="recommendations per VU")
    ap.add_argument("--language", default="en")
    ap.add_argument("--think", type=float, default=0.0, help="seconds between a VU's requests")
    ap.add_argument("--model-latency", type=float, default=0.9, help="expected model latency (s) for target maths")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    if a.mode == "live":
        # Hard caps: a live run is a probe, not a soak. Every request is billed.
        if a.vus * a.requests > LIVE_MAX_REQUESTS or a.vus > LIVE_MAX_VUS:
            print(f"refusing live run: vus*requests must be <= {LIVE_MAX_REQUESTS} and vus <= {LIVE_MAX_VUS}", file=sys.stderr)
            return 2
        targets = {"p95_s": 15.0, "p99_s": 20.0, "error_rate": 0.000001}
    else:
        targets = {"p95_s": a.model_latency + 1.5, "p99_s": a.model_latency + 3.0, "error_rate": 0.01}

    col = Collector()
    tokens = await register_users(a.base, a.vus, col)
    if len(tokens) < a.vus:
        print(f"only {len(tokens)}/{a.vus} users registered", file=sys.stderr)
    col.t0 = time.perf_counter()  # measured window starts once everyone is signed in
    await asyncio.gather(*(vu(i, a.base, a.requests, col, a.language, a.think, tok) for i, tok in enumerate(tokens)))
    col.t1 = time.perf_counter()
    rep = col.report(a.mode, targets)
    rep["config"] = {"vus_signed_in": len(tokens), "vus": a.vus, "requests_per_vu": a.requests, "language": a.language, "think_s": a.think, "base": a.base}
    text = json.dumps(rep, indent=2, ensure_ascii=False)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)
    return 0 if rep["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
