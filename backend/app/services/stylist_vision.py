"""Mode A vision analysis for the StyleList stylist.

Asks a VISION model (the NVIDIA ``GARMENT_VISION`` role, walked through its
verified failover chain) what garments are in the shopper's photos. The model's
answer is treated as a CLAIM to be checked, not as a fact:

* the result is a plain dataclass with ``available`` and a ``reason``; a failed
  or unconfigured call is ``available=False`` and the caller falls back to Mode B
  with that reason shown. It never raises into the request path and never
  invents an analysis;
* colour words from the model are normalised onto the catalogue vocabulary and
  cross-checked against the deterministic pixel palette (see
  ``stylist_image_intake.extract_palette``). A model colour that the pixels do
  not support is marked uncertain rather than trusted.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.providers.nvidia import ImagePart, ModelRole, NvidiaClient
from backend.app.services.stylist_image_intake import ParsedImage

#: Dedicated client: one credential attempt per model. Worst case is
#: ``len(chain) * STYLIST_VISION_TIMEOUT_SECONDS``, which keeps a vision failure
#: from stacking key rotations on top of model failover.
_vision_client = NvidiaClient(key_attempts=1)

_SYSTEM = (
    "You are a fashion garment analyst. Look at the photo and list the clothing and "
    "accessories that are clearly visible. Reply with ONLY a JSON object of this "
    'exact shape: {"garments":[{"category":"top|bottom|outerwear|dress|footwear|accessory",'
    '"description":"short phrase","color_family":"one plain colour word"}],'
    '"summary":"one sentence about the overall look"}. Do not guess items you cannot see. '
    "Do not name brands."
)

_MAX_GARMENTS = 8
_CATEGORIES = {"top", "bottom", "outerwear", "dress", "footwear", "accessory"}


@dataclass
class GarmentObservation:
    category: str
    description: str
    color_family: Optional[str]  # None when the model gave no usable colour word
    #: Which attached photo (0-based, in upload order) this came from.
    image_index: Optional[int] = None


@dataclass
class VisionAnalysis:
    available: bool
    reason: Optional[str] = None
    engine: Optional[str] = None  # "NVIDIA <model id that actually served>"
    garments: List[GarmentObservation] = field(default_factory=list)
    summary: Optional[str] = None
    #: How many photos the shopper attached, and how many were actually analysed.
    #: A partial result says so; it is never presented as the full set.
    images_total: int = 0
    images_analysed: int = 0
    #: One entry per photo: {"index", "analysed", "summary"} (no image content).
    per_image: List[Dict[str, Any]] = field(default_factory=list)

    def to_public(self) -> Dict[str, Any]:
        return {
            "available": self.available,
            "reason": self.reason,
            "engine": self.engine,
            "summary": self.summary,
            "images_total": self.images_total,
            "images_analysed": self.images_analysed,
            "per_image": self.per_image,
            "garments": [
                {
                    "category": g.category,
                    "description": g.description,
                    "color_family": g.color_family,
                    "image_index": g.image_index,
                }
                for g in self.garments
            ],
        }


def _clean(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _parse_analysis(data: Dict[str, Any], engine: str) -> VisionAnalysis:
    raw_garments = data.get("garments")
    if not isinstance(raw_garments, list):
        return VisionAnalysis(available=False, reason="The image model returned an unreadable analysis.", engine=engine)
    garments: List[GarmentObservation] = []
    for item in raw_garments[:_MAX_GARMENTS]:
        if not isinstance(item, dict):
            continue
        category = _clean(item.get("category"), 20).lower()
        if category not in _CATEGORIES:
            continue
        colour = _clean(item.get("color_family"), 30).lower() or None
        garments.append(
            GarmentObservation(
                category=category,
                description=_clean(item.get("description"), 120),
                color_family=colour,
            )
        )
    return VisionAnalysis(
        available=True,
        engine=engine,
        garments=garments,
        summary=_clean(data.get("summary"), 400) or None,
    )


async def _analyse_one(image: ParsedImage, index: int, shopper_request: str) -> VisionAnalysis:
    """One photo, one vision request. Never raises."""
    import base64

    url = f"data:{image.mime};base64,{base64.b64encode(image.data).decode('ascii')}"
    user = (
        "Analyse the photo for a stylist. The shopper said: "
        f"{shopper_request[:400]!r}. Return the JSON object only."
    )
    try:
        parsed = await _vision_client.chat_json(
            ModelRole.GARMENT_VISION,
            system=_SYSTEM,
            user=user,
            images=[ImagePart(url=url)],
            timeout_s=settings.STYLIST_VISION_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 - every failure is an honest "unavailable"
        logger.warn(
            "stylist_vision_unavailable",
            image_index=index,
            error_type=type(exc).__name__,
            error=str(exc)[:200],
        )
        return VisionAnalysis(
            available=False,
            reason="The image analysis service did not answer for this photo.",
        )

    served = parsed.get("_model_id") or "unknown"
    engine = f"NVIDIA {served}"
    if not isinstance(parsed, dict):  # pragma: no cover - chat_json guarantees a dict
        return VisionAnalysis(available=False, reason="The image model returned an unreadable analysis.")
    result = _parse_analysis(parsed, engine)
    for garment in result.garments:
        garment.image_index = index
    return result


async def analyze_images(images: Sequence[ParsedImage], shopper_request: str) -> VisionAnalysis:
    """Analyse every attached photo, one vision request per photo. Never raises.

    WHY ONE REQUEST PER PHOTO. Measured 2026-10-10 against the live NVIDIA chain
    with the same two catalogue photos: a single request carrying BOTH images
    timed out at the 15s budget on both candidate models, while each photo alone
    answered in 3.7s and 5.0s with structured observations. Sending the photos in
    one request therefore silently lost them. Each photo is now analysed on its
    own, in parallel, and the observations are merged with their photo index.

    A partial result is reported as partial (images_analysed < images_total).
    It is never presented as an analysis of photos that failed.
    """
    total = len(images)
    if not images:
        return VisionAnalysis(available=False, reason="No images were attached.")
    if not settings.STYLIST_VISION_ENABLED:
        return VisionAnalysis(available=False, reason="Image styling is turned off on this deployment.", images_total=total)
    if not _vision_client.configured:
        return VisionAnalysis(available=False, reason="Image analysis is not configured on this deployment.", images_total=total)

    results = await asyncio.gather(
        *(_analyse_one(img, i, shopper_request) for i, img in enumerate(images))
    )

    per_image: List[Dict[str, Any]] = []
    garments: List[GarmentObservation] = []
    engines: List[str] = []
    summaries: List[str] = []
    for index, result in enumerate(results):
        per_image.append({
            "index": index,
            "analysed": result.available,
            "summary": result.summary if result.available else None,
        })
        if result.available:
            garments.extend(result.garments)
            if result.engine:
                engines.append(result.engine)
            if result.summary:
                summaries.append(result.summary)

    analysed = sum(1 for r in results if r.available)
    if analysed == 0:
        return VisionAnalysis(
            available=False,
            reason="The image analysis service did not answer for any of your photos, so this reply uses your text request only.",
            images_total=total,
            images_analysed=0,
            per_image=per_image,
        )
    reason = None
    if analysed < total:
        reason = f"Analysis worked for {analysed} of {total} photos. The other photo(s) were not used."
    return VisionAnalysis(
        available=True,
        reason=reason,
        engine=engines[0] if engines else None,
        garments=garments,
        summary=" ".join(summaries)[:400] or None,
        images_total=total,
        images_analysed=analysed,
        per_image=per_image,
    )


def stylist_model_routing_report() -> Dict[str, Any]:
    """Credential-free description of the models the stylist can use (STY-16).

    Lists model ids, whether each accepts images, the NAME of the environment variable
    that holds its key, and whether a usable credential exists. No key value is
    ever included.
    """
    from backend.app.providers.nvidia import get_chain
    from backend.app.providers.nvidia.keypool import key_pool

    def describe(role: ModelRole):
        rows = []
        for index, spec in enumerate(get_chain(role)):
            rows.append({
                "position": "primary" if index == 0 else f"failover_{index}",
                "model_id": spec.model_id,
                "supports_vision": bool(spec.supports_vision),
                "key_env": spec.slot_key_env,
                # True when a credential can be used for this model (its own slot
                # key, or the shared legacy key). The value is never reported.
                "credential_available": bool(key_pool.slot(spec.slot_key_env) or key_pool.configured),
            })
        return rows

    return {
        "stylist_text": describe(ModelRole.STYLIST_CHAT),
        "stylist_vision": describe(ModelRole.GARMENT_VISION),
        "vision_enabled": bool(settings.STYLIST_VISION_ENABLED),
        "vision_timeout_seconds": settings.STYLIST_VISION_TIMEOUT_SECONDS,
        "text_timeout_seconds": settings.AI_PROVIDER_TIMEOUT_SECONDS,
    }
