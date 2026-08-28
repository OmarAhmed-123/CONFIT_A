from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict


class CategoryOut(BaseModel):
    id: int
    name: str
    name_ar: str
    slug: str
    parent_id: Optional[int]
    icon_name: str

    model_config = ConfigDict(from_attributes=True)


class ProductSKUOut(BaseModel):
    id: int
    product_id: int
    sku_code: str
    size: str
    color: str
    color_hex: str
    price_override: Optional[float]
    stock_level: int
    is_in_stock: bool

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
    dominant_hex: str
    style_tags: List[str]
    occasion_tags: List[str]
    rating: float
    style_compatibility_score: int
    ai_fit_score: int = 94
    is_featured: bool

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
    bnpl_monthly_installment: float  # e.g., base_price / 4
    brand: BrandSummaryOut
    related_outfits: List[Dict[str, Any]] = []


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
