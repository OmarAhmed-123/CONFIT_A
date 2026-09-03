import json
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.app.models.catalog import Product, ProductSKU
from backend.app.models.user import BrandProfile, User, UserRole
from backend.app.repositories.brand_repository import BrandRepository
from backend.app.core.exceptions import ResourceNotFoundError, ValidationDomainError, AuthorizationError


class BrandService:
    def __init__(self, db: Session):
        self.db = db
        self.brand_repo = BrandRepository(db)

    def get_brand_profile_by_user(self, user: User) -> Dict[str, Any]:
        """Resolves Brand Organization for the requesting user with strict tenant validation."""
        bp = self.brand_repo.get_by_user_id(user.id)
        if not bp:
            if user.role == UserRole.ADMIN:
                all_b = self.brand_repo.get_all_brands()
                bp = all_b[0] if all_b else None
                if not bp:
                    raise ResourceNotFoundError("BrandProfile for admin", user.id)
            else:
                raise AuthorizationError(f"User {user.email} is not associated with an active Brand Organization.")
        return self._format_brand(bp)

    def get_brand_analytics_dashboard(self, user: User, brand_id: int) -> Dict[str, Any]:
        """Returns analytics strictly scoped to the user's verified brand tenant."""
        self._assert_brand_ownership(user, brand_id)
        return self.brand_repo.get_brand_analytics(brand_id)

    def get_brand_products(self, user: User, brand_id: int) -> List[Dict[str, Any]]:
        """Returns product catalog strictly scoped to the user's brand tenant."""
        self._assert_brand_ownership(user, brand_id)
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
                "style_compatibility_score": None,
                "ai_fit_score": None,
                "is_featured": p.is_featured,
                "skus": skus_out
            })
        return results

    def update_sku(self, user: User, sku_id: int, stock_level: int, price_override: Optional[float] = None) -> Dict[str, Any]:
        """Updates SKU inventory and price with strict tenant ownership verification."""
        sku = self.db.query(ProductSKU).filter(ProductSKU.id == sku_id).first()
        if not sku:
            raise ResourceNotFoundError("ProductSKU", sku_id)

        product = self.db.query(Product).filter(Product.id == sku.product_id).first()
        if not product:
            raise ResourceNotFoundError("Product for SKU", sku_id)

        # Enforce Tenant Isolation: Only SKU owner or Platform Admin can mutate
        self._assert_brand_ownership(user, product.brand_id)

        updated_sku = self.brand_repo.update_sku_stock(sku_id, stock_level, price_override)
        return {
            "id": updated_sku.id,
            "product_id": updated_sku.product_id,
            "sku_code": updated_sku.sku_code,
            "size": updated_sku.size,
            "color": updated_sku.color,
            "color_hex": updated_sku.color_hex,
            "price_override": updated_sku.price_override,
            "stock_level": updated_sku.stock_level,
            "is_in_stock": updated_sku.is_in_stock
        }

    def create_sponsored_placement(self, user: User, brand_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Creates sponsored ad placement with tenant and product ownership verification."""
        self._assert_brand_ownership(user, brand_id)

        product = self.db.query(Product).filter(Product.id == data["product_id"]).first()
        if not product or product.brand_id != brand_id:
            raise ValidationDomainError(f"Product {data['product_id']} does not belong to your brand organization.")

        # Parse dates if provided. An unparseable date is a client error — it
        # used to be silently replaced by None (placement quietly became open-ended).
        from datetime import datetime

        def _parse_iso(value, field):
            if value is None or isinstance(value, datetime):
                return value
            if isinstance(value, str):
                try:
                    return datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    raise ValidationDomainError(f"{field} must be an ISO-8601 datetime (got {value!r})")
            raise ValidationDomainError(f"{field} must be an ISO-8601 datetime string")

        start_date = _parse_iso(data.get("start_date"), "start_date")
        end_date = _parse_iso(data.get("end_date"), "end_date")

        try:
            p = self.brand_repo.create_placement(
                brand_id=brand_id,
                product_id=data["product_id"],
                placement_type=data.get("placement_type", "stylist_featured"),
                bid_amount=data.get("bid_amount_per_click", 0.50),
                daily_budget=data.get("daily_budget", 50.0),
                start_date=start_date,
                end_date=end_date
            )
        except ValueError as e:
            raise ValidationDomainError(str(e))
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

    def get_placements(self, user: User, brand_id: int) -> List[Dict[str, Any]]:
        """Returns sponsored placements strictly scoped to the verified brand tenant."""
        self._assert_brand_ownership(user, brand_id)
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

    def _assert_brand_ownership(self, user: User, target_brand_id: int) -> None:
        """Verifies that the user has tenant authorization for target_brand_id."""
        if user.role == UserRole.ADMIN:
            return  # Platform Admin has global oversight

        if not user.brand_profile:
            raise AuthorizationError("Access denied: User is not linked to any Brand Organization.")

        if user.brand_profile.id != target_brand_id:
            raise AuthorizationError(
                f"Tenant scope violation: Your account belongs to Brand #{user.brand_profile.id} ({user.brand_profile.brand_name}) "
                f"and cannot access or mutate resources of Brand #{target_brand_id}."
            )

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
