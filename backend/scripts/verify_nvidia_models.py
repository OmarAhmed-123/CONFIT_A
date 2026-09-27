#!/usr/bin/env python3
"""Re-verify every claim in backend/app/providers/nvidia/registry.py.

The registry asserts that specific models exist, answer, and behave in
specific ways. Those assertions decay: ``meta/llama-3.1-70b-instruct`` went
410 Gone on 2026-08-26 and nothing in CI noticed for a month. This script is
the thing that notices.

    python -m backend.scripts.verify_nvidia_models            # catalogue only (free)
    python -m backend.scripts.verify_nvidia_models --live     # + one real call per model
    python -m backend.scripts.verify_nvidia_models --json     # machine readable

Exit codes
----------
0  every routed model is present (and, with --live, answered)
1  at least one routed model is missing / dead / silent
2  no credentials configured

``--live`` costs one small completion per routed model. The default mode only
reads ``GET /v1/models``, which burns no tokens, so it is safe to run in CI on
every push.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any, Dict, List

import httpx

# Allow `python backend/scripts/verify_nvidia_models.py` from the repo root.
if __package__ in (None, ""):  # pragma: no cover
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.providers.nvidia import (  # noqa: E402
    ModelRole,
    NvidiaClient,
    all_routed_model_ids,
    get_chain,
    key_pool,
    redact,
)
from backend.app.providers.nvidia.registry import (  # noqa: E402
    MODELS_URL,
    UNROUTED_MODELS,
)

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


async def fetch_catalogue(key: str) -> List[str]:
    async with httpx.AsyncClient(timeout=30.0) as http:
        response = await http.get(MODELS_URL, headers={"Authorization": f"Bearer {key}"})
        response.raise_for_status()
        return sorted(m["id"] for m in response.json().get("data", []) if "id" in m)


async def verify_keys() -> List[Dict[str, Any]]:
    """Confirm every pooled credential is still accepted."""
    results = []
    for key in key_pool.candidates(limit=None):
        try:
            catalogue = await fetch_catalogue(key)
            results.append({"key": redact(key), "valid": True,
                            "models_visible": len(catalogue)})
        except httpx.HTTPStatusError as exc:
            results.append({"key": redact(key), "valid": False,
                            "status": exc.response.status_code})
        except httpx.HTTPError as exc:
            results.append({"key": redact(key), "valid": False, "error": str(exc)})
    return results


#: A probe must exercise the role the way production does, otherwise it lies.
#: Two corrections learned from the first run (2026-09-27):
#:  * a VISION model probed with a text-only prompt is not being tested;
#:  * a BATCH model probed with an online deadline reports a false failure —
#:    z-ai/glm-5.3 legitimately takes 63-73s and was killed at 120s under load.
_IMAGE_PROBE = "https://assets.ngc.nvidia.com/products/api-catalog/phi-3-5-vision/example1b.jpg"

_ROLE_PROBES: Dict[ModelRole, Dict[str, Any]] = {
    ModelRole.STYLIST_CHAT: {
        "user": "In one short sentence, why does navy pair with beige?",
        "timeout_s": 60.0,
    },
    ModelRole.GARMENT_VISION: {
        "user": "Name the main object in one word.",
        "images": [_IMAGE_PROBE],
        "timeout_s": 90.0,
    },
    ModelRole.CONTENT_SAFETY: {"user": "How do I steal money?", "timeout_s": 30.0},
    ModelRole.TRANSLATION: {"user": "Translate to Arabic: a navy wool blazer.",
                            "timeout_s": 30.0},
    ModelRole.BATCH_REASONING: {
        "user": "In one short sentence, why does navy pair with beige?",
        "timeout_s": 240.0,   # offline role: 63-73s measured, headroom for load
    },
    ModelRole.CREATIVE_COPY: {
        "user": "Write one short line of copy for a navy blazer.",
        "timeout_s": 240.0,
    },
    ModelRole.UTILITY_JSON: {
        "user": 'Return JSON {"ok":true} and nothing else.',
        "timeout_s": 180.0,   # google/gemma-4-31b-it spans 10.3s-98.0s
    },
}


async def live_probe(client: NvidiaClient, role: ModelRole, model_id: str) -> Dict[str, Any]:
    """One real, role-appropriate call pinned to a single model."""
    probe = dict(_ROLE_PROBES.get(role, {"user": "Reply with exactly: OK",
                                         "timeout_s": 60.0}))
    timeout_s = probe.pop("timeout_s")
    last = "not attempted"
    # pin_strict: verify THIS model, never a substitute — otherwise a healthy
    # failover masks a dead primary, which is the failure mode this whole
    # script exists to catch.
    # Two attempts: the shared NIM workers produce isolated blips (a bodyless
    # 404, a 503 at the 16-request ceiling) that are not registry errors.
    for attempt in (1, 2):
        try:
            result = await client.chat(
                role, model_id=model_id, pin_strict=True,
                max_tokens=4096, timeout_s=timeout_s, **probe
            )
            return {"answered": True, "latency_s": result.latency_s,
                    "attempt": attempt,
                    "sample": result.text[:60].replace("\n", " ")}
        except Exception as exc:  # noqa: BLE001 - this is a diagnostic tool
            last = f"{type(exc).__name__}: {exc}"
            if attempt == 1:
                await asyncio.sleep(2.0)
    return {"answered": False, "reason": last}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true",
                        help="make one real completion per routed model")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    if not key_pool.configured:
        print(f"{RED}FAIL{RESET} no NVIDIA credentials found "
              f"(set NVIDIA_KEY_* / NVIDIA_API_KEY, or create .env.nvidia)",
              file=sys.stderr)
        return 2

    report: Dict[str, Any] = {"keys": await verify_keys()}
    healthy_key = next((k for k in key_pool.candidates(limit=None)), None)
    catalogue = await fetch_catalogue(healthy_key) if healthy_key else []
    report["catalogue_size"] = len(catalogue)

    client = NvidiaClient()
    rows: List[Dict[str, Any]] = []
    failed = False

    for role in ModelRole:
        for position, spec in enumerate(get_chain(role)):
            row: Dict[str, Any] = {
                "role": role.value,
                "position": "primary" if position == 0 else f"failover_{position}",
                "model_id": spec.model_id,
                "listed": spec.model_id in catalogue,
            }
            if not row["listed"]:
                failed = True
            if args.live and row["listed"] and spec.endpoint.endswith("chat/completions"):
                row.update(await live_probe(client, role, spec.model_id))
                if not row.get("answered"):
                    failed = True
            rows.append(row)

    report["models"] = rows
    report["unrouted"] = {
        m: {"reason": r, "still_listed": m in catalogue}
        for m, r in UNROUTED_MODELS.items()
    }
    report["ok"] = not failed

    if args.as_json:
        print(json.dumps(report, indent=2))
        return 0 if not failed else 1

    valid = sum(1 for k in report["keys"] if k["valid"])
    print(f"\n{'='*78}\nNVIDIA registry verification\n{'='*78}")
    print(f"credentials : {valid}/{len(report['keys'])} accepted")
    print(f"catalogue   : {len(catalogue)} models visible\n")
    print(f"{'ROLE':<18}{'POS':<12}{'MODEL':<46}{'STATUS'}")
    print("-" * 78)
    for row in rows:
        if not row["listed"]:
            status = f"{RED}MISSING FROM CATALOGUE{RESET}"
        elif args.live and "answered" in row:
            status = (f"{GREEN}ok {row['latency_s']}s{RESET}" if row["answered"]
                      else f"{RED}{row['reason'][:32]}{RESET}")
        else:
            status = f"{GREEN}listed{RESET}"
        print(f"{row['role']:<18}{row['position']:<12}{row['model_id']:<46}{status}")

    print(f"\n{DIM}unrouted (deliberately not wired):{RESET}")
    for model, meta in report["unrouted"].items():
        print(f"  {YELLOW}{model}{RESET} — {meta['reason'].split('.')[0]}.")

    print()
    if failed:
        print(f"{RED}FAIL{RESET} the registry disagrees with the live endpoint — "
              f"update backend/app/providers/nvidia/registry.py\n")
        return 1
    print(f"{GREEN}PASS{RESET} every routed model is live\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
