"""Contracts for explicit platform-admin catalog operations.

Admin is intentionally not a partner tenant. These schemas back `/admin/catalog`
routes where an administrator must select a brand explicitly; partner contracts
remain scoped to the caller's linked BrandProfile.
"""
from datetime import datetime
from typing import Annotated, List, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from backend.app.schemas.money_types import PositiveMoney, OptionalPositiveMoney


CatalogTag = Annotated[str, Field(min_length=1, max_length=100)]


class AdminCatalogSKUCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sku_code: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    size: str = Field(min_length=1, max_length=20)
    color: str = Field(min_length=1, max_length=50)
    color_hex: str = Field("#1B1F3B", pattern=r"^#[0-9A-Fa-f]{6}$")
    price_override: OptionalPositiveMoney = None
    stock_level: int = Field(0, ge=0, le=100000, strict=True)


class AdminCatalogProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category_id: int = Field(gt=0, strict=True)
    title: str = Field(min_length=2, max_length=255)
    title_ar: str = Field(min_length=2, max_length=255)
    description: str = Field(min_length=2, max_length=4000)
    description_ar: str = Field(min_length=2, max_length=4000)
    base_price: PositiveMoney
    currency: str = Field("USD", pattern=r"^[A-Z]{3}$")
    material: Optional[str] = Field(None, max_length=255)
    care_instructions: Optional[str] = Field(None, max_length=500)
    color_family: str = Field(min_length=1, max_length=50)
    dominant_hex: str = Field("#1B1F3B", pattern=r"^#[0-9A-Fa-f]{6}$")
    thumbnail_url: HttpUrl
    images: List[HttpUrl] = Field(default_factory=list, max_length=20)
    style_tags: List[CatalogTag] = Field(default_factory=list, max_length=30)
    occasion_tags: List[CatalogTag] = Field(default_factory=list, max_length=30)
    is_featured: bool = False
    skus: List[AdminCatalogSKUCreate] = Field(min_length=1, max_length=100)


class AdminCatalogProductPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category_id: Optional[int] = Field(None, gt=0, strict=True)
    title: Optional[str] = Field(None, min_length=2, max_length=255)
    title_ar: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = Field(None, min_length=2, max_length=4000)
    description_ar: Optional[str] = Field(None, min_length=2, max_length=4000)
    base_price: OptionalPositiveMoney = None
    currency: Optional[str] = Field(None, pattern=r"^[A-Z]{3}$")
    material: Optional[str] = Field(None, max_length=255)
    care_instructions: Optional[str] = Field(None, max_length=500)
    color_family: Optional[str] = Field(None, min_length=1, max_length=50)
    dominant_hex: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    thumbnail_url: Optional[HttpUrl] = None
    images: Optional[List[HttpUrl]] = Field(None, max_length=20)
    style_tags: Optional[List[CatalogTag]] = Field(None, max_length=30)
    occasion_tags: Optional[List[CatalogTag]] = Field(None, max_length=30)
    is_featured: Optional[bool] = None

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one editable product field")
        required = {
            "category_id", "title", "title_ar", "description", "description_ar",
            "base_price", "currency", "color_family", "dominant_hex", "thumbnail_url",
            "images", "style_tags", "occasion_tags", "is_featured",
        }
        if any(getattr(self, field) is None for field in required & self.model_fields_set):
            raise ValueError("Required product fields cannot be null")
        return self


class AdminCatalogSKUPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stock_level: Optional[int] = Field(None, ge=0, le=100000, strict=True)
    # Explicit null clears an override and falls back to the product base price.
    price_override: OptionalPositiveMoney = None

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("Provide stock_level or price_override")
        return self


class AdminCatalogBrandSummaryOut(BaseModel):
    id: int
    brand_name: str
    slug: str
    is_verified: bool
    product_count: int
    active_product_count: int
    sku_count: int
    store_count: int
    placement_count: int


class AdminCatalogSnapshotOut(BaseModel):
    brand: AdminCatalogBrandSummaryOut
    products: List[dict]
    inventory: List[dict]
    placements: List[dict]
    stores: List[dict]
    imports: List[dict]
    categories: List[dict]
    generated_at: datetime
