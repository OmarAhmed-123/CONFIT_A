"""Eachlabs Bria Virtual Try-On API client.

Protocol: Eachlabs REST API (https://api.eachlabs.ai/v1)
- Model: bria-virtual-try-on
- Input: person_image (URL), garment_images (array of URLs)
- Output: polling-based with Status checking
- Cost: dynamic ($0.04 per execution)
- Polling: /v1/prediction/{id}

This adapter follows the project's honesty principles:
- No fabricated results
- Explicit failure states (503 when unavailable)
- No raw image bytes stored in database
- Timeout-bounded polling with explicit fail states
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.providers.vton.registry import GarmentCategory, VtonEngineSpec


class EachlabsError(RuntimeError):
    """Eachlabs API error with retryable classification.

    Carries `retryable` so the caller can decide between advancing the fallback
    chain and giving up, without parsing a message string.
    """

    def __init__(self, message: str, *, retryable: bool = True, status_code: Optional[int] = None):
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


@dataclass(frozen=True)
class EachlabsVtonResult:
    """A produced try-on image plus metadata.

    `engine` and metadata travel WITH the render for audit trail.
    """

    image_url: str
    engine: str = "eachlabs_bria_vton"
    license: str = "Proprietary (Eachlabs Commercial API)"
    commercial: bool = True
    elapsed_seconds: float = 0.0
    prediction_id: str = ""
    model_slug: str = "bria-virtual-try-on"


class EachlabsVtonClient:
    """Production Eachlabs Bria VTON client with honest polling.

    - No retries across the same job (polling is the mechanism)
    - Explicit timeout on polling loop (configurable, default 180s)
    - Honest status classification (transient vs permanent failure)
    - No image bytes ever stored in the database
    """

    BASE_URL = "https://api.eachlabs.ai/v1"
    MODEL_SLUG = "bria-virtual-try-on"
    DEFAULT_TIMEOUT_SECONDS = 180.0
    POLL_INTERVAL_SECONDS = 2.0
    MAX_POLL_ATTEMPTS = int(DEFAULT_TIMEOUT_SECONDS / POLL_INTERVAL_SECONDS)

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        """Initialize the Eachlabs client.

        Args:
            api_key: Bearer token for Eachlabs API. Defaults to EACHLABS_API_KEY env var.
            timeout_seconds: Total polling timeout. Bounded by config max.
        """
        self.api_key = (api_key or getattr(settings, "EACHLABS_API_KEY", None) or "").strip()
        self.timeout_seconds = float(timeout_seconds)
        self._http_client: Optional[httpx.AsyncClient] = None

    def _is_configured(self) -> bool:
        """True only if a real API key is present."""
        return bool(self.api_key and len(self.api_key) > 10)

    async def _get_client(self) -> httpx.AsyncClient:
        """Reuse or create an async HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=5.0),
                follow_redirects=True,
            )
        return self._http_client

    async def close(self) -> None:
        """Clean up the HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def submit_job(
        self,
        person_image_url: str,
        garment_image_urls: List[str],
        instruction: Optional[str] = None,
        aspect_ratio: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> str:
        """Submit a virtual try-on job to Eachlabs.

        Returns: prediction ID for polling
        Raises: EachlabsError on any failure
        """
        if not self._is_configured():
            raise EachlabsError(
                "Eachlabs API key not configured",
                retryable=False,
            )

        client = await self._get_client()
        payload = {
            "model": self.MODEL_SLUG,
            "input": {
                "person_image": person_image_url,
                "garment_images": garment_image_urls[:3],  # API limit: 1-3 images
            },
        }
        if instruction:
            payload["input"]["instruction"] = instruction
        if aspect_ratio:
            payload["input"]["aspect_ratio"] = aspect_ratio
        if seed is not None:
            payload["input"]["seed"] = seed

        try:
            response = await client.post(
                f"{self.BASE_URL}/prediction/",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30.0,
            )
        except httpx.TimeoutException as exc:
            raise EachlabsError(
                f"Eachlabs submit timeout: {exc}",
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise EachlabsError(
                f"Eachlabs HTTP error: {exc}",
                retryable=True,
            ) from exc

        if response.status_code == 401:
            raise EachlabsError(
                "Eachlabs API key invalid or expired",
                retryable=False,
                status_code=401,
            )
        if response.status_code == 429:
            raise EachlabsError(
                "Eachlabs rate limit exceeded (100 creates/min, 10 concurrent)",
                retryable=True,
                status_code=429,
            )
        if response.status_code == 400:
            try:
                error_detail = response.json().get("details", "Invalid input")
            except Exception:
                error_detail = response.text
            raise EachlabsError(
                f"Eachlabs input validation failed: {error_detail}",
                retryable=False,
                status_code=400,
            )
        if response.status_code >= 500:
            raise EachlabsError(
                f"Eachlabs server error ({response.status_code})",
                retryable=True,
                status_code=response.status_code,
            )

        if response.status_code != 201:
            raise EachlabsError(
                f"Eachlabs unexpected status {response.status_code}",
                retryable=True,
                status_code=response.status_code,
            )

        try:
            data = response.json()
            prediction_id = data.get("predictionID")
            if not prediction_id:
                raise EachlabsError(
                    "Eachlabs response missing predictionID",
                    retryable=True,
                )
            return prediction_id
        except (json.JSONDecodeError, ValueError) as exc:
            raise EachlabsError(
                f"Eachlabs response not JSON: {exc}",
                retryable=True,
            ) from exc

    async def poll_job(
        self,
        prediction_id: str,
        timeout_seconds: Optional[float] = None,
    ) -> EachlabsVtonResult:
        """Poll for job completion until timeout.

        Returns: result with image URL
        Raises: EachlabsError on any failure or timeout
        """
        if not self._is_configured():
            raise EachlabsError(
                "Eachlabs API key not configured",
                retryable=False,
            )

        timeout_s = timeout_seconds or self.timeout_seconds
        start_time = time.time()
        poll_count = 0
        client = await self._get_client()

        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout_s:
                raise EachlabsError(
                    f"Eachlabs polling timeout after {elapsed:.1f}s",
                    retryable=True,
                )

            try:
                response = await client.get(
                    f"{self.BASE_URL}/prediction/{prediction_id}",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=15.0,
                )
            except httpx.TimeoutException as exc:
                raise EachlabsError(
                    f"Eachlabs poll timeout: {exc}",
                    retryable=True,
                ) from exc
            except httpx.HTTPError as exc:
                raise EachlabsError(
                    f"Eachlabs HTTP error during poll: {exc}",
                    retryable=True,
                ) from exc

            if response.status_code == 401:
                raise EachlabsError(
                    "Eachlabs API key invalid",
                    retryable=False,
                    status_code=401,
                )
            if response.status_code == 404:
                raise EachlabsError(
                    f"Eachlabs prediction {prediction_id} not found",
                    retryable=False,
                    status_code=404,
                )
            if response.status_code >= 500:
                raise EachlabsError(
                    f"Eachlabs server error ({response.status_code})",
                    retryable=True,
                    status_code=response.status_code,
                )

            if response.status_code != 200:
                raise EachlabsError(
                    f"Eachlabs unexpected poll status {response.status_code}",
                    retryable=True,
                    status_code=response.status_code,
                )

            try:
                data = response.json()
            except (json.JSONDecodeError, ValueError) as exc:
                raise EachlabsError(
                    f"Eachlabs poll response not JSON: {exc}",
                    retryable=True,
                ) from exc

            status = data.get("status", "").lower()
            poll_count += 1

            if status == "succeeded":
                output_url = data.get("output")
                if not output_url:
                    raise EachlabsError(
                        "Eachlabs success response missing output URL",
                        retryable=True,
                    )
                logger.info(
                    "eachlabs_vton_success",
                    prediction_id=prediction_id,
                    elapsed_seconds=elapsed,
                    poll_attempts=poll_count,
                )
                return EachlabsVtonResult(
                    image_url=output_url,
                    elapsed_seconds=elapsed,
                    prediction_id=prediction_id,
                )

            if status == "failed":
                error_msg = data.get("error", "Unknown error")
                # User-facing message (real error, not fake success)
                logger.warning(
                    "eachlabs_vton_failed",
                    prediction_id=prediction_id,
                    error=error_msg,
                    poll_attempts=poll_count,
                )
                raise EachlabsError(
                    f"Eachlabs job failed: {error_msg}",
                    retryable=False,  # Don't retry a failed job
                )

            if status not in ("processing", ""):
                logger.warning(
                    "eachlabs_vton_unknown_status",
                    prediction_id=prediction_id,
                    status=status,
                )

            # Still processing — wait and retry
            await asyncio.sleep(self.POLL_INTERVAL_SECONDS)


# Singleton instance for the provider
_eachlabs_client: Optional[EachlabsVtonClient] = None


def get_eachlabs_client() -> EachlabsVtonClient:
    """Get or create the singleton Eachlabs client."""
    global _eachlabs_client
    if _eachlabs_client is None:
        _eachlabs_client = EachlabsVtonClient()
    return _eachlabs_client
