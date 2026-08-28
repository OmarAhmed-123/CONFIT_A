import json
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from backend.app.repositories.wardrobe_repository import WardrobeRepository
from backend.app.repositories.catalog_repository import CatalogRepository


class GapAnalysisService:
    """Identifies missing wardrobe staples and maps them to high-synergy catalog items."""

    def __init__(self, db: Session):
        self.db = db
        self.wardrobe_repo = WardrobeRepository(db)
        self.catalog_repo = CatalogRepository(db)

    def analyze_wardrobe_gaps(self, user_id: int) -> List[Dict[str, Any]]:
        existing_items = self.wardrobe_repo.get_user_items(user_id)
        categories_owned = {it.category.lower() for it in existing_items}

        gaps = []
        # Check standard wardrobe matrix
        if "bottoms" not in categories_owned or len([i for i in existing_items if i.category.lower() == "bottoms"]) < 2:
            catalog_recs = self.catalog_repo.filter_products(category_slug="bottoms", limit=3)
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
            gaps.append({
                "id": 1,
                "missing_category": "Bottoms",
                "missing_subcategory": "Pleated Neutral Trousers",
                "suggested_colors": ["Beige", "Charcoal Grey", "Navy"],
                "rationale": "You own structured blazers and shirts, but lack tailored neutral trousers to complete formal and smart casual silhouettes.",
                "unlocks_outfit_count": 4,
                "recommended_products": rec_dicts
            })

        if "outerwear" not in categories_owned:
            catalog_recs = self.catalog_repo.filter_products(category_slug="outerwear", limit=3)
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
            gaps.append({
                "id": 2,
                "missing_category": "Outerwear",
                "missing_subcategory": "Lightweight Minimalist Trench / Overcoat",
                "suggested_colors": ["Camel", "Navy", "Sage"],
                "rationale": "Adding a clean outerwear layer will bridge your transition outfits for evening and formal events.",
                "unlocks_outfit_count": 5,
                "recommended_products": rec_dicts
            })

        return gaps


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
        strict_mode: bool = False
    ) -> Dict[str, Any]:
        wardrobe_items = self.wardrobe_repo.get_user_items(user_id)
        if not wardrobe_items:
            return {"has_duplicate_risk": False, "similarity_score": 0}

        for item in wardrobe_items:
            category_match = item.category.lower() in category.lower() or category.lower() in item.category.lower()
            color_match = item.color_name.lower() in color_family.lower() or color_family.lower() in item.color_name.lower()

            if category_match and color_match:
                similarity = 92 if strict_mode else 85
                item_dict = {
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
                return {
                    "has_duplicate_risk": True,
                    "similarity_score": similarity,
                    "owned_item": item_dict,
                    "alert_message": f"Smart Duplicate Alert: You already own a similar {item.color_name} {item.category} ('{item.title}').",
                    "comparison_notes": "CONFIT's smart shopping engine noticed strong aesthetic and color overlap with an item in your virtual wardrobe. Would you like to style what you own first or proceed with this purchase?"
                }

        return {
            "has_duplicate_risk": False,
            "similarity_score": 25,
            "owned_item": None,
            "alert_message": None,
            "comparison_notes": None
        }
