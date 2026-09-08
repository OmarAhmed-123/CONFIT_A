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

import asyncio
import base64
import os
from typing import Any, Dict
from urllib.parse import urlparse

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

    def _transport(self) -> str:
        return (getattr(settings, "QWEN_VL_TRANSPORT", "web") or "web").strip().lower()

    def _modal_creds_present(self) -> bool:
        # MODAL_TOKEN_ID / MODAL_TOKEN_SECRET are server-side only (Modal CLI env
        # contract). Never read from request state; never logged.
        return bool(os.environ.get("MODAL_TOKEN_ID")) and bool(os.environ.get("MODAL_TOKEN_SECRET"))

    def is_configured(self) -> bool:
        """True only when an inference worker is configured AND not disabled.

        This is the single opt-in signal: leaving the worker unset keeps the entire
        existing Gemini-only behaviour unchanged. For ``transport="web"`` that means
        ``QWEN_VL_WORKER_URL`` is set; for ``transport="remote"`` that means the
        server-side Modal credentials (MODAL_TOKEN_ID/SECRET) are present.
        """
        if not getattr(settings, "QWEN_VL_ENABLED", True):
            return False
        if self._transport() == "remote":
            return self._modal_creds_present()
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
        Dispatches by ``QWEN_VL_TRANSPORT`` (web | remote).
        """
        if not image_url_or_base64:
            raise QwenVisionError("bad_input", "empty image reference")
        if not prompt or not prompt.strip():
            raise QwenVisionError("bad_input", "empty prompt")
        if self._transport() == "remote":
            return await self._analyze_remote(image_url_or_base64, prompt, mode=mode)
        return await self._analyze_web(image_url_or_base64, prompt, mode=mode)

    async def _analyze_web(
        self,
        image_url_or_base64: str,
        prompt: str,
        *,
        mode: str = "visual_search",
    ) -> Dict[str, Any]:
        if not self.is_configured():
            raise QwenVisionError("not_configured", "QWEN_VL_WORKER_URL is not set")
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

    _BLOCKED_HOST_PREFIXES = (
        "127.", "10.", "192.168.", "169.254.", "0.",
        "172.16.", "172.17.", "172.18.", "172.19.", "172.20.", "172.21.", "172.22.",
        "172.23.", "172.24.", "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
        "172.30.", "172.31.",
    )

    @classmethod
    def _image_ref_to_base64_mime(cls, image_ref: str) -> tuple[str, str]:
        """Resolve an image reference (data URL or http(s) URL) to (base64, mime)
        for the Modal ``.remote()`` transport. Same SSRF guard + 15MB cap as the
        worker's web path. Raises :class:`QwenVisionError` on bad input."""
        if image_ref.startswith("data:image"):
            header, encoded = image_ref.split(",", 1)
            mime = header.split(";")[0].replace("data:", "") or "image/jpeg"
            return encoded, mime
        if image_ref.startswith(("http://", "https://")):
            host = (urlparse(image_ref).hostname or "").lower()
            if not host or host == "localhost" or host.startswith(cls._BLOCKED_HOST_PREFIXES):
                raise QwenVisionError("bad_input", "refused unsafe image URL (private/loopback)")
            with httpx.Client(timeout=20.0, follow_redirects=True) as client:
                resp = client.get(image_ref)
                resp.raise_for_status()
                mime = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                if mime not in ("image/jpeg", "image/png", "image/webp"):
                    raise QwenVisionError("bad_input", f"unsupported image content type: {mime or 'unknown'}")
                if len(resp.content) > 15 * 1024 * 1024:
                    raise QwenVisionError("bad_input", "image exceeds 15MB limit")
                return base64.b64encode(resp.content).decode(), mime
        raise QwenVisionError("bad_input", "image must be a data URL or http(s) URL")

    # Worker error code (vlm_analyze) -> client reason.
    _REMOTE_ERROR_MAP = {
        "VLM_NOT_READY": "worker_not_ready",
        "BAD_INPUT": "bad_input",
        "GPU_OOM": "worker_error",
        "output_invalid": "invalid_response",
        "INFERENCE_FAILED": "worker_error",
    }

    async def _analyze_remote(
        self,
        image_url_or_base64: str,
        prompt: str,
        *,
        mode: str = "visual_search",
    ) -> Dict[str, Any]:
        """Serve via the deployed Modal Function ``vlm_analyze`` over ``.remote()``
        (server-to-server; the container is held for the call, so the heavy cold start
        is fine — the robust path for this 16.6 GB model when a warm container is not
        available). ``modal`` is imported lazily so the web path stays dependency-free.
        """
        if not self.is_configured():
            raise QwenVisionError(
                "not_configured",
                "MODAL_TOKEN_ID/SECRET not set for QWEN_VL_TRANSPORT=remote",
            )
        try:
            b64, mime = await asyncio.to_thread(self._image_ref_to_base64_mime, image_url_or_base64)
        except QwenVisionError:
            raise
        except Exception as exc:
            raise QwenVisionError("bad_input", f"could not resolve image: {exc}") from exc

        try:
            import modal  # lazy: only needed for the remote transport
        except ImportError as exc:
            raise QwenVisionError("worker_unavailable", f"modal SDK unavailable for remote transport: {exc}") from exc

        app_name = getattr(settings, "QWEN_VL_REMOTE_APP", "confit-vlm-worker")
        fn_name = getattr(settings, "QWEN_VL_REMOTE_FN", "vlm_analyze")
        timeout = float(getattr(settings, "QWEN_VL_TIMEOUT_SECONDS", 90.0))

        def _call() -> Dict[str, Any]:
            # The Modal SDK is synchronous; the worker's vlm_analyze has its own GPU
            # timeout (900s). We bound the caller so a wedged container surfaces
            # honestly instead of hanging the request.
            fn = modal.Function.from_name(app_name, fn_name)
            return fn.remote(b64, mime, prompt, mode)

        try:
            data = await asyncio.wait_for(asyncio.to_thread(_call), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise QwenVisionError("timeout", f"worker inference timed out after {timeout:.0f}s") from exc
        except Exception as exc:
            raise QwenVisionError("worker_unavailable", f"could not reach VLM worker via .remote(): {exc}") from exc

        if not isinstance(data, dict):
            raise QwenVisionError("invalid_response", "worker response is not an object")

        result: Dict[str, Any] = dict(data)
        result["analysis_available"] = bool(data.get("analysis_available", False))
        result["analysis_source"] = data.get("analysis_source") or self._model_id
        if not isinstance(result["analysis_source"], str):
            result["analysis_source"] = str(result["analysis_source"])
        if not result["analysis_available"]:
            err = str(data.get("error") or "worker_error")
            detail = str(data.get("detail") or "")[:200]
            reason = self._REMOTE_ERROR_MAP.get(err, "worker_error")
            logger.info("qwen_vision_worker_returned_unusable", reason=f"{err}: {detail}")
            raise QwenVisionError(reason, f"{err}: {detail}".strip())
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
