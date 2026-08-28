import json
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.app.models.stylist import Outfit
from backend.app.repositories.stylist_repository import StylistRepository
from backend.app.repositories.catalog_repository import CatalogRepository
from backend.app.services.styling_engine import StylingEngine


class OutfitService:
    def __init__(self, db: Session):
        self.db = db
        self.stylist_repo = StylistRepository(db)
        self.catalog_repo = CatalogRepository(db)

    def evaluate_compatibility(self, product_ids: List[int], target_occasion: str = "Casual") -> Dict[str, Any]:
        products = []
        for pid in product_ids:
            p = self.catalog_repo.get_product_by_id(pid)
            if p:
                products.append({
                    "id": p.id,
                    "title": p.title,
                    "color_family": p.color_family,
                    "dominant_hex": p.dominant_hex,
                    "style_tags": json.loads(p.style_tags) if p.style_tags else [],
                    "occasion_tags": json.loads(p.occasion_tags) if p.occasion_tags else [],
                    "category": p.category.name if p.category else "Apparel",
                    "price": p.base_price
                })

        return StylingEngine.calculate_compatibility(products, target_occasion=target_occasion)

    def save_outfit(
        self,
        user_id: int,
        title: str,
        occasion: str,
        product_sku_ids: List[int],
        description: Optional[str] = None
    ) -> Outfit:
        products = []
        items_payload = []
        total_price = 0.0
        hexes = []

        for sku_id in product_sku_ids:
            sku = self.catalog_repo.get_sku_by_id(sku_id)
            if not sku:
                continue
            product = sku.product
            position = "top"
            cat_slug = product.category.slug.lower()
            if "bottom" in cat_slug or "trouser" in cat_slug:
                position = "bottom"
            elif "outer" in cat_slug or "blazer" in cat_slug:
                position = "outerwear"
            elif "shoe" in cat_slug or "footwear" in cat_slug:
                position = "shoes"
            elif "bag" in cat_slug or "accessory" in cat_slug:
                position = "accessory"

            price = sku.price_override or product.base_price
            total_price += price
            hexes.append(sku.color_hex or product.dominant_hex)

            products.append({
                "id": product.id,
                "color_family": product.color_family,
                "dominant_hex": product.dominant_hex,
                "style_tags": json.loads(product.style_tags) if product.style_tags else [],
                "occasion_tags": json.loads(product.occasion_tags) if product.occasion_tags else []
            })

            items_payload.append({
                "product_id": product.id,
                "product_sku_id": sku.id,
                "position": position
            })

        comp = StylingEngine.calculate_compatibility(products, target_occasion=occasion)

        return self.stylist_repo.save_outfit(
            user_id=user_id,
            title=title,
            occasion=occasion,
            compatibility_score=comp["compatibility_score"],
            total_price=total_price,
            color_palette=list(set(hexes)),
            style_tags=["Curated", occasion],
            items=items_payload,
            is_saved=True,
            is_system_curated=False
        )

    def get_user_looks(self, user_id: int) -> List[Dict[str, Any]]:
        outfits = self.stylist_repo.get_user_outfits(user_id, saved_only=True)
        results = []
        for o in outfits:
            items_data = []
            for it in o.items:
                items_data.append({
                    "id": it.id,
                    "product_id": it.product_id,
                    "product_title": it.product.title if it.product else "Garment",
                    "brand_name": it.product.brand.brand_name if it.product and it.product.brand else "CONFIT",
                    "category_name": it.product.category.name if it.product and it.product.category else "Fashion",
                    "price": it.product.base_price if it.product else 0.0,
                    "image_url": it.product.thumbnail_url if it.product else "",
                    "color_hex": it.product.dominant_hex if it.product else "#1B1F3B",
                    "position": it.position,
                    "sku_id": it.product_sku_id,
                    "selected_size": it.sku.size if it.sku else "M"
                })
            results.append({
                "id": o.id,
                "title": o.title,
                "description": o.description,
                "occasion": o.occasion,
                "total_price": o.total_price,
                "compatibility_score": o.compatibility_score,
                "color_palette": json.loads(o.color_palette) if o.color_palette else [],
                "style_tags": json.loads(o.style_tags) if o.style_tags else [],
                "is_saved": o.is_saved,
                "is_system_curated": o.is_system_curated,
                "items": items_data,
                "created_at": o.created_at
            })
        return results
