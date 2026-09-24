import json
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.config import settings
from backend.app.core.dependencies import get_current_user_optional
from backend.app.models.user import User
from backend.app.repositories.catalog_repository import CatalogRepository
from backend.app.services.search_service import SearchService
from backend.app.services.dashboard_service import DashboardService
from backend.app.services.product_context_service import ProductContextService
from backend.app.schemas.catalog import (
    CategoryOut,
    ProductSummaryOut,
    ProductDetailOut,
    StoreInventoryOut,
    SearchResponseOut,
    AutocompleteResponse
)
from backend.app.core.exceptions import ResourceNotFoundError
from backend.app.models.catalog import StoreLocation
from backend.app.services.capability_service import capability_flags

router = APIRouter(prefix="/catalog", tags=["Catalog & Products"])


def _product_summary(p, fit_score=None, style_score=None) -> ProductSummaryOut:
    return ProductSummaryOut(
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
        style_compatibility_score=style_score,
        ai_fit_score=fit_score,
        is_featured=p.is_featured
    )


@router.get("/categories", response_model=List[CategoryOut])
def get_categories(db: Session = Depends(get_db)):
    repo = CatalogRepository(db)
    return repo.get_categories()


@router.get("/dashboard", response_model=Dict[str, Any])
def get_home_dashboard(
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lon: Optional[float] = Query(None, ge=-180, le=180),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Home Dashboard (G2.4): personalized picks, trending, real recently-viewed,
    and new-from-your-brands, composed from the profile + real catalog.
    Optional lat/lon enable the real weather provider when configured (G2-S5)."""
    service = DashboardService(db)
    return service.get_dashboard(user.id if user else None, lat=lat, lon=lon)


@router.get("/search", response_model=SearchResponseOut)
def search_catalog(
    q: str = Query(..., min_length=1, max_length=100, description="Search query string"),
    category: Optional[str] = Query(None),
    brand_id: Optional[int] = Query(None),
    color: Optional[str] = Query(None),
    occasion: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None, ge=0, allow_inf_nan=False),
    max_price: Optional[float] = Query(None, ge=0, allow_inf_nan=False),
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
    min_price: Optional[float] = Query(None, ge=0, allow_inf_nan=False),
    max_price: Optional[float] = Query(None, ge=0, allow_inf_nan=False),
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

    # List views do not invent fit/style percentages. Those scores are
    # computed on the product page against the shopper's profile.
    return [_product_summary(p) for p in products]


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

    if user is not None:
        repo.record_product_view(user.id, p.id)

    context = ProductContextService(db).enrich_product(p, user)

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

    try:
        size_chart = json.loads(p.size_chart_json) if p.size_chart_json else {}
        if not isinstance(size_chart, dict):
            size_chart = {}
    except (TypeError, ValueError):
        size_chart = {}

    bnpl = context.get("bnpl") or {}
    installment = bnpl.get("installment_amount") if bnpl.get("eligible") else None

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
        style_compatibility_score=context.get("style_compatibility_score"),
        ai_fit_score=context.get("ai_fit_score"),
        is_featured=p.is_featured,
        description=p.description,
        description_ar=p.description_ar,
        material=p.material,
        care_instructions=p.care_instructions,
        images=json.loads(p.images) if p.images else [p.thumbnail_url],
        size_chart=size_chart,
        skus=skus_out,
        bnpl_monthly_installment=installment,
        bnpl=bnpl,
        brand=brand_out,
        related_outfits=context.get("related_outfits") or [],
        recommended_size=context.get("recommended_size"),
        recommended_size_available=context.get("recommended_size_available"),
        fit_available=bool(context.get("fit_available")),
        fit_reasoning=context.get("fit_reasoning"),
        style_compatibility_available=bool(context.get("style_compatibility_available")),
        style_compatibility_reason=context.get("style_compatibility_reason"),
    )


@router.get("/skus/{sku_id}/stores", response_model=List[StoreInventoryOut])
def get_bopis_stores_for_sku(sku_id: int, db: Session = Depends(get_db)):
    repo = CatalogRepository(db)
    return repo.get_stores_for_product_sku(sku_id)


class CapabilityFlagsOut(BaseModel):
    """J-01 marketing-honesty remediation (2026-09-06 audit): a single
    server-authoritative source of truth for what the platform can ACTUALLY
    do right now. The UI binds trust badges and commerce claims to these
    flags instead of hardcoding them — a claim shown without the matching
    capability is a bug, not a marketing decision.

    Every flag is derived from live configuration OR a real measurement, and the
    two are never conflated:

    * ``vton_gpu_ready`` / ``vton_engine_state`` / ``vton_renderable`` — from the
      live GPU worker probe, not from ``VTON_WORKER_URL``;
    * ``photo_upload_available`` — from ``storage_status()``, which folds the live
      put/get/delete probe into ``production_grade``; ``storage_mode`` is the
      provider's *name* and is not a verdict;
    * ``bnpl_live`` — from ``bnpl_is_live()``: payments live AND a provider key
      AND a live PSP adapter. A configured key alone is not an instalment offer;
    * ``payments_live`` — MEASURED: a payment service provider rail is live on
      this deployment (``payment_method_is_live`` for at least one method other
      than cash on delivery). It used to mirror ``PAYMENTS_LIVE``, and the
      consumer trust footer renders it as "Card payments are processed by a live
      payment service provider." — so one environment variable, with no key and
      no adapter, published a live-PSP claim (2026-09-23, same class as the
      catalogue literal);
    * ``payments_live_methods`` — the measured ids behind that verdict, so the
      claim is auditable rather than summarised;
    * ``cod_live`` — cash on delivery settles without a PSP, so it is reported
      separately: blocking it into ``payments_live`` would let the UI say
      "nothing works" on a deployment where COD orders do flow;
    * ``ai_stylist_live`` — MEASURED (2026-09-23): true only when a cached probe
      reached a provider and its credential was accepted. It used to mean "at
      least one provider key is configured", i.e. configuration published as
      readiness; the configuration fact now has its own name,
      ``ai_stylist_configured``, and ``ai_stylist_state`` carries the measured
      verdict (``not_probed`` before the first probe — the honest answer, and
      the reason the flag is then False rather than assumed true);
    * ``bopis_store_count`` is a real COUNT from the stores table — the UI must
      not promise cities the DB does not contain.
    """
    payments_live: bool
    #: MEASURED live method ids (see the module docstring). One list, not a claim.
    payments_live_methods: List[str]
    #: Measured: cash on delivery can settle here (no PSP involved).
    cod_live: bool
    #: CONFIGURATION: which mode this deployment is switched to. Not a verdict.
    payments_mode: str
    bnpl_live: bool
    #: MEASURED GPU readiness (live probe), not the presence of VTON_WORKER_URL.
    vton_gpu_ready: bool
    #: Canonical engine state; identical to /try-on/capabilities `engine_state`.
    vton_engine_state: str
    #: Whether the deployment offers try-on at all. False = not offered here.
    vton_offered: bool
    #: Whether a job submitted now can produce a render (ready or cold start).
    vton_renderable: bool
    ai_stylist_live: bool
    #: CONFIGURATION, not readiness: is at least one provider key present?
    ai_stylist_configured: bool
    #: MEASURED state: not_configured | not_probed | ready | degraded |
    #: unavailable | auth_failed | quota_exhausted | rate_limited | timeout.
    ai_stylist_state: str
    #: MEASURED: can a consumer photo actually be persisted right now?
    #: Derived from storage_status() (live probe when enabled), NOT from the
    #: `storage_mode` name — a configured-but-unreachable bucket reports "s3".
    photo_upload_available: bool
    bopis_live: bool
    bopis_store_count: int
    storage_mode: str
    returns_window_days: int


@router.get("/capabilities", response_model=CapabilityFlagsOut)
def get_capability_flags(db: Session = Depends(get_db)):
    """Shopper-facing capability flags.

    Delegates to ``capability_service`` — the same source of truth the health
    endpoints use, so this surface and ``/health`` cannot disagree about what
    the deployment can do.

    That claim was aspirational until 2026-09-22: ``capability_flags``
    hardcoded ``vton_gpu_ready = bool(settings.VTON_WORKER_URL)`` while
    ``/try-on/capabilities`` probed the worker live, so production answered
    ``true`` and ``temporarily_unavailable`` about the same GPU at the same
    moment. The flag is now derived from the shared probe classifier, and
    ``tests/test_capability_single_source.py`` pins the agreement.

    Why this endpoint also *starts* a readiness measurement (2026-09-24): the AI
    verdict is measured per process, and on serverless the operator `/health`
    probe only warms the instance it lands on. Measured in production: three
    consumer reads reported ``ai_stylist_state = not_probed`` /
    ``ai_stylist_live = false``, and after a single `/health` hit six consecutive
    consumer reads reported ``ready`` — one capability, two answers, decided by
    instance routing. ``refresh_when_unmeasured`` starts the existing bounded
    background refresh only when THIS instance has no usable verdict, so the
    response a shopper gets is still immediate and still honest (``not_probed``
    stays ``not_probed``) and the next read on that instance carries a real
    measurement. It never probes inline and is floored by a retry interval, so a
    failed provider cannot be turned into a burst by page traffic.
    """
    from backend.app.services.ai_readiness import refresh_when_unmeasured

    refresh_when_unmeasured()
    return CapabilityFlagsOut(**capability_flags(db))
