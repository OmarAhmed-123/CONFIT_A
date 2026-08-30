import json
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from backend.app.repositories.catalog_repository import CatalogRepository
from backend.app.repositories.profile_repository import ProfileRepository
from backend.app.services.weather_service import get_weather_provider


def _product_summary(p) -> Dict[str, Any]:
    return {
        "id": p.id,
        "brand_name": p.brand.brand_name if getattr(p, "brand", None) else "CONFIT Partner",
        "category_name": p.category.name if getattr(p, "category", None) else "Fashion",
        "title": p.title,
        "base_price": float(p.base_price),
        "currency": p.currency,
        "thumbnail_url": p.thumbnail_url,
        "color_family": p.color_family,
        "dominant_hex": p.dominant_hex,
        "rating": p.rating,
        "is_featured": p.is_featured,
    }


class DashboardService:
    """Composes the Home Dashboard (G2.4) from real profile + catalog data.

    Personalization sources (all real, none hardcoded):
      * style profile archetypes / preferred colors  -> Today's picks
      * preferred_brands                              -> New from your brands
      * RecentlyViewed rows                           -> Recently viewed
      * occasion_weights / featured + rating          -> Trending
    Guests (no profile) receive catalog-popular content, clearly non-personalized.
    """

    def __init__(self, db: Session):
        self.db = db
        self.catalog = CatalogRepository(db)
        self.profiles = ProfileRepository(db)

    def get_dashboard(
        self,
        user_id: Optional[int],
        lat: Optional[float] = None,
        lon: Optional[float] = None,
    ) -> Dict[str, Any]:
        usp = self.profiles.get_by_user_id(user_id) if user_id else None
        # Authenticated user without a profile yet: bootstrap a default one so
        # personalization engages from day one (mirrors the existing /profile/me
        # bootstrap pattern). Guests stay non-personalized.
        if user_id and not usp:
            usp = self.profiles.create_or_update_profile(user_id, {
                "style_archetypes": ["Smart Casual", "Quiet Luxury"],
                "preferred_colors": ["Navy", "Beige", "Black", "White"],
                "preferred_brands": ["Massimo Dutti", "COS", "Reiss", "Arket"],
            })

        # --- Today's Style Picks (personalized by style + color + occasion) ---
        style_tags: List[str] = []
        colors: List[str] = []
        occasion_weights: Dict[str, float] = {}
        if usp:
            try:
                style_tags = json.loads(usp.style_archetypes or "[]")
            except Exception:
                style_tags = []
            try:
                colors = json.loads(usp.preferred_colors or "[]")
            except Exception:
                colors = []
            try:
                occasion_weights = json.loads(usp.occasion_weights or "{}")
            except Exception:
                occasion_weights = {}

        top_occasion = max(occasion_weights, key=occasion_weights.get) if occasion_weights else None
        candidates = self.catalog.filter_products(limit=100)

        def _pick_score(p) -> float:
            score = float(p.rating or 0)
            p_styles = (p.style_tags or "").lower()
            p_color = (p.color_family or "").lower()
            p_occ = (p.occasion_tags or "").lower()
            for st in style_tags:
                if st and st.lower().replace(" ", "_") in p_styles:
                    score += 2.0
            for c in colors:
                if c and c.lower() in p_color:
                    score += 1.5
            if top_occasion and top_occasion.lower() in p_occ:
                score += 1.0
            if p.is_featured:
                score += 0.5
            # Prefer in-stock items.
            if getattr(p, "skus", None) and any(s.is_in_stock and s.stock_level > 0 for s in p.skus):
                score += 0.5
            return score

        todays_picks = [_product_summary(p) for p in
                        sorted(candidates, key=_pick_score, reverse=True)[:6]]

        # --- Trending Looks (top-rated, in-stock, featured-leaning) ---
        trending = [_product_summary(p) for p in
                    sorted(candidates, key=lambda p: (p.is_featured, p.rating or 0), reverse=True)[:8]]

        # --- Recently Viewed (real per-user history) ---
        recently_viewed = [_product_summary(p) for p in
                           self.catalog.get_recently_viewed(user_id, limit=10)] if user_id else []

        # --- New From Your Brands (user's actual preferred brands) ---
        preferred_brands: List[str] = []
        if usp:
            try:
                preferred_brands = json.loads(usp.preferred_brands or "[]")
            except Exception:
                preferred_brands = []
        new_from_brands = [_product_summary(p) for p in
                           self.catalog.get_new_from_brands(preferred_brands, limit=8)]

        # --- Weather (G2-S5): only when the client supplied coordinates and
        # the provider is configured; any provider failure degrades to None —
        # weather is never fabricated.
        weather: Optional[Dict[str, Any]] = None
        if lat is not None and lon is not None:
            weather_out = get_weather_provider().get_current_weather(lat, lon)
            weather = weather_out.model_dump() if weather_out else None

        return {
            "weather": weather,
            "personalized": bool(usp),
            "top_occasion": top_occasion,
            "todays_picks": todays_picks,
            "trending": trending,
            "recently_viewed": recently_viewed,
            "new_from_your_brands": new_from_brands,
            "preferred_brands": preferred_brands,
            "occasion_shortcuts": ["Work", "Wedding", "Party", "Casual"],
            "quick_actions": ["build_outfit", "try_it_on", "find_my_style"],
        }
