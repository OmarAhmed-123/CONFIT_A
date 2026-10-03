"""Feature 06 — outfit compatibility provider (Modal CPU worker client).

Calls the `confit-outfit-worker` Modal app (OutfitTransformer
OutfitCLIPTransformer: frozen FashionCLIP item encoder + 6-layer
transformer, Polyvore-trained, MIT — vendored at
vendor/outfit-transformer) and maps its honest response contract onto the
backend's error taxonomy.

The worker never invents scores: compatibility is a real sigmoid over the
item set, fill-in-the-blank is cosine retrieval in the complementary
model's learned space. Refusals come back as 422 {error:{code,message}}.
This provider preserves the worker's disclosures (model licenses, Polyvore
training note, TATTOO-style advisory axes) instead of flattening them, and
degrades to an honest ``{"compatibility_available": False, "reason": ...}``
envelope — never a fabricated score — when unconfigured or unreachable.

Contract (POST <OUTFIT_WORKER_COMPAT_URL>, header X-VTON-Admin):
  request : {job_id, items: [{image_base64_or_url, slot?, title?}],
             include_axes?}
  response: {status, engine: outfit_transformer_clip_cpu,
             compatibility_score (0-1), compatibility_score_0_100,
             type_aware{slots, polyvore_categories, duplicate_slots,
             coverage, warnings}, aesthetic_axes{...}|null, models{...},
             training_data_note, timings, job_id}

Contract (POST <OUTFIT_WORKER_FITB_URL>):
  request : {job_id, outfit: [item…], candidates: [{id, …item}],
             target_slot?, top_k?}
  response: {status, engine, target_category_used, ranked[{id, rank,
             similarity}], disclaimer, models, timings, job_id}

Design mirrors the tagging provider (feature 07): shared-secret header,
explicit FULL endpoint URLs (one per Modal web endpoint — Modal gives each
@modal.fastapi_endpoint function its own URL, stable here via endpoint
labels), honest error codes, one attempt (an outfit check uploads N images;
a blind retry doubles the wait for nothing).
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

import httpx

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.providers.base import BaseProvider

_ENGINE = "outfit_transformer_clip_cpu"


class OutfitCompatProvider(BaseProvider):
    """Client for the feature-06 outfit compatibility worker on Modal (CPU)."""

    def __init__(self):
        timeout = float(getattr(settings, "OUTFIT_WORKER_TIMEOUT_SECONDS", 120.0) or 120.0)
        # max_retries=1 (BaseProvider counts ATTEMPTS): exactly one attempt.
        super().__init__(name="Outfit_Compat_Provider", timeout_seconds=timeout, max_retries=1)

    # ── public API ───────────────────────────────────────────────────

    def is_configured(self) -> bool:
        return bool(settings.OUTFIT_WORKER_COMPAT_URL
                    and settings.OUTFIT_WORKER_ADMIN_TOKEN)

    def fitb_configured(self) -> bool:
        return bool(settings.OUTFIT_WORKER_FITB_URL
                    and settings.OUTFIT_WORKER_ADMIN_TOKEN)

    async def score_compatibility(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Score one outfit (2-16 items with image URLs).

        ``items``: [{image_base64_or_url, slot?, title?}] — the caller
        builds them from REAL catalog products; the worker refuses sets
        with fewer than 2 items or missing images.
        """
        if not self.is_configured():
            return _unavailable("outfit_model_not_configured")
        result = await self.execute_with_resilience(
            self._call_worker, url=settings.OUTFIT_WORKER_COMPAT_URL,
            payload={"items": items})
        if result.get("compatibility_available") is False:
            return result
        problem = _validate_compat_response(result)
        if problem:
            logger.error("outfit_worker_contract_violation",
                         job_id=result.get("job_id"), problem=problem)
            return _unavailable("outfit_model_invalid_response", problem)
        result["compatibility_available"] = True
        return result

    async def fill_in_the_blank(
        self,
        outfit: List[Dict[str, Any]],
        candidates: List[Dict[str, Any]],
        target_slot: Optional[str] = None,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """Complete a partial outfit: rank candidates for the blank slot."""
        if not self.fitb_configured():
            return _unavailable("outfit_model_not_configured")
        result = await self.execute_with_resilience(
            self._call_worker, url=settings.OUTFIT_WORKER_FITB_URL,
            payload={
                "outfit": outfit,
                "candidates": candidates,
                "target_slot": target_slot,
                "top_k": top_k,
            })
        if result.get("compatibility_available") is False:
            return result
        problem = _validate_fitb_response(result)
        if problem:
            logger.error("outfit_worker_contract_violation",
                         job_id=result.get("job_id"), problem=problem)
            return _unavailable("outfit_model_invalid_response", problem)
        result["compatibility_available"] = True
        return result

    async def fallback(self, *args, **kwargs) -> Dict[str, Any]:
        """Honest degradation (BaseProvider contract): a compatibility score
        is a real model output or it is unavailable — never synthesized."""
        return _unavailable("outfit_model_unavailable")

    # ── internals ────────────────────────────────────────────────────

    async def _call_worker(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        job_id = f"outfit_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
        body = {"job_id": job_id, **payload}
        headers = {"X-VTON-Admin": settings.OUTFIT_WORKER_ADMIN_TOKEN or ""}
        started = time.time()
        http_timeout = max(5.0, self.timeout_seconds - 2.0)
        try:
            async with httpx.AsyncClient(timeout=http_timeout) as client:
                resp = await client.post(url, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            logger.warn("outfit_worker_timeout", job_id=job_id,
                        timeout=self.timeout_seconds, error=str(exc)[:120])
            return _unavailable("outfit_worker_timeout")
        except httpx.HTTPError as exc:
            logger.warn("outfit_worker_unreachable", job_id=job_id,
                        error=str(exc)[:120])
            return _unavailable("outfit_worker_unreachable")

        if resp.status_code == 401:
            logger.error("outfit_worker_auth_failure", job_id=job_id)
            return _unavailable("outfit_worker_auth_failure")
        if resp.status_code == 422:
            # The worker's honest refusals (invalid set, no candidates, bad
            # image) — preserve the actionable message for the shopper.
            code, message = _safe_error(resp)
            return _unavailable(f"worker_refused:{code}", message)
        if resp.status_code >= 500:
            logger.error("outfit_worker_error", job_id=job_id,
                         status=resp.status_code,
                         detail=_safe_error(resp)[1][:200])
            return _unavailable("outfit_worker_infra_error",
                                status_code=resp.status_code)
        if resp.status_code != 200:
            return _unavailable(f"outfit_worker_http_{resp.status_code}")

        try:
            parsed = resp.json()
        except ValueError:
            logger.error("outfit_worker_invalid_json", job_id=job_id)
            return _unavailable("outfit_worker_invalid_response")

        parsed["job_id"] = job_id
        parsed["backend_call_seconds"] = round(time.time() - started, 2)
        return parsed


# ── validation + honest envelopes ─────────────────────────────────────


def _unavailable(reason: str, detail: Optional[str] = None,
                 status_code: Optional[int] = None) -> Dict[str, Any]:
    envelope: Dict[str, Any] = {
        "compatibility_available": False,
        "reason": reason,
    }
    if detail:
        envelope["guidance"] = detail
    if status_code:
        envelope["worker_status"] = status_code
    return envelope


def _safe_error(resp: httpx.Response) -> Tuple[str, str]:
    """Extract (code, message) from a worker error body without raising."""
    try:
        d = resp.json().get("detail")
        if isinstance(d, dict):
            err = d.get("error") or {}
            return str(err.get("code", "UNKNOWN")), str(err.get("message", ""))
    except Exception:
        pass
    return "UNKNOWN", ""


def _validate_compat_response(body: Dict[str, Any]) -> Optional[str]:
    """Return a problem string, or None when the contract holds."""
    if body.get("status") != "ok":
        return f"status={body.get('status')!r}"
    if body.get("engine") != _ENGINE:
        return f"engine={body.get('engine')!r}"
    score = body.get("compatibility_score")
    if not isinstance(score, (int, float)) or not 0.0 <= float(score) <= 1.0:
        return f"compatibility_score={score!r}"
    ta = body.get("type_aware")
    if not isinstance(ta, dict) or "coverage" not in ta or "warnings" not in ta:
        return "type_aware block missing"
    return None


def _validate_fitb_response(body: Dict[str, Any]) -> Optional[str]:
    if body.get("status") != "ok":
        return f"status={body.get('status')!r}"
    if body.get("engine") != _ENGINE:
        return f"engine={body.get('engine')!r}"
    ranked = body.get("ranked")
    if not isinstance(ranked, list):
        return "ranked missing"
    for entry in ranked:
        if not isinstance(entry, dict) or "id" not in entry or "rank" not in entry \
                or "similarity" not in entry:
            return f"ranked entry malformed: {entry!r}"
    return None
