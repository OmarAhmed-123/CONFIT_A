import json
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import hashlib
from sqlalchemy import Integer
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.config import settings
from backend.app.core.dependencies import get_current_user_optional, get_presentation_currency
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
from backend.app.services.pricing_presentation import (
    PresentationCurrency,
    present,
    presentation_meta,
    supported_currencies,
)

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
        # Real prior price, when one exists. Added to BOTH builders in this
        # file: they construct the response field-by-field, so a new column
        # is silently dropped and Pydantic's default (None) is served
        # instead — the storefront then shows no discount even though the
        # database has one.
        compare_at_price=p.compare_at_price,
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
    db: Session = Depends(get_db),
    fx: PresentationCurrency = Depends(get_presentation_currency),
):
    """Home Dashboard (G2.4): personalized picks, trending, real recently-viewed,
    and new-from-your-brands, composed from the profile + real catalog.
    Optional lat/lon enable the real weather provider when configured (G2-S5)."""
    service = DashboardService(db)
    return present(service.get_dashboard(user.id if user else None, lat=lat, lon=lon), fx)


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
    db: Session = Depends(get_db),
    fx: PresentationCurrency = Depends(get_presentation_currency),
):
    service = SearchService(db)
    result = service.search_products(
        query=q,
        category=category,
        brand_id=brand_id,
        color=color,
        occasion=occasion,
        min_price=fx.to_pricing(min_price),
        max_price=fx.to_pricing(max_price),
        page=page,
        limit=limit,
        sort_by=sort_by
    )
    # The price-range facet is money too — converting the results but not the
    # facet would hand the UI a slider whose bounds exclude its own items.
    payload = result if isinstance(result, dict) else result.model_dump()
    return present(payload, fx)


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
    include_sold_out: bool = Query(
        False,
        description=(
            "Storefront reads hide products with no purchasable stock. Set true "
            "only for merchandising/QA views that must see sold-out rows."
        ),
    ),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    fx: PresentationCurrency = Depends(get_presentation_currency),
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
        # Filters arrive in the DISPLAYED currency, so they are converted
        # back to the price book before they touch SQL (see
        # PresentationCurrency.to_pricing).
        min_price=fx.to_pricing(min_price),
        max_price=fx.to_pricing(max_price),
        search_query=_clean(search),
        is_featured=is_featured,
        limit=limit,
        offset=offset,
        sort_by=_clean(sort_by) or "recommended",
        # A sold-out product on the shelf is a promise the platform cannot
        # keep: the shopper clicks through, picks a size and only then meets
        # an InventoryUnavailableError at add-to-cart. Hidden by DEFAULT, and
        # in SQL so pagination still counts real rows.
        in_stock_only=not include_sold_out,
    )

    # List views do not invent fit/style percentages. Those scores are
    # computed on the product page against the shopper's profile.
    return present([_product_summary(p).model_dump() for p in products], fx)


@router.get("/products/{slug_or_id}", response_model=ProductDetailOut)
def get_product_detail(
    slug_or_id: str,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
    fx: PresentationCurrency = Depends(get_presentation_currency),
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

    detail = ProductDetailOut(
        id=p.id,
        brand_id=p.brand_id,
        brand_name=p.brand.brand_name,
        category_id=p.category_id,
        category_name=p.category.name,
        title=p.title,
        title_ar=p.title_ar,
        slug=p.slug,
        base_price=p.base_price,
        # Real prior price, when one exists. Added to BOTH builders in this
        # file: they construct the response field-by-field, so a new column
        # is silently dropped and Pydantic's default (None) is served
        # instead — the storefront then shows no discount even though the
        # database has one.
        compare_at_price=p.compare_at_price,
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
    # SKU price overrides and the BNPL installment are money too, and they are
    # nested — present() walks the whole payload so no nested price escapes
    # conversion while its parent gets converted.
    return present(detail.model_dump(), fx)


@router.get("/currencies")
def list_currencies(fx: PresentationCurrency = Depends(get_presentation_currency)):
    """Currencies the storefront can actually render, plus what this request
    resolved to.

    Deliberately reports ``available: false`` for a market currency with no
    configured FX rate instead of offering it and serving 1:1 numbers — a
    silently wrong price is worse than an unavailable option.
    """
    return {
        "active": presentation_meta(fx),
        "supported": supported_currencies(),
    }


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


@router.get("/revision")
def get_catalog_revision(db: Session = Depends(get_db)):
    """A cheap fingerprint of everything a shopper could see change.

    WHY THIS EXISTS
    ---------------
    The web client caches catalogue queries with `staleTime: 5 minutes`. That
    is right for bandwidth and wrong for stock: when a brand sells out a size
    or edits a price, every other role — shoppers browsing, an admin auditing,
    a second brand user — kept seeing the OLD figure for up to five minutes,
    with no way to know it was stale. A shopper could add a sold-out size to
    their bag and only discover it at checkout.

    Long-polling the full catalogue would fix staleness by throwing away the
    cache. Instead this endpoint returns a single hash over the fields that
    actually matter, so the client can poll something tiny and invalidate ONLY
    when something really moved.

    The signature covers stock levels, in-stock flags, prices, the sale price
    and store-level quantities — i.e. exactly the values rendered on a card, a
    product page and the brand inventory table. It deliberately excludes
    descriptive fields: re-fetching the world because someone fixed a typo
    would reintroduce the cost this is meant to avoid.

    One aggregate query, no row materialisation.
    """
    from sqlalchemy import func as _f
    from backend.app.models.catalog import Product as _P, ProductSKU as _S, StoreInventory as _I

    sku = db.query(
        _f.count(_S.id), _f.coalesce(_f.sum(_S.stock_level), 0),
        _f.coalesce(_f.sum(_f.cast(_S.is_in_stock, Integer)), 0),
        _f.coalesce(_f.sum(_S.price_override), 0),
    ).one()
    prod = db.query(
        _f.count(_P.id), _f.coalesce(_f.sum(_P.base_price), 0),
        _f.coalesce(_f.sum(_P.compare_at_price), 0),
        _f.coalesce(_f.sum(_f.cast(_P.is_active, Integer)), 0),
    ).one()
    inv = db.query(
        _f.count(_I.id), _f.coalesce(_f.sum(_I.quantity), 0),
        _f.coalesce(_f.sum(_I.reserved_quantity), 0),
    ).one()

    payload = "|".join(str(v) for v in (*sku, *prod, *inv))
    revision = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return {
        "revision": revision,
        # Stated so an operator can see WHY it changed without guessing.
        "counts": {
            "products": int(prod[0]), "skus": int(sku[0]),
            "store_inventory_rows": int(inv[0]),
        },
        "sellable_units": int(sku[1]),
        "store_units": int(inv[1]),
        "reserved_units": int(inv[2]),
    }


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
