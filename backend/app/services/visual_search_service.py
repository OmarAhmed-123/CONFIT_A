from backend.app.core.logging import logger
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from backend.app.core.exceptions import ValidationDomainError
from backend.app.core.money import to_float
from backend.app.core.config import settings
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


    async def _embedding_matches(
        self,
        target_img: str,
        *,
        limit: int,
        in_stock_only: bool,
        min_price=None,
        max_price=None,
        brand_ids=None,
    ) -> dict:
        """Visual similarity from real image embeddings, or {} if unavailable.

        Returns {product_id: similarity_percent}. Empty means "not used" —
        never an error, because the keyword path below is a working fallback
        and an optional accelerator must not take the feature down.

        Only products embedded with the SAME model are considered. Vectors
        from two models are not comparable, and scoring across them degrades
        ranking silently instead of failing.
        """
        from backend.app.providers.moda import embeddings as moda

        # WHY THIS RECORDS A REASON (added 2026-10-01)
        # Every branch below returns {} and the caller silently falls back to
        # keyword ranking with HTTP 200 and plausible-looking results. That is
        # the correct DEGRADATION, but it was invisible: on production a
        # self-match query (cosine 1.0, impossible to drop) still came back
        # scored 56 from the keyword band, and nothing in the response said
        # the visual path had not run. An operator could not tell a working
        # visual search from a broken one. The reason is now recorded and
        # surfaced in the payload.
        self._embedding_skip_reason = None

        if not moda.is_available():
            self._embedding_skip_reason = "not_configured"
            return {}

        raw = await self._image_bytes(target_img)
        if not raw:
            self._embedding_skip_reason = "query_image_unreadable"
            return {}

        query_vector = await moda.embed_image(raw)
        if not query_vector:
            # embed_image swallows every transport error by design, so this
            # covers timeout, 401, 5xx and malformed payload alike.
            self._embedding_skip_reason = "embed_call_failed"
            return {}

        import json as _json

        from backend.app.models.catalog import Product

        rows = (
            self.db.query(Product.id, Product.style_embedding)
            .filter(
                Product.is_active.is_(True),
                Product.style_embedding.isnot(None),
                Product.style_embedding_model == moda.MODEL_ID,
            )
            .all()
        )
        catalog = {}
        for product_id, blob in rows:
            try:
                vector = _json.loads(blob)
            except Exception:
                # A corrupt row must not abort the whole search.
                continue
            if isinstance(vector, list) and len(vector) == moda.EMBED_DIM:
                catalog[product_id] = vector

        if not catalog:
            self._embedding_skip_reason = "no_embedded_products"
            logger.info("visual_search_no_embedded_products")
            return {}

        ranked = moda.rank_catalog(query_vector, catalog, limit=limit)
        if not ranked:
            # Not a fault: every candidate scored below MIN_COSINE_SCORE, and
            # dropping weak matches is deliberate. Measured on this model
            # 2026-10-01: noise sits at 0.29-0.41, a genuine same-category
            # match reaches 0.55-0.66, an identical image is 1.00. Saying so
            # distinguishes "nothing looked similar" from "the path is down".
            self._embedding_skip_reason = "all_below_threshold"
        logger.info(
            "visual_search_embedding_ranked",
            embedded_products=len(catalog),
            matches=len(ranked),
        )
        return {r.product_id: r.similarity_percent for r in ranked}

    async def _image_bytes(self, target_img: str) -> bytes | None:
        """Materialise a data URL or http(s) URL to bytes for embedding."""
        import base64 as _b64

        if target_img.startswith("data:"):
            try:
                return _b64.b64decode(target_img.split(",", 1)[1])
            except Exception:
                return None
        if target_img.startswith(("http://", "https://")):
            from backend.app.core.security import is_safe_image_url

            if not is_safe_image_url(target_img):
                return None
            import httpx

            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    response = await client.get(target_img)
                    response.raise_for_status()
                    return response.content
            except Exception:
                return None
        return None

    def _apply_embedding_scores(self, scored_matches, embedding_matches):
        """Replace keyword scores with visual ones where we have them.

        A product the embedding model ranked is scored by SIGHT; the rest
        keep their keyword score. Visual matches are offset above the
        keyword band so a genuine visual hit cannot be outranked by a
        coincidental word overlap — that inversion is the whole reason this
        path exists.
        """
        if not embedding_matches:
            return scored_matches
        rescored = []
        for score, product, breakdown in scored_matches:
            visual = embedding_matches.get(product.id)
            if visual is not None:
                breakdown = {**breakdown, "visual_embedding": visual}
                score = 100.0 + visual
            rescored.append((score, product, breakdown))
        return rescored

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
        # 1b. EMBEDDING RETRIEVAL — preferred when an embedding service is
        #     configured and the catalogue has been backfilled.
        #
        #     The keyword path below compares WORDS from a Gemini description.
        #     This compares the IMAGES. It is attempted first and falls
        #     through silently when unavailable, so the feature degrades to
        #     exactly its previous behaviour rather than failing.
        embedding_matches = await self._embedding_matches(
            target_img, limit=limit, in_stock_only=in_stock_only,
            min_price=min_price, max_price=max_price, brand_ids=brand_ids,
        )

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
        #
        #    When USE_ENHANCED_VISUAL_SEARCH_SCORING is enabled, use the
        #    deterministic enhanced scoring with synonym normalization,
        #    category hierarchy, LAB color similarity, and style weighting.
        use_enhanced = settings.USE_ENHANCED_VISUAL_SEARCH_SCORING

        if use_enhanced:
            from backend.app.services.visual_search_enhanced import calculate_enhanced_score

        cat_tokens = [t for t in (detected_cat or "").lower().replace("&", " ").split() if len(t) > 2]
        col_tokens = [t for t in (detected_col or "").lower().split() if len(t) > 2]
        sty_tokens = [t.replace(" ", "_") for t in (detected_sty or "").lower().split("/") if t.strip()]

        scored_matches = []
        for p in all_prods:
            p_cat = (p.category.name if p.category else "").lower()
            p_title = p.title.lower()
            p_color = (p.color_family or "").lower()
            p_tags = (p.style_tags or "").lower()

            if use_enhanced and analysis_available:
                # Enhanced deterministic scoring
                score, breakdown = calculate_enhanced_score(
                    detected_category=detected_cat,
                    detected_color=detected_col,
                    detected_style=detected_sty,
                    detected_pattern=detected_pat,
                    product_category=p_cat,
                    product_color=p_color,
                    product_style_tags=p_tags,
                    product_title=p_title,
                    analysis_available=analysis_available,
                )
                scored_matches.append((score, p, breakdown))
            else:
                # Baseline token-matching scoring
                score = 50.0  # neutral base — ranking comes only from real signals
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
                scored_matches.append((score, p, {"base": 50.0, "category": 30.0 if any(t in p_cat or t in p_title for t in cat_tokens) and analysis_available else 0.0, "color": 15.0 if any(t in p_color for t in col_tokens) and analysis_available else 0.0, "style": 8.0 if any(t in p_tags for t in sty_tokens) and analysis_available else 0.0}))

        scored_matches = self._apply_embedding_scores(
            scored_matches, embedding_matches
        )

        # Sort by similarity score descending, with deterministic tie-breaking
        # for enhanced scoring (higher category score wins, then higher color score)
        if use_enhanced:
            scored_matches.sort(
                key=lambda x: (x[0], x[2].get("category", 0), x[2].get("color", 0)),
                reverse=True
            )
        else:
            scored_matches.sort(key=lambda x: x[0], reverse=True)

        # Honour the caller's requested result count (schema: top_k, 1..20). The
        # DB query above is already bounded by ``limit``; slicing here keeps the
        # response size consistent with the request instead of a hard-coded 8.
        result_limit = limit if isinstance(limit, int) and limit > 0 else 8
        matches = []
        for idx, (sim, p, breakdown) in enumerate(scored_matches[:result_limit]):
            match_type = "Exact Match" if idx == 0 and sim >= 95 else ("Silhouette Match" if sim >= 88 else "Complementary Alternative")
            match_entry = {
                "product_id": p.id,
                "title": p.title,
                "brand_name": p.brand.brand_name if p.brand else "CONFIT",
                "price": to_float(p.base_price),
                "currency": p.currency or "USD",
                "image_url": p.thumbnail_url,
                "similarity_score": int(sim),
                "detected_color": p.color_family,
                "match_type": match_type
            }
            # Include score breakdown when enhanced scoring is active
            if use_enhanced:
                match_entry["score_breakdown"] = breakdown
            matches.append(match_entry)

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
            "matches": matches,
            "scoring_method": "enhanced" if use_enhanced else "baseline",
            # Visual-embedding provenance. `True` means the ranking was
            # decided by SIGHT; `False` plus a reason means it fell back to
            # keywords, which the caller previously had no way to detect.
            "visual_embedding_used": bool(embedding_matches),
            "visual_embedding_detail": (
                f"{len(embedding_matches)} product(s) ranked by image embedding"
                if embedding_matches
                else f"not applied: {getattr(self, '_embedding_skip_reason', None) or 'unknown'}"
            ),
        }
