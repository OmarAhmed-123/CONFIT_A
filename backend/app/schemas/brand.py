from datetime import datetime
from typing import Optional, List, Dict, Any
from decimal import Decimal
from pydantic import BaseModel, ConfigDict
from backend.app.schemas.money_types import PositiveMoney, OptionalPositiveMoney


class BrandProfileOut(BaseModel):
    id: int
    user_id: int
    brand_name: str
    slug: str
    logo_url: Optional[str]
    banner_url: Optional[str]
    description: Optional[str]
    website: Optional[str]
    commission_rate: int
    return_rate_benchmark: int
    current_return_rate: int
    is_verified: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SKUCreateOrUpdate(BaseModel):
    sku_code: str
    size: str
    color: str
    color_hex: str = "#1B1F3B"
    price_override: OptionalPositiveMoney = None
    stock_level: int = 20


class ProductCreateInput(BaseModel):
    category_id: int
    title: str
    title_ar: str
    description: str
    description_ar: str
    base_price: PositiveMoney
    currency: str = "USD"
    material: Optional[str] = None
    care_instructions: Optional[str] = None
    color_family: str
    dominant_hex: str = "#1B1F3B"
    thumbnail_url: str
    images: List[str] = []
    style_tags: List[str] = []
    occasion_tags: List[str] = []
    skus: List[SKUCreateOrUpdate]


class CatalogBulkImportRequest(BaseModel):
    products: List[ProductCreateInput]


class SponsoredPlacementCreate(BaseModel):
    product_id: int
    placement_type: str = "stylist_featured"
    bid_amount_per_click: PositiveMoney = Decimal("0.50")
    daily_budget: PositiveMoney = Decimal("50.00")
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class SponsoredPlacementOut(BaseModel):
    id: int
    brand_id: int
    product_id: int
    product_title: str
    placement_type: str
    bid_amount_per_click: float
    daily_budget: float
    spent_today: float
    status: str
    impressions: int
    clicks: int
    conversions: int
    revenue_generated: float
    created_at: datetime
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class BrandAnalyticsDashboardOut(BaseModel):
    brand_name: str
    total_products_count: int
    total_skus_count: int
    total_views: int
    total_tryons: int
    total_add_to_carts: int
    total_purchases: int
    funnel_conversion_rate: float
    return_rate_before_vton: float
    return_rate_after_vton: float
    return_reduction_percentage: float
    outfit_appearance_rankings: List[Dict[str, Any]]
    bopis_store_fulfillment_rate: float
    ad_spend_total: float
    ad_revenue_total: float


class AdminPlatformAnalyticsOut(BaseModel):
    total_users_count: int
    total_brands_count: int
    total_gmv: float
    total_orders: int
    tryon_adoption_rate: float
    stylist_conversion_ratio: float
    platform_avg_return_rate: float
    return_rate_tryon_users: float
    return_rate_non_tryon_users: float
    revenue_attribution: Dict[str, Any]  # Exclusive attribution with priority to avoid double count
    top_performing_brands: List[Dict[str, Any]]
    style_preference_heatmap: Dict[str, Any]
    most_styled_items: Optional[List[Dict[str, Any]]] = None
    outfit_to_purchase_ratio: Optional[float] = None

    model_config = ConfigDict(extra="allow")
