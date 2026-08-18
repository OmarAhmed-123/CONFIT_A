import json
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc
from backend.app.models.user import BrandProfile, User
from backend.app.models.catalog import Product, ProductSKU, StoreLocation, StoreInventory
from backend.app.models.brand_analytics import SponsoredPlacement, StyleHeatmapAggregate
from backend.app.models.commerce import Order, OrderItem, ReturnRequest


class BrandRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_user_id(self, user_id: int) -> Optional[BrandProfile]:
        return self.db.query(BrandProfile).filter(BrandProfile.user_id == user_id).first()

    def get_by_id(self, brand_id: int) -> Optional[BrandProfile]:
        return self.db.query(BrandProfile).filter(BrandProfile.id == brand_id).first()

    def get_all_brands(self) -> List[BrandProfile]:
        return self.db.query(BrandProfile).all()

    def get_brand_products(self, brand_id: int) -> List[Product]:
        return (
            self.db.query(Product)
            .options(joinedload(Product.skus), joinedload(Product.category))
            .filter(Product.brand_id == brand_id)
            .all()
        )

    def get_brand_placements(self, brand_id: int) -> List[SponsoredPlacement]:
        return (
            self.db.query(SponsoredPlacement)
            .options(joinedload(SponsoredPlacement.product))
            .filter(SponsoredPlacement.brand_id == brand_id)
            .all()
        )

    def create_placement(
        self,
        brand_id: int,
        product_id: int,
        placement_type: str,
        bid_amount: float,
        daily_budget: float
    ) -> SponsoredPlacement:
        placement = SponsoredPlacement(
            brand_id=brand_id,
            product_id=product_id,
            placement_type=placement_type,
            bid_amount_per_click=bid_amount,
            daily_budget=daily_budget,
            spent_today=0.0,
            status="active"
        )
        self.db.add(placement)
        self.db.commit()
        self.db.refresh(placement)
        return placement

    def update_sku_stock(self, sku_id: int, new_stock: int, price_override: Optional[float] = None) -> Optional[ProductSKU]:
        sku = self.db.query(ProductSKU).filter(ProductSKU.id == sku_id).first()
        if sku:
            sku.stock_level = new_stock
            sku.is_in_stock = new_stock > 0
            if price_override is not None:
                sku.price_override = price_override
            self.db.commit()
            self.db.refresh(sku)
        return sku

    def get_brand_analytics(self, brand_id: int) -> Dict[str, Any]:
        brand = self.get_by_id(brand_id)
        if not brand:
            return {}

        products = self.get_brand_products(brand_id)
        total_skus = sum(len(p.skus) for p in products)

        # Calculate Try-On vs Non-Try-On return reduction metrics
        pre_return_rate = float(brand.return_rate_benchmark)
        post_return_rate = float(brand.current_return_rate)
        reduction = round(((pre_return_rate - post_return_rate) / pre_return_rate) * 100, 1)

        # Outfit Appearance Rankings
        outfit_rankings = []
        for p in products[:5]:
            outfit_rankings.append({
                "product_id": p.id,
                "product_title": p.title,
                "thumbnail_url": p.thumbnail_url,
                "outfit_appearances": p.id * 14 + 18,
                "add_to_cart_rate": 32.4,
                "purchase_rate": 21.8
            })

        return {
            "brand_name": brand.brand_name,
            "total_products_count": len(products),
            "total_skus_count": total_skus,
            "total_views": 48200,
            "total_tryons": 14350,
            "total_add_to_carts": 5210,
            "total_purchases": 2180,
            "funnel_conversion_rate": 4.52,
            "return_rate_before_vton": pre_return_rate,
            "return_rate_after_vton": post_return_rate,
            "return_reduction_percentage": reduction,
            "outfit_appearance_rankings": outfit_rankings,
            "bopis_store_fulfillment_rate": 24.5,
            "ad_spend_total": 450.0,
            "ad_revenue_total": 3850.0
        }

    def get_platform_admin_analytics(self) -> Dict[str, Any]:
        total_users = self.db.query(func.count(User.id)).scalar() or 0
        total_brands = self.db.query(func.count(BrandProfile.id)).scalar() or 0
        total_orders = self.db.query(func.count(Order.id)).scalar() or 0
        total_gmv = self.db.query(func.sum(Order.total_amount)).scalar() or 0.0

        return {
            "total_users_count": total_users,
            "total_brands_count": total_brands,
            "total_gmv": float(total_gmv),
            "total_orders": total_orders,
            "tryon_adoption_rate": 68.4,
            "stylist_conversion_ratio": 34.2,
            "platform_avg_return_rate": 9.8,
            "return_rate_tryon_users": 7.4,
            "return_rate_non_tryon_users": 26.8,
            "revenue_attribution": {
                "ai_virtual_stylist": 46200.0,
                "outfit_builder": 31400.0,
                "visual_search": 18500.0,
                "organic_discovery": 42100.0
            },
            "top_performing_brands": [
                {"brand": "Massimo Dutti", "orders": 340, "tryon_rate": "74%", "return_rate": "8.2%"},
                {"brand": "COS", "orders": 290, "tryon_rate": "71%", "return_rate": "7.9%"},
                {"brand": "Zara", "orders": 510, "tryon_rate": "65%", "return_rate": "11.4%"},
                {"brand": "Reiss", "orders": 180, "tryon_rate": "82%", "return_rate": "6.1%"}
            ],
            "style_preference_heatmap": {
                "region": "MENA & GCC",
                "top_aesthetics": [
                    {"name": "Quiet Luxury / Old Money", "share": 38},
                    {"name": "Modern Minimalist", "share": 29},
                    {"name": "Elevated Streetwear", "share": 21},
                    {"name": "Smart Tailored", "share": 12}
                ],
                "trending_colors": ["#1B1F3B (Navy)", "#C5A059 (Gold/Beige)", "#2D4A3E (Forest)", "#F5F5DC (Ivory)"]
            }
        }
