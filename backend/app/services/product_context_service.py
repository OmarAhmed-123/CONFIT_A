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
from backend.app.services.capability_service import bnpl_is_live
from backend.app.providers.payment.capability_registry import MarketPaymentCapabilityRegistry
from backend.app.core.exceptions import EncryptionError
from backend.app.core.logging import logger
from backend.app.repositories.catalog_repository import CatalogRepository
from backend.app.repositories.profile_repository import ProfileRepository
from backend.app.services.no_photo_fit_service import NoPhotoFitService
from backend.app.services.fit.units import (
    BodyMeasurements,
    MeasurementValidationError,
    UnitSystem,
)
from backend.app.services.styling_engine import StylingEngine


def _as_float(value: Any) -> Optional[float]:
    """Coerce a stored profile value to float, or None when it is not a number.

    Encrypted body payloads are free-form JSON written over several app
    versions, so a field can legitimately be a string, null or missing.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
                try:
                    body = self.profile_repo.get_decrypted_body_data(profile)
                except EncryptionError:
                    # AUDIT-2026-09-06 P0 regression: a body blob encrypted under
                    # a rotated key used to raise here and 500 EVERY authenticated
                    # product-detail request. Product browsing must not collapse
                    # because an optional fit enrichment cannot run. Degrade
                    # honestly: no body measurements are used (empty dict), fit
                    # falls back to the user's saved size or reports
                    # fit_available=False — never a fabricated fit. Owner-facing
                    # profile endpoints still raise (G1.BODY-02 integrity).
                    logger.error(
                        "Body-data decryption failed during product enrichment — "
                        "serving product without body-based fit context",
                        user_id=user.id,
                        product_id=product.id,
                    )
                    body = {}

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
        """PDP size hint — the SAME engine the Fit Finder page uses.

        Rewritten 2026-09-21 with the Fit Finder remediation. The previous
        version had two defects that this one removes:

        * it called the sizing service and then, when the answer was out of
          stock, substituted "the closest listed size" of its own invention —
          a different size than the engine computed, presented with the
          engine's authority. Stock is now an engine input, so the recommended
          size is in stock by construction and no second opinion is fabricated.
        * it degraded an out-of-stock answer to ``max(40, score - 25)``, an
          arbitrary number unrelated to fit quality.

        Duplicating sizing logic here would also violate DRY and let the PDP
        and the Fit Finder page disagree about the same garment — the exact
        class of inconsistency the audit asked us to close.
        """
        available_sizes = [
            s.size for s in (product.skus or []) if s.is_in_stock and (s.stock_level or 0) > 0
        ]
        preferred_size = None
        if profile is not None:
            preferred_size = profile.size_tops or profile.size_bottoms

        height = body.get("height_cm")
        if height:
            try:
                measurements = BodyMeasurements.from_payload(
                    units=UnitSystem.METRIC,
                    height=float(height),
                    weight=_as_float(body.get("weight_kg")),
                    chest=_as_float(body.get("chest_cm")),
                    waist=_as_float(body.get("waist_cm")),
                    hip=_as_float(body.get("hip_cm")),
                    shoulder=_as_float(body.get("shoulder_width_cm")),
                    inseam=_as_float(body.get("inseam_cm")),
                    body_shape=body.get("body_shape")
                    or (profile.body_shape_tag if profile else None),
                )
            except MeasurementValidationError:
                # Stored profile data is out of range: surface no fit rather
                # than a fit computed from impossible numbers.
                logger.warning(
                    "Stored body measurements are out of range — skipping PDP fit hint",
                    product_id=product.id,
                )
                measurements = None

            if measurements is not None:
                result = self.fit_service.calculate_fit(
                    product_id=product.id,
                    units="metric",
                    height=measurements.height_cm,
                    weight=measurements.weight_kg,
                    chest=measurements.chest_cm,
                    waist=measurements.waist_cm,
                    hip=measurements.hip_cm,
                    shoulder=measurements.shoulder_cm,
                    inseam=measurements.inseam_cm,
                    body_shape=measurements.body_shape,
                    preferred_fit=(profile.fit_preference if profile else None) or "regular",
                )
                if result.get("recommended"):
                    return {
                        "available": True,
                        "score": int(result.get("confidence_score") or 0),
                        "recommended_size": result["recommended_size"],
                        # True by construction: the engine only ranks sellable sizes.
                        "recommended_size_available": True,
                        "reasoning": result.get("confidence_disclosure"),
                    }
                # The engine declined. Say so instead of guessing a size.
                return {
                    "available": False,
                    "score": None,
                    "recommended_size": None,
                    "recommended_size_available": None,
                    "reasoning": result.get("confidence_disclosure"),
                }

        if preferred_size:
            available = preferred_size in available_sizes
            return {
                "available": True,
                # A saved size is the user's own statement, not a measurement:
                # it carries no fit score of ours.
                "score": None,
                "recommended_size": preferred_size,
                "recommended_size_available": available,
                "reasoning": (
                    f"Based on the size you saved to your profile ({preferred_size}), "
                    "not on a measurement-based calculation."
                    if available
                    else f"Your saved size {preferred_size} is not in stock for this garment."
                ),
            }

        return {
            "available": False,
            "score": None,
            "recommended_size": None,
            "recommended_size_available": None,
            "reasoning": (
                "Add your measurements in Fit Finder to see a size recommendation for this item."
            ),
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
        """The instalment line on the product page.

        Until 2026-09-23 this published a lender's name unconditionally. The
        quote is computed locally (``BNPLProvider.quote_sync`` — no provider is
        contacted; see its ``_fetch_remote_quote``), so production told shoppers
        "4 payments of 72.25 USD with Tabby" while the deployment had no Tabby
        key, no live PSP adapter, ``payments_mode=demo`` and ``bnpl_live=false``.
        A named lender's offer that the lender never made is a false claim, not
        a teaser.

        Now the brand is attached only when ``bnpl_is_live()`` — the same
        authority the capability flags and the health probe read. Otherwise the
        split is published as an explicitly-labelled estimate with no lender
        attribution and a disclosure that instalments are not enabled, so the
        shopper sees the same fact the trust footer states.
        """
        market = (settings.MARKET or "EG").upper()
        capabilities = MarketPaymentCapabilityRegistry.get_capabilities_for_market(market)
        bnpl_methods = [m for m in capabilities.available_methods if m.installment_available]
        default_name = (settings.BNPL_DEFAULT_PROVIDER or "tabby").lower()
        chosen = next((m for m in bnpl_methods if default_name in m.id), None) or (
            bnpl_methods[0] if bnpl_methods else None
        )
        if not chosen:
            return {"eligible": False, "provider": None, "installment_amount": None, "installments_count": 0}

        provider = BNPLProvider(provider_name=chosen.provider_name)
        # Quote is computed from the real Decimal price and provider rules (sync fallback).
        quote = provider.quote_sync(amount=product.base_price, currency=product.currency or capabilities.currency_code)
        quote["market"] = market
        quote["method_id"] = chosen.id

        live = bnpl_is_live()
        quote["is_estimate"] = not live
        if live:
            # A real offer: the provider is named because the provider stands behind it.
            quote["disclaimer"] = (
                f"Split in {quote.get('installments_count')} interest-free payments of "
                f"{quote.get('installment_amount')} {product.currency or capabilities.currency_code} "
                f"with {chosen.provider_name.title()}."
            )
        else:
            # No lender is named: it has offered nothing here.
            quote["provider"] = None
            quote["disclaimer"] = (
                "Illustrative only — instalment payments are not enabled on this "
                "deployment, so this is not an offer and not a payment plan."
            )
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
