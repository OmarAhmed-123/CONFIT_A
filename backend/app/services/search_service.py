import time
import json
import html
import re
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from backend.app.models.catalog import Product, Category
from backend.app.models.user import BrandProfile
from backend.app.schemas.catalog import (
    SearchResponseOut,
    SearchResultItemOut,
    SearchFacetsOut,
    FacetCount,
    PriceRangeFacet,
    AutocompleteResponse,
    AutocompleteSuggestion
)


class SearchService:
    """Production Search Engine Service.
    Implements weighted multi-field relevance scoring, bounded typo tolerance,
    contextual snippet extraction, dynamic faceted aggregations, and fast autocomplete.
    """

    TYPO_CORRECTIONS = {
        "blzer": "blazer",
        "blazr": "blazer",
        "shrt": "shirt",
        "shrt": "shirt",
        "oxfrd": "oxford",
        "oxfords": "oxford",
        "trousr": "trouser",
        "trouser": "trouser",
        "sweatr": "sweater",
        "swater": "sweater",
        "drss": "dress",
        "loaferss": "loafer",
        "massimmo": "massimo",
        "massimoduty": "massimo",
        "rekiss": "reiss",
        "arktt": "arket",
        "coss": "cos"
    }

    def __init__(self, db: Session):
        self.db = db

    ALLOWED_SORT_FIELDS = {"relevance", "price_asc", "price_desc", "rating", "newest"}

    def sanitize_query(self, raw_query: str) -> str:
        """Sanitizes user input: bounds length to 100 chars, strips control chars, escapes metacharacters."""
        if not raw_query:
            return ""
        # Bound length
        q = raw_query.strip()[:100]
        # Remove dangerous control chars & SQL wildcard abuse
        q = re.sub(r'[\x00-\x1f\x7f]', '', q)
        q = re.sub(r'[%_\*\+\?\^\$\{\}\(\)\|\[\]\\]', '', q)
        return q.strip()

    def correct_typos(self, tokens: List[str]) -> Tuple[List[str], Optional[str]]:
        corrected_tokens = []
        had_correction = False
        for tok in tokens:
            tok_lower = tok.lower()
            if tok_lower in self.TYPO_CORRECTIONS:
                corrected_tokens.append(self.TYPO_CORRECTIONS[tok_lower])
                had_correction = True
            else:
                corrected_tokens.append(tok)

        did_you_mean = " ".join(corrected_tokens) if had_correction else None
        return corrected_tokens, did_you_mean

    def search_products(
        self,
        query: str,
        category: Optional[str] = None,
        brand_id: Optional[int] = None,
        color: Optional[str] = None,
        occasion: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        page: int = 1,
        limit: int = 20,
        sort_by: str = "relevance"
    ) -> SearchResponseOut:
        start_time = time.time()
        clean_q = self.sanitize_query(query)

        tokens = [t.lower() for t in clean_q.split() if len(t) >= 2]
        corrected_tokens, did_you_mean = self.correct_typos(tokens)
        search_tokens = corrected_tokens if corrected_tokens else tokens

        # 1. Base Active Products Query
        base_query = (
            self.db.query(Product)
            .options(
                joinedload(Product.brand),
                joinedload(Product.category),
                joinedload(Product.skus)
            )
            .filter(Product.is_active == True)
        )

        # 2. Hard Filters
        if category:
            base_query = base_query.join(Category).filter(Category.slug == category)
        if brand_id:
            base_query = base_query.filter(Product.brand_id == brand_id)
        if color:
            base_query = base_query.filter(Product.color_family.ilike(f"%{color}%"))
        if occasion:
            base_query = base_query.filter(Product.occasion_tags.like(f"%{occasion}%"))
        if min_price is not None:
            base_query = base_query.filter(Product.base_price >= min_price)
        if max_price is not None:
            base_query = base_query.filter(Product.base_price <= max_price)

        all_candidate_products = base_query.all()

        # 3. Weighted Relevance Scoring & Snippet Extraction
        scored_results = []
        for p in all_candidate_products:
            score, matched_field, snippet = self._compute_product_relevance(p, clean_q, search_tokens)
            if not clean_q or score > 0:
                scored_results.append((score, matched_field, snippet, p))

        # Validate and bound sort_by against strict allowlist
        effective_sort = sort_by.lower().strip() if sort_by else "relevance"
        if effective_sort not in self.ALLOWED_SORT_FIELDS:
            effective_sort = "relevance"

        # 4. Sorting Strategy
        if effective_sort == "price_asc":
            scored_results.sort(key=lambda x: x[3].base_price)
        elif effective_sort == "price_desc":
            scored_results.sort(key=lambda x: x[3].base_price, reverse=True)
        elif effective_sort == "rating":
            scored_results.sort(key=lambda x: x[3].rating, reverse=True)
        elif effective_sort == "newest":
            scored_results.sort(key=lambda x: x[3].created_at, reverse=True)
        else:
            # Relevance sorting with secondary rating boost
            scored_results.sort(key=lambda x: (x[0], x[3].rating), reverse=True)

        total_matches = len(scored_results)

        # 5. Bounded Pagination (DoS Prevention)
        safe_page = max(1, min(1000, page))
        safe_limit = min(100, max(1, limit))
        start_idx = (safe_page - 1) * safe_limit
        paged_items = scored_results[start_idx : start_idx + safe_limit]

        # 6. Transform to Output Schema
        output_results = []
        for score, field_name, snippet, p in paged_items:
            in_stock = any(s.stock_level > 0 for s in p.skus) if p.skus else True
            output_results.append(
                SearchResultItemOut(
                    id=p.id,
                    brand_id=p.brand_id,
                    brand_name=p.brand.brand_name if p.brand else "CONFIT Partner",
                    category_id=p.category_id,
                    category_name=p.category.name if p.category else "Fashion",
                    title=p.title,
                    title_ar=p.title_ar,
                    slug=p.slug,
                    base_price=p.base_price,
                    currency=p.currency,
                    thumbnail_url=p.thumbnail_url,
                    color_family=p.color_family,
                    dominant_hex=p.dominant_hex,
                    style_tags=json.loads(p.style_tags) if p.style_tags else [],
                    occasion_tags=json.loads(p.occasion_tags) if p.occasion_tags else [],
                    rating=p.rating,
                    style_compatibility_score=None,
                    ai_fit_score=None,
                    is_featured=p.is_featured,
                    relevance_score=round(score, 2),
                    matched_field=field_name,
                    highlighted_snippet=snippet,
                    in_stock=in_stock
                )
            )

        # 7. Compute Dynamic Search Facets
        facets = self._compute_search_facets([item[3] for item in scored_results], category, brand_id, color)

        execution_time = (time.time() - start_time) * 1000.0

        return SearchResponseOut(
            query=clean_q,
            total_matches=total_matches,
            page=safe_page,
            limit=safe_limit,
            results=output_results,
            facets=facets,
            did_you_mean=did_you_mean,
            execution_time_ms=round(execution_time, 2)
        )

    def _compute_product_relevance(
        self,
        product: Product,
        raw_query: str,
        tokens: List[str]
    ) -> Tuple[float, str, Optional[str]]:
        if not raw_query or not tokens:
            return 1.0, "catalog", None

        score = 0.0
        matched_field = "description"
        title_lower = product.title.lower()
        desc_lower = product.description.lower()
        brand_lower = product.brand.brand_name.lower() if product.brand else ""
        cat_lower = product.category.name.lower() if product.category else ""
        color_lower = product.color_family.lower()
        tags_str = (product.style_tags or "") + " " + (product.occasion_tags or "")

        # 1. Exact SKU Code Match (Top Priority)
        for sku in product.skus:
            if raw_query.lower() in sku.sku_code.lower():
                return 100.0, "sku", f"Matched SKU: {sku.sku_code}"

        # 2. Exact Title Match
        if raw_query.lower() == title_lower:
            score += 85.0
            matched_field = "title"
        elif raw_query.lower() in title_lower:
            score += 65.0
            matched_field = "title"

        # 3. Token-level matching with field weights
        matched_tokens = 0
        for tok in tokens:
            if tok in title_lower:
                score += 30.0
                matched_tokens += 1
                if matched_field == "description":
                    matched_field = "title"
            elif tok in brand_lower:
                score += 25.0
                matched_tokens += 1
                if matched_field == "description":
                    matched_field = "brand"
            elif tok in cat_lower:
                score += 20.0
                matched_tokens += 1
                if matched_field == "description":
                    matched_field = "category"
            elif tok in color_lower:
                score += 15.0
                matched_tokens += 1
            elif tok in tags_str.lower():
                score += 12.0
                matched_tokens += 1
            elif tok in desc_lower:
                score += 5.0
                matched_tokens += 1

        if matched_tokens == 0:
            return 0.0, "none", None

        # 4. In-Stock and Rating Boosts
        if any(s.stock_level > 0 for s in product.skus):
            score += 10.0
        score += (product.rating / 5.0) * 5.0

        # 5. Extract Safe Highlighted Snippet
        snippet = self._generate_safe_snippet(product.description, tokens)

        return score, matched_field, snippet

    def _generate_safe_snippet(self, text: str, tokens: List[str]) -> str:
        """Extracts a concise matching snippet and safely escapes HTML."""
        if not text:
            return ""
        escaped = html.escape(text)
        sentences = re.split(r'(?<=[.!?])\s+', escaped)

        for s in sentences:
            if any(tok in s.lower() for tok in tokens):
                # Return first matching sentence (bounded to 120 chars)
                return s[:120] + "..." if len(s) > 120 else s

        return escaped[:100] + "..." if len(escaped) > 100 else escaped

    def _compute_search_facets(
        self,
        products: List[Product],
        selected_cat: Optional[str],
        selected_brand: Optional[int],
        selected_color: Optional[str]
    ) -> SearchFacetsOut:
        cat_counts: Dict[str, int] = {}
        brand_counts: Dict[str, int] = {}
        color_counts: Dict[str, int] = {}
        prices: List[float] = []

        for p in products:
            prices.append(p.base_price)
            if p.category:
                cat_counts[p.category.slug] = cat_counts.get(p.category.slug, 0) + 1
            if p.brand:
                brand_counts[p.brand.brand_name] = brand_counts.get(p.brand.brand_name, 0) + 1
            if p.color_family:
                color_counts[p.color_family] = color_counts.get(p.color_family, 0) + 1

        cat_facets = [
            FacetCount(label=slug.replace('-', ' ').title(), value=slug, count=cnt, selected=(selected_cat == slug))
            for slug, cnt in sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)[:20]
        ]
        brand_facets = [
            FacetCount(label=bname, value=bname, count=cnt, selected=False)
            for bname, cnt in sorted(brand_counts.items(), key=lambda x: x[1], reverse=True)[:20]
        ]
        color_facets = [
            FacetCount(label=cname, value=cname, count=cnt, selected=(selected_color == cname))
            for cname, cnt in sorted(color_counts.items(), key=lambda x: x[1], reverse=True)[:20]
        ]

        min_p = min(prices) if prices else 0.0
        max_p = max(prices) if prices else 500.0
        avg_p = (sum(prices) / len(prices)) if prices else 0.0

        return SearchFacetsOut(
            categories=cat_facets,
            brands=brand_facets,
            colors=color_facets,
            price_range=PriceRangeFacet(min_price=round(min_p, 2), max_price=round(max_p, 2), avg_price=round(avg_p, 2))
        )

    def autocomplete(self, query: str) -> AutocompleteResponse:
        """Fast prefix & keyword autocomplete engine emitting suggestions in < 5ms."""
        clean_q = self.sanitize_query(query).lower()
        if len(clean_q) < 2:
            return AutocompleteResponse(query=clean_q, suggestions=[])

        suggestions: List[AutocompleteSuggestion] = []
        seen_titles = set()

        # 1. Product Title Matches
        matching_prods = (
            self.db.query(Product)
            .options(joinedload(Product.brand))
            .filter(Product.is_active == True)
            .filter(or_(Product.title.ilike(f"%{clean_q}%"), Product.title_ar.ilike(f"%{clean_q}%")))
            .limit(5)
            .all()
        )

        for p in matching_prods:
            if p.title not in seen_titles:
                seen_titles.add(p.title)
                suggestions.append(
                    AutocompleteSuggestion(
                        title=p.title,
                        type="product",
                        slug_or_query=p.slug,
                        subtitle=f"{p.brand.brand_name} · ${p.base_price:.2f}",
                        thumbnail_url=p.thumbnail_url
                    )
                )

        # 2. Brand Matches
        matching_brands = (
            self.db.query(BrandProfile)
            .filter(BrandProfile.brand_name.ilike(f"%{clean_q}%"))
            .limit(3)
            .all()
        )
        for b in matching_brands:
            suggestions.append(
                AutocompleteSuggestion(
                    title=b.brand_name,
                    type="brand",
                    slug_or_query=b.slug,
                    subtitle="Brand Collection",
                    thumbnail_url=b.logo_url
                )
            )

        # 3. Category Matches
        matching_cats = (
            self.db.query(Category)
            .filter(or_(Category.name.ilike(f"%{clean_q}%"), Category.name_ar.ilike(f"%{clean_q}%")))
            .limit(3)
            .all()
        )
        for c in matching_cats:
            suggestions.append(
                AutocompleteSuggestion(
                    title=c.name,
                    type="category",
                    slug_or_query=c.slug,
                    subtitle="Category",
                    thumbnail_url=None
                )
            )

        return AutocompleteResponse(query=clean_q, suggestions=suggestions[:8])
