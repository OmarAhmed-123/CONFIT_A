"""Deterministic upload validation must run BEFORE the content-safety model.

Regression for a live observation (2026-10-26): with the NVIDIA safety
classifier configured, a 16 MB upload was forwarded to the classifier, which
choked on it, and the user received a generic 503 "safety screening
unavailable" instead of the contract's 422 "Image exceeds the 15MB size limit".
"""
from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from backend.app.controllers.wardrobe_controller import _require_safe_image
from backend.app.services.wardrobe_service import MAX_IMAGE_BYTES


def _configured_service() -> MagicMock:
    svc = MagicMock()
    svc.configured = True
    svc.check_image = AsyncMock()
    return svc


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "blob, mime",
    [
        (b"\xff\xd8" + b"\0" * (MAX_IMAGE_BYTES + 1), "image/jpeg"),  # oversized
        (b"", "image/jpeg"),  # empty
        (b"GIF89a" + b"\0" * 64, "image/gif"),  # unsupported type
        (b"definitely-not-an-image", "image/png"),  # undecodable bytes
    ],
)
async def test_invalid_uploads_never_reach_the_safety_classifier(blob: bytes, mime: str) -> None:
    svc = _configured_service()
    await _require_safe_image(blob, mime, user_id=1, service=svc)
    svc.check_image.assert_not_awaited()


@pytest.mark.asyncio
async def test_valid_image_is_still_screened() -> None:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 30, 30)).save(buf, format="JPEG")
    svc = _configured_service()
    verdict = MagicMock(measured=True, should_block=False)
    svc.check_image.return_value = verdict
    await _require_safe_image(buf.getvalue(), "image/jpeg", user_id=1, service=svc)
    svc.check_image.assert_awaited_once()
