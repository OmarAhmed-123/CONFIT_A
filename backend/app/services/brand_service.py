import json
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.app.models.catalog import Product, ProductSKU, Category
from backend.app.models.user import BrandProfile
from backend.app.repositories.brand_repository import BrandRepository
from backend.app.core.exceptions import ResourceNotFoundError, ValidationDomainError


class BrandService:
    def __init__(self, db: Session):
        self.db = db
        self.brand_repo = BrandRepository(db)

    def get_brand_profile_by_user(self, user_id: int) -> Dict[str, Any]:
        bp = self.brand_repo.get_by_user_id(user_id)
        if not bp:
            # Fallback to first brand for demo/admin convenience
            all_b = self.brand_repo.get_all_brands()
            bp = all_b[0] if all_b else None
            if not bp:
                raise ResourceNotFoundError("BrandProfile for user", user_id)
        return self._format_brand(bp)

    def get_brand_analytics_dashboard(self, brand_id: int) -> Dict[str, Any]:
        return self.brand_repo.get_brand_analytics(brand_id)

    def get_brand_products(self, brand_id: int) -> List[Dict[str, Any]]:
        products = self.brand_repo.get_brand_products(brand_id)
        results = []
        for p in products:
            skus_out = [
                {
                    "id": s.id,
                    "product_id": s.product_id,
                    "sku_code": s.sku_code,
                    "size": s.size,
                    "color": s.color,
                    "color_hex": s.color_hex,
                    "price_override": s.price_override,
                    "stock_level": s.stock_level,
                    "is_in_stock": s.is_in_stock
                }
                for s in p.skus
            ]
            results.append({
                "id": p.id,
                "brand_id": p.brand_id,
                "brand_name": p.brand.brand_name if p.brand else "CONFIT",
                "category_id": p.category_id,
                "category_name": p.category.name if p.category else "Category",
                "title": p.title,
                "title_ar": p.title_ar,
                "slug": p.slug,
                "base_price": p.base_price,
                "currency": p.currency,
                "thumbnail_url": p.thumbnail_url,
                "color_family": p.color_family,
                "dominant_hex": p.dominant_hex,
                "style_tags": json.loads(p.style_tags) if p.style_tags else [],
                "occasion_tags": json.loads(p.occasion_tags) if p.occasion_tags else [],
                "rating": p.rating,
                "style_compatibility_score": p.style_compatibility_base,
                "ai_fit_score": 94,
                "is_featured": p.is_featured,
                "skus": skus_out
            })
        return results

    def update_sku(self, sku_id: int, stock_level: int, price_override: Optional[float] = None) -> Dict[str, Any]:
        sku = self.brand_repo.update_sku_stock(sku_id, stock_level, price_override)
        if not sku:
            raise ResourceNotFoundError("ProductSKU", sku_id)
        return {
            "id": sku.id,
            "product_id": sku.product_id,
            "sku_code": sku.sku_code,
            "size": sku.size,
            "color": sku.color,
            "color_hex": sku.color_hex,
            "price_override": sku.price_override,
            "stock_level": sku.stock_level,
            "is_in_stock": sku.is_in_stock
        }

    def create_sponsored_placement(self, brand_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        p = self.brand_repo.create_placement(
            brand_id=brand_id,
            product_id=data["product_id"],
            placement_type=data.get("placement_type", "stylist_featured"),
            bid_amount=data.get("bid_amount_per_click", 0.50),
            daily_budget=data.get("daily_budget", 50.0)
        )
        return {
            "id": p.id,
            "brand_id": p.brand_id,
            "product_id": p.product_id,
            "product_title": p.product.title if p.product else "Product",
            "placement_type": p.placement_type,
            "bid_amount_per_click": p.bid_amount_per_click,
            "daily_budget": p.daily_budget,
            "spent_today": p.spent_today,
            "status": p.status,
            "impressions": p.impressions,
            "clicks": p.clicks,
            "conversions": p.conversions,
            "revenue_generated": p.revenue_generated,
            "created_at": p.created_at
        }

    def get_placements(self, brand_id: int) -> List[Dict[str, Any]]:
        placements = self.brand_repo.get_brand_placements(brand_id)
        return [
            {
                "id": p.id,
                "brand_id": p.brand_id,
                "product_id": p.product_id,
                "product_title": p.product.title if p.product else "Product",
                "placement_type": p.placement_type,
                "bid_amount_per_click": p.bid_amount_per_click,
                "daily_budget": p.daily_budget,
                "spent_today": p.spent_today,
                "status": p.status,
                "impressions": p.impressions,
                "clicks": p.clicks,
                "conversions": p.conversions,
                "revenue_generated": p.revenue_generated,
                "created_at": p.created_at
            }
            for p in placements
        ]

    def _format_brand(self, bp: BrandProfile) -> Dict[str, Any]:
        return {
            "id": bp.id,
            "user_id": bp.user_id,
            "brand_name": bp.brand_name,
            "slug": bp.slug,
            "logo_url": bp.logo_url,
            "banner_url": bp.banner_url,
            "description": bp.description,
            "website": bp.website,
            "commission_rate": bp.commission_rate,
            "return_rate_benchmark": bp.return_rate_benchmark,
            "current_return_rate": bp.current_return_rate,
            "is_verified": bp.is_verified,
            "created_at": bp.created_at
        }
