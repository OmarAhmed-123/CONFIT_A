"""watsonx.ai vision tier for wardrobe auto-tagging.

Returns the same envelope the rest of the wardrobe pipeline already consumes
(``analysis_available``, ``category`` … ``confidence``) so
``WardrobeService._run_ai_analysis`` and ``wardrobe_taxonomy.
normalize_wardrobe_analysis`` work unchanged. Additionally sets
``analysis_source`` to the model id that REALLY answered (FR-18 honesty).

Image handling: the stored photo is decoded with Pillow, EXIF-oriented,
downscaled to ``MAX_EDGE`` px and re-encoded as JPEG before it is base64'd.
That keeps requests small (a 15 MB phone photo would otherwise be sent as a
20 MB data URL) without losing garment detail at the resolution a VLM uses.
"""
from __future__ import annotations

import base64
import binascii
import io
import json
import re
from typing import Any, Dict, Optional, Tuple

from PIL import Image, ImageOps, UnidentifiedImageError

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.providers.watsonx import client as _client_mod
from backend.app.providers.watsonx.client import WatsonxClient, WatsonxError, WatsonxNotConfiguredError
from backend.app.providers.watsonx.prompts import VISION_PROMPT_VERSION, WARDROBE_VISION_PROMPT

MAX_EDGE = 1024
JPEG_QUALITY = 85
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def prepare_image_data_url(data_url_or_bytes: Any) -> Tuple[str, Dict[str, Any]]:
    """Validate + downscale an image and return ``(jpeg_data_url, info)``.

    Accepts raw bytes or a ``data:image/...;base64,`` URL. Raises ``ValueError``
    for anything that is not a decodable JPEG/PNG/WebP image.
    """
    if isinstance(data_url_or_bytes, (bytes, bytearray)):
        raw = bytes(data_url_or_bytes)
    elif isinstance(data_url_or_bytes, str) and data_url_or_bytes.startswith("data:image"):
        try:
            raw = base64.b64decode(data_url_or_bytes.split(",", 1)[1], validate=False)
        except (IndexError, binascii.Error, ValueError) as exc:
            raise ValueError("image data URL is not valid base64") from exc
    else:
        raise ValueError("image must be bytes or a data:image/... URL")

    try:
        with Image.open(io.BytesIO(raw)) as im:
            fmt = (im.format or "").upper()
            if fmt not in ("JPEG", "PNG", "WEBP"):
                raise ValueError(f"unsupported image format {fmt or 'unknown'}")
            im = ImageOps.exif_transpose(im)
            original = im.size
            im = im.convert("RGB")
            im.thumbnail((MAX_EDGE, MAX_EDGE))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            resized = im.size
    except UnidentifiedImageError as exc:
        raise ValueError("file is not a readable image") from exc
    jpeg = buf.getvalue()
    info = {"original_size": original, "sent_size": resized, "sent_bytes": len(jpeg), "source_format": fmt}
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii"), info


def parse_vision_json(text: str) -> Dict[str, Any]:
    """Tolerant-but-strict JSON extraction: strips markdown fences and any
    prose around the first ``{…}`` block, then requires a JSON object."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty model response")
    cleaned = _FENCE_RE.sub("", text.strip()).strip()
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("model response contains no JSON object")
        try:
            obj = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError("model response is not valid JSON") from exc
    if not isinstance(obj, dict):
        raise ValueError("model response is not a JSON object")
    return obj


class WatsonxVisionProvider:
    """Analyse one wardrobe photo with the configured watsonx vision model."""

    def __init__(self, client: Optional[WatsonxClient] = None, model_id: Optional[str] = None):
        # Late-bound lookup so tests (and operators hot-swapping config) can
        # replace the process client without re-importing this module.
        self._client = client or _client_mod.get_watsonx_client()
        self.model_id = model_id or settings.WATSONX_VISION_MODEL_ID

    def is_configured(self) -> bool:
        return self._client.configured

    async def analyze_wardrobe_image(self, image: Any) -> Dict[str, Any]:
        """Never raises for service problems: returns ``analysis_available=False``
        with a stable ``reason`` so the service layer can mark the item
        failed/retryable. Raises ``ValueError`` only for an unreadable image
        (a validation failure, not a provider one)."""
        if not self.is_configured():
            return {"analysis_available": False, "reason": WatsonxNotConfiguredError.code,
                    "analysis_source": None}
        data_url, info = prepare_image_data_url(image)
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": WARDROBE_VISION_PROMPT},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }]
        try:
            result = await self._client.chat(
                model_id=self.model_id, messages=messages, max_tokens=500, temperature=0.0,
            )
        except WatsonxError as exc:
            logger.warn("watsonx_vision_failed", code=exc.code, status=exc.status, model_id=self.model_id)
            return {"analysis_available": False, "reason": exc.code, "retryable": exc.retryable,
                    "analysis_source": None}

        try:
            parsed = parse_vision_json(result.content)
        except ValueError as exc:
            logger.warn("watsonx_vision_malformed_output", model_id=result.model_id, error=str(exc),
                        sample=result.content[:120])
            return {"analysis_available": False, "reason": "watsonx_vision_malformed_output",
                    "retryable": True, "analysis_source": result.model_id}

        parsed["analysis_available"] = True
        parsed["analysis_source"] = result.model_id
        parsed["analysis_prompt_version"] = VISION_PROMPT_VERSION
        parsed["analysis_latency_seconds"] = result.latency_seconds
        parsed["image_sent"] = info
        logger.info("watsonx_vision_ok", model_id=result.model_id, latency=result.latency_seconds,
                    category=parsed.get("category"), tokens=result.usage.get("total_tokens"))
        return parsed
