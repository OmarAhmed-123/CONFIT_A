import json
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from backend.app.core.config import settings
from backend.app.repositories.wardrobe_repository import WardrobeRepository
from backend.app.repositories.catalog_repository import CatalogRepository
from backend.app.services import wardrobe_taxonomy as taxonomy


class GapAnalysisService:
    """Identifies missing wardrobe staples and maps them to high-synergy catalog items."""

    def __init__(self, db: Session):
        self.db = db
        self.wardrobe_repo = WardrobeRepository(db)
        self.catalog_repo = CatalogRepository(db)

    # Capsule-wardrobe matrix (BRD §26): the minimum coverage a versatile
    # wardrobe needs per category before the platform may suggest a purchase.
    # If the wardrobe already satisfies a row, that row is NOT a gap and no
    # product is recommended for it — gap analysis answers "what is actually
    # missing", never "what can we sell".
    CAPSULE_MATRIX = [
        # (category, min_ready_items, suggested subcategory, unlocks)
        ("Tops", 2, "Versatile Neutral Shirt / Knit", 4),
        ("Bottoms", 2, "Pleated Neutral Trousers", 4),
        ("Outerwear", 1, "Lightweight Minimalist Trench / Overcoat", 5),
        ("Footwear", 1, "Minimalist Leather Sneakers / Loafers", 3),
        ("Accessories", 1, "Leather Belt or Silk Scarf", 3),
    ]

    _CATEGORY_TO_SLUG = {
        "Tops": "tops", "Bottoms": "bottoms", "Outerwear": "outerwear",
        "Footwear": "footwear", "Accessories": "accessories", "Dresses": "dresses",
    }

    def analyze_wardrobe_gaps(self, user_id: int) -> List[Dict[str, Any]]:
        # Only fully-processed items count as wardrobe coverage — a failed or
        # still-processing upload cannot suppress a genuine gap.
        existing_items = [
            it for it in self.wardrobe_repo.get_user_items(user_id)
            if getattr(it, "processing_status", "ready") == "ready"
        ]
        owned_counts: Dict[str, int] = {}
        owned_colors: List[str] = []
        for it in existing_items:
            cat = taxonomy.normalize_category(it.category)
            owned_counts[cat] = owned_counts.get(cat, 0) + 1
            owned_colors.append(taxonomy.normalize_color(it.color_name))

        # Suggested colors harmonize with what the user already owns (existing
        # ColorHarmonyEngine vocabulary) rather than a fixed palette.
        anchor = max(set(owned_colors), key=owned_colors.count) if owned_colors else "Navy"
        suggested = self._harmonizing_colors(anchor)

        gaps: List[Dict[str, Any]] = []
        gap_id = 1
        for category, min_count, subcategory, unlocks in self.CAPSULE_MATRIX:
            if owned_counts.get(category, 0) >= min_count:
                continue  # already covered — suppress the purchase suggestion

            slug = self._CATEGORY_TO_SLUG.get(category, category.lower())
            catalog_recs = self.catalog_repo.filter_products(category_slug=slug, limit=3)
            rec_dicts = [
                {
                    "product_id": p.id,
                    "title": p.title,
                    "brand_name": p.brand.brand_name if p.brand else "CONFIT",
                    "price": p.base_price,
                    "image_url": p.thumbnail_url
                }
                for p in catalog_recs
            ]
            count = owned_counts.get(category, 0)
            gaps.append({
                "id": gap_id,
                "missing_category": category,
                "missing_subcategory": subcategory,
                "suggested_colors": suggested,
                "rationale": (
                    f"Your wardrobe has {count} ready {category.lower()} item(s); a versatile "
                    f"capsule needs at least {min_count}. Adding a {subcategory.lower()} in "
                    f"{suggested[0]} would pair with your existing {anchor.lower()} pieces."
                ),
                "unlocks_outfit_count": unlocks,
                "recommended_products": rec_dicts
            })
            gap_id += 1

        return gaps

    @staticmethod
    def _harmonizing_colors(anchor_family: str) -> List[str]:
        """Pull 3 palette suggestions from the existing color-harmony map,
        falling back to wardrobe-safe neutrals for unmapped anchors."""
        from backend.app.services.styling.color_harmony import ColorHarmonyEngine

        partners = ColorHarmonyEngine.HARMONY_PAIRS.get(anchor_family.lower()) or []
        palette = [p.replace("light blue", "Blue").title() for p in partners[:3]]
        while len(palette) < 3:
            for fallback in ("Beige", "Charcoal", "Navy", "Ivory"):
                if fallback not in palette:
                    palette.append(fallback)
                    break
        return palette[:3]


class DuplicateDetectorService:
    """Alerts user at Add-to-Cart if they already own a highly similar item in their wardrobe."""

    def __init__(self, db: Session):
        self.db = db
        self.wardrobe_repo = WardrobeRepository(db)
        self.catalog_repo = CatalogRepository(db)

    def check_duplicate(
        self,
        user_id: int,
        product_id: int,
        product_title: str,
        category: str,
        color_family: str,
        strict_mode: bool = False,
        pattern: str = None
    ) -> Dict[str, Any]:
        """Deterministic, explainable wardrobe-vs-product similarity (BRD §28-30).

        Scoring is attribute-based (no model call — structured fields solve
        this reliably and cheaply):
            type match ........ +55   (normalized wardrobe category)
            color match ....... +35   (normalized color family)
            pattern match ..... +10   (normalized pattern)
        Both sides are normalized through the shared taxonomy first, so
        'Navy Blue' vs 'navy' or 'trousers' vs 'Bottoms' cannot miss.

        Thresholds come from centralized config:
            strict — DUPLICATE_ALERT_SIMILARITY_THRESHOLD (near-exact:
                     requires type + color)
            loose  — DUPLICATE_ALERT_LOOSE_THRESHOLD (similar style/category:
                     type + one supporting signal is enough)
        The best-scoring owned item is returned with the match reasons so the
        alert can explain WHY it fired. Advisory only — never blocks purchase.
        """
        wardrobe_items = [it for it in self.wardrobe_repo.get_user_items(user_id)
                          if getattr(it, "processing_status", "ready") == "ready"]
        if not wardrobe_items:
            return {"has_duplicate_risk": False, "similarity_score": 0,
                    "owned_item": None, "alert_message": None, "comparison_notes": None}

        product_category = taxonomy.normalize_category(category)
        product_color = taxonomy.normalize_color(color_family)
        product_pattern = taxonomy.normalize_pattern(pattern) if pattern else None

        best = None  # (score, reasons, item)
        for item in wardrobe_items:
            score = 0
            reasons: List[str] = []
            if taxonomy.normalize_category(item.category) == product_category:
                score += 55
                reasons.append(f"same type ({product_category})")
            if taxonomy.normalize_color(item.color_name) == product_color:
                score += 35
                reasons.append(f"same color family ({product_color})")
            if product_pattern and taxonomy.normalize_pattern(item.pattern) == product_pattern:
                score += 10
                reasons.append(f"same pattern ({product_pattern})")
            if best is None or score > best[0]:
                best = (score, reasons, item)

        threshold = (settings.DUPLICATE_ALERT_SIMILARITY_THRESHOLD if strict_mode
                     else settings.DUPLICATE_ALERT_LOOSE_THRESHOLD)
        best_score, reasons, item = best
        has_risk = best_score >= round(threshold * 100)

        item_dict = None
        if has_risk and item is not None:
            item_dict = self._owned_item_dict(item)

        return {
            "has_duplicate_risk": has_risk,
            "similarity_score": best_score if has_risk else min(best_score, 25),
            "owned_item": item_dict,
            "alert_message": (
                f"Smart Duplicate Alert: You already own a similar {item.color_name} "
                f"{item.category} ('{item.title}')."
            ) if has_risk else None,
            "comparison_notes": (
                f"Match signals: {', '.join(reasons)}. "
                "CONFIT's smart shopping engine noticed overlap with an item in your virtual "
                "wardrobe. Would you like to style what you own first or proceed with this purchase?"
            ) if has_risk else None,
        }

    @staticmethod
    def _owned_item_dict(item) -> Dict[str, Any]:
        return {
            "id": item.id,
            "user_id": item.user_id,
            "title": item.title,
            "category": item.category,
            "subcategory": item.subcategory,
            "color_name": item.color_name,
            "color_hex": item.color_hex,
            "pattern": item.pattern,
            "brand_name": item.brand_name,
            "image_url": item.image_url,
            "ai_tags": json.loads(item.ai_tags) if item.ai_tags else [],
            "occasions": json.loads(item.occasions) if item.occasions else [],
            "wear_frequency": item.wear_frequency,
            "wear_count": item.wear_count,
            "is_favorite": item.is_favorite,
            "created_at": item.created_at
        }
