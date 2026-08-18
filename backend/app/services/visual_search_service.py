from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from backend.app.repositories.catalog_repository import CatalogRepository
from backend.app.repositories.tryon_repository import TryOnRepository
from backend.app.providers.tryon_provider import VisualSearchAIProvider


class VisualSearchService:
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
        max_price: Optional[float] = None,
        in_stock_only: bool = True
    ) -> Dict[str, Any]:
        target_img = image_url or "https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=600&auto=format&fit=crop&q=80"

        # Vision AI analysis
        analysis = await self.ai_provider.analyze_fashion_image(target_img)

        detected_cat = analysis.get("detected_category", "Blazers")
        detected_col = analysis.get("detected_color", "Navy Blue")
        detected_pat = analysis.get("detected_pattern", "Solid")
        detected_sty = analysis.get("detected_style", "Smart Casual")

        # Query catalog
        catalog_products = self.catalog_repo.filter_products(max_price=max_price, limit=12)

        matches = []
        for idx, p in enumerate(catalog_products[:6]):
            similarity = 96 - (idx * 5)
            match_type = "Exact Match" if idx == 0 else ("Silhouette Match" if idx < 3 else "Complementary Alternative")
            matches.append({
                "product_id": p.id,
                "title": p.title,
                "brand_name": p.brand.brand_name if p.brand else "CONFIT",
                "price": p.base_price,
                "image_url": p.thumbnail_url,
                "similarity_score": max(72, similarity),
                "detected_color": p.color_family,
                "match_type": match_type
            })

        self.tryon_repo.log_visual_search(
            input_image_url=target_img,
            user_id=user_id,
            detected_category=detected_cat,
            detected_color=detected_col,
            detected_pattern=detected_pat,
            detected_style=detected_sty,
            detected_attributes=analysis.get("detected_attributes", {}),
            matches=matches
        )

        return {
            "query_id": 901,
            "detected_category": detected_cat,
            "detected_color": detected_col,
            "detected_pattern": detected_pat,
            "detected_style": detected_sty,
            "results_count": len(matches),
            "matches": matches
        }
