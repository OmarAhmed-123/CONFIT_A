"""Feature 07 — Brand Portal product auto-tagging (server-side).

Orchestrates the honest tagging flow for a brand's own product:

    POST /partner/products/{id}/auto-tag   (also /brand/ alias)

Ownership: the product must belong to the caller's brand tenant — the same
``_resolve_brand`` / brand_id discipline every other brand-portal route
uses. A foreign product id is 404, never tagged, never leaked.

Merge policy (AI assists, the brand stays in charge):
  * style_tags / occasion_tags — UNION with the AI suggestions: existing
    human tags are never removed, AI tags are appended once.
  * color_family / material — filled only when the column is empty or its
    shipped default; a value the brand already set is KEPT and reported as
    ``kept_existing``. An AI suggestion never silently overwrites human
    data.
  * platform_category — a SUGGESTION in the response only; the category
    column is never mutated (it drives catalogue routing).
  * dry_run=true runs the models and reports what WOULD change, writing
    nothing.

Everything the product columns cannot carry (per-tag provenance,
confidence, unresolved axes, model licenses) rides on the response so the
portal can show it — nothing is silently dropped.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.models.catalog import Product
from backend.app.models.user import User
from backend.app.providers.tagging_provider import TaggingProvider
from backend.app.services.brand_service import BrandService


class ProductTaggingService:
    def __init__(self, db: Session, provider: Optional[TaggingProvider] = None):
        self.db = db
        self.brands = BrandService(db)
        self.provider = provider or TaggingProvider()

    # ── public API ───────────────────────────────────────────────────
    async def auto_tag_product(
        self,
        user: User,
        product_id: int,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        brand = self.brands._resolve_brand(user)
        product = (
            self.db.query(Product).filter(Product.id == product_id).first()
        )
        if product is None or product.brand_id != brand.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found in your catalogue.",
            )

        # The product must give the models SOMETHING to work with.
        has_image = bool(product.thumbnail_url)
        has_text = bool(product.title or product.description
                        or product.title_ar or product.description_ar)
        if not has_image and not has_text:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="This product has neither an image nor a description to tag.",
            )

        result = await self.provider.tag_product(
            image_url=product.thumbnail_url if has_image else None,
            title=product.title or "",
            description=product.description or "",
            title_ar=product.title_ar or "",
            description_ar=product.description_ar or "",
        )

        if not result.get("tagging_available"):
            reason = str(result.get("reason", "tagging_unavailable"))
            guidance = str(result.get("guidance", "")) or (
                "Auto-tagging is unavailable right now. Please try again later."
            )
            if reason.startswith("worker_refused:"):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "error": {
                            "code": reason.split(":", 1)[1],
                            "message": guidance,
                        }
                    },
                )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": {
                        "code": "TAGGING_UNAVAILABLE",
                        "message": guidance,
                        "reason": reason,
                    }
                },
            )

        suggestions = result.get("product_suggestions", {})
        applied = self._apply_suggestions(product, suggestions, dry_run=dry_run)

        return {
            "status": "success",
            "product_id": product.id,
            "dry_run": dry_run,
            "quality": result.get("quality"),
            "tag_count": result.get("tag_count"),
            "tags": result.get("tags", []),
            "axes_unresolved": result.get("axes_unresolved", []),
            "product_suggestions": suggestions,
            "applied": applied["applied"],
            "skipped": applied["skipped"],
            "models": result.get("models"),
            "disclaimer": result.get("disclaimer"),
            "timings": result.get("timings"),
            "backend_call_seconds": result.get("backend_call_seconds"),
        }

    # ── internals ────────────────────────────────────────────────────
    def _apply_suggestions(
        self, product: Product, suggestions: Dict[str, Any], *, dry_run: bool
    ) -> Dict[str, List[Dict[str, str]]]:
        """Merge AI suggestions into the product columns under the
        documented policy. Returns exactly what was applied and what was
        skipped (with reasons) — the audit trail of the change."""
        applied: List[Dict[str, str]] = []
        skipped: List[Dict[str, str]] = []

        def _json_list(raw: str) -> List[str]:
            try:
                v = json.loads(raw or "[]")
                return v if isinstance(v, list) else []
            except (ValueError, TypeError):
                return []

        # 1. style_tags / occasion_tags: union merge (append-only)
        for column, key in (("style_tags", "style_tags"),
                            ("occasion_tags", "occasion_tags")):
            ai_tags = suggestions.get(key)
            if not isinstance(ai_tags, list) or not ai_tags:
                continue
            current = _json_list(getattr(product, column))
            fresh = [t for t in ai_tags if t not in current]
            if not fresh:
                skipped.append({"field": column, "reason": "already_present"})
                continue
            merged = current + fresh
            if not dry_run:
                setattr(product, column, json.dumps(merged))
            applied.append({"field": column, "values": fresh})

        # 2. color_family / material: fill only when empty — never overwrite
        #    a value the brand already curated.
        for column, key in (("color_family", "color_family"),
                            ("material", "material")):
            value = suggestions.get(key)
            if value is None:
                continue
            existing = (getattr(product, column) or "").strip()
            if existing:
                skipped.append({
                    "field": column,
                    "reason": "kept_existing",
                    "existing": existing,
                    "suggestion": str(value),
                })
                continue
            if not dry_run:
                setattr(product, column, str(value))
            applied.append({"field": column, "values": [str(value)]})

        if applied and not dry_run:
            self.db.commit()

        # platform_category is a suggestion only — never applied to the
        # category column (catalogue routing is not the model's call).
        if suggestions.get("platform_category"):
            skipped.append({
                "field": "category",
                "reason": "suggestion_only",
                "suggestion": suggestions["platform_category"],
            })
        return {"applied": applied, "skipped": skipped}
