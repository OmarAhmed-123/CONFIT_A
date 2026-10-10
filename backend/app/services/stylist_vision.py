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


@dataclass
class VisionAnalysis:
    available: bool
    reason: Optional[str] = None
    engine: Optional[str] = None  # "NVIDIA <model id that actually served>"
    garments: List[GarmentObservation] = field(default_factory=list)
    summary: Optional[str] = None

    def to_public(self) -> Dict[str, Any]:
        return {
            "available": self.available,
            "reason": self.reason,
            "engine": self.engine,
            "summary": self.summary,
            "garments": [
                {
                    "category": g.category,
                    "description": g.description,
                    "color_family": g.color_family,
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


async def analyze_images(images: Sequence[ParsedImage], shopper_request: str) -> VisionAnalysis:
    """Analyse the shopper's images with the vision chain. Never raises."""
    if not images:
        return VisionAnalysis(available=False, reason="No images were attached.")
    if not settings.STYLIST_VISION_ENABLED:
        return VisionAnalysis(available=False, reason="Image styling is turned off on this deployment.")
    if not _vision_client.configured:
        return VisionAnalysis(available=False, reason="Image analysis is not configured on this deployment.")

    import base64

    urls = [
        f"data:{img.mime};base64,{base64.b64encode(img.data).decode('ascii')}" for img in images
    ]
    user = (
        "Analyse the photo(s) for a stylist. The shopper said: "
        f"{shopper_request[:400]!r}. Return the JSON object only."
    )
    try:
        parsed = await _vision_client.chat_json(
            ModelRole.GARMENT_VISION,
            system=_SYSTEM,
            user=user,
            images=[ImagePart(url=u) for u in urls],
            timeout_s=settings.STYLIST_VISION_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 - every failure is an honest "unavailable"
        logger.warn("stylist_vision_unavailable", error_type=type(exc).__name__, error=str(exc)[:200])
        return VisionAnalysis(
            available=False,
            reason="The image analysis service did not answer, so this reply uses your text request only.",
        )

    served = parsed.get("_model_id") or "unknown"
    engine = f"NVIDIA {served}"
    if not isinstance(parsed, dict):  # pragma: no cover - chat_json guarantees a dict
        return VisionAnalysis(available=False, reason="The image model returned an unreadable analysis.")
    return _parse_analysis(parsed, engine)


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
