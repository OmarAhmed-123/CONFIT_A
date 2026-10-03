"""Feature 04 — Smart Wardrobe extraction provider (Modal CPU worker client).

Calls the `confit-wardrobe-worker` Modal app (SCHP-ATR-18 garment parsing +
BiRefNet_lite matting, both MIT) and maps its honest response contract onto
the backend's error taxonomy. The worker NEVER fabricates items: regions
below the area threshold come back in ``skipped`` with a reason, and this
provider preserves that honesty instead of padding the item list.

Contract (POST <WARDROBE_WORKER_URL>, header X-VTON-Admin):
  request : {job_id, image_base64_or_url (data: URL|safe https URL), max_items}
  response: {items: [{slot_type, category, label_names, bbox, area_fraction,
                      confidence, cutout_data_url}],
             person_detected, person_labels, skipped: [{label, reason, area?}],
             parse_seconds, matting_seconds, total_seconds, engine, commercial}

Design mirrors the VTON worker shells (tryon_service / telemetry_controller):
shared-secret header, explicit endpoint URLs, honest error codes, and an
``extraction_available=False`` answer (never a fake success) when the feature
is not configured or the worker is unreachable.
"""
from __future__ import annotations

import base64
import binascii
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

import httpx

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.providers.base import BaseProvider

# The worker's slot vocabulary (services/wardrobe-worker/extraction.py
# SLOT_TO_CATEGORY, shared with the VTON engine) -> platform taxonomy
# (wardrobe_taxonomy.WARDROBE_CATEGORIES, BRD §4.1).
WORKER_CATEGORY_TO_PLATFORM = {
    "tops": "Tops",
    "bottoms": "Bottoms",
    "one-pieces": "Dresses",
    "footwear": "Footwear",
    "accessory": "Accessories",
}

_SLOT_TITLES = {
    "upper_outer": "Top",
    "lower": "Bottom",
    "dress": "Dress",
    "footwear": "Footwear",
    "accessory": "Accessory",
}

_KNOWN_SLOTS = set(_SLOT_TITLES)


def slot_title(slot_type: str) -> str:
    """Human title for an extraction slot (used until the per-item vision
    analysis refines it with a real subcategory)."""
    return _SLOT_TITLES.get(slot_type, "Wardrobe Item")


class WardrobeExtractionProvider(BaseProvider):
    """Client for the feature-04 extraction worker on Modal (CPU)."""

    def __init__(self):
        timeout = float(getattr(settings, "WARDROBE_WORKER_TIMEOUT_SECONDS", 180.0) or 180.0)
        # max_retries=1 (BaseProvider counts ATTEMPTS, not retries): exactly
        # one attempt, no blind re-send. An extraction costs tens of
        # CPU-seconds; retrying after a timeout would double the user's wait
        # and the worker's bill for a request that may already be executing.
        # The retry path is the user-visible "analyze again" button, not a
        # hidden re-send.
        super().__init__(name="Wardrobe_Extraction_Provider", timeout_seconds=timeout, max_retries=1)

    # ── public API ───────────────────────────────────────────────────
    def is_configured(self) -> bool:
        return bool(settings.WARDROBE_WORKER_URL and settings.WARDROBE_WORKER_ADMIN_TOKEN)

    async def extract_garments(self, data_url: str, max_items: int = 4) -> Dict[str, Any]:
        """Run SCHP-ATR-18 + BiRefNet_lite extraction on one outfit photo.

        Returns the worker's validated dict, or an honest
        ``{"extraction_available": False, "reason": ...}`` envelope. Never
        raises for infrastructure problems — the caller decides how to
        degrade (per BRD §20 honest failure, no invented items).
        """
        if not self.is_configured():
            return {
                "extraction_available": False,
                "reason": "wardrobe_extraction_not_configured",
            }
        result = await self.execute_with_resilience(self._call_worker, data_url=data_url, max_items=max_items)
        # Error envelopes (timeouts, 401/5xx, bad JSON) are recognisable by
        # their honest flag; the worker's 200 body never carries it.
        if result.get("extraction_available") is False:
            return result
        validated, problem = _validate_worker_response(result)
        if problem:
            logger.error("wardrobe_worker_contract_violation", job_id=result.get("job_id"), problem=problem)
            return {
                "extraction_available": False,
                "reason": "wardrobe_worker_invalid_response",
                "detail": problem,
                "job_id": result.get("job_id"),
            }
        validated["extraction_available"] = True
        validated["job_id"] = result.get("job_id")
        validated["backend_call_seconds"] = result.get("backend_call_seconds")
        return validated

    async def fallback(self, *args, **kwargs) -> Dict[str, Any]:
        """Honest degradation (BaseProvider contract): extraction is a real
        model call or it is unavailable — never a synthesized item list."""
        return {"extraction_available": False, "reason": "wardrobe_extraction_unavailable"}

    # ── internals ────────────────────────────────────────────────────
    async def _call_worker(self, data_url: str, max_items: int) -> Dict[str, Any]:
        job_id = f"imp_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
        headers = {"X-VTON-Admin": settings.WARDROBE_WORKER_ADMIN_TOKEN or ""}
        payload = {
            "job_id": job_id,
            "image_base64_or_url": data_url,
            "max_items": max(1, min(int(max_items), 6)),
        }
        started = time.time()
        # httpx timeout sits just under the resilience wrapper's wait_for so
        # the httpx TimeoutException (mapped to the honest timeout envelope)
        # fires instead of a raw asyncio.TimeoutError.
        http_timeout = max(5.0, self.timeout_seconds - 2.0)
        try:
            async with httpx.AsyncClient(timeout=http_timeout) as client:
                resp = await client.post(settings.WARDROBE_WORKER_URL or "", headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            logger.warn("wardrobe_worker_timeout", job_id=job_id, timeout=self.timeout_seconds, error=str(exc)[:120])
            return {"extraction_available": False, "reason": "wardrobe_worker_timeout", "job_id": job_id}
        except httpx.HTTPError as exc:
            logger.warn("wardrobe_worker_unreachable", job_id=job_id, error=str(exc)[:120])
            return {"extraction_available": False, "reason": "wardrobe_worker_unreachable", "job_id": job_id}

        if resp.status_code == 401:
            logger.error("wardrobe_worker_auth_failure", job_id=job_id)
            return {"extraction_available": False, "reason": "wardrobe_worker_auth_failure", "job_id": job_id}
        if resp.status_code == 422:
            return {
                "extraction_available": False,
                "reason": "wardrobe_worker_input_invalid",
                "detail": _safe_detail(resp),
                "job_id": job_id,
            }
        if resp.status_code >= 500:
            logger.error("wardrobe_worker_error", job_id=job_id, status=resp.status_code, detail=_safe_detail(resp)[:200])
            return {
                "extraction_available": False,
                "reason": "wardrobe_worker_infra_error",
                "status": resp.status_code,
                "job_id": job_id,
            }
        if resp.status_code != 200:
            return {"extraction_available": False, "reason": f"wardrobe_worker_http_{resp.status_code}", "job_id": job_id}

        try:
            body = resp.json()
        except ValueError:
            logger.error("wardrobe_worker_invalid_json", job_id=job_id)
            return {"extraction_available": False, "reason": "wardrobe_worker_invalid_response", "job_id": job_id}

        # Structural validation lives in extract_garments (one level up) so
        # that mocking ONLY the HTTP boundary still exercises the real
        # contract checks. The 200 body is returned as-is plus call metadata.
        body["job_id"] = job_id
        body["backend_call_seconds"] = round(time.time() - started, 2)
        return body


def _safe_detail(resp: httpx.Response) -> str:
    try:
        d = resp.json().get("detail")
        if isinstance(d, dict):
            return str(d.get("error", {}).get("message", ""))[:200]
        return str(d)[:200]
    except Exception:
        return resp.text[:200]


def _validate_worker_response(body: Any) -> Tuple[Dict[str, Any], Optional[str]]:
    """Structural validation of the worker response before anything is
    persisted: an item without a usable cutout is dropped (and reported),
    never half-imported."""
    if not isinstance(body, dict):
        return {}, "response is not an object"
    items_raw = body.get("items")
    if not isinstance(items_raw, list):
        return {}, "items is not a list"

    items: List[Dict[str, Any]] = []
    dropped: List[Dict[str, Any]] = []
    for raw in items_raw:
        if not isinstance(raw, dict):
            dropped.append({"label": None, "reason": "malformed_item"})
            continue
        slot = raw.get("slot_type")
        category = WORKER_CATEGORY_TO_PLATFORM.get(str(raw.get("category", "")))
        cutout = raw.get("cutout_data_url") or ""
        if slot not in _KNOWN_SLOTS or category is None:
            dropped.append({"label": raw.get("slot_type"), "reason": "unknown_slot"})
            continue
        png_bytes, cutout_problem = _decode_cutout(cutout)
        if cutout_problem or not png_bytes:
            dropped.append({"label": slot, "reason": cutout_problem or "empty_cutout"})
            continue
        items.append({
            "slot_type": slot,
            "category": category,
            "label_names": [str(x) for x in (raw.get("label_names") or [])][:8] or [slot],
            "bbox": raw.get("bbox"),
            "area_fraction": raw.get("area_fraction"),
            "confidence": _clamp01(raw.get("confidence")),
            "cutout_png": png_bytes,
        })

    skipped = body.get("skipped") if isinstance(body.get("skipped"), list) else []
    return (
        {
            "items": items,
            "dropped_items": dropped,
            "skipped": [s for s in skipped if isinstance(s, dict)],
            "person_detected": bool(body.get("person_detected")),
            "person_labels": [str(x) for x in (body.get("person_labels") or [])][:18],
            "engine": str(body.get("engine") or "unknown"),
            "commercial": bool(body.get("commercial", False)),
            "parse_seconds": body.get("parse_seconds"),
            "matting_seconds": body.get("matting_seconds"),
            "total_seconds": body.get("total_seconds"),
        },
        None,
    )


def _decode_cutout(data_url: str) -> Tuple[Optional[bytes], Optional[str]]:
    if not data_url.startswith("data:image/png;base64,"):
        return None, "cutout_not_png_data_url"
    try:
        png = base64.b64decode(data_url.split(",", 1)[1], validate=False)
    except (binascii.Error, ValueError):
        return None, "cutout_base64_invalid"
    if len(png) < 100 or not png.startswith(b"\x89PNG\r\n\x1a\n"):
        return None, "cutout_not_png"
    if len(png) > 20 * 1024 * 1024:
        return None, "cutout_too_large"
    return png, None


def _clamp01(value: Any) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, v))
