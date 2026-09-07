"""Lightweight HTTP client for the self-hosted Qwen2.5-VL inference worker.

Binding design constraints honoured here:

* No torch / transformers / weight access in this module — safe to import in the
  Vercel serverless function (250 MB, no heavy ML).
* **Single attempt + hard timeout. No retry loop** on a local GPU model: a slow
  or absent worker must surface honestly, not be hammered (no infinite retry).
* The response contract is EXACTLY the Gemini structured-output contract the
  service layer already consumes (top-level fields + ``analysis_available`` +
  ``analysis_source``), so ``visual_search_service`` and ``wardrobe_service``
  are unchanged.
* It never invents detections. On any failure it raises :class:`QwenVisionError`
  and the caller degrades to the existing honest ``analysis_available=False``.
"""
from __future__ import annotations

import os
from typing import Any, Dict

import httpx

from backend.app.core.config import settings
from backend.app.core.logging import logger

from .errors import QwenVisionError

_USER_AGENT = "CONFIT-VLM/1.0"


class QwenVisionProvider:
    """Client for the self-hosted Qwen2.5-VL worker.

    The worker is the only place the model weights live and inference runs. This
    client sends ``{image, prompt, mode}`` and expects back the Gemini-compatible
    structured JSON.
    """

    def __init__(self) -> None:
        self._model_id = getattr(settings, "QWEN_VL_MODEL_ID", "Qwen/Qwen2.5-VL-7B-Instruct")

    @property
    def model_id(self) -> str:
        return self._model_id

    def is_configured(self) -> bool:
        """True only when an inference worker is configured AND not disabled.

        This is the single opt-in signal: leaving ``QWEN_VL_WORKER_URL`` unset
        keeps the entire existing Gemini-only behaviour unchanged.
        """
        if not getattr(settings, "QWEN_VL_ENABLED", True):
            return False
        return bool(getattr(settings, "QWEN_VL_WORKER_URL", None))

    def _base_url(self) -> str:
        return str(getattr(settings, "QWEN_VL_WORKER_URL", "") or "").rstrip("/")

    def _auth_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"User-Agent": _USER_AGENT}
        token = (
            getattr(settings, "QWEN_VL_WORKER_TOKEN", None)
            or os.environ.get("QWEN_VL_WORKER_TOKEN", "")
        )
        if token:
            headers["X-VLM-Admin"] = token
        return headers

    async def analyze(
        self,
        image_url_or_base64: str,
        prompt: str,
        *,
        mode: str = "visual_search",
    ) -> Dict[str, Any]:
        """Run one vision analysis on the self-hosted worker.

        Returns the Gemini-compatible flat dict on success. Raises
        :class:`QwenVisionError` on any failure so the caller can degrade honestly.
        ``mode`` is for observability only; the prompt defines the JSON keys.
        """
        if not self.is_configured():
            raise QwenVisionError("not_configured", "QWEN_VL_WORKER_URL is not set")
        if not image_url_or_base64:
            raise QwenVisionError("bad_input", "empty image reference")
        if not prompt or not prompt.strip():
            raise QwenVisionError("bad_input", "empty prompt")

        url = f"{self._base_url()}/analyze"
        payload = {
            "image": image_url_or_base64,
            "prompt": prompt,
            "mode": mode,
            "model_id": self._model_id,
        }
        timeout = float(getattr(settings, "QWEN_VL_TIMEOUT_SECONDS", 90.0))

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                res = await client.post(url, json=payload, headers=self._auth_headers())
        except httpx.TimeoutException as exc:
            raise QwenVisionError("timeout", f"worker inference timed out after {timeout:.0f}s: {exc}") from exc
        except httpx.HTTPError as exc:
            raise QwenVisionError("worker_unavailable", f"could not reach VLM worker: {exc}") from exc

        if res.status_code == 401:
            raise QwenVisionError("auth", "VLM worker rejected admin token", http_status=401)
        if res.status_code == 503:
            raise QwenVisionError("worker_not_ready", "VLM worker model not loaded", http_status=503)
        if res.status_code >= 500:
            raise QwenVisionError("worker_error", self._extract_error(res), http_status=res.status_code)
        if res.status_code != 200:
            raise QwenVisionError("invalid_response", f"unexpected HTTP {res.status_code}", http_status=res.status_code)

        try:
            data = res.json()
        except Exception as exc:
            raise QwenVisionError("invalid_response", "worker returned non-JSON body") from exc
        if not isinstance(data, dict):
            raise QwenVisionError("invalid_response", "worker response is not an object")

        result: Dict[str, Any] = dict(data)
        result["analysis_available"] = bool(data.get("analysis_available", False))
        result["analysis_source"] = data.get("analysis_source") or self._model_id
        if not isinstance(result["analysis_source"], str):
            result["analysis_source"] = str(result["analysis_source"])
        if not result["analysis_available"]:
            logger.info(
                "qwen_vision_worker_returned_unusable",
                reason=str(data.get("error") or data.get("detail") or ""),
            )
        return result

    @staticmethod
    def _extract_error(res: httpx.Response) -> str:
        try:
            body = res.json()
            err = body.get("error") or body.get("detail") or body
            if isinstance(err, dict):
                return f"{err.get('code') or 'INFERENCE_FAILED'}: {err.get('message') or res.text[:200]}"
            return f"INFERENCE_FAILED: {str(err)[:200]}"
        except Exception:
            return res.text[:200]
