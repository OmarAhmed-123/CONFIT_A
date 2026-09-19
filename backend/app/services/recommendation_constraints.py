"""Structured, deterministic recommendation constraints for guided styling.

This module deliberately uses catalog/profile facts only. It does not call an
AI provider and does not manufacture fit confidence. Palette ranking is derived
from normalized catalog colour fields; fit support is limited to SKU-size
availability from an explicit request/profile size.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend.app.core.exceptions import ValidationDomainError


PALETTE_TAXONOMY: Dict[str, Tuple[str, ...]] = {
    "navy": ("navy", "blue", "midnight"),
    "black": ("black", "obsidian", "midnight"),
    "white": ("white", "ivory", "optic"),
    "gold": ("gold", "champagne", "metallic"),
    "green": ("green", "emerald"),
    "neutral": ("beige", "camel", "cream", "taupe", "ivory", "white", "grey", "gray", "black"),
    "earth": ("brown", "camel", "olive", "tan", "beige"),
}
SUPPORTED_FIT_PREFERENCES = {"slim", "regular", "relaxed", "oversized"}


@dataclass(frozen=True)
class RecommendationConstraints:
    palette: Optional[str] = None
    avoid_palette: Optional[str] = None
    preferred_fit: Optional[str] = None
    size_tops: Optional[str] = None
    size_bottoms: Optional[str] = None
    size_shoes: Optional[str] = None


def normalize_palette(value: Optional[str], *, field: str = "palette") -> Optional[str]:
    if value is None or str(value).strip() == "":
        return None
    key = str(value).strip().lower().replace(" ", "_").replace("&", " ")
    aliases = {
        "navy_blue": "navy",
        "midnight_blue": "navy",
        "midnight_black": "black",
        "optic_white": "white",
        "champagne_gold": "gold",
        "metallic_gold": "gold",
        "emerald_green": "green",
        "earth_tones": "earth",
        "neutrals": "neutral",
        "neutral_palette": "neutral",
    }
    key = aliases.get(key, key)
    if key not in PALETTE_TAXONOMY:
        raise ValidationDomainError(
            f"Unsupported {field}: {value!r}",
            field_errors={field: {"supported": sorted(PALETTE_TAXONOMY), "received": value}},
        )
    return key


def normalize_fit(value: Optional[str]) -> Optional[str]:
    if value is None or str(value).strip() == "":
        return None
    key = str(value).strip().lower().replace("tailored", "slim")
    if key not in SUPPORTED_FIT_PREFERENCES:
        raise ValidationDomainError(
            f"Unsupported preferred_fit: {value!r}",
            field_errors={"preferred_fit": {"supported": sorted(SUPPORTED_FIT_PREFERENCES), "received": value}},
        )
    return key


def constraints_from_payload(payload: Optional[Dict[str, Any]], profile: Any = None) -> RecommendationConstraints:
    payload = payload or {}
    palette = normalize_palette(payload.get("palette") or payload.get("palette_preference"))
    avoid = normalize_palette(payload.get("avoid_palette") or payload.get("avoided_palette"), field="avoid_palette")
    if palette and avoid and palette == avoid:
        raise ValidationDomainError(
            "palette and avoid_palette cannot be the same",
            field_errors={"palette": palette, "avoid_palette": avoid},
        )
    preferred_fit = normalize_fit(payload.get("preferred_fit") or getattr(profile, "fit_preference", None))
    return RecommendationConstraints(
        palette=palette,
        avoid_palette=avoid,
        preferred_fit=preferred_fit,
        size_tops=payload.get("size_tops") or getattr(profile, "size_tops", None),
        size_bottoms=payload.get("size_bottoms") or getattr(profile, "size_bottoms", None),
        size_shoes=payload.get("size_shoes") or getattr(profile, "size_shoes", None),
    )


def _product_color_text(product: Any) -> str:
    values = [getattr(product, "color_family", ""), getattr(product, "dominant_hex", "")]
    for sku in getattr(product, "skus", None) or []:
        values.extend([getattr(sku, "color", ""), getattr(sku, "color_hex", "")])
    return " ".join(str(v).lower() for v in values if v)


def _slot_for_product(product: Any) -> str:
    slug = (getattr(getattr(product, "category", None), "slug", "") or "").lower()
    name = (getattr(getattr(product, "category", None), "name", "") or "").lower()
    text = f"{slug} {name} {getattr(product, 'title', '')}".lower()
    if "shoe" in text or "footwear" in text:
        return "shoes"
    if "bottom" in text or "trouser" in text or "pant" in text:
        return "bottoms"
    if "dress" in text:
        return "dress"
    if "top" in text or "shirt" in text or "outer" in text or "blazer" in text or "jacket" in text:
        return "tops"
    return "other"


def _size_for_slot(c: RecommendationConstraints, slot: str) -> Optional[str]:
    if slot == "shoes":
        return c.size_shoes
    if slot == "bottoms":
        return c.size_bottoms
    if slot in {"tops", "dress"}:
        return c.size_tops
    return None


def _has_in_stock_size(product: Any, size: Optional[str]) -> Optional[bool]:
    if not size:
        return None
    wanted = str(size).strip().lower()
    skus = list(getattr(product, "skus", None) or [])
    if not skus:
        return None
    matching = [s for s in skus if str(getattr(s, "size", "")).strip().lower() == wanted]
    if not matching:
        return False
    return any(bool(getattr(s, "is_in_stock", False)) and int(getattr(s, "stock_level", 0) or 0) > 0 for s in matching)


def apply_constraints(products: Iterable[Any], constraints: RecommendationConstraints) -> Tuple[List[Any], Dict[str, Any]]:
    """Return deterministically ranked products and an explainable audit block."""
    scored = []
    matched_palette = 0
    avoided_penalties = 0
    fit_supported = 0
    fit_unavailable = 0
    palette_terms = PALETTE_TAXONOMY.get(constraints.palette or "", ())
    avoid_terms = PALETTE_TAXONOMY.get(constraints.avoid_palette or "", ())

    for p in products:
        score = 0
        reasons = []
        color_text = _product_color_text(p)
        if palette_terms and any(t in color_text for t in palette_terms):
            score += 100
            matched_palette += 1
            reasons.append("palette_match")
        if avoid_terms and any(t in color_text for t in avoid_terms):
            score -= 1000
            avoided_penalties += 1
            reasons.append("avoided_palette")
        slot = _slot_for_product(p)
        desired_size = _size_for_slot(constraints, slot)
        fit_result = _has_in_stock_size(p, desired_size)
        if fit_result is True:
            score += 40
            fit_supported += 1
            reasons.append("requested_size_in_stock")
        elif fit_result is False:
            score -= 60
            fit_unavailable += 1
            reasons.append("requested_size_unavailable")
        # stable catalog-quality tie breakers only
        score += float(getattr(p, "rating", 0) or 0)
        scored.append((score, getattr(p, "id", 0), p, reasons))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    for score, _pid, product, reasons in scored:
        setattr(product, "_constraint_reasons", reasons)
        setattr(product, "_constraint_score", score)
    meta = {
        "palette": constraints.palette,
        "avoid_palette": constraints.avoid_palette,
        "palette_authority": "catalog_color_family_and_sku_color",
        "palette_matches": matched_palette,
        "fit_preference": constraints.preferred_fit,
        "fit_authority": "sku_size_availability" if any([constraints.size_tops, constraints.size_bottoms, constraints.size_shoes]) else "none_without_size_profile",
        "fit_supported_products": fit_supported,
        "fit_unavailable_products": fit_unavailable,
        "ranking": "deterministic_constraints_then_existing_styling_rules",
    }
    return [p for *_rest, p, __ in scored], meta
