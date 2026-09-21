from fastapi import Header
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

from backend.app.services.brand_access import require_partner

brand_auth = require_partner()


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
    an = service.get_brand_analytics_dashboard(user, bp["id"])
    repo = BrandRepository(db)
    per_sku = repo.get_conversion_analytics_per_sku(bp["id"])
    return {
        "views": an["total_views"],
        "tryons": an["total_tryons"],
        "add_to_cart": an["total_add_to_carts"],
        "purchases": an["total_purchases"],
        "conversion_rate": an["funnel_conversion_rate"],
        "per_sku": per_sku,
        "grain": "product",
        "methodology": an["methodology"]
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
    after: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    return service.get_brand_products(user, bp["id"], after, limit)


@router.post("/partner/catalog/import", status_code=status.HTTP_202_ACCEPTED)
@router.post("/brand/catalog/upload", status_code=status.HTTP_202_ACCEPTED)
def import_catalog_bulk(
    payload: CatalogBulkImportRequest,
    user: User = Depends(require_partner("catalog.import")),
    db: Session = Depends(get_db)
):
    bp = BrandService(db).get_brand_profile_by_user(user)
    return BrandCatalogService(db).process_json_import(payload.products, bp["id"], actor_id=user.id)


@router.post("/partner/catalog/upload/csv", status_code=status.HTTP_202_ACCEPTED)
async def upload_catalog_csv(
    file: UploadFile = File(...),
    user: User = Depends(require_partner("catalog.import")),
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
    user: User = Depends(require_partner("inventory.write")),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    result = service.update_sku(user, sku_id, stock_level, price_override)
    return result


# 4. Inventory & Store Management - REAL IMPLEMENTATION
@router.get("/partner/inventory")
def get_partner_inventory(
    after: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    repo = BrandRepository(db)

    # Real inventory: products with SKUs and store inventories — FIXED N+1 via single query
    products = repo.get_brand_products(bp["id"], after, limit)
    stock_totals = repo.product_stock_totals(bp["id"], [p.id for p in products])
    # Single query for all store inventories for this brand's SKUs
    from backend.app.models.catalog import StoreInventory
    all_sku_ids = [sku.id for prod in products for sku in prod.skus]
    inv_map: Dict[int, List] = {}
    if all_sku_ids:
        all_invs = db.query(StoreInventory).filter(StoreInventory.sku_id.in_(all_sku_ids)).all()
        for inv in all_invs:
            inv_map.setdefault(inv.sku_id, []).append(inv)

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
                    {"id": inv.id, "store_id": inv.store_id, "quantity": inv.quantity, "reserved": inv.reserved_quantity, "available": inv.quantity - inv.reserved_quantity}
                    for inv in invs
                ]
            })

        result.append({
            "product_id": product.id,
            "title": product.title,
            "thumbnail_url": product.thumbnail_url,
            "total_stock": stock_totals.get(product.id, 0),
            "skus_next_cursor": getattr(product, "_skus_next_cursor", None),
            "skus": sku_details
        })

    return result


@router.post("/partner/inventory")
def set_partner_inventory(
    payload: InventoryUpdateRequest,
    user: User = Depends(require_partner("inventory.write")),
    db: Session = Depends(get_db)
):
    """Explicit store/SKU upsert; PATCH continues to require a real inventory ID."""
    bp = BrandService(db).get_brand_profile_by_user(user)
    try:
        inv = BrandRepository(db).update_store_inventory(payload.store_id, payload.sku_id, payload.quantity, bp["id"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"inventory_id": inv.id, "store_id": inv.store_id, "sku_id": inv.sku_id,
            "quantity": inv.quantity, "reserved": inv.reserved_quantity,
            "available": inv.quantity - inv.reserved_quantity}


@router.patch("/partner/inventory/{inventory_id}")
def update_partner_inventory(
    inventory_id: int,
    payload: InventoryUpdateRequest,
    user: User = Depends(require_partner("inventory.write")),
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
    after: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    repo = BrandRepository(db)
    stores = repo.get_brand_stores(bp["id"], after, limit)
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
    user: User = Depends(require_partner("stores.write")),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    repo = BrandRepository(db)
    try:
        store = repo.create_store(bp["id"], payload.model_dump())
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
    user: User = Depends(require_partner("stores.write")),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    repo = BrandRepository(db)
    try:
        store = repo.update_store(store_id, bp["id"], payload.model_dump(exclude_unset=True))
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
    user: User = Depends(require_partner("placements.write")),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    try:
        created = service.create_sponsored_placement(user, bp["id"], payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return created


@router.patch("/partner/placements/{placement_id}")
def patch_placement(
    placement_id: int,
    payload: Dict[str, Any],
    user: User = Depends(require_partner("placements.write")),
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
    from backend.app.models.user import BrandProfile
    if candidate['status']=='active' and db.get(BrandProfile,bp['id']).is_test:
        raise HTTPException(409,'Production test tenants cannot activate advertising')
    if candidate["status"] not in ["active", "paused", "budget_exhausted"]:
        raise HTTPException(status_code=422, detail="Invalid status")
    try:
        candidate = validate_placement(candidate, spent=plc.spent_today)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    for key, value in candidate.items():
        setattr(plc, key, value)

    from backend.app.services.partner_audit import append_event
    append_event(db, bp["id"], "BRAND_PLACEMENT_UPDATED", "SponsoredPlacement", placement_id, after=candidate)
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
    user: User = Depends(require_partner("placements.write")),
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

    from backend.app.services.partner_audit import append_event
    append_event(db, bp["id"], "BRAND_PLACEMENT_CANCELLED", "SponsoredPlacement", placement_id)
    plc.status = "cancelled"
    db.commit()
    return {"status": "cancelled", "placement_id": placement_id}


# Partner-reported telemetry. Not an ad-serving receipt or verified invoice.
@router.post("/partner/placements/{placement_id}/impression")
def track_impression(placement_id: int, idempotency_key: Optional[str] = Header(None),
    user: User = Depends(require_partner("placements.write")), db: Session = Depends(get_db)):
    from backend.app.services.placement_counters import record
    bp=BrandService(db).get_brand_profile_by_user(user)
    return record(db,bp['id'],placement_id,'impression',idempotency_key)


@router.post("/partner/placements/{placement_id}/click")
def track_click(placement_id: int, idempotency_key: Optional[str] = Header(None),
    user: User = Depends(require_partner("placements.write")), db: Session = Depends(get_db)):
    from backend.app.services.placement_counters import record
    bp=BrandService(db).get_brand_profile_by_user(user)
    return record(db,bp['id'],placement_id,'click',idempotency_key)
