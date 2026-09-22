from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, field_validator


class CategoryOut(BaseModel):
    id: int
    name: str
    name_ar: str
    slug: str
    parent_id: Optional[int]
    icon_name: str

    model_config = ConfigDict(from_attributes=True)


class ProductSKUOut(BaseModel):
    """Presentation contract for a SKU.

    NULL-TOLERANT ON PURPOSE (2026-09-22). `color_hex` is nullable in the
    database but its default lives in the ORM model, so any row written outside
    the ORM (a SQL backfill, a bulk import, a migration) stores NULL. A strict
    `str` here then raises a ValidationError while SERIALISING THE RESPONSE,
    which FastAPI surfaces as a 500 — and because the catalog endpoint returns a
    list, ONE such row takes down the ENTIRE catalog for that brand, not just
    the offending item. That was observed in production: a single product with
    NULL cosmetic fields made GET /brand/products return 500.

    A missing decorative hex is not a server error. The field now carries the
    same default the model declares, so the contract degrades gracefully instead
    of failing closed on cosmetics. Genuinely required identifiers (id,
    sku_code, size) stay strict — those really are errors if absent.
    """
    id: int
    product_id: int
    sku_code: str
    size: str
    color: str
    color_hex: Optional[str] = None
    price_override: Optional[float] = None
    stock_level: int = 0
    # An explicit NULL is not the same as an absent key: a plain default only
    # applies when the field is MISSING, so a NULL column still fails. These
    # validators turn NULL into the model's declared default.
    is_in_stock: bool = False

    @field_validator("stock_level", mode="before")
    @classmethod
    def _null_stock_is_zero(cls, v):
        return 0 if v is None else v

    @field_validator("is_in_stock", mode="before")
    @classmethod
    def _null_in_stock_is_false(cls, v):
        return False if v is None else v

    model_config = ConfigDict(from_attributes=True)


class BrandSummaryOut(BaseModel):
    id: int
    brand_name: str
    slug: str
    logo_url: Optional[str]
    return_rate_benchmark: int
    current_return_rate: int

    model_config = ConfigDict(from_attributes=True)


class ProductSummaryOut(BaseModel):
    id: int
    brand_id: int
    brand_name: str
    category_id: int
    category_name: str
    title: str
    title_ar: str
    slug: str
    base_price: float
    currency: str
    thumbnail_url: str
    color_family: str
    # Cosmetic/derived fields are nullable in the database but their defaults
    # live in the ORM model, so rows written outside the ORM store NULL. Strict
    # types here turn a missing decoration into a 500 for the whole list
    # response. See ProductSKUOut above for the full rationale.
    dominant_hex: Optional[str] = None
    style_tags: List[str] = []
    occasion_tags: List[str] = []
    rating: Optional[float] = None
    style_compatibility_score: Optional[int] = None
    ai_fit_score: Optional[int] = None
    is_featured: bool = False

    @field_validator("is_featured", mode="before")
    @classmethod
    def _null_featured_is_false(cls, v):
        return False if v is None else v

    @field_validator("style_tags", "occasion_tags", mode="before")
    @classmethod
    def _null_tags_are_empty(cls, v):
        return [] if v is None else v

    model_config = ConfigDict(from_attributes=True)


ProductOut = ProductSummaryOut


class ProductDetailOut(ProductSummaryOut):
    description: str
    description_ar: str
    material: Optional[str]
    care_instructions: Optional[str]
    images: List[str]
    size_chart: Dict[str, Any]
    skus: List[ProductSKUOut]
    bnpl_monthly_installment: Optional[float] = None
    bnpl: Optional[Dict[str, Any]] = None
    brand: BrandSummaryOut
    related_outfits: List[Dict[str, Any]] = []
    recommended_size: Optional[str] = None
    recommended_size_available: Optional[bool] = None
    fit_available: bool = False
    fit_reasoning: Optional[str] = None
    style_compatibility_available: bool = False
    style_compatibility_reason: Optional[str] = None


class StoreInventoryOut(BaseModel):
    store_id: int
    store_name: str
    store_name_ar: str
    address: str
    city: str
    country: str
    distance_km: Optional[float] = None
    quantity_available: int
    is_available_for_pickup: bool
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class ProductFilterParams(BaseModel):
    category: Optional[str] = None
    brand: Optional[str] = None
    color: Optional[str] = None
    occasion: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    search: Optional[str] = None
    sort_by: Optional[str] = "recommended"  # "recommended", "price_asc", "price_desc", "rating", "newest"


# =========================================================================
# Production Search, Facets & Autocomplete Schemas
# =========================================================================
class FacetCount(BaseModel):
    label: str
    value: str
    count: int
    selected: bool = False


class PriceRangeFacet(BaseModel):
    min_price: float
    max_price: float
    avg_price: float


class SearchFacetsOut(BaseModel):
    categories: List[FacetCount] = []
    brands: List[FacetCount] = []
    colors: List[FacetCount] = []
    price_range: PriceRangeFacet


class SearchResultItemOut(ProductSummaryOut):
    relevance_score: float = 1.0
    matched_field: str = "title"
    highlighted_snippet: Optional[str] = None
    in_stock: bool = True


class SearchResponseOut(BaseModel):
    query: str
    total_matches: int
    page: int
    limit: int
    results: List[SearchResultItemOut]
    facets: SearchFacetsOut
    did_you_mean: Optional[str] = None
    execution_time_ms: float


class AutocompleteSuggestion(BaseModel):
    title: str
    type: str  # "product", "category", "brand"
    slug_or_query: str
    subtitle: Optional[str] = None
    thumbnail_url: Optional[str] = None


class AutocompleteResponse(BaseModel):
    query: str
    suggestions: List[AutocompleteSuggestion]
