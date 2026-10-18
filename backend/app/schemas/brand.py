from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field
from backend.app.schemas.catalog import ProductSummaryOut, ProductSKUOut
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
    model_config = ConfigDict(extra="forbid")
    # Row validation is shared with CSV and reports all field errors per row.
    products: List[Dict[str, Any]] = Field(min_length=1, max_length=1000)



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
    data_source: str
    methodology: str
    return_cohorts: Dict[str, Any]
    brand_name: str
    total_products_count: int
    total_skus_count: int
    total_views: int
    total_tryons: int
    total_add_to_carts: int
    total_purchases: int
    # Nullable by contract: None means "no denominator" (zero views), which is
    # NOT the same claim as 0% conversion. Clients must render N/A, not a number.
    funnel_conversion_rate: Optional[float]
    return_rate_before_vton: Optional[float]
    return_rate_after_vton: Optional[float]
    return_reduction_percentage: Optional[float]
    outfit_appearance_rankings: List[Dict[str, Any]]
    bopis_store_fulfillment_rate: Optional[float]
    ad_spend_total: float
    ad_revenue_total: float


class AdminPlatformAnalyticsOut(BaseModel):
    total_users_count: int
    total_brands_count: int
    # Null when the selected population contains multiple currencies: adding
    # USD + EGP would fabricate a monetary total. Use gmv_by_currency instead.
    total_gmv: Optional[float] = None
    currency: Optional[str] = None
    currency_status: str = "no_data"
    gmv_by_currency: Dict[str, float] = Field(default_factory=dict)
    attribution_by_currency: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    total_orders: int
    # P1 (2026-09-22 audit): rates are Optional — None means "denominator was
    # zero, nothing was measured" and renders as N/A. A forced 0.0 would claim
    # a measured zero that never happened.
    tryon_adoption_rate: Optional[float] = None
    stylist_conversion_ratio: Optional[float] = None
    platform_avg_return_rate: Optional[float] = None
    return_rate_tryon_users: Optional[float] = None
    return_rate_non_tryon_users: Optional[float] = None
    revenue_attribution: Dict[str, Any]  # Exclusive attribution with priority to avoid double count
    # P1 financial-semantics separation: these figures are OPERATIONAL
    # metrics derived from transactional tables. They are NOT a billing
    # ledger: commission/attribution amounts must not be invoiced from this
    # payload without independent reconciliation against payment records.
    financial_semantics: str = (
        "operational_metrics — derived from transactional tables (orders, "
        "order_items, analytics events). NOT a verified billing ledger: do "
        "not invoice or settle from these figures; reconcile against payment "
        "provider records first."
    )
    top_performing_brands: List[Dict[str, Any]]
    style_preference_heatmap: Dict[str, Any]
    most_styled_items: Optional[List[Dict[str, Any]]] = None
    outfit_to_purchase_ratio: Optional[float] = None
    # G-15: the resolved window and how it was computed, so a consumer can tell
    # which question each figure answers instead of assuming "all time".
    time_range: Optional[Dict[str, Any]] = None
    # G-13: the revenue rule the headline was computed under.
    revenue_basis: Optional[str] = None
    revenue_excludes_statuses: Optional[List[str]] = None
    methodology: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(extra="allow")


class PartnerLeadCreate(BaseModel):
    company_name: str
    contact_name: str
    work_email: str
    website: Optional[str] = None
    phone: Optional[str] = None
    monthly_order_volume: Optional[str] = None
    message: Optional[str] = None
    source_path: Optional[str] = "/b2b"


class PartnerLeadOut(BaseModel):
    id: int
    status: str
    notification_status: str
    duplicate: bool = False
    message: str

    model_config = ConfigDict(from_attributes=True)


class BrandProductOut(ProductSummaryOut):
    """Partner catalog needs variants; public product summaries omit them."""
    skus: List[ProductSKUOut]


class BrandRegistrationRequest(BaseModel):
    brand_name: str = Field(min_length=2, max_length=255)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = Field(None, max_length=2000)
    description_ar: Optional[str] = Field(None, max_length=2000)
    website: Optional[str] = Field(None, max_length=500)
    logo_url: Optional[str] = Field(None, max_length=1000)
    country: Optional[str] = Field("UAE", max_length=100)
    city: Optional[str] = Field("Dubai", max_length=100)
    preferred_language: Optional[str] = Field("en", max_length=10)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BrandRegistrationResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    brand: BrandProfileOut
    message: str
    status: str  # "created" | "existing"
    next_step: str
    is_verified: bool

    model_config = ConfigDict(from_attributes=True)


class BrandOnboardingStep(BaseModel):
    key: str
    title: str
    description: str
    is_completed: bool
    action_url: str


class BrandOnboardingStatusOut(BaseModel):
    brand_id: int
    brand_name: str
    is_verified: bool
    is_published: bool
    publication_status: str  # "active" | "pending_review" | "draft"
    welcome_message: str
    primary_cta_label: str
    primary_cta_url: str
    completed_steps_count: int
    total_steps_count: int
    completion_percentage: int
    steps: List[BrandOnboardingStep]
    stores_count: int
    products_count: int
    active_promotions_count: int

    model_config = ConfigDict(from_attributes=True)


class PartnerStoreDetailOut(BaseModel):
    id: int
    brand_id: int
    name: str
    name_ar: str
    city: str
    country: str
    address: str
    latitude: float
    longitude: float
    phone: Optional[str] = None
    pickup_instructions: Optional[str] = None
    is_bopis_enabled: bool
    is_location_verified: bool
    inventory_items_count: int
    total_stock_units: int
    google_maps_url: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BrandMemberOut(BaseModel):
    """One membership row for the team list. ``email`` is nulled for viewers
    below manager (the controller strips it) — never the API trusting the UI."""
    id: int
    brand_id: int
    user_id: int
    full_name: str
    email: Optional[str] = None
    role: Literal["owner", "manager", "staff"]
    status: Literal["active", "revoked"]
    created_at: datetime
    revoked_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class BrandInvitationOut(BaseModel):
    id: int
    brand_id: int
    email: str
    role: Literal["owner", "manager", "staff"]
    status: Literal["pending", "accepted", "revoked", "expired"]
    created_at: datetime
    expires_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MemberInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    email: str = Field(min_length=3, max_length=255)
    role: Literal["owner", "manager", "staff"]


class MemberRoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    role: Literal["owner", "manager", "staff"]


class InvitationAcceptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    token: str = Field(min_length=20, max_length=128)


class MyMembershipOut(BaseModel):
    brand_id: int
    brand_name: str
    slug: str
    role: Literal["owner", "manager", "staff"]
    status: Literal["active", "revoked"]

    model_config = ConfigDict(from_attributes=True)
