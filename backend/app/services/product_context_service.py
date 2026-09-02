"""Product-page context: fit, style match, BNPL teaser, complete-the-look.

Reuses NoPhotoFitService, StylingEngine, BNPLProvider, and the catalog —
does not invent a second recommendation or fit engine.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.models.catalog import Product
from backend.app.models.user import User
from backend.app.providers.bnpl_provider import BNPLProvider
from backend.app.providers.payment.capability_registry import MarketPaymentCapabilityRegistry
from backend.app.repositories.catalog_repository import CatalogRepository
from backend.app.repositories.profile_repository import ProfileRepository
from backend.app.services.no_photo_fit_service import NoPhotoFitService
from backend.app.services.styling_engine import StylingEngine


def _parse_json_list(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
        if isinstance(value, list):
            return [str(x).lower() for x in value]
    except (TypeError, ValueError):
        return []
    return []


class ProductContextService:
    def __init__(self, db: Session):
        self.db = db
        self.catalog_repo = CatalogRepository(db)
        self.profile_repo = ProfileRepository(db)
        self.fit_service = NoPhotoFitService(db)

    def enrich_product(self, product: Product, user: Optional[User]) -> Dict[str, Any]:
        profile = None
        body = {}
        if user is not None:
            profile = self.profile_repo.get_by_user_id(user.id)
            if profile:
                body = self.profile_repo.get_decrypted_body_data(profile)

        fit = self._fit_recommendation(product, profile, body)
        style = self._style_compatibility(product, profile)
        bnpl = self._bnpl_teaser(product)
        related = self._complete_the_look(product)
        return {
            "ai_fit_score": fit.get("score"),
            "recommended_size": fit.get("recommended_size"),
            "recommended_size_available": fit.get("recommended_size_available"),
            "fit_reasoning": fit.get("reasoning"),
            "fit_available": fit.get("available", False),
            "style_compatibility_score": style.get("score"),
            "style_compatibility_available": style.get("available", False),
            "style_compatibility_reason": style.get("reason"),
            "bnpl": bnpl,
            "related_outfits": related,
        }

    def _fit_recommendation(
        self,
        product: Product,
        profile: Any,
        body: Dict[str, Any],
    ) -> Dict[str, Any]:
        available_sizes = [s.size for s in (product.skus or []) if s.is_in_stock and s.stock_level > 0]
        if not available_sizes:
            available_sizes = [s.size for s in (product.skus or [])]

        height = body.get("height_cm")
        weight = body.get("weight_kg")
        preferred_size = None
        if profile is not None:
            preferred_size = profile.size_tops or profile.size_bottoms

        if height and weight:
            result = self.fit_service.calculate_fit(
                product_id=product.id,
                height_cm=float(height),
                weight_kg=float(weight),
                body_shape=body.get("body_shape") or (profile.body_shape_tag if profile else "regular") or "regular",
                chest_cm=body.get("chest_cm"),
                waist_cm=body.get("waist_cm"),
                hip_cm=body.get("hip_cm"),
                preferred_fit=(profile.fit_preference if profile else None) or "regular",
            )
            rec = result["recommended_size"]
            available = rec in available_sizes
            fallback = rec
            if not available and available_sizes:
                # Pick the closest listed size rather than inventing stock.
                order = ["XS", "S", "M", "L", "XL", "XXL"]
                if rec in order:
                    idx = order.index(rec)
                    candidates = [s for s in order if s in available_sizes]
                    fallback = min(candidates, key=lambda s: abs(order.index(s) - idx)) if candidates else available_sizes[0]
                else:
                    fallback = available_sizes[0]
            score = int(result.get("confidence_score") or 0)
            if not available:
                score = max(40, score - 25)
            return {
                "available": True,
                "score": score,
                "recommended_size": rec,
                "recommended_size_available": available,
                "reasoning": (
                    result.get("brand_sizing_tendency")
                    if available
                    else f"Recommended size {rec} is not currently in stock. Closest available: {fallback}."
                ),
            }

        if preferred_size:
            available = preferred_size in available_sizes
            return {
                "available": True,
                "score": 88 if available else 55,
                "recommended_size": preferred_size,
                "recommended_size_available": available,
                "reasoning": (
                    f"Based on your saved size ({preferred_size})."
                    if available
                    else f"Your saved size {preferred_size} is not in stock for this garment."
                ),
            }

        return {
            "available": False,
            "score": None,
            "recommended_size": None,
            "recommended_size_available": None,
            "reasoning": None,
        }

    def _style_compatibility(self, product: Product, profile: Any) -> Dict[str, Any]:
        if profile is None or not profile.onboarding_completed:
            return {
                "available": False,
                "score": None,
                "reason": "Complete your style profile to see a personal match score.",
            }

        user_styles = set(_parse_json_list(profile.style_archetypes) + _parse_json_list(profile.fashion_aesthetics))
        user_colors = set(_parse_json_list(profile.preferred_colors))
        avoided = set(_parse_json_list(profile.avoided_colors))
        product_styles = set(_parse_json_list(product.style_tags) + _parse_json_list(product.occasion_tags))
        product_color = (product.color_family or "").lower()

        if not user_styles and not user_colors:
            return {
                "available": False,
                "score": None,
                "reason": "Your style profile does not yet have enough attributes to score this piece.",
            }

        style_overlap = 0.0
        if user_styles and product_styles:
            style_overlap = len(user_styles & product_styles) / max(len(user_styles), 1)
        elif user_styles:
            # No product tags: cannot honestly claim a high match.
            style_overlap = 0.0

        color_score = 0.5
        if user_colors:
            color_score = 1.0 if any(c in product_color for c in user_colors) else 0.35
        if avoided and any(c in product_color for c in avoided):
            color_score = 0.15

        brands = _parse_json_list(profile.preferred_brands)
        blacklisted = _parse_json_list(profile.blacklisted_brands)
        brand_name = (product.brand.brand_name if product.brand else "").lower()
        brand_score = 0.7
        if brands and brand_name in brands:
            brand_score = 1.0
        if blacklisted and brand_name in blacklisted:
            return {
                "available": True,
                "score": 8,
                "reason": "This brand is on your avoided list.",
            }

        # Weighted, no artificial floor — a mismatch scores genuinely low.
        composite = int(round(100 * (0.55 * style_overlap + 0.30 * color_score + 0.15 * brand_score)))
        composite = max(0, min(100, composite))
        if not product_styles:
            return {
                "available": False,
                "score": None,
                "reason": "This product does not have enough style metadata to score.",
            }
        return {
            "available": True,
            "score": composite,
            "reason": "Match against your saved archetypes, colours, and brand preferences.",
        }

    def _bnpl_teaser(self, product: Product) -> Dict[str, Any]:
        market = (settings.MARKET or "EG").upper()
        capabilities = MarketPaymentCapabilityRegistry.get_capabilities_for_market(market)
        bnpl_methods = [m for m in capabilities.available_methods if m.installment_available]
        default_name = (settings.BNPL_DEFAULT_PROVIDER or "tabby").lower()
        chosen = next((m for m in bnpl_methods if default_name in m.id), None) or (
            bnpl_methods[0] if bnpl_methods else None
        )
        if not chosen:
            return {"eligible": False, "provider": None, "installment_amount": None, "installments_count": 0}

        price = float(product.base_price)
        provider = BNPLProvider(provider_name=chosen.provider_name)
        # Quote is computed from the real price and provider rules (sync fallback).
        quote = provider.quote_sync(amount=price, currency=product.currency or capabilities.currency_code)
        quote["market"] = market
        quote["method_id"] = chosen.id
        return quote

    def _complete_the_look(self, product: Product) -> List[Dict[str, Any]]:
        """Companion items from the live catalog via the existing outfit composer."""
        in_stock = [
            p
            for p in self.catalog_repo.filter_products(limit=80, offset=0)
            if p.is_active and any(s.is_in_stock and s.stock_level > 0 for s in (p.skus or []))
        ]
        if not in_stock:
            return []

        occasions = _parse_json_list(product.occasion_tags)
        occasion = occasions[0].replace("_", " ").title() if occasions else "Smart Casual"
        intent = StylingEngine.parse_intent(
            prompt=f"complete the look with {product.title}",
            occasion_hint=occasion,
            budget_hint=None,
        )
        outfits = StylingEngine.compose_outfits(
            available_products=in_stock,
            intent=intent,
            user_profile=None,
            max_outfits=2,
        )
        by_id = {p.id: p for p in in_stock}
        related: List[Dict[str, Any]] = []
        for outfit in outfits:
            items = []
            for item in outfit.get("items") or []:
                pid = item.get("product_id")
                if pid == product.id:
                    continue
                companion = by_id.get(pid)
                items.append(
                    {
                        "product_id": pid,
                        "product_title": item.get("product_title") or item.get("title"),
                        "brand_name": item.get("brand_name"),
                        "category_name": item.get("category_name") or item.get("position"),
                        "price": item.get("price"),
                        "image_url": item.get("image_url"),
                        "slug": companion.slug if companion else item.get("slug"),
                        "position": item.get("position"),
                    }
                )
            if not items:
                continue
            related.append(
                {
                    "title": outfit.get("title") or "Complete the look",
                    "occasion": outfit.get("occasion") or occasion,
                    "compatibility_score": outfit.get("compatibility_score"),
                    "items": items[:4],
                }
            )
        return related[:2]
