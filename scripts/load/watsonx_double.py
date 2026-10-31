"""Local watsonx.ai test double for load tests. NEVER deploy.

Implements just enough of IBM Cloud IAM + watsonx.ai text/chat for the
backend's ``WatsonxClient``:

* ``POST /identity/token``            → IAM token (expires in 1h)
* ``POST /ml/v1/text/chat``           → canned stylist JSON (model echoed back)
* ``POST /ml/v1/deployments/{id}/text/chat`` → same, for deploy-on-demand routing

Knobs (env): ``DOUBLE_LATENCY_MS`` (base simulated inference latency, default
900 — roughly what granite-4-h-small showed live), ``DOUBLE_JITTER_MS``
(default 400), ``DOUBLE_ERROR_RATE`` (0..1 share of 503s, default 0.02),
``DOUBLE_RATE_LIMIT_RATE`` (share of 429s, default 0.0), ``DOUBLE_FAULT_TIMING``
(``after`` = fault after the simulated latency, default; ``before`` = immediate).

The canned answer references wardrobe item ids from the request's closet
list, so the backend's id validation accepts them — it reads the ids out of
the prompt text it was sent (the real model does the same).

Run:  uvicorn scripts.load.watsonx_double:app --port 8089
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="watsonx double")

LAT = float(os.getenv("DOUBLE_LATENCY_MS", "900")) / 1000.0
JIT = float(os.getenv("DOUBLE_JITTER_MS", "400")) / 1000.0
ERR = float(os.getenv("DOUBLE_ERROR_RATE", "0.02"))
RL = float(os.getenv("DOUBLE_RATE_LIMIT_RATE", "0.0"))
# When do injected faults arrive? "after" (default, pessimistic: the fault is
# returned only after the full simulated inference delay, so a retried request
# costs two model latencies) or "before" (gateway-style: 429/503 returned
# immediately, as watsonx's rate limiter was observed to do during live probes).
# Added 2026-10-29 while investigating the p99 miss; the default is unchanged
# so historical runs stay comparable.
FAULT_TIMING = os.getenv("DOUBLE_FAULT_TIMING", "after").strip().lower()

STATS = {"iam": 0, "chat": 0, "errors_injected": 0, "rate_limits_injected": 0}

# Closet records in the user message look like {"wardrobe_item_id": 12, "category": ...}
_ID_RE = re.compile(r'"wardrobe_item_id":\s*(\d{1,9}),\s*"category"')


@app.post("/identity/token")
async def iam_token():
    STATS["iam"] += 1
    return {"access_token": "double-" + uuid.uuid4().hex, "token_type": "Bearer", "expires_in": 3600,
            "expiration": int(time.time()) + 3600}


def _closet_ids(body: dict) -> list[int]:
    parts: list[str] = []
    for m in body.get("messages", []) or []:
        c = m.get("content")
        if isinstance(c, str):
            parts.append(c)
        elif isinstance(c, list):
            parts.extend(str(x.get("text", "")) for x in c if isinstance(x, dict))
    text = "\n".join(parts)
    ids: list[int] = []
    for m in _ID_RE.finditer(text):
        v = int(m.group(1))
        if v not in ids:
            ids.append(v)
    return ids[:6]


def _stylist_payload(ids: list[int]) -> dict:
    roles = ["top", "bottom", "footwear", "outerwear", "accessory", "accessory"]
    return {
        "title": "Double look",
        "summary": "Assembled by the load-test double from the closet it was shown.",
        "items": [{"wardrobe_item_id": i, "role": roles[n % len(roles)], "reason": "Load-test pick."} for n, i in enumerate(ids)],
        "styling_notes": ["This is synthetic output from a test double."],
        "limitations": [],
        "assumptions": [],
    }


async def _chat(request: Request, served_model: str | None):
    STATS["chat"] += 1
    body = await request.json()
    r = random.random()
    if FAULT_TIMING != "before" or r >= RL + ERR:
        await asyncio.sleep(max(0.0, LAT + random.uniform(-JIT, JIT)))
    if r < RL:
        STATS["rate_limits_injected"] += 1
        return JSONResponse({"errors": [{"code": "rate_limit", "message": "double: too many requests"}], "status_code": 429},
                            status_code=429, headers={"Retry-After": "1"})
    if r < RL + ERR:
        STATS["errors_injected"] += 1
        return JSONResponse({"errors": [{"code": "service_unavailable", "message": "double: injected 503"}], "status_code": 503},
                            status_code=503)
    model = served_model or body.get("model_id") or "ibm/granite-4-h-small"
    content = json.dumps(_stylist_payload(_closet_ids(body)))
    return {
        "id": "chatcmpl-" + uuid.uuid4().hex[:12], "object": "chat.completion", "model_id": model, "model": model,
        "created": int(time.time()),
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 600, "completion_tokens": 120, "total_tokens": 720},
    }


@app.post("/ml/v1/text/chat")
async def chat(request: Request):
    return await _chat(request, None)


@app.post("/ml/v1/deployments/{deployment_id}/text/chat")
async def chat_deployment(deployment_id: str, request: Request):
    return await _chat(request, f"ibm/granite-vision-4-1-4b@{deployment_id}")


@app.get("/__stats")
async def stats():
    return STATS
