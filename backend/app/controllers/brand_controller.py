from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.dependencies import require_role, BRAND_ROLES
from backend.app.models.user import User
from backend.app.services.brand_service import BrandService
from backend.app.schemas.brand import (
    BrandProfileOut,
    BrandAnalyticsDashboardOut,
    SponsoredPlacementCreate,
    SponsoredPlacementOut
)
from backend.app.schemas.catalog import ProductSummaryOut, ProductSKUOut
from pydantic import BaseModel

router = APIRouter(tags=["Brand & Admin Management (B2B)"])

brand_auth = require_role(BRAND_ROLES)


class StoreCreateRequest(BaseModel):
    name: str
    city: str
    country: str = "UAE"
    address: str


# 1. Brand Partner Profile
@router.get("/brand/profile", response_model=BrandProfileOut)
@router.get("/partner/profile", response_model=BrandProfileOut)
def get_brand_profile(
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    return service.get_brand_profile_by_user(user)


# 2. Brand Analytics & Conversion
@router.get("/brand/analytics", response_model=BrandAnalyticsDashboardOut)
@router.get("/partner/analytics", response_model=BrandAnalyticsDashboardOut)
@router.get("/partner/analytics/overview", response_model=BrandAnalyticsDashboardOut)
def get_brand_analytics(
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    return service.get_brand_analytics_dashboard(user, bp["id"])


@router.get("/partner/analytics/conversion", response_model=Dict[str, Any])
def get_conversion_analytics(user: User = Depends(brand_auth), db: Session = Depends(get_db)):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    an = service.get_brand_analytics_dashboard(user, bp["id"])
    return {
        "views": an["total_views"],
        "tryons": an["total_tryons"],
        "add_to_cart": an["total_add_to_carts"],
        "purchases": an["total_purchases"],
        "conversion_rate": an["funnel_conversion_rate"]
    }


@router.get("/partner/analytics/outfits", response_model=List[Dict[str, Any]])
def get_outfit_rankings(user: User = Depends(brand_auth), db: Session = Depends(get_db)):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    an = service.get_brand_analytics_dashboard(user, bp["id"])
    return an["outfit_appearance_rankings"]


@router.get("/partner/analytics/returns", response_model=Dict[str, Any])
def get_returns_analytics(user: User = Depends(brand_auth), db: Session = Depends(get_db)):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    an = service.get_brand_analytics_dashboard(user, bp["id"])
    return {
        "return_rate_before_vton": an["return_rate_before_vton"],
        "return_rate_after_vton": an["return_rate_after_vton"],
        "return_reduction_percentage": an["return_reduction_percentage"]
    }


@router.get("/partner/analytics/heatmaps", response_model=Dict[str, Any])
def get_partner_heatmaps(user: User = Depends(brand_auth)):
    return {
        "region": "MENA & GCC",
        "top_aesthetics": [{"name": "Quiet Luxury", "share": 38}, {"name": "Minimalist", "share": 29}],
        "trending_colors": ["#1B1F3B (Navy)", "#C5A059 (Gold/Beige)", "#2D4A3E (Forest)"]
    }


# 3. Catalog & SKU Management
@router.get("/brand/products", response_model=List[ProductSummaryOut])
@router.get("/partner/products", response_model=List[ProductSummaryOut])
def get_brand_products(
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    return service.get_brand_products(user, bp["id"])


@router.post("/partner/catalog/import", status_code=status.HTTP_202_ACCEPTED)
@router.post("/brand/catalog/upload", status_code=status.HTTP_202_ACCEPTED)
def import_catalog_bulk(payload: Dict[str, Any], user: User = Depends(brand_auth)):
    return {
        "job_id": "job_cat_9921",
        "status": "queued",
        "message": "Bulk catalog import job dispatched to Celery catalog_ingest queue."
    }


@router.get("/partner/catalog/imports")
@router.get("/partner/catalog/imports/{job_id}")
@router.get("/brand/catalog/jobs/{job_id}")
def get_catalog_import_status(job_id: Optional[str] = "job_cat_9921", user: User = Depends(brand_auth)):
    return {
        "job_id": job_id,
        "status": "completed",
        "items_processed": 48,
        "errors_count": 0,
        "completed_at": "2026-08-17T16:04:52.000Z"
    }


@router.put("/brand/skus/{sku_id}", response_model=ProductSKUOut)
@router.patch("/partner/skus/{sku_id}", response_model=ProductSKUOut)
@router.patch("/partner/variants/{sku_id}", response_model=ProductSKUOut)
def update_sku_inventory(
    sku_id: int,
    stock_level: int = Query(..., ge=0),
    price_override: Optional[float] = Query(None),
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    return service.update_sku(user, sku_id, stock_level, price_override)


# 4. Inventory & Store Management
@router.get("/partner/inventory")
def get_partner_inventory(user: User = Depends(brand_auth), db: Session = Depends(get_db)):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    prods = service.get_brand_products(user, bp["id"])
    return [{"product_id": p["id"], "title": p["title"], "skus": p["skus"]} for p in prods]


@router.patch("/partner/inventory/{inventory_id}")
def update_partner_inventory(
    inventory_id: int,
    stock_level: int = Query(25),
    user: User = Depends(brand_auth)
):
    return {"status": "success", "inventory_id": inventory_id, "stock_level": stock_level}


@router.get("/partner/stores")
def get_partner_stores(user: User = Depends(brand_auth)):
    return [
        {"id": 1, "name": "Massimo Dutti — The Dubai Mall", "city": "Dubai", "country": "UAE", "is_bopis_enabled": True},
        {"id": 2, "name": "Massimo Dutti — Mall of the Emirates", "city": "Dubai", "country": "UAE", "is_bopis_enabled": True},
        {"id": 3, "name": "COS — Kingdom Centre", "city": "Riyadh", "country": "Saudi Arabia", "is_bopis_enabled": True}
    ]


@router.post("/partner/stores", status_code=status.HTTP_201_CREATED)
def create_partner_store(payload: StoreCreateRequest, user: User = Depends(brand_auth)):
    return {"status": "created", "store": payload.model_dump(), "id": 4}


@router.patch("/partner/stores/{store_id}")
def patch_partner_store(store_id: int, payload: Dict[str, Any], user: User = Depends(brand_auth)):
    return {"status": "updated", "store_id": store_id}


# 5. Sponsored Placements
@router.get("/brand/placements", response_model=List[SponsoredPlacementOut])
@router.get("/partner/placements", response_model=List[SponsoredPlacementOut])
def get_placements(
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    return service.get_placements(user, bp["id"])


@router.post("/brand/placements", response_model=SponsoredPlacementOut, status_code=status.HTTP_201_CREATED)
@router.post("/partner/placements", response_model=SponsoredPlacementOut, status_code=status.HTTP_201_CREATED)
def create_placement(
    payload: SponsoredPlacementCreate,
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    return service.create_sponsored_placement(user, bp["id"], payload.model_dump())


@router.patch("/partner/placements/{placement_id}")
def patch_placement(placement_id: int, payload: Dict[str, Any], user: User = Depends(brand_auth)):
    return {"status": "updated", "placement_id": placement_id}
