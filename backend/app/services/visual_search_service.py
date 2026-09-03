from backend.app.core.logging import logger
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from backend.app.core.exceptions import ValidationDomainError
from backend.app.core.money import to_float
from backend.app.repositories.catalog_repository import CatalogRepository
from backend.app.repositories.tryon_repository import TryOnRepository
from backend.app.providers.tryon_provider import VisualSearchAIProvider


class VisualSearchService:
    """Production Visual Search & Style Matching Engine grounded in real database products."""

    def __init__(self, db: Session):
        self.db = db
        self.catalog_repo = CatalogRepository(db)
        self.tryon_repo = TryOnRepository(db)
        self.ai_provider = VisualSearchAIProvider()

    async def search_by_image(
        self,
        image_url: Optional[str] = None,
        image_base64: Optional[str] = None,
        user_id: Optional[int] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        brand_ids: Optional[List[int]] = None,
        in_stock_only: bool = True,
        limit: int = 24,
        session_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        target_img = image_url or image_base64
        if not target_img:
            raise ValidationDomainError("An image_url or image_base64 is required for visual search.")

        # 1. Vision AI Analysis (Extracts Category, Color, Texture, Style).
        #    When no vision model is configured the provider returns
        #    analysis_available=False and we degrade honestly — no fabricated
        #    "navy blazer" detection is invented.
        analysis = await self.ai_provider.analyze_fashion_image(target_img)
        analysis_available = bool(analysis.get("analysis_available"))
        detected_cat = analysis.get("detected_category")
        detected_col = analysis.get("detected_color")
        detected_pat = analysis.get("detected_pattern")
        detected_sty = analysis.get("detected_style")

        # 2. Retrieve real catalog products from database
        #    Filters are pushed into the DB query — not filtered on a sliced
        #    in-memory set — so they work across the whole catalogue.
        all_prods = self.catalog_repo.filter_products(
            min_price=min_price,
            max_price=max_price,
            brand_ids=brand_ids,
            in_stock_only=in_stock_only,
            limit=limit if isinstance(limit, int) and limit > 0 else 24,
        )

        # 3. Score real catalog items against what the vision model ACTUALLY
        #    detected — the old code hard-coded blazer/navy bonuses for every
        #    image, so any upload returned the same ranking.
        cat_tokens = [t for t in (detected_cat or "").lower().replace("&", " ").split() if len(t) > 2]
        col_tokens = [t for t in (detected_col or "").lower().split() if len(t) > 2]
        sty_tokens = [t.replace(" ", "_") for t in (detected_sty or "").lower().split("/") if t.strip()]

        scored_matches = []
        for p in all_prods:
            score = 50.0  # neutral base — ranking comes only from real signals
            p_cat = (p.category.name if p.category else "").lower()
            p_title = p.title.lower()
            p_color = (p.color_family or "").lower()
            p_tags = (p.style_tags or "").lower()

            if analysis_available:
                # Category match: detected category words against product category/title
                if any(t in p_cat or t in p_title for t in cat_tokens):
                    score += 30.0
                # Color family match
                if any(t in p_color for t in col_tokens):
                    score += 15.0
                # Style tag match
                if any(t in p_tags for t in sty_tokens):
                    score += 8.0

            score = min(98.0, round(score, 1))
            scored_matches.append((score, p))

        # Sort by similarity score descending
        scored_matches.sort(key=lambda x: x[0], reverse=True)

        # Honour the caller's requested result count (schema: top_k, 1..20). The
        # DB query above is already bounded by ``limit``; slicing here keeps the
        # response size consistent with the request instead of a hard-coded 8.
        result_limit = limit if isinstance(limit, int) and limit > 0 else 8
        matches = []
        for idx, (sim, p) in enumerate(scored_matches[:result_limit]):
            match_type = "Exact Match" if idx == 0 and sim >= 95 else ("Silhouette Match" if sim >= 88 else "Complementary Alternative")
            matches.append({
                "product_id": p.id,
                "title": p.title,
                "brand_name": p.brand.brand_name if p.brand else "CONFIT",
                # base_price is Numeric(12,2) -> Decimal since migration 0012.
                # Serialise through the canonical money helper: the response
                # schema and the persisted matches_json (json.dumps) both need
                # a JSON-native number; the authoritative value stays Decimal
                # in the database.
                "price": to_float(p.base_price),
                "image_url": p.thumbnail_url,
                "similarity_score": int(sim),
                "detected_color": p.color_family,
                "match_type": match_type
            })

        # 4. Log visual search query to database for telemetry & analytics
        log_image_ref = target_img if (image_url and len(target_img) < 2000) else "data:image/jpeg;base64,[Client Uploaded Vision Image]"
        logged = self.tryon_repo.log_visual_search(
            input_image_url=log_image_ref,
            user_id=user_id,
            detected_category=detected_cat,
            detected_color=detected_col,
            detected_pattern=detected_pat,
            detected_style=detected_sty,
            detected_attributes=analysis.get("detected_attributes", {}),
            matches=matches
        )

        # 4b. Instrument BrandAnalyticsEvent for visual_search view — real attribution signal
        try:
            from backend.app.repositories.brand_repository import BrandRepository
            brand_repo = BrandRepository(self.db)
            for m in matches[:3]:  # top 3 matches to avoid spam
                pid = m.get("product_id")
                if not pid:
                    continue
                prod = self.catalog_repo.get_product_by_id(pid) if hasattr(self.catalog_repo, 'get_product_by_id') else None
                # Fallback query product directly
                if not prod:
                    from backend.app.models.catalog import Product
                    prod = self.db.query(Product).filter(Product.id == pid).first()
                if not prod:
                    continue
                brand_repo.create_analytics_event(
                    brand_id=prod.brand_id,
                    event_type="view",
                    attribution_source="visual_search",
                    product_id=pid,
                    user_id=user_id,
                    # Browser session token enables guest -> authenticated
                    # attribution stitching at checkout (same X-Session-Token).
                    session_token=session_token,
                    outfit_id=None,
                    order_id=None,
                    revenue_amount=None,
                    event_metadata={"query_id": logged.id, "similarity": m.get("similarity_score")},
                    idempotency_key=f"vs_view_{logged.id}_{pid}"
                )
        except Exception as exc:
            # The search result itself is still valid, but a lost VIEW event
            # means a later purchase of this product cannot be attributed to
            # visual search. Roll back the failed instrumentation, log it
            # loudly with the query id, and continue — never silently.
            self.db.rollback()
            logger.error(
                "visual_search_attribution_event_failed",
                query_id=getattr(logged, "id", None),
                error=f"{type(exc).__name__}: {str(exc)[:200]}",
            )

        return {
            "query_id": logged.id,
            "analysis_available": analysis_available,
            "analysis_source": analysis.get("analysis_source"),
            "detected_category": detected_cat,
            "detected_color": detected_col,
            "detected_pattern": detected_pat,
            "detected_style": detected_sty,
            "results_count": len(matches),
            "matches": matches
        }
