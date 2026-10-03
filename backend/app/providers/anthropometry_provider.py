"""Feature 05 — body-measurement estimation provider (Modal CPU worker client).

Calls the `confit-anthropometry-worker` Modal app (MediaPipe
pose_landmarker_heavy, Apache-2.0 + vendored Landmarks2Anthropometry
VISAPP-2024 Bayesian-ridge bundles, unlicensed-research-only) and maps its
honest response contract onto the backend's error taxonomy.

The worker NEVER fabricates measurements: implausible model outputs come
back in ``excluded`` with a machine-readable reason, direct-geometry
measurements always ship, and out-of-envelope photos are refused with
actionable guidance (HTTP 422 from the worker, preserved here). The
mandatory ±2-3 cm accuracy note and disclaimer ride on every successful
response — the provider keeps them intact instead of stripping provenance.

Contract (POST <ANTHROPOMETRY_WORKER_URL>, header X-VTON-Admin):
  request : {job_id, image_base64_or_url (data: URL|safe https URL),
             sex: "male"|"female", height_cm?}
  response: {status, sex, quality: full|partial|geometry_only,
             measurements: [{name, value_mm, value_cm, source: model|direct_geometry}],
             excluded: [{name, value_mm, reason}], measurement_method: ai_estimate,
             accuracy_note: "±2-3 cm", disclaimer, landmark_source, pose_quality,
             scale_calibration, engine, model{license, commercial: false}, timings}

Design mirrors the wardrobe extraction provider (feature 04): shared-secret
header, explicit endpoint URL, honest error codes, and an
``estimation_available=False`` envelope (never a fake success) when the
feature is not configured or the worker is unreachable.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional, Tuple

import httpx

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.providers.base import BaseProvider

_REQUIRED_TOP_KEYS = ("status", "quality", "measurements", "accuracy_note")
_VALID_QUALITY = {"full", "partial", "geometry_only"}
_VALID_SOURCES = {"model", "direct_geometry"}


class AnthropometryProvider(BaseProvider):
    """Client for the feature-05 estimation worker on Modal (CPU)."""

    def __init__(self):
        timeout = float(getattr(settings, "ANTHROPOMETRY_WORKER_TIMEOUT_SECONDS", 120.0) or 120.0)
        # max_retries=1 (BaseProvider counts ATTEMPTS): exactly one attempt.
        # A photo estimation already uploads a full image; a blind re-send
        # after a timeout would double the user's wait and the worker's
        # bill. The retry path is the user-visible "try again" action.
        super().__init__(name="Anthropometry_Provider", timeout_seconds=timeout, max_retries=1)

    # ── public API ───────────────────────────────────────────────────
    def is_configured(self) -> bool:
        return bool(settings.ANTHROPOMETRY_WORKER_URL and settings.ANTHROPOMETRY_WORKER_ADMIN_TOKEN)

    async def estimate_from_photo(
        self, data_url: str, sex: str, height_cm: Optional[float] = None
    ) -> Dict[str, Any]:
        """Estimate body measurements from one full-body photo.

        Returns the worker's validated dict, or an honest
        ``{"estimation_available": False, "reason": ..., "guidance": ...}``
        envelope. Never raises for infrastructure problems — the caller
        decides how to surface the failure (BRD §20 honest failure, no
        invented measurements).
        """
        if not self.is_configured():
            return {
                "estimation_available": False,
                "reason": "anthropometry_not_configured",
                "guidance": "Photo-based measurement is not available right now.",
            }
        result = await self.execute_with_resilience(
            self._call_worker, data_url=data_url, sex=sex, height_cm=height_cm
        )
        if result.get("estimation_available") is False:
            return result
        validated, problem = _validate_worker_response(result)
        if problem:
            logger.error("anthropometry_worker_contract_violation",
                         job_id=result.get("job_id"), problem=problem)
            return {
                "estimation_available": False,
                "reason": "anthropometry_invalid_response",
                "detail": problem,
                "job_id": result.get("job_id"),
            }
        validated["estimation_available"] = True
        validated["job_id"] = result.get("job_id")
        validated["backend_call_seconds"] = result.get("backend_call_seconds")
        return validated

    async def fallback(self, *args, **kwargs) -> Dict[str, Any]:
        """Honest degradation (BaseProvider contract): a measurement set is
        a real model output or it is unavailable — never synthesized."""
        return {"estimation_available": False, "reason": "anthropometry_unavailable"}

    # ── internals ────────────────────────────────────────────────────
    async def _call_worker(self, data_url: str, sex: str, height_cm: Optional[float]) -> Dict[str, Any]:
        job_id = f"anthro_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
        headers = {"X-VTON-Admin": settings.ANTHROPOMETRY_WORKER_ADMIN_TOKEN or ""}
        payload: Dict[str, Any] = {
            "job_id": job_id,
            "image_base64_or_url": data_url,
            "sex": sex,
        }
        if height_cm is not None:
            payload["height_cm"] = float(height_cm)
        started = time.time()
        http_timeout = max(5.0, self.timeout_seconds - 2.0)
        try:
            async with httpx.AsyncClient(timeout=http_timeout) as client:
                resp = await client.post(
                    settings.ANTHROPOMETRY_WORKER_URL or "", headers=headers, json=payload
                )
        except httpx.TimeoutException as exc:
            logger.warn("anthropometry_worker_timeout", job_id=job_id,
                        timeout=self.timeout_seconds, error=str(exc)[:120])
            return {"estimation_available": False, "reason": "anthropometry_worker_timeout",
                    "guidance": "The measurement took too long. Please try again.",
                    "job_id": job_id}
        except httpx.HTTPError as exc:
            logger.warn("anthropometry_worker_unreachable", job_id=job_id, error=str(exc)[:120])
            return {"estimation_available": False, "reason": "anthropometry_worker_unreachable",
                    "guidance": "The measurement service is unreachable. Please try again later.",
                    "job_id": job_id}

        if resp.status_code == 401:
            logger.error("anthropometry_worker_auth_failure", job_id=job_id)
            return {"estimation_available": False, "reason": "anthropometry_worker_auth_failure",
                    "job_id": job_id}
        if resp.status_code == 422:
            # The worker's honest refusals (no pose / out-of-envelope /
            # implausible) — preserve its actionable guidance verbatim.
            code, message = _safe_error(resp)
            return {
                "estimation_available": False,
                "reason": f"worker_refused:{code}",
                "guidance": message,
                "job_id": job_id,
            }
        if resp.status_code >= 500:
            logger.error("anthropometry_worker_error", job_id=job_id,
                         status=resp.status_code, detail=_safe_error(resp)[1][:200])
            return {"estimation_available": False, "reason": "anthropometry_worker_infra_error",
                    "status": resp.status_code, "job_id": job_id}
        if resp.status_code != 200:
            return {"estimation_available": False,
                    "reason": f"anthropometry_worker_http_{resp.status_code}",
                    "job_id": job_id}

        try:
            body = resp.json()
        except ValueError:
            logger.error("anthropometry_worker_invalid_json", job_id=job_id)
            return {"estimation_available": False, "reason": "anthropometry_worker_invalid_response",
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
    """Structural validation of the worker's 200 body before anything is
    persisted or surfaced: every required disclosure must be present and
    every measurement must carry an honest source label."""
    if not isinstance(body, dict):
        return body, "response is not an object"
    for key in _REQUIRED_TOP_KEYS:
        if key not in body:
            return body, f"missing key: {key}"
    if body.get("status") != "completed":
        return body, f"unexpected status: {body.get('status')}"
    if body.get("quality") not in _VALID_QUALITY:
        return body, f"invalid quality: {body.get('quality')}"
    if body.get("measurement_method") != "ai_estimate":
        return body, "measurement_method must be ai_estimate"
    measurements = body.get("measurements")
    if not isinstance(measurements, list) or not measurements:
        return body, "measurements must be a non-empty list"
    for m in measurements:
        if not isinstance(m, dict):
            return body, "measurement entry is not an object"
        if not m.get("name") or not isinstance(m.get("value_mm"), (int, float)):
            return body, "measurement entry missing name/value_mm"
        if m.get("source") not in _VALID_SOURCES:
            return body, f"invalid measurement source: {m.get('source')}"
    excluded = body.get("excluded", [])
    if not isinstance(excluded, list):
        return body, "excluded must be a list"
    for e in excluded:
        if not isinstance(e, dict) or not e.get("name") or not e.get("reason"):
            return body, "excluded entry missing name/reason"
    model_info = body.get("model")
    if not isinstance(model_info, dict) or model_info.get("commercial") is not False:
        return body, "model disclosure missing or commercial not false"
    if not body.get("disclaimer"):
        return body, "disclaimer missing"
    return body, None
