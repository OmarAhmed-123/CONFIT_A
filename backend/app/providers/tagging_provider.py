"""Feature 07 — product auto-tagging provider (Modal CPU worker client).

Calls the `confit-tagging-worker` Modal app (FashionCLIP
patrickjohncyh/fashion-clip, MIT + GLiNER urchade/gliner_multi-v2.1,
Apache-2.0) and maps its honest response contract onto the backend's
error taxonomy.

The worker NEVER invents tags: every emitted tag carries {axis, value,
confidence, source}; axes below threshold come back in ``axes_unresolved``
with reasons; ``product_suggestions`` only contains fields that earned a
confident value. Licenses and commercial-safety are disclosed in every
response. This provider preserves all of that instead of flattening it.

Contract (POST <TAGGING_WORKER_URL>, header X-VTON-Admin):
  request : {job_id, image_base64_or_url?, title?, description?,
             title_ar?, description_ar?}
  response: {status, quality: full|image_only|text_only|none,
             tags[{axis,value,confidence,source,corroborated_by,...}],
             tag_count, axes_unresolved[{axis,reason}],
             product_suggestions{color_family?,material?,style_tags?,
             occasion_tags?,platform_category?},
             models{fashionclip{license:mit,commercial:true},
                    gliner{license:apache-2.0,commercial:true}},
             disclaimer, timings}

Design mirrors the wardrobe/anthropometry providers: shared-secret header,
explicit endpoint URL, honest error codes, ``tagging_available=False``
envelopes (never a fake success) when unconfigured or unreachable.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional, Tuple

import httpx

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.providers.base import BaseProvider

_REQUIRED_TOP_KEYS = ("status", "quality", "tags", "product_suggestions", "models")
_VALID_QUALITY = {"full", "image_only", "text_only", "none"}
_VALID_SOURCES = {"fashionclip", "gliner"}


class TaggingProvider(BaseProvider):
    """Client for the feature-07 tagging worker on Modal (CPU)."""

    def __init__(self):
        timeout = float(getattr(settings, "TAGGING_WORKER_TIMEOUT_SECONDS", 90.0) or 90.0)
        # max_retries=1 (BaseProvider counts ATTEMPTS): exactly one attempt —
        # a tagging call already uploads/fetches a product image; a blind
        # retry after a timeout would double the wait. Retry = the brand's
        # "try again" button.
        super().__init__(name="Tagging_Provider", timeout_seconds=timeout, max_retries=1)

    # ── public API ───────────────────────────────────────────────────
    def is_configured(self) -> bool:
        return bool(settings.TAGGING_WORKER_URL and settings.TAGGING_WORKER_ADMIN_TOKEN)

    async def tag_product(
        self,
        image_url: Optional[str],
        title: str = "",
        description: str = "",
        title_ar: str = "",
        description_ar: str = "",
    ) -> Dict[str, Any]:
        """Auto-tag one product (image URL and/or text fields).

        Returns the worker's validated dict, or an honest
        ``{"tagging_available": False, "reason": ...}`` envelope. Never
        raises for infrastructure problems — the caller decides how to
        surface the failure (no invented tags, ever).
        """
        if not self.is_configured():
            return {
                "tagging_available": False,
                "reason": "tagging_not_configured",
                "guidance": "Auto-tagging is not available right now.",
            }
        result = await self.execute_with_resilience(
            self._call_worker,
            image_url=image_url,
            title=title,
            description=description,
            title_ar=title_ar,
            description_ar=description_ar,
        )
        if result.get("tagging_available") is False:
            return result
        validated, problem = _validate_worker_response(result)
        if problem:
            logger.error("tagging_worker_contract_violation",
                         job_id=result.get("job_id"), problem=problem)
            return {
                "tagging_available": False,
                "reason": "tagging_invalid_response",
                "detail": problem,
                "job_id": result.get("job_id"),
            }
        validated["tagging_available"] = True
        validated["job_id"] = result.get("job_id")
        validated["backend_call_seconds"] = result.get("backend_call_seconds")
        return validated

    async def fallback(self, *args, **kwargs) -> Dict[str, Any]:
        """Honest degradation (BaseProvider contract): a tag set is a real
        model output or it is unavailable — never synthesized."""
        return {"tagging_available": False, "reason": "tagging_unavailable"}

    # ── internals ────────────────────────────────────────────────────
    async def _call_worker(
        self,
        image_url: Optional[str],
        title: str,
        description: str,
        title_ar: str,
        description_ar: str,
    ) -> Dict[str, Any]:
        job_id = f"tag_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
        headers = {"X-VTON-Admin": settings.TAGGING_WORKER_ADMIN_TOKEN or ""}
        payload: Dict[str, Any] = {"job_id": job_id}
        if image_url:
            payload["image_base64_or_url"] = image_url
        for key, value in (
            ("title", title), ("description", description),
            ("title_ar", title_ar), ("description_ar", description_ar),
        ):
            if value:
                payload[key] = value[:2000]

        started = time.time()
        http_timeout = max(5.0, self.timeout_seconds - 2.0)
        try:
            async with httpx.AsyncClient(timeout=http_timeout) as client:
                resp = await client.post(
                    settings.TAGGING_WORKER_URL or "", headers=headers, json=payload
                )
        except httpx.TimeoutException as exc:
            logger.warn("tagging_worker_timeout", job_id=job_id,
                        timeout=self.timeout_seconds, error=str(exc)[:120])
            return {"tagging_available": False, "reason": "tagging_worker_timeout",
                    "guidance": "Tagging took too long. Please try again.",
                    "job_id": job_id}
        except httpx.HTTPError as exc:
            logger.warn("tagging_worker_unreachable", job_id=job_id, error=str(exc)[:120])
            return {"tagging_available": False, "reason": "tagging_worker_unreachable",
                    "guidance": "The tagging service is unreachable. Please try again later.",
                    "job_id": job_id}

        if resp.status_code == 401:
            logger.error("tagging_worker_auth_failure", job_id=job_id)
            return {"tagging_available": False, "reason": "tagging_worker_auth_failure",
                    "job_id": job_id}
        if resp.status_code == 422:
            # The worker's honest refusals (bad image URL, nothing to tag)
            # — preserve its actionable guidance verbatim.
            code, message = _safe_error(resp)
            return {"tagging_available": False,
                    "reason": f"worker_refused:{code}",
                    "guidance": message, "job_id": job_id}
        if resp.status_code >= 500:
            logger.error("tagging_worker_error", job_id=job_id,
                         status=resp.status_code, detail=_safe_error(resp)[1][:200])
            return {"tagging_available": False, "reason": "tagging_worker_infra_error",
                    "status": resp.status_code, "job_id": job_id}
        if resp.status_code != 200:
            return {"tagging_available": False,
                    "reason": f"tagging_worker_http_{resp.status_code}",
                    "job_id": job_id}

        try:
            body = resp.json()
        except ValueError:
            logger.error("tagging_worker_invalid_json", job_id=job_id)
            return {"tagging_available": False, "reason": "tagging_worker_invalid_response",
                    "job_id": job_id}

        body["job_id"] = job_id
        body["backend_call_seconds"] = round(time.time() - started, 2)
        return body


def _safe_error(resp: httpx.Response) -> Tuple[str, str]:
    """Extract (code, message) from a worker error body without raising."""
    try:
        d = resp.json().get("detail")
        if isinstance(d, dict):
            err = d.get("error", {})
            return str(err.get("code", "UNKNOWN")), str(err.get("message", ""))[:400]
        return "UNKNOWN", str(d)[:400]
    except Exception:
        return "UNKNOWN", resp.text[:400]


def _validate_worker_response(body: Any) -> Tuple[Dict[str, Any], Optional[str]]:
    """Structural validation of the worker's 200 body: every required
    disclosure must be present and every tag must carry an honest source."""
    if not isinstance(body, dict):
        return body, "response is not an object"
    for key in _REQUIRED_TOP_KEYS:
        if key not in body:
            return body, f"missing key: {key}"
    if body.get("status") != "completed":
        return body, f"unexpected status: {body.get('status')}"
    if body.get("quality") not in _VALID_QUALITY:
        return body, f"invalid quality: {body.get('quality')}"
    tags = body.get("tags")
    if not isinstance(tags, list):
        return body, "tags must be a list"
    for t in tags:
        if not isinstance(t, dict):
            return body, "tag entry is not an object"
        if not t.get("axis") or not t.get("value"):
            return body, "tag entry missing axis/value"
        if not isinstance(t.get("confidence"), (int, float)):
            return body, "tag entry missing numeric confidence"
        if t.get("source") not in _VALID_SOURCES:
            return body, f"invalid tag source: {t.get('source')}"
    if not isinstance(body.get("product_suggestions"), dict):
        return body, "product_suggestions must be an object"
    if not isinstance(body.get("axes_unresolved"), list):
        return body, "axes_unresolved must be a list"
    models = body.get("models")
    if not isinstance(models, dict):
        return body, "models disclosure missing"
    if models.get("fashionclip", {}).get("license") != "mit":
        return body, "fashionclip license disclosure missing"
    if models.get("gliner", {}).get("license") != "apache-2.0":
        return body, "gliner license disclosure missing"
    if not body.get("disclaimer"):
        return body, "disclaimer missing"
    return body, None
