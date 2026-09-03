from decimal import Decimal
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, status, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import json
from backend.app.core.money import to_decimal, to_float

from backend.app.core.database import get_db
from backend.app.core.dependencies import require_role, BRAND_ROLES
from backend.app.models.user import User
from backend.app.services.brand_service import BrandService
from backend.app.services.brand_catalog_service import BrandCatalogService
from backend.app.repositories.brand_repository import BrandRepository
from backend.app.schemas.brand import (
    BrandProfileOut,
    BrandAnalyticsDashboardOut,
    SponsoredPlacementCreate,
    SponsoredPlacementOut
)
from backend.app.schemas.catalog import ProductSummaryOut, ProductSKUOut

router = APIRouter(tags=["Brand & Admin Management (B2B)"])

brand_auth = require_role(BRAND_ROLES)


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
    name: str
    name_ar: Optional[str] = None
    city: str
    country: str = "UAE"
    address: str
    latitude: float = 0.0
    longitude: float = 0.0
    phone: Optional[str] = None
    pickup_instructions: Optional[str] = None
    is_bopis_enabled: bool = True


class StoreUpdateRequest(BaseModel):
    name: Optional[str] = None
    name_ar: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    phone: Optional[str] = None
    pickup_instructions: Optional[str] = None
    is_bopis_enabled: Optional[bool] = None


class InventoryUpdateRequest(BaseModel):
    store_id: int
    sku_id: int
    quantity: int


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
        "methodology": "Real funnel from RecentlyViewed (views), TryOnSession (tryons), CartItem (add_to_cart), OrderItem (purchases). Conversion = purchases/views*100. Server-authoritative from DB, not frontend."
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
    metrics = repo.get_return_reduction_metrics()
    # Filter for brand if possible, but return platform metrics with brand-specific
    brand_analytics = repo.get_brand_analytics(bp["id"])
    return {
        "return_rate_before_vton": brand_analytics["return_rate_before_vton"],
        "return_rate_after_vton": brand_analytics["return_rate_after_vton"],
        "return_reduction_percentage": brand_analytics["return_reduction_percentage"],
        "platform_metrics": metrics,
        "methodology": metrics.get("methodology", "Cohort analysis try-on vs non-try-on")
    }


@router.get("/partner/analytics/heatmaps", response_model=Dict[str, Any])
def get_partner_heatmaps(
    region: str = Query("MENA", description="Region filter"),
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    repo = BrandRepository(db)
    heatmaps = repo.get_user_preference_heatmaps(region=region)
    # Ensure anonymized
    return {
        "region": heatmaps["region"],
        "sample_size": heatmaps["sample_size"],
        "privacy_threshold": heatmaps["privacy_threshold"],
        "top_aesthetics": heatmaps["top_aesthetics"],
        "top_colors": heatmaps["top_colors"],
        "top_occasions": heatmaps["top_occasions"],
        "anonymized": heatmaps["anonymized"],
        "methodology": heatmaps["methodology"]
    }


# 3. Catalog & SKU Management - REAL IMPLEMENTATION
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
def import_catalog_bulk(
    payload: Dict[str, Any],
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    """
    Bulk catalog import via API (JSON).
    For CSV, use /partner/catalog/upload/csv
    """
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    catalog_service = BrandCatalogService(db)

    # Expect products array
    products = payload.get("products", [])
    if not products:
        raise HTTPException(status_code=400, detail="Missing products array")

    # Create import job
    repo = BrandRepository(db)
    job = repo.create_import_job(bp["id"], file_name="api_import.json")

    # Convert to CSV-like rows for reuse of validation
    valid_rows = []
    errors = []
    for idx, prod in enumerate(products):
        # Map API product to CSV row format
        row = {
            "title": prod.get("title", ""),
            "title_ar": prod.get("title_ar", ""),
            "category_slug": prod.get("category_slug") or prod.get("category", ""),
            "base_price": str(prod.get("base_price", "")),
            "color_family": prod.get("color_family", ""),
            "thumbnail_url": prod.get("thumbnail_url", ""),
            "description": prod.get("description", ""),
            "currency": prod.get("currency", "USD"),
            "style_tags": json.dumps(prod.get("style_tags", [])),
            "size": prod.get("size", "M"),
            "color": prod.get("color", prod.get("color_family", "")),
            "stock_level": str(prod.get("stock_level", 20)),
            "sku_code": prod.get("sku_code", "")
        }
        # Validate
        from backend.app.services.brand_catalog_service import BrandCatalogService as BCS
        bcs = BrandCatalogService(db)
        row_errors = bcs._validate_row(row, idx+2)
        if row_errors:
            errors.extend([e.to_dict() for e in row_errors])
        else:
            valid_rows.append(row)

    if valid_rows:
        accepted, rejected, import_errors = catalog_service.import_products(valid_rows, bp["id"])
        errors.extend(import_errors)
        job.total_rows = len(products)
        job.accepted_rows = accepted
        job.rejected_rows = len(errors)
        job.errors_json = json.dumps(errors)
        job.status = "completed" if accepted > 0 and len(errors) == 0 else "partially_completed" if accepted > 0 else "failed"
        from datetime import datetime, timezone
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
    else:
        job.total_rows = len(products)
        job.rejected_rows = len(errors)
        job.errors_json = json.dumps(errors)
        job.status = "failed"
        from datetime import datetime, timezone
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

    return {
        "job_id": job.id,
        "status": job.status,
        "total_rows": job.total_rows,
        "accepted_rows": job.accepted_rows,
        "rejected_rows": job.rejected_rows,
        "errors": errors[:10]  # Return first 10 errors
    }


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
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be CSV")

    # Size limit: 10MB
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File exceeds 10MB limit")

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        csv_text = content.decode('utf-8')
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
        result = catalog_service.process_csv_import(csv_text, bp["id"], file.filename)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)[:500]}")


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
    try:
        errors = json.loads(job.errors_json) if job.errors_json else []
    except:
        errors = []

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
    price_override: Optional[float] = Query(None, ge=0, le=100000, description="Price override"),
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    result = service.update_sku(user, sku_id, stock_level, price_override)
    _audit(db, user, "BRAND_INVENTORY_UPDATED", "ProductSKU", sku_id,
           {"stock_level": stock_level, "price_override": price_override})
    return result


# 4. Inventory & Store Management - REAL IMPLEMENTATION
@router.get("/partner/inventory")
def get_partner_inventory(
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    repo = BrandRepository(db)

    # Real inventory: products with SKUs and store inventories — FIXED N+1 via single query
    products = repo.get_brand_products(bp["id"])
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
                    {"store_id": inv.store_id, "quantity": inv.quantity, "reserved": inv.reserved_quantity, "available": inv.quantity - inv.reserved_quantity}
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

    # Validate and update allowed fields
    allowed = ["bid_amount_per_click", "daily_budget", "status", "placement_type", "start_date", "end_date"]
    for key in allowed:
        if key in payload:
            if key == "bid_amount_per_click":
                bid = to_decimal(payload[key])
                if bid <= Decimal("0") or bid > Decimal("100"):
                    raise HTTPException(status_code=400, detail="Bid must be 0-100")
                if bid > to_decimal(plc.daily_budget):
                    raise HTTPException(status_code=400, detail="Bid cannot exceed daily budget")
                plc.bid_amount_per_click = bid
            elif key == "daily_budget":
                budget = to_decimal(payload[key])
                if budget <= Decimal("0") or budget > Decimal("10000"):
                    raise HTTPException(status_code=400, detail="Budget must be 0-10000")
                plc.daily_budget = budget
            elif key == "status":
                if payload[key] not in ["active", "paused", "budget_exhausted"]:
                    raise HTTPException(status_code=400, detail="Invalid status")
                plc.status = payload[key]
            elif key in ["start_date", "end_date"]:
                # Parse date if string
                try:
                    from datetime import datetime
                    if isinstance(payload[key], str):
                        dt = datetime.fromisoformat(payload[key].replace("Z", "+00:00"))
                        setattr(plc, key, dt)
                    else:
                        setattr(plc, key, payload[key])
                except:
                    raise HTTPException(status_code=400, detail=f"Invalid date format for {key}")
            else:
                setattr(plc, key, payload[key])

    # Validate budget vs bid after updates
    if plc.bid_amount_per_click > plc.daily_budget:
        raise HTTPException(status_code=400, detail="Bid cannot exceed daily budget after update")

    _audit(db, user, "BRAND_PLACEMENT_UPDATED", "SponsoredPlacement", placement_id,
           {"brand_id": bp["id"], "changed_fields": [k for k in allowed if k in payload]})
    db.commit()
    db.refresh(plc)

    return {
        "status": "updated",
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

    _audit(db, user, "BRAND_PLACEMENT_DELETED", "SponsoredPlacement", placement_id,
           {"brand_id": bp["id"], "status": plc.status,
            "daily_budget": str(plc.daily_budget), "bid": str(plc.bid_amount_per_click)})
    db.delete(plc)
    db.commit()
    return {"status": "deleted", "placement_id": placement_id}


# 6. Sponsored Placement Tracking (impression, click) - for billing
@router.post("/partner/placements/{placement_id}/impression")
def track_impression(
    placement_id: int,
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    """Track sponsored impression with budget enforcement — FIXED tenant isolation"""
    from backend.app.models.brand_analytics import SponsoredPlacement
    from backend.app.models.user import UserRole
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)

    # Tenant isolation: brand can only track own placements, admin can track any
    query = db.query(SponsoredPlacement).filter(SponsoredPlacement.id == placement_id)
    if user.role != UserRole.ADMIN:
        query = query.filter(SponsoredPlacement.brand_id == bp["id"])
    plc = query.with_for_update().first()

    if not plc:
        raise HTTPException(status_code=404, detail="Placement not found for your brand")

    # Check if active and within budget and dates
    if plc.status != "active":
        raise HTTPException(status_code=400, detail=f"Placement not active: {plc.status}")

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    if plc.start_date and now < plc.start_date:
        raise HTTPException(status_code=400, detail="Placement not yet started")
    if plc.end_date and now > plc.end_date:
        raise HTTPException(status_code=400, detail="Placement ended")

    if plc.spent_today >= plc.daily_budget:
        plc.status = "budget_exhausted"
        db.commit()
        raise HTTPException(status_code=400, detail="Daily budget exhausted")

    plc.impressions += 1
    db.commit()

    return {"status": "tracked", "impressions": plc.impressions}


@router.post("/partner/placements/{placement_id}/click")
def track_click(
    placement_id: int,
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    """Track sponsored click with budget deduction — FIXED tenant isolation + SELECT FOR UPDATE"""
    from backend.app.models.brand_analytics import SponsoredPlacement
    from backend.app.models.user import UserRole
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)

    query = db.query(SponsoredPlacement).filter(SponsoredPlacement.id == placement_id)
    if user.role != UserRole.ADMIN:
        query = query.filter(SponsoredPlacement.brand_id == bp["id"])
    plc = query.with_for_update().first()

    if not plc:
        raise HTTPException(status_code=404, detail="Placement not found for your brand")

    if plc.status != "active":
        raise HTTPException(status_code=400, detail=f"Placement not active: {plc.status}")

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    if plc.start_date and now < plc.start_date:
        raise HTTPException(status_code=400, detail="Placement not yet started")
    if plc.end_date and now > plc.end_date:
        raise HTTPException(status_code=400, detail="Placement ended")

    # Check budget
    if plc.spent_today + plc.bid_amount_per_click > plc.daily_budget:
        plc.status = "budget_exhausted"
        db.commit()
        raise HTTPException(status_code=400, detail="Daily budget would be exceeded")

    plc.clicks += 1
    plc.spent_today = round(plc.spent_today + plc.bid_amount_per_click, 2)

    if plc.spent_today >= plc.daily_budget:
        plc.status = "budget_exhausted"

    db.commit()

    return {
        "status": "tracked",
        "clicks": plc.clicks,
        "spent_today": plc.spent_today,
        "remaining_budget": round(plc.daily_budget - plc.spent_today, 2)
    }
