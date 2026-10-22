"""Orchestrate a benchmark run over adapters x cases.

Dry-run by default: every result is a non-render unless the adapter's gate is open
AND dry_run is False. Each candidate sees identical inputs and the same seed, so a
real run is reproducible; the exact GPU (or its absence) is recorded in ``env``.
"""

from __future__ import annotations

import datetime
import os
from dataclasses import asdict
from typing import Iterable

from adapters.base import RenderResult, VTONBenchmarkAdapter
from harness.metrics import detect_gpu


def run(
    adapters: Iterable[VTONBenchmarkAdapter],
    manifest_data: dict,
    out_dir: str,
    seed: int = 1234,
    dry_run: bool = True,
) -> dict:
    adapters = list(adapters)
    env = {
        "gpu": detect_gpu(),
        "seed": seed,
        "dry_run": dry_run,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "gpu_enabled": os.environ.get("VTON_BENCH_ENABLE_GPU") == "1",
        "paid_enabled": os.environ.get("VTON_BENCH_ENABLE_PAID") == "1",
    }
    results: list[RenderResult] = []
    for ad in adapters:
        ok, reason = ad.available()
        for case in manifest_data["cases"]:
            if not ok:
                results.append(RenderResult(ad.name, case["id"], is_render=False, error=f"GATED: {reason}"))
            elif dry_run:
                results.append(RenderResult(ad.name, case["id"], is_render=False, error="dry_run (adapter enabled; pass --no-dry-run to render)"))
            else:
                try:
                    ad.warmup()
                    results.append(ad.render(case, out_dir, seed))
                except Exception as exc:  # noqa: BLE001 — a failed render is data, not a crash
                    results.append(RenderResult(ad.name, case["id"], is_render=False, error=f"{type(exc).__name__}: {exc}"))
    return {
        "env": env,
        "adapters": [
            {"name": a.name, "version": a.version, "license": a.license,
             "available": a.available()[0], "reason": a.available()[1]}
            for a in adapters
        ],
        "results": [asdict(r) for r in results],
        "summary": {
            "adapters": len(adapters),
            "cases": len(manifest_data.get("cases", [])),
            "renders": sum(1 for r in results if r.is_render),
            "non_renders": sum(1 for r in results if not r.is_render),
        },
    }
