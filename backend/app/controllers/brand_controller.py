from decimal import Decimal
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, status, UploadFile, File, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, ConfigDict, model_validator
import json
from backend.app.core.money import to_decimal, to_float, validate_money, money_add, money_sub, MoneyValueError, MoneyRangeError

from backend.app.core.database import get_db
from backend.app.core.dependencies import require_role, BRAND_ROLES
from backend.app.models.user import User
from backend.app.services.brand_service import BrandService
from backend.app.services.brand_catalog_service import BrandCatalogService
from backend.app.repositories.brand_repository import BrandRepository
from backend.app.schemas.brand import (
    BrandProfileOut,
    BrandProductOut,
    CatalogBulkImportRequest,
    BrandAnalyticsDashboardOut,
    SponsoredPlacementCreate,
    SponsoredPlacementOut,
    PartnerLeadCreate,
    PartnerLeadOut
)
from backend.app.schemas.catalog import ProductSummaryOut, ProductSKUOut
from backend.app.services.partner_lead_service import PartnerLeadService
from backend.app.core.rate_limit import limiter

router = APIRouter(tags=["Brand & Admin Management (B2B)"])

brand_auth = require_role(BRAND_ROLES)


@router.post("/brand/request-demo", response_model=PartnerLeadOut, status_code=status.HTTP_201_CREATED)
@router.post("/b2b/request-demo", response_model=PartnerLeadOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/hour")
def request_partner_demo(
    request: Request,
    payload: PartnerLeadCreate,
    db: Session = Depends(get_db),
):
    """Public B2B request-demo workflow.

    Persists a lead and optionally sends the approved SMTP notification if email
    transport is configured. It does not create a partner account, grant roles,
    or pretend a CRM integration exists.
    """
    import re
    email = payload.work_email.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(status_code=422, detail={"error": {"code": "VALIDATION_ERROR", "message": "A valid work email is required."}})
    if len(payload.company_name.strip()) < 2 or len(payload.contact_name.strip()) < 2:
        raise HTTPException(status_code=422, detail={"error": {"code": "VALIDATION_ERROR", "message": "Company and contact name are required."}})
    lead = PartnerLeadService(db).submit(
        payload={**payload.model_dump(), "work_email": email},
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return PartnerLeadOut(
        id=lead["id"],
        status=lead["status"],
        notification_status=lead["notification_status"],
        duplicate=lead["duplicate"],
        message="Request received. The CONFIT team will review it using the persisted lead workflow.",
    )


def _audit(db: Session, user: User, action: str, resource_type: str,
           resource_id, details: dict | None = None) -> None:
    """Persist a B2B admin audit event.

    Final truth audit finding: none of the brand/admin mutating endpoints
    (inventory, catalog, placements, stores) wrote to AuditLog. Audit coverage
    of security-sensitive B2B operations is a BRD/security requirement, so
    these call sites now persist real AuditLog rows.

    Never raises: auditing must not break the business operation, but a failure
    is logged so it is not silent.
    """
    try:
        from backend.app.repositories.user_repository import UserRepository
        UserRepository(db).log_audit(
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            user_id=getattr(user, "id", None),
            details=json.dumps(details or {}, default=str)[:2000],
        )
    except Exception as _e:  # pragma: no cover - defensive
        import logging
        logging.getLogger(__name__).warning("audit_write_failed action=%s err=%s", action, _e)


class StoreCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    name: str = Field(min_length=1, max_length=255)
    name_ar: Optional[str] = Field(None, max_length=255)
    city: str = Field(min_length=1, max_length=100)
    country: str = Field("UAE", min_length=1, max_length=100)
    address: str = Field(min_length=1, max_length=500)
    latitude: float = Field(0, ge=-90, le=90)
    longitude: float = Field(0, ge=-180, le=180)
    phone: Optional[str] = Field(None, max_length=50)
    pickup_instructions: Optional[str] = Field(None, max_length=2000)
    is_bopis_enabled: bool = True


class StoreUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    name_ar: Optional[str] = Field(None, min_length=1, max_length=255)
    city: Optional[str] = Field(None, min_length=1, max_length=100)
    country: Optional[str] = Field(None, min_length=1, max_length=100)
    address: Optional[str] = Field(None, min_length=1, max_length=500)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    phone: Optional[str] = Field(None, max_length=50)
    pickup_instructions: Optional[str] = Field(None, max_length=2000)
    is_bopis_enabled: Optional[bool] = None

    @model_validator(mode="after")
    def reject_null_required_columns(self):
        required = {"name", "name_ar", "city", "country", "address", "latitude", "longitude", "is_bopis_enabled"}
        if not self.model_fields_set:
            raise ValueError("Provide at least one store field")
        if any(getattr(self, field) is None for field in required & self.model_fields_set):
            raise ValueError("Required store fields cannot be null")
        return self


class InventoryUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    store_id: int = Field(gt=0, strict=True)
    sku_id: int = Field(gt=0, strict=True)
    quantity: int = Field(ge=0, le=100000, strict=True)


# 1. Brand Partner Profile
@router.get("/brand/profile", response_model=BrandProfileOut)
@router.get("/partner/profile", response_model=BrandProfileOut)
def get_brand_profile(
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    return service.get_brand_profile_by_user(user)


# 2. Brand Analytics & Conversion - REAL DATA
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
    # Tenant check stays explicit and unconditional -- the speedup below must
    # never come at the cost of the authorization step.
    service.assert_brand_ownership(user, bp["id"])
    repo = BrandRepository(db)
    # Only the activity snapshot is needed here, not the whole dashboard. The
    # previous call to get_brand_analytics_dashboard() also computed outfit
    # rankings, return cohorts, BOPIS fulfilment and ad totals -- five extra
    # round trips to the managed database whose results were thrown away, on an
    # endpoint the audit measured at over 6s. Same six values, same definitions
    # (both callers share get_activity_snapshot), far fewer hops.
    an = repo.get_activity_snapshot(bp["id"])
    per_sku = repo.get_conversion_analytics_per_sku(bp["id"])
    # Two DIFFERENT things, deliberately returned under two different keys.
    #
    # activity_snapshot counts four unrelated tables independently. Dividing one
    # by another mixes measurement units -- that is how this endpoint previously
    # produced 3500% (35 try-on rows over 0 retained view rows). It stays because
    # raw volume is genuinely useful, but it is NOT a funnel.
    #
    # attributed_funnel only ever counts SESSIONS, each stage a subset of the one
    # before it, so it cannot exceed 100%. It reports its own coverage because it
    # can only see activity that carried a session token.
    #
    # The legacy top-level keys are preserved so existing clients do not break.
    funnel = repo.get_attributed_funnel(bp["id"])
    return {
        "views": an["total_views"],
        "tryons": an["total_tryons"],
        "add_to_cart": an["total_add_to_carts"],
        "purchases": an["total_purchases"],
        "conversion_rate": an["funnel_conversion_rate"],
        "per_sku": per_sku,
        "grain": "product",
        "methodology": an["methodology"],
        "activity_snapshot": {
            "grain": "product",
            "is_funnel": False,
            "views": an["total_views"],
            "tryons": an["total_tryons"],
            "add_to_cart": an["total_add_to_carts"],
            "purchases": an["total_purchases"],
            "methodology": an["methodology"],
        },
        "attributed_funnel": funnel,
    }


@router.get("/partner/analytics/outfits", response_model=List[Dict[str, Any]])
def get_outfit_rankings(user: User = Depends(brand_auth), db: Session = Depends(get_db)):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    repo = BrandRepository(db)
    analytics = repo.get_brand_analytics(bp["id"])
    return analytics["outfit_appearance_rankings"]


@router.get("/partner/analytics/returns", response_model=Dict[str, Any])
def get_returns_analytics(user: User = Depends(brand_auth), db: Session = Depends(get_db)):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    repo = BrandRepository(db)
    return repo.get_brand_return_metrics(bp["id"])


@router.get("/partner/analytics/heatmaps", response_model=Dict[str, Any])
def get_partner_heatmaps(
    region: str = Query("MENA", description="Region filter"),
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    bp = BrandService(db).get_brand_profile_by_user(user)
    return BrandRepository(db).get_brand_preference_heatmaps(bp["id"], region=region)


# 3. Catalog & SKU Management - REAL IMPLEMENTATION
@router.get("/brand/products", response_model=List[BrandProductOut])
@router.get("/partner/products", response_model=List[BrandProductOut])
def get_brand_products(
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    return service.get_brand_products(user, bp["id"])


@router.post("/partner/catalog/import", status_code=status.HTTP_202_ACCEPTED)
@router.post("/brand/catalog/upload", status_code=status.HTTP_202_ACCEPTED)
def import_catalog_bulk(
    payload: CatalogBulkImportRequest,
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    bp = BrandService(db).get_brand_profile_by_user(user)
    return BrandCatalogService(db).process_json_import(payload.products, bp["id"], actor_id=user.id)


@router.post("/partner/catalog/upload/csv", status_code=status.HTTP_202_ACCEPTED)
async def upload_catalog_csv(
    file: UploadFile = File(...),
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    """
    Bulk SKU import via CSV with image assets.
    Real implementation with validation, idempotency, transactional behavior.
    """
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)

    # Validate file
    if not (file.filename or '').lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be CSV")

    # Size limit: 10MB
    content = await file.read(BrandCatalogService.MAX_BYTES + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File exceeds 10MB limit")

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        csv_text = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            csv_text = content.decode('utf-8-sig')
        except:
            raise HTTPException(status_code=400, detail="Invalid CSV encoding, must be UTF-8")

    # MIME validation
    if not file.content_type or "csv" not in file.content_type.lower():
        # Allow if filename is csv even if mime not csv (some browsers)
        if not file.filename.lower().endswith('.csv'):
            raise HTTPException(status_code=400, detail="Invalid file type, must be CSV")

    catalog_service = BrandCatalogService(db)
    try:
        result = catalog_service.process_csv_import(csv_text, bp["id"], file.filename, actor_id=user.id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail="Import interrupted; inspect import history before retrying")


@router.get("/partner/catalog/imports")
def get_catalog_imports(
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    repo = BrandRepository(db)
    jobs = repo.get_brand_import_jobs(bp["id"], limit=limit)
    return [
        {
            "job_id": j.id,
            "file_name": j.file_name,
            "status": j.status,
            "total_rows": j.total_rows,
            "accepted_rows": j.accepted_rows,
            "rejected_rows": j.rejected_rows,
            "duplicate_rows": j.duplicate_rows,
            "created_at": j.created_at,
            "completed_at": j.completed_at
        }
        for j in jobs
    ]


@router.get("/partner/catalog/imports/{job_id}")
@router.get("/brand/catalog/jobs/{job_id}")
def get_catalog_import_status(
    job_id: int,
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    repo = BrandRepository(db)
    job = repo.get_import_job(job_id, bp["id"])
    if not job:
        raise HTTPException(status_code=404, detail=f"Import job {job_id} not found for your brand")

    errors = []
    if job.errors_json:
        try:
            errors = json.loads(job.errors_json)
        except (TypeError, ValueError) as exc:
            # A corrupt errors_json must be visible, not rendered as "no errors".
            errors = [{"row": None, "field": "errors_json",
                       "message": f"stored error log is unreadable: {type(exc).__name__}", "value": None}]

    return {
        "job_id": job.id,
        "file_name": job.file_name,
        "status": job.status,
        "total_rows": job.total_rows,
        "accepted_rows": job.accepted_rows,
        "rejected_rows": job.rejected_rows,
        "duplicate_rows": job.duplicate_rows,
        "errors": errors[:50],  # Limit to 50
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at
    }


@router.put("/brand/skus/{sku_id}", response_model=ProductSKUOut)
@router.patch("/partner/skus/{sku_id}", response_model=ProductSKUOut)
@router.patch("/partner/variants/{sku_id}", response_model=ProductSKUOut)
def update_sku_inventory(
    sku_id: int,
    stock_level: int = Query(..., ge=0, le=100000, description="New stock level"),
    price_override: Optional[Decimal] = Query(None, gt=0, le=100000, max_digits=12, decimal_places=2,
                                               description="Price override (2dp, > 0)"),
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    result = service.update_sku(user, sku_id, stock_level, price_override)
    _audit(db, user, "BRAND_INVENTORY_UPDATED", "ProductSKU", sku_id,
           {"stock_level": stock_level, "price_override": str(price_override) if price_override is not None else None})
    return result


# 4. Inventory & Store Management - REAL IMPLEMENTATION
@router.get("/partner/inventory")
def get_partner_inventory(
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    """Store-level inventory for the caller's brand ONLY.

    P1 FIX (cross-tenant inventory leak, production-confirmed 2026-09-22):
    this endpoint used to select StoreInventory rows by `sku_id IN (...)`
    with NO constraint that the owning StoreLocation belongs to the same
    brand. Legacy/seed rows attach a tenant's SKU to another tenant's store,
    so COS (0 stores) rendered "Store #1: 6 avail" — Store #1 belongs to
    Massimo Dutti. That is not a display glitch: it published another
    tenant's store id and stock level into this tenant's API response.

    The breakdown is now produced by ONE join that is scoped by the same
    brand_id as the store-locations count, so the two numbers can never
    disagree again (`get_brand_store_inventory_map` is the single source of
    truth, shared with /partner/stores — DRY).
    """
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    repo = BrandRepository(db)

    products = repo.get_brand_products(bp["id"])
    # Tenant-scoped, single query, no N+1: {sku_id: [inventory rows]} where the
    # store is verified to belong to THIS brand.
    inv_map = repo.get_brand_store_inventory_map(bp["id"])

    result = []
    for product in products:
        sku_details = []
        for sku in product.skus:
            invs = inv_map.get(sku.id, [])
            sku_details.append({
                "id": sku.id,
                "sku_code": sku.sku_code,
                "size": sku.size,
                "color": sku.color,
                "stock_level": sku.stock_level,
                "is_in_stock": sku.is_in_stock,
                "price_override": sku.price_override,
                "store_inventories": [
                    {"id": inv.id, "store_id": inv.store_id, "store_name": inv.store_name,
                     "quantity": inv.quantity, "reserved": inv.reserved_quantity,
                     "available": inv.quantity - inv.reserved_quantity}
                    for inv in invs
                ]
            })

        result.append({
            "product_id": product.id,
            "title": product.title,
            "thumbnail_url": product.thumbnail_url,
            "total_stock": sum(s.stock_level for s in product.skus),
            "skus": sku_details
        })

    return result


@router.post("/partner/inventory")
def set_partner_inventory(
    payload: InventoryUpdateRequest,
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    """Explicit store/SKU upsert; PATCH continues to require a real inventory ID."""
    bp = BrandService(db).get_brand_profile_by_user(user)
    try:
        inv = BrandRepository(db).update_store_inventory(payload.store_id, payload.sku_id, payload.quantity, bp["id"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _audit(db, user, "BRAND_STORE_INVENTORY_UPDATED", "StoreInventory", inv.id,
           {"brand_id": bp["id"], "quantity": inv.quantity})
    return {"inventory_id": inv.id, "store_id": inv.store_id, "sku_id": inv.sku_id,
            "quantity": inv.quantity, "reserved": inv.reserved_quantity,
            "available": inv.quantity - inv.reserved_quantity}


@router.patch("/partner/inventory/{inventory_id}")
def update_partner_inventory(
    inventory_id: int,
    payload: InventoryUpdateRequest,
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    """Update store inventory with tenant isolation and concurrency control"""
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    repo = BrandRepository(db)

    from backend.app.models.catalog import StoreInventory, StoreLocation, ProductSKU, Product
    existing = db.query(StoreInventory).join(StoreLocation).join(
        ProductSKU, ProductSKU.id == StoreInventory.sku_id
    ).join(Product, Product.id == ProductSKU.product_id).filter(
        StoreInventory.id == inventory_id, StoreLocation.brand_id == bp["id"],
        Product.brand_id == bp["id"], StoreInventory.store_id == payload.store_id,
        StoreInventory.sku_id == payload.sku_id,
    ).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Inventory not found for this store, SKU and brand")
    try:
        inv = repo.update_store_inventory(
            store_id=payload.store_id,
            sku_id=payload.sku_id,
            quantity=payload.quantity,
            brand_id=bp["id"]
        )
        _audit(db, user, "BRAND_STORE_INVENTORY_UPDATED", "StoreInventory", inv.id,
               {"brand_id": bp["id"], "quantity": inv.quantity})
        return {
            "status": "success",
            "inventory_id": inv.id,
            "store_id": inv.store_id,
            "sku_id": inv.sku_id,
            "quantity": inv.quantity,
            "reserved": inv.reserved_quantity,
            "available": inv.quantity - inv.reserved_quantity
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/partner/stores")
def get_partner_stores(
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    repo = BrandRepository(db)
    stores = repo.get_brand_stores(bp["id"])
    return [
        {
            "id": s.id,
            "name": s.name,
            "name_ar": s.name_ar,
            "city": s.city,
            "country": s.country,
            "address": s.address,
            "latitude": s.latitude,
            "longitude": s.longitude,
            "phone": s.phone,
            "is_bopis_enabled": s.is_bopis_enabled,
            "created_at": s.created_at
        }
        for s in stores
    ]


@router.post("/partner/stores", status_code=status.HTTP_201_CREATED)
def create_partner_store(
    payload: StoreCreateRequest,
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    repo = BrandRepository(db)
    try:
        store = repo.create_store(bp["id"], payload.model_dump())
        _audit(db, user, "BRAND_STORE_CREATED", "Store", store.id,
               {"brand_id": bp["id"], "name": store.name, "city": store.city})
        return {
            "status": "created",
            "id": store.id,
            "name": store.name,
            "city": store.city,
            "country": store.country,
            "is_bopis_enabled": store.is_bopis_enabled
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/partner/stores/{store_id}")
def patch_partner_store(
    store_id: int,
    payload: StoreUpdateRequest,
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    repo = BrandRepository(db)
    try:
        store = repo.update_store(store_id, bp["id"], payload.model_dump(exclude_unset=True))
        _audit(db, user, "BRAND_STORE_UPDATED", "Store", store.id, {"brand_id": bp["id"]})
        return {
            "status": "updated",
            "id": store.id,
            "name": store.name,
            "city": store.city,
            "country": store.country,
            "is_bopis_enabled": store.is_bopis_enabled
        }
    except ValueError as e:
        raise HTTPException(status_code=404 if "not found" in str(e).lower() else 400, detail=str(e))


# 5. Sponsored Placements - REAL WITH VALIDATION
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
    try:
        created = service.create_sponsored_placement(user, bp["id"], payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _audit(db, user, "BRAND_PLACEMENT_CREATED", "SponsoredPlacement",
           created.get("id") if isinstance(created, dict) else getattr(created, "id", None),
           {"brand_id": bp["id"], "payload": payload.model_dump()})
    return created


@router.patch("/partner/placements/{placement_id}")
def patch_placement(
    placement_id: int,
    payload: Dict[str, Any],
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)

    # Verify ownership with locking
    from backend.app.models.brand_analytics import SponsoredPlacement
    plc = db.query(SponsoredPlacement).filter(
        SponsoredPlacement.id == placement_id,
        SponsoredPlacement.brand_id == bp["id"]
    ).with_for_update().first()

    if not plc:
        raise HTTPException(status_code=404, detail=f"Placement {placement_id} not found for your brand")

    from backend.app.services.placement_policy import validate_placement
    allowed = ["bid_amount_per_click", "daily_budget", "status", "placement_type", "start_date", "end_date"]
    if not payload or set(payload) - set(allowed):
        raise HTTPException(status_code=422, detail="Provide only editable placement fields")
    candidate = {k: payload.get(k, getattr(plc, k)) for k in allowed}
    if candidate["status"] not in ["active", "paused", "budget_exhausted"]:
        raise HTTPException(status_code=422, detail="Invalid status")
    try:
        candidate = validate_placement(candidate, spent=plc.spent_today)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    for key, value in candidate.items():
        setattr(plc, key, value)

    _audit(db, user, "BRAND_PLACEMENT_UPDATED", "SponsoredPlacement", placement_id,
           {"brand_id": bp["id"], "changed_fields": [k for k in allowed if k in payload]})
    db.commit()
    db.refresh(plc)

    return {
        "result": "updated",
        "placement_id": plc.id,
        "bid_amount_per_click": plc.bid_amount_per_click,
        "daily_budget": plc.daily_budget,
        "status": plc.status
    }


@router.delete("/partner/placements/{placement_id}")
def delete_placement(
    placement_id: int,
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    from backend.app.models.brand_analytics import SponsoredPlacement
    plc = db.query(SponsoredPlacement).filter(
        SponsoredPlacement.id == placement_id,
        SponsoredPlacement.brand_id == bp["id"]
    ).first()

    if not plc:
        raise HTTPException(status_code=404, detail=f"Placement {placement_id} not found")

    # FINANCIAL RECORD RETENTION.
    # A hard DELETE cascades to ad_ledger_entries and destroys the billing
    # history of money that was actually charged — the brand loses the evidence
    # behind its invoice, and a later placement reusing the id would inherit
    # the orphaned rows. A journal you can delete is not a journal.
    #
    # So: a placement that has EVER been billed is cancelled (soft-deleted),
    # never erased. One with no financial history has nothing to protect and is
    # removed as before, so the endpoint stays useful for clearing mistakes.
    from backend.app.models.brand_analytics import AdLedgerEntry
    ledger_rows = db.query(AdLedgerEntry).filter(
        AdLedgerEntry.placement_id == placement_id).count()

    _audit(db, user, "BRAND_PLACEMENT_DELETED", "SponsoredPlacement", placement_id,
           {"brand_id": bp["id"], "status": plc.status,
            "daily_budget": str(plc.daily_budget), "bid": str(plc.bid_amount_per_click),
            "ledger_entries": ledger_rows,
            "mode": "cancelled_retaining_ledger" if ledger_rows else "hard_deleted"})

    if ledger_rows:
        plc.status = "cancelled"
        db.commit()
        return {
            "status": "cancelled",
            "placement_id": placement_id,
            "detail": (f"Placement has {ledger_rows} billing ledger entr"
                       f"{'y' if ledger_rows == 1 else 'ies'} and was cancelled rather than "
                       "deleted. It will no longer serve; its financial history is retained "
                       "for reconciliation and invoicing."),
            "ledger_entries_retained": ledger_rows,
        }

    db.delete(plc)
    db.commit()
    return {"status": "deleted", "placement_id": placement_id}


# 6. Sponsored Placement Tracking — ledger-backed billing
#
# AUDIT P1 CLOSURE. These endpoints previously mutated counters in place
# (`plc.impressions += 1`, `plc.spent_today += bid`) with no journal, no
# idempotency and no daily window, so "spend" was an unauditable, un-resettable
# number. They now delegate to AdBillingService, which appends an immutable
# AdLedgerEntry, enforces exactly-once via UNIQUE(event_key), rolls the daily
# budget window, and applies click fraud de-duplication. See
# backend/app/services/ad_billing_service.py for the full rationale.


def _billing_error_status(code: str) -> int:
    return {
        "PLACEMENT_NOT_FOUND": 404,
        "INVALID_ENTRY_TYPE": 422,
    }.get(code, 400)


def _track_placement_event(entry_type: str, placement_id: int, request: Request,
                           idempotency_key: Optional[str], user: User, db: Session):
    from backend.app.models.user import UserRole
    from backend.app.services.ad_billing_service import AdBillingService, AdBillingError

    bp = BrandService(db).get_brand_profile_by_user(user)
    try:
        return AdBillingService(db).record_event(
            placement_id=placement_id,
            brand_id=bp["id"],
            entry_type=entry_type,
            event_key=idempotency_key,
            actor_user_id=user.id,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            request_id=request.headers.get("x-request-id"),
            allow_any_brand=(user.role == UserRole.ADMIN),
        )
    except AdBillingError as exc:
        raise HTTPException(status_code=_billing_error_status(exc.code),
                            detail={"error": {"code": exc.code, "message": str(exc)}})


@router.post("/partner/placements/{placement_id}/impression")
def track_impression(
    placement_id: int,
    request: Request,
    idempotency_key: Optional[str] = Query(None, max_length=128,
        description="Client-supplied event id; a repeat of the same key is never charged twice."),
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    """Record a sponsored impression (CPC model: recorded, not charged)."""
    return _track_placement_event("impression", placement_id, request, idempotency_key, user, db)


@router.post("/partner/placements/{placement_id}/click")
def track_click(
    placement_id: int,
    request: Request,
    idempotency_key: Optional[str] = Query(None, max_length=128,
        description="Client-supplied event id; a repeat of the same key is never charged twice."),
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    """Record a billable click: ledger append + budget deduction, exactly once."""
    return _track_placement_event("click", placement_id, request, idempotency_key, user, db)


@router.post("/partner/placements/{placement_id}/conversion")
def track_conversion(
    placement_id: int,
    request: Request,
    idempotency_key: Optional[str] = Query(None, max_length=128),
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    """Record a conversion attributed to a placement (recorded, not charged)."""
    return _track_placement_event("conversion", placement_id, request, idempotency_key, user, db)


@router.get("/partner/placements/{placement_id}/reconciliation")
def placement_reconciliation(
    placement_id: int,
    on_date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD); defaults to today UTC"),
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    """Independent reconciliation: ledger sum vs the cached spend counter.

    The audit required that billing not be asserted from counters. This
    endpoint is the evidence: it recomputes the day's spend from the immutable
    journal and reports whether the projection agrees.
    """
    from datetime import date as _date
    from backend.app.services.ad_billing_service import AdBillingService, AdBillingError
    bp = BrandService(db).get_brand_profile_by_user(user)

    from backend.app.models.brand_analytics import SponsoredPlacement
    owned = db.query(SponsoredPlacement.id).filter(
        SponsoredPlacement.id == placement_id,
        SponsoredPlacement.brand_id == bp["id"]).first()
    if not owned:
        raise HTTPException(status_code=404, detail="Placement not found for your brand")

    parsed = None
    if on_date:
        try:
            parsed = _date.fromisoformat(on_date)
        except ValueError:
            raise HTTPException(status_code=422, detail="on_date must be ISO YYYY-MM-DD")
    try:
        return AdBillingService(db).reconcile(placement_id, parsed)
    except AdBillingError as exc:
        raise HTTPException(status_code=_billing_error_status(exc.code), detail=str(exc))


@router.get("/partner/billing/statement")
def brand_billing_statement(
    start_date: Optional[str] = Query(None, description="ISO date, default 30 days ago"),
    end_date: Optional[str] = Query(None, description="ISO date, default today"),
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    """Per-day ad billing statement derived ONLY from the append-only ledger."""
    from datetime import date as _date, timedelta as _td
    from backend.app.services.ad_billing_service import AdBillingService, utc_today
    bp = BrandService(db).get_brand_profile_by_user(user)
    try:
        end = _date.fromisoformat(end_date) if end_date else utc_today()
        start = _date.fromisoformat(start_date) if start_date else end - _td(days=30)
    except ValueError:
        raise HTTPException(status_code=422, detail="Dates must be ISO YYYY-MM-DD")
    if start > end:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    if (end - start).days > 366:
        raise HTTPException(status_code=422, detail="Statement range is limited to 366 days")
    return AdBillingService(db).brand_statement(bp["id"], start, end)


# ---------------------------------------------------------------------------
# Brand reporting (JSON + PDF)
#
# One dataset, two representations. `BrandReportService` owns every number and
# both endpoints below consume it, so the JSON a brand sees on screen and the
# PDF it files away can never disagree. Tenancy is resolved from the
# authenticated user via `get_brand_profile_by_user`; the brand id is NEVER
# taken from the request, so a brand manager cannot render another tenant's
# report by editing a query string.
# ---------------------------------------------------------------------------
def _report_params(date_from: Optional[str], date_to: Optional[str],
                   category_id: Optional[int], product_id: Optional[int]):
    from datetime import datetime as _dt
    parsed = {}
    for name, raw in (("date_from", date_from), ("date_to", date_to)):
        if not raw:
            parsed[name] = None
            continue
        try:
            parsed[name] = _dt.fromisoformat(raw)
        except ValueError:
            raise HTTPException(status_code=422,
                                detail=f"{name} must be ISO-8601 (YYYY-MM-DD)")
    if parsed["date_from"] and parsed["date_to"] and parsed["date_from"] > parsed["date_to"]:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")
    return parsed["date_from"], parsed["date_to"], category_id, product_id


@router.get("/partner/reports/product-sales")
@router.get("/brand/reports/product-sales")
def brand_product_sales_report(
    date_from: Optional[str] = Query(None, description="ISO date, inclusive"),
    date_to: Optional[str] = Query(None, description="ISO date, inclusive"),
    category_id: Optional[int] = Query(None),
    product_id: Optional[int] = Query(None),
    include_zero_sales: bool = Query(True),
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db),
):
    """Product and sales dataset for the authenticated brand (JSON)."""
    from backend.app.services.brand_report_service import BrandReportService
    bp = BrandService(db).get_brand_profile_by_user(user)
    df, dt, cid, pid = _report_params(date_from, date_to, category_id, product_id)
    data = BrandReportService(db).build_product_sales_report(
        bp["id"], date_from=df, date_to=dt, category_id=cid, product_id=pid,
        include_zero_sales=include_zero_sales)
    # Decimals/datetimes -> JSON-safe primitives without losing precision.
    return {
        **data,
        "generated_at": data["generated_at"].isoformat(),
        "period": {**data["period"],
                   "from": data["period"]["from"].isoformat() if data["period"]["from"] else None,
                   "to": data["period"]["to"].isoformat() if data["period"]["to"] else None},
        "rows": [{**r,
                  "list_price": str(r["list_price"]),
                  "gross_sales": str(r["gross_sales"]),
                  "net_sales": str(r["net_sales"])} for r in data["rows"]],
        "totals": {**data["totals"],
                   "gross_sales": str(data["totals"]["gross_sales"]),
                   "net_sales": str(data["totals"]["net_sales"])},
    }


@router.get("/partner/reports/product-sales.pdf")
@router.get("/brand/reports/product-sales.pdf")
def brand_product_sales_report_pdf(
    date_from: Optional[str] = Query(None, description="ISO date, inclusive"),
    date_to: Optional[str] = Query(None, description="ISO date, inclusive"),
    category_id: Optional[int] = Query(None),
    product_id: Optional[int] = Query(None),
    include_zero_sales: bool = Query(True),
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db),
):
    """The same dataset, rendered as a downloadable PDF."""
    from fastapi.responses import Response
    from backend.app.services.brand_report_service import BrandReportService
    bp = BrandService(db).get_brand_profile_by_user(user)
    df, dt, cid, pid = _report_params(date_from, date_to, category_id, product_id)
    data = BrandReportService(db).build_product_sales_report(
        bp["id"], date_from=df, date_to=dt, category_id=cid, product_id=pid,
        include_zero_sales=include_zero_sales)
    try:
        from backend.app.services.brand_report_pdf import render_report_pdf
    except ImportError:
        # Never pretend: if the renderer is unavailable, say exactly that.
        raise HTTPException(
            status_code=503,
            detail="PDF rendering is unavailable in this deployment (reportlab missing). "
                   "The same data is available as JSON at /partner/reports/product-sales.")
    pdf = render_report_pdf(data)
    _audit(db, user, "BRAND_REPORT_PDF_GENERATED", "BrandProfile", bp["id"],
           {"rows": len(data["rows"]), "period": data["period"]["label"]})
    db.commit()
    slug = (data["brand"]["slug"] or f"brand-{bp['id']}")
    stamp = data["generated_at"].strftime("%Y%m%d")
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="confit-{slug}-product-sales-{stamp}.pdf"'})
