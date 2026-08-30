import json
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user_optional
from backend.app.models.user import User
from backend.app.repositories.catalog_repository import CatalogRepository
from backend.app.services.search_service import SearchService
from backend.app.services.dashboard_service import DashboardService
from backend.app.schemas.catalog import (
    CategoryOut,
    ProductSummaryOut,
    ProductDetailOut,
    StoreInventoryOut,
    SearchResponseOut,
    AutocompleteResponse
)
from backend.app.core.exceptions import ResourceNotFoundError

router = APIRouter(prefix="/catalog", tags=["Catalog & Products"])


@router.get("/categories", response_model=List[CategoryOut])
def get_categories(db: Session = Depends(get_db)):
    repo = CatalogRepository(db)
    return repo.get_categories()


@router.get("/dashboard", response_model=Dict[str, Any])
def get_home_dashboard(
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Home Dashboard (G2.4): personalized picks, trending, real recently-viewed,
    and new-from-your-brands, composed from the profile + real catalog."""
    service = DashboardService(db)
    return service.get_dashboard(user.id if user else None)


# =========================================================================
# Enhanced Full-Text Search, Ranking, Facets & Autocomplete Endpoints
# =========================================================================
@router.get("/search", response_model=SearchResponseOut)
def search_catalog(
    q: str = Query(..., min_length=1, max_length=100, description="Search query string"),
    category: Optional[str] = Query(None),
    brand_id: Optional[int] = Query(None),
    color: Optional[str] = Query(None),
    occasion: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    sort_by: str = Query("relevance", description="'relevance', 'price_asc', 'price_desc', 'rating', 'newest'"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    service = SearchService(db)
    return service.search_products(
        query=q,
        category=category,
        brand_id=brand_id,
        color=color,
        occasion=occasion,
        min_price=min_price,
        max_price=max_price,
        page=page,
        limit=limit,
        sort_by=sort_by
    )


@router.get("/autocomplete", response_model=AutocompleteResponse)
def autocomplete_catalog(
    q: str = Query(..., min_length=1, max_length=50, description="Prefix search term"),
    db: Session = Depends(get_db)
):
    service = SearchService(db)
    return service.autocomplete(query=q)


@router.get("/products", response_model=List[ProductSummaryOut])
def list_products(
    category: Optional[str] = Query(None),
    brand_id: Optional[int] = Query(None),
    color: Optional[str] = Query(None),
    occasion: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    search: Optional[str] = Query(None),
    sort_by: Optional[str] = Query("recommended"),
    is_featured: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    # Defense in depth: JS clients that accidentally serialize undefined/null
    # send the literal strings "undefined"/"null" — treat them as absent
    # instead of applying them as real filters (which silently empties the
    # entire catalog, as happened in production on 2026-08-29).
    def _clean(v):
        return None if v in (None, "", "undefined", "null") else v

    repo = CatalogRepository(db)
    products = repo.filter_products(
        category_slug=_clean(category),
        brand_id=brand_id,
        color=_clean(color),
        occasion=_clean(occasion),
        min_price=min_price,
        max_price=max_price,
        search_query=_clean(search),
        is_featured=is_featured,
        limit=limit,
        offset=offset,
        sort_by=_clean(sort_by) or "recommended"
    )

    results = []
    for p in products:
        results.append(ProductSummaryOut(
            id=p.id,
            brand_id=p.brand_id,
            brand_name=p.brand.brand_name if p.brand else "CONFIT Partner",
            category_id=p.category_id,
            category_name=p.category.name if p.category else "Fashion",
            title=p.title,
            title_ar=p.title_ar,
            slug=p.slug,
            base_price=p.base_price,
            currency=p.currency,
            thumbnail_url=p.thumbnail_url,
            color_family=p.color_family,
            dominant_hex=p.dominant_hex,
            style_tags=json.loads(p.style_tags) if p.style_tags else [],
            occasion_tags=json.loads(p.occasion_tags) if p.occasion_tags else [],
            rating=p.rating,
            style_compatibility_score=p.style_compatibility_base,
            ai_fit_score=94,
            is_featured=p.is_featured
        ))
    return results


@router.get("/products/{slug_or_id}", response_model=ProductDetailOut)
def get_product_detail(
    slug_or_id: str,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    repo = CatalogRepository(db)
    if slug_or_id.isdigit():
        p = repo.get_product_by_id(int(slug_or_id))
    else:
        p = repo.get_product_by_slug(slug_or_id)

    if not p:
        raise ResourceNotFoundError("Product", slug_or_id)

    # Record real recently-viewed history for authenticated users (G2.4).
    if user is not None:
        repo.record_product_view(user.id, p.id)

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

    brand_out = {
        "id": p.brand.id,
        "brand_name": p.brand.brand_name,
        "slug": p.brand.slug,
        "logo_url": p.brand.logo_url,
        "return_rate_benchmark": p.brand.return_rate_benchmark,
        "current_return_rate": p.brand.current_return_rate
    }

    return ProductDetailOut(
        id=p.id,
        brand_id=p.brand_id,
        brand_name=p.brand.brand_name,
        category_id=p.category_id,
        category_name=p.category.name,
        title=p.title,
        title_ar=p.title_ar,
        slug=p.slug,
        base_price=p.base_price,
        currency=p.currency,
        thumbnail_url=p.thumbnail_url,
        color_family=p.color_family,
        dominant_hex=p.dominant_hex,
        style_tags=json.loads(p.style_tags) if p.style_tags else [],
        occasion_tags=json.loads(p.occasion_tags) if p.occasion_tags else [],
        rating=p.rating,
        style_compatibility_score=p.style_compatibility_base,
        ai_fit_score=95,
        is_featured=p.is_featured,
        description=p.description,
        description_ar=p.description_ar,
        material=p.material,
        care_instructions=p.care_instructions,
        images=json.loads(p.images) if p.images else [p.thumbnail_url],
        size_chart=json.loads(p.size_chart_json) if p.size_chart_json else {
            "S": {"chest": "96cm", "waist": "80cm", "shoulder": "44cm"},
            "M": {"chest": "100cm", "waist": "84cm", "shoulder": "46cm"},
            "L": {"chest": "106cm", "waist": "90cm", "shoulder": "48cm"},
            "XL": {"chest": "112cm", "waist": "96cm", "shoulder": "50cm"}
        },
        skus=skus_out,
        bnpl_monthly_installment=round(p.base_price / 4, 2),
        brand=brand_out,
        related_outfits=[]
    )


@router.get("/skus/{sku_id}/stores", response_model=List[StoreInventoryOut])
def get_bopis_stores_for_sku(sku_id: int, db: Session = Depends(get_db)):
    repo = CatalogRepository(db)
    return repo.get_stores_for_product_sku(sku_id)
