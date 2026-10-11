"""Eachlabs Bria VTON provider adapter for the CONFIT VTON pipeline.

Integrates with the project's registry and honest-failure contract:
- Returns VtonRenderError with retryable classification
- No fake success or cached results
- Engine metadata included in the output
- Only supports on-model garments (requires_flatlay=False)
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.providers.vton.eachlabs_client import (
    EachlabsError,
    EachlabsVtonClient,
    get_eachlabs_client,
)
from backend.app.providers.vton.registry import GarmentCategory, VtonEngineSpec, VtonRenderError, VtonRenderResult


class EachlabsVtonProvider:
    """Adapter for Eachlabs Bria Virtual Try-On API.

    Honest contract:
    - Returns REAL try-on results from Eachlabs or raises VtonRenderError
    - Non-transient errors (bad input, auth) are retryable=False
    - Transient errors (timeout, server error) are retryable=True
    - No fabricated or cached results
    """

    ENGINE_KEY = "eachlabs_bria_vton"

    def __init__(self, timeout_seconds: float = 180.0):
        self.timeout_seconds = timeout_seconds
        self.client: EachlabsVtonClient = get_eachlabs_client()

    def is_configured(self) -> bool:
        """True only if API key is set."""
        api_key = (getattr(settings, "EACHLABS_API_KEY", None) or "").strip()
        return bool(api_key and len(api_key) > 10)

    async def render(
        self,
        person_image_url: str,
        garment_image_urls: list[str],
        instruction: Optional[str] = None,
        aspect_ratio: Optional[str] = None,
    ) -> VtonRenderResult:
        """Render a virtual try-on via Eachlabs.

        Args:
            person_image_url: URL of the person's photo
            garment_image_urls: List of garment URLs (up to 3)
            instruction: Optional styling direction
            aspect_ratio: Output aspect ratio (e.g., "9:16")

        Returns:
            VtonRenderResult with image URL and metadata

        Raises:
            VtonRenderError with retryable classification
        """
        if not self.is_configured():
            raise VtonRenderError(
                "Eachlabs not configured (missing EACHLABS_API_KEY)",
                engine=self.ENGINE_KEY,
                retryable=False,
            )

        start_time = time.time()

        # Validate inputs
        if not person_image_url or not isinstance(person_image_url, str):
            raise VtonRenderError(
                "Invalid person image URL",
                engine=self.ENGINE_KEY,
                retryable=False,
            )

        if not garment_image_urls or len(garment_image_urls) == 0:
            raise VtonRenderError(
                "No garment images provided",
                engine=self.ENGINE_KEY,
                retryable=False,
            )

        if len(garment_image_urls) > 3:
            garment_image_urls = garment_image_urls[:3]
            logger.info("eachlabs_truncated_garments_to_3")

        # Step 1: Submit job
        try:
            prediction_id = await self.client.submit_job(
                person_image_url=person_image_url,
                garment_image_urls=garment_image_urls,
                instruction=instruction,
                aspect_ratio=aspect_ratio,
            )
            logger.info(
                "eachlabs_job_submitted",
                prediction_id=prediction_id,
                garment_count=len(garment_image_urls),
            )
        except EachlabsError as exc:
            raise VtonRenderError(
                f"Eachlabs submit failed: {exc}",
                engine=self.ENGINE_KEY,
                retryable=exc.retryable,
            ) from exc

        # Step 2: Poll for completion
        try:
            result = await self.client.poll_job(
                prediction_id=prediction_id,
                timeout_seconds=self.timeout_seconds,
            )
        except EachlabsError as exc:
            raise VtonRenderError(
                f"Eachlabs poll failed: {exc}",
                engine=self.ENGINE_KEY,
                retryable=exc.retryable,
            ) from exc

        elapsed = time.time() - start_time

        # Return the result
        return VtonRenderResult(
            image_path=result.image_url,
            engine=self.ENGINE_KEY,
            license="Proprietary (Eachlabs Commercial API)",
            commercial=True,
            elapsed_seconds=elapsed,
            category="virtual_tryon",
        )
