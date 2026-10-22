from decimal import Decimal
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, status, UploadFile, File, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, ConfigDict, model_validator
import json
from backend.app.core.money import to_decimal, to_float, validate_money, money_add, money_sub, MoneyValueError, MoneyRangeError

from backend.app.core.database import get_db
from backend.app.core.dependencies import (
    require_role, BRAND_ROLES, require_brand_access, get_current_user,
)
from backend.app.core.exceptions import ResourceNotFoundError, ValidationDomainError, AuthorizationError
from backend.app.models.user import User, UserRole, BrandProfile
from backend.app.models.membership import BrandMembership
from backend.app.services.brand_service import BrandService
from backend.app.services.brand_catalog_service import BrandCatalogService
from backend.app.services.product_tagging_service import ProductTaggingService
from backend.app.repositories.brand_repository import BrandRepository
from backend.app.schemas.brand import (
    BrandProfileOut,
    BrandMemberOut,
    BrandInvitationOut,
    MemberInviteRequest,
    MemberRoleUpdate,
    InvitationAcceptRequest,
    MyMembershipOut,
    BrandProductOut,
    CatalogBulkImportRequest,
    BrandAnalyticsDashboardOut,
    SponsoredPlacementCreate,
    SponsoredPlacementOut,
    PartnerLeadCreate,
    PartnerLeadOut,
    BrandRegistrationRequest,
    BrandRegistrationResponse,
    BrandOnboardingStatusOut,
    PartnerStoreDetailOut,
)
from backend.app.schemas.catalog import ProductSummaryOut, ProductSKUOut
from backend.app.services.partner_lead_service import PartnerLeadService
from backend.app.repositories.catalog_repository import build_google_maps_url
from backend.app.core.rate_limit import limiter

router = APIRouter(tags=["Brand & Admin Management (B2B)"])

# BRD-02 (0039): partner access is TENANT-scoped. ``brand_auth`` keeps the
# read-level capability every active member holds; mutation routes declare the
# specific capability they need below. Membership (not users.role) is the
# grant, resolved server-side; the legacy founder path still resolves.
brand_auth = require_brand_access("brand:read")
brand_inventory = require_brand_access("inventory:write")
brand_catalog = require_brand_access("catalog:write")
brand_stores = require_brand_access("stores:write")
brand_placements = require_brand_access("placements:manage")
brand_profile = require_brand_access("profile:write")
brand_billing = require_brand_access("billing:read")
# Tenant governance: owner-only and NO admin override (platform admin must not
# manage who belongs to a brand through the partner API).
brand_members = require_brand_access("members:manage", allow_admin=False)


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


# ============================================================================
# Automated Brand Registration & Workspace Provisioning
# ============================================================================

@router.post(
    "/brand/register",
    response_model=BrandRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/auth/brand/register",
    response_model=BrandRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("10/minute")
def register_brand_account(
    request: Request,
    payload: BrandRegistrationRequest,
    db: Session = Depends(get_db),
):
    """Automated brand registration.

    Provisions the brand owner user, creates the BrandProfile entity, generates
    a unique slug, provisions the tenant workspace, logs the audit record,
    and returns session tokens and onboarding guidance.
    """
    service = BrandService(db)
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    try:
        result = service.register_brand(
            brand_name=payload.brand_name,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            phone=payload.phone,
            description=payload.description,
            description_ar=payload.description_ar,
            website=payload.website,
            logo_url=payload.logo_url,
            country=payload.country,
            city=payload.city,
            preferred_language=payload.preferred_language or "en",
            ip_address=client_ip,
            user_agent=user_agent,
        )
        _audit(db, None, "BRAND_REGISTERED", "BrandProfile", result["brand"]["id"], {
            "brand_name": payload.brand_name,
            "email": payload.email,
            "status": result["status"]
        })
        return BrandRegistrationResponse(**result)
    except ValidationDomainError as exc:
        err_msg = str(exc)
        status_code = (
            status.HTTP_409_CONFLICT
            if "already registered" in err_msg.lower() or "already exists" in err_msg.lower()
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(
            status_code=status_code,
            detail=err_msg,
        )


@router.get("/partner/onboarding-status", response_model=BrandOnboardingStatusOut)
@router.get("/brand/onboarding-status", response_model=BrandOnboardingStatusOut)
def get_brand_onboarding_status(
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db),
):
    """Calculates guided onboarding progress across 7 dimensions."""
    service = BrandService(db)
    return service.get_onboarding_status(user)


def _audit(db: Session, user: User, action: str, resource_type: str,
           resource_id, details: dict | None = None,
           before: dict | None = None, after: dict | None = None) -> None:
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
            before=before, after=after,
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


class BrandProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    description: Optional[str] = Field(None, max_length=2000)
    description_ar: Optional[str] = Field(None, max_length=2000)
    website: Optional[str] = Field(None, max_length=500)
    logo_url: Optional[str] = Field(None, max_length=1000)
    banner_url: Optional[str] = Field(None, max_length=1000)


# 1. Brand Partner Profile
@router.get("/brand/profile", response_model=BrandProfileOut)
@router.get("/partner/profile", response_model=BrandProfileOut)
def get_brand_profile(
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    return service.get_brand_profile_by_user(user)


@router.patch("/brand/profile", response_model=BrandProfileOut)
@router.patch("/partner/profile", response_model=BrandProfileOut)
def patch_brand_profile(
    payload: BrandProfileUpdate,
    user: User = Depends(brand_profile),
    db: Session = Depends(get_db),
):
    service = BrandService(db)
    bp_dict = service.get_brand_profile_by_user(user)
    from backend.app.models.user import BrandProfile
    bp = db.get(BrandProfile, bp_dict["id"])
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(bp, key, value)
    db.commit()
    db.refresh(bp)
    _audit(db, user, "BRAND_PROFILE_UPDATED", "BrandProfile", bp.id, payload.model_dump(exclude_unset=True))
    return service._format_brand(bp)


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
    user: User = Depends(brand_catalog),
    db: Session = Depends(get_db)
):
    bp = BrandService(db).get_brand_profile_by_user(user)
    return BrandCatalogService(db).process_json_import(payload.products, bp["id"], actor_id=user.id)


@router.get("/partner/catalog/template.csv")
@router.get("/brand/catalog/template.csv")
def download_catalog_template():
    """Download official CSV template matching CONFIT_A schema."""
    from fastapi.responses import Response
    csv_text = "\ufeff" + BrandCatalogService.generate_sample_csv()
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="confit-catalog-template.csv"'}
    )


@router.post("/partner/catalog/preview-csv")
@router.post("/brand/catalog/preview-csv")
async def preview_catalog_csv(
    file: UploadFile = File(...),
    target_store_id: Optional[int] = Query(None),
    user: User = Depends(brand_catalog),
    db: Session = Depends(get_db)
):
    """
    Parses and validates CSV catalog file without database mutations.
    Returns row breakdown, summary stats, field-level errors and preview records.
    """
    bp = BrandService(db).get_brand_profile_by_user(user)

    if not (file.filename or '').lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be CSV")

    content = await file.read(BrandCatalogService.MAX_BYTES + 1)
    if len(content) > BrandCatalogService.MAX_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds 10MB limit")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="CSV file is empty")

    try:
        csv_text = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            csv_text = content.decode('latin-1')
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid CSV encoding, must be UTF-8")

    catalog_service = BrandCatalogService(db)
    result = catalog_service.preview_csv(csv_text, bp["id"], target_store_id=target_store_id)
    return result


@router.post("/partner/catalog/export-errors")
@router.post("/brand/catalog/export-errors")
def export_catalog_import_errors(
    payload: Dict[str, Any],
    user: User = Depends(brand_catalog),
    db: Session = Depends(get_db)
):
    """
    Generates and returns downloadable CSV error report with spreadsheet formula injection protection.
    """
    from fastapi.responses import Response
    errors = payload.get("errors", [])
    csv_text = "\ufeff" + BrandCatalogService.generate_error_report_csv(errors)
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="confit-import-errors.csv"'}
    )


@router.post("/partner/catalog/confirm-import", status_code=status.HTTP_202_ACCEPTED)
@router.post("/partner/catalog/upload/csv", status_code=status.HTTP_202_ACCEPTED)
async def upload_catalog_csv(
    file: UploadFile = File(...),
    target_store_id: Optional[int] = Query(None),
    # Bulk catalog import must not email the customer base by default. A
    # dataset load of a thousand rows would fire a campaign nobody asked for,
    # and the previous default (True) made that a one-click accident. Emailing
    # is now an explicit opt-in.
    send_notifications: bool = Query(False),
    user: User = Depends(brand_catalog),
    db: Session = Depends(get_db)
):
    """
    Bulk SKU import via CSV with image assets, branch inventory association,
    and automated customer notification dispatch.
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
            csv_text = content.decode('latin-1')
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid CSV encoding, must be UTF-8")

    # ------------------------------------------------------------------
    # DURABLE ACCEPTANCE, NOT A SLOW REQUEST
    # ------------------------------------------------------------------
    # This endpoint used to declare 202 and then run the entire import — every
    # row, every image download, every rendition — inside the request. The 202
    # was therefore a lie: the work was not accepted for later, it was happening
    # right there, and it died with the connection. The order is now:
    #
    #   1. persist the job WITH the file (migration 0042), so it is durable;
    #   2. dispatch the worker task;
    #   3. answer 202 with the job id and where to poll it.
    #
    # If the dispatch fails the job is marked failed with a reason and we answer
    # 503 — never "queued" for work nothing will ever pick up. The payload is
    # kept, so the recovery sweep (or the retry endpoint) can run it later.
    catalog_service = BrandCatalogService(db)
    job = catalog_service.enqueue_csv_import(
        csv_text,
        bp["id"],
        file.filename,
        actor_id=user.id,
        target_store_id=target_store_id,
        send_notifications=send_notifications,
    )

    from backend.app.workers.tasks import dispatch_catalog_import_job

    try:
        async_result = dispatch_catalog_import_job(job.id)
        job.celery_task_id = getattr(async_result, "id", None)
        db.commit()
    except Exception as exc:  # broker unreachable / task unroutable
        catalog_service.mark_dispatch_failed(job.id, str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=("The import queue is unavailable, so nothing was imported. "
                    "The file was kept; retry the import when the worker is back."),
        )

    # Re-read the row after dispatch. Normally it is still 'queued' — nothing has
    # run yet — but if the worker is fast (or a test runs it eagerly) the honest
    # answer is the state the database holds now, not a stale copy in memory.
    db.refresh(job)
    errors = []
    if job.errors_json:
        try:
            errors = json.loads(job.errors_json)[:50]
        except (TypeError, ValueError):
            errors = [{"row": None, "field": "errors_json",
                       "message": "stored error log is unreadable", "value": None}]

    return {
        "job_id": job.id,
        "status": job.status,
        "total_rows": job.total_rows,
        "processed_rows": job.processed_rows or 0,
        "accepted_rows": job.accepted_rows,
        "rejected_rows": job.rejected_rows,
        "duplicate_rows": job.duplicate_rows,
        # Errors the worker already recorded (empty on the normal fast path).
        "errors": errors,
        # Where to watch it: the brand-scoped job endpoint that already exists.
        "status_url": f"/api/v1/partner/catalog/imports/{job.id}",
        "attempts": job.attempts or 0,
    }


@router.get("/partner/catalog/export.csv")
@router.get("/brand/catalog/export.csv")
@limiter.limit("60/hour")
def export_brand_catalog_csv(
    request: Request,
    user: User = Depends(brand_catalog),
    db: Session = Depends(get_db),
):
    """Export the authenticated partner's own catalog and SKUs as a formula-safe UTF-8 CSV."""
    from fastapi.responses import Response

    brand_svc = BrandService(db)
    bp = brand_svc.get_brand_profile_by_user(user)
    csv_body = BrandCatalogService(db).export_catalog_csv(bp["id"])
    slug = (bp.get("slug") or f"brand-{bp['id']}").replace('"', "")
    return Response(
        content=csv_body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{slug}-catalog-export.csv"',
            "Cache-Control": "no-store",
        },
    )


@router.patch("/partner/catalog/products/{product_id}")
@router.patch("/brand/products/{product_id}")
@limiter.limit("120/hour")
def patch_brand_product(
    request: Request,
    product_id: int,
    payload: Dict[str, Any],
    user: User = Depends(brand_catalog),
    db: Session = Depends(get_db),
):
    """Update brand-editable product fields under the shared catalog field contract.

    Admin-owned fields (`is_featured`, `is_active`, `moderation_status`,
    `verification_status`, `rating`, `review_count`, `sales_count`) are explicitly
    refused with 422 rather than silently ignored.
    """
    from backend.app.models.catalog import Category, Product
    from backend.app.services import catalog_field_contract as field_contract

    if not isinstance(payload, dict) or not payload:
        raise HTTPException(
            status_code=422,
            detail={"message": "Request body must be a non-empty JSON object", "errors": []},
        )

    forbidden = field_contract.forbidden_field_errors(
        payload,
        row_number=1,
        error_factory=lambda row, field, message, value=None: {
            "field": field,
            "message": message,
            "value": value,
        },
    )
    if forbidden:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Protected system-managed fields cannot be set by a brand",
                "errors": forbidden,
            },
        )

    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    product = (
        db.query(Product)
        .filter(Product.id == product_id, Product.brand_id == bp["id"])
        .one_or_none()
    )
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    ALLOWED_PATCH_FIELDS = {
        "title",
        "title_ar",
        "description",
        "description_ar",
        "material",
        "care_instructions",
        "color_family",
        "dominant_hex",
        "gender",
        "style_tags",
        "occasion_tags",
        "category_id",
        "category_slug",
    }
    unknown_keys = sorted(set(payload.keys()) - ALLOWED_PATCH_FIELDS)
    if unknown_keys:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Unsupported product fields supplied",
                "errors": [
                    {"field": k, "message": f"Field {k!r} is not supported on brand product edit."}
                    for k in unknown_keys
                ],
            },
        )

    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    changed: Dict[str, Any] = {}

    if "title" in payload:
        val = str(payload.get("title") or "").strip()
        if not val or len(val) > 255:
            errors.append({"field": "title", "message": "title must be 1–255 characters."})
        else:
            product.title = val
            changed["title"] = val

    if "title_ar" in payload:
        val = str(payload.get("title_ar") or "").strip()
        if not val or len(val) > 255:
            errors.append({"field": "title_ar", "message": "title_ar must be 1–255 characters."})
        else:
            product.title_ar = val
            changed["title_ar"] = val

    if "description" in payload:
        val = str(payload.get("description") or "").strip()
        if not val or len(val) > 2000:
            errors.append({"field": "description", "message": "description must be 1–2000 characters."})
        else:
            product.description = val
            changed["description"] = val

    if "description_ar" in payload:
        val = str(payload.get("description_ar") or "").strip()
        if not val or len(val) > 2000:
            errors.append({"field": "description_ar", "message": "description_ar must be 1–2000 characters."})
        else:
            product.description_ar = val
            changed["description_ar"] = val

    if "material" in payload:
        raw_mat = payload.get("material")
        val_mat = str(raw_mat).strip() if raw_mat is not None else None
        if val_mat and len(val_mat) > 255:
            errors.append({"field": "material", "message": "material must be at most 255 characters."})
        else:
            product.material = val_mat or None
            changed["material"] = product.material

    if "care_instructions" in payload:
        raw_care = payload.get("care_instructions")
        val_care = str(raw_care).strip() if raw_care is not None else None
        if val_care and len(val_care) > 500:
            errors.append({"field": "care_instructions", "message": "care_instructions must be at most 500 characters."})
        else:
            product.care_instructions = val_care or None
            changed["care_instructions"] = product.care_instructions

    if "color_family" in payload:
        val_col = str(payload.get("color_family") or "").strip()
        if not val_col or len(val_col) > 50:
            errors.append({"field": "color_family", "message": "color_family must be 1–50 characters."})
        else:
            product.color_family = val_col
            changed["color_family"] = val_col

    if "dominant_hex" in payload and payload.get("dominant_hex") is not None:
        import re as _re
        val_hex = str(payload.get("dominant_hex")).strip()
        if not _re.fullmatch(r"#[0-9A-Fa-f]{6}", val_hex):
            errors.append({"field": "dominant_hex", "message": "dominant_hex must match #RRGGBB."})
        else:
            product.dominant_hex = val_hex
            changed["dominant_hex"] = val_hex

    if "gender" in payload:
        raw_gender = str(payload.get("gender") or "").strip()
        try:
            canon_g, _ = field_contract.normalize_gender(raw_gender)
        except ValueError as exc:
            errors.append({"field": "gender", "message": str(exc)})
        else:
            if not canon_g:
                errors.append({"field": "gender", "message": "Gender cannot be blank."})
            else:
                product.gender = canon_g
                changed["gender"] = canon_g

    if "style_tags" in payload:
        raw_st = payload.get("style_tags")
        try:
            parsed_st = field_contract.split_tag_cell(raw_st)
        except ValueError as exc:
            errors.append({"field": "style_tags", "message": str(exc)})
        else:
            canon_st, _ = field_contract.canonical_tags(parsed_st, kind="style")
            product.style_tags = json.dumps(canon_st)
            changed["style_tags"] = canon_st

    if "occasion_tags" in payload:
        raw_oc = payload.get("occasion_tags")
        try:
            parsed_oc = field_contract.split_tag_cell(raw_oc)
        except ValueError as exc:
            errors.append({"field": "occasion_tags", "message": str(exc)})
        else:
            canon_oc, unrec_oc = field_contract.canonical_tags(parsed_oc, kind="occasion")
            product.occasion_tags = json.dumps(canon_oc)
            changed["occasion_tags"] = canon_oc
            if unrec_oc:
                warnings.append({
                    "field": "occasion_tags",
                    "code": "occasion_unrecognised",
                    "unrecognised": unrec_oc,
                    "message": (
                        f"Stored {unrec_oc}, which is outside CONFIT's standard occasion "
                        f"filter vocabulary ({', '.join(field_contract._taxonomy().OCCASIONS)})."
                    ),
                })

    if "category_id" in payload and payload.get("category_id") is not None:
        cat = db.query(Category).filter(Category.id == int(payload["category_id"])).first()
        if cat is None:
            errors.append({"field": "category_id", "message": "Unknown category_id."})
        else:
            product.category_id = cat.id
            changed["category_id"] = cat.id
    elif "category_slug" in payload and payload.get("category_slug"):
        cat = db.query(Category).filter(Category.slug == str(payload["category_slug"]).strip().lower()).first()
        if cat is None:
            errors.append({"field": "category_slug", "message": "Unknown category_slug."})
        else:
            product.category_id = cat.id
            changed["category_id"] = cat.id

    if errors:
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail={"message": "Product update failed validation", "errors": errors},
        )

    _audit(db, user, "PRODUCT_CONTRACT_UPDATED", "Product", product.id, {"changed": list(changed.keys())})
    db.commit()
    db.refresh(product)
    refreshed = next(
        (item for item in service.get_brand_products(user, bp["id"]) if item["id"] == product.id),
        None,
    )
    return {
        "product": refreshed,
        "warnings": warnings,
    }


@router.put("/partner/catalog/products/{product_id}/size-chart")
@limiter.limit("120/hour")
def put_product_size_chart(
    request: Request,
    product_id: int,
    payload: Dict[str, Any],
    user: User = Depends(brand_catalog),
    db: Session = Depends(get_db),
):
    """Author a product's size chart, validated before it is stored.

    The chart is what the fit engine scores a shopper against, so an invalid one
    is not a cosmetic problem: it either silently disappears (the shopper gets
    no guidance) or produces a confident wrong size. It is therefore validated
    here, at the write, and the caller gets the exact cell that is wrong.

    Send `{}` or `null` to publish no chart — that is a legitimate state, and it
    is distinct from an invalid one.
    """
    from backend.app.models.catalog import Product
    from backend.app.services.size_chart_schema import validate as validate_chart

    bp = BrandService(db).get_brand_profile_by_user(user)
    product = (db.query(Product)
                 .filter(Product.id == product_id, Product.brand_id == bp["id"])
                 .one_or_none())
    if product is None:
        # Same answer for "does not exist" and "belongs to another brand": a
        # distinguishable 403 would confirm the existence of another tenant's SKU.
        raise HTTPException(status_code=404, detail="Product not found")

    chart = payload.get("size_chart") if isinstance(payload, dict) and "size_chart" in payload else payload
    result = validate_chart(chart)
    if not result.ok:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Size chart rejected; nothing was saved",
                "schema_version": result.as_dict()["schema_version"],
                "errors": result.as_dict()["errors"],
            },
        )

    before = product.size_chart_json
    product.size_chart_json = result.normalised
    _audit(db, user, "PRODUCT_SIZE_CHART_UPDATED", "Product", product.id,
           {"has_chart": result.has_chart,
            "warnings": [w.as_dict() for w in result.warnings]},
           before={"length": len(before or "")},
           after={"length": len(result.normalised)})
    db.commit()
    return {
        "product_id": product.id,
        "has_chart": result.has_chart,
        "size_chart": json.loads(result.normalised) if result.has_chart else {},
        "warnings": [w.as_dict() for w in result.warnings],
    }


# ============================================================================
# Brand image-source ownership (migration 0045)
# ============================================================================
# A brand may only import images from hosts it has PROVEN it controls, or from
# the platform's licensed stock sources. These routes are how it proves that.
# Every one of them is tenant-scoped server-side: the brand is resolved from the
# session, never from a request field.
@router.get("/partner/brand/domains")
def list_brand_domains(
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db),
):
    """The caller's domain claims and their verification state."""
    from backend.app.models.user import BrandDomain
    from backend.app.services.image_ownership import domain_expires_at, is_domain_expired

    bp = BrandService(db).get_brand_profile_by_user(user)
    records = (db.query(BrandDomain)
                 .filter(BrandDomain.brand_id == bp["id"])
                 .order_by(BrandDomain.id)
                 .all())
    return {
        "domains": [{
            "hostname": r.hostname,
            "status": r.status,
            "method": r.method,
            "verification_record": f"_confit-verify.{r.hostname}",
            "verification_value": f"confit-verify={r.token}",
            "verified_at": r.verified_at,
            "expires_at": domain_expires_at(r),
            "is_expired": is_domain_expired(r) if r.status == "verified" else False,
            "revoked_at": r.revoked_at,
            "last_checked_at": r.last_checked_at,
            "last_error": r.last_error,
        } for r in records],
        "imports_allowed_from": "verified non-expired domains and platform stock sources only",
    }


@router.post("/partner/brand/domains", status_code=status.HTTP_201_CREATED)
@limiter.limit("20/hour")
def claim_brand_domain(
    request: Request,
    payload: Dict[str, Any],
    user: User = Depends(brand_profile),
    db: Session = Depends(get_db),
):
    """Claim a domain. Returns the DNS TXT record the brand must publish.

    `brand_profile` capability, not `catalog:write`: claiming a domain is a
    company-level assertion, not a catalogue edit. A brand staff member who can
    import products should not be able to assert that the company owns a host.
    """
    from backend.app.services.image_ownership import ImageOwnershipService, OwnershipError

    bp = BrandService(db).get_brand_profile_by_user(user)
    service = ImageOwnershipService(db)
    try:
        record = service.request_domain(bp["id"], (payload or {}).get("hostname", ""))
    except OwnershipError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _audit(db, user, "BRAND_DOMAIN_CLAIMED", "BrandDomain", record.id,
           {"hostname": record.hostname})
    return {
        "hostname": record.hostname,
        "status": record.status,
        "verification_record": f"_confit-verify.{record.hostname}",
        "verification_value": f"confit-verify={record.token}",
        "instructions": (
            f"Publish a DNS TXT record on {record.hostname} with the value "
            f"confit-verify={record.token}, then verify."
        ),
    }


@router.post("/partner/brand/domains/verify")
@limiter.limit("20/hour")
def verify_brand_domain(
    request: Request,
    payload: Dict[str, Any],
    user: User = Depends(brand_profile),
    db: Session = Depends(get_db),
):
    """Check the DNS TXT claim now.

    Returns the resulting status either way — a failed check is a normal
    outcome, not an error, and the brand needs to see why.
    """
    from backend.app.services.image_ownership import ImageOwnershipService, OwnershipError

    bp = BrandService(db).get_brand_profile_by_user(user)
    service = ImageOwnershipService(db)
    try:
        record = service.verify_domain(bp["id"], (payload or {}).get("hostname", ""))
    except OwnershipError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    _audit(db, user, "BRAND_DOMAIN_VERIFIED", "BrandDomain", record.id,
           {"hostname": record.hostname, "status": record.status})
    from backend.app.services.image_ownership import domain_expires_at, is_domain_expired
    return {
        "hostname": record.hostname,
        "status": record.status,
        "verified_at": record.verified_at,
        "expires_at": domain_expires_at(record),
        "is_expired": is_domain_expired(record) if record.status == "verified" else False,
        "last_error": record.last_error,
        "imports_allowed": record.status == "verified" and not is_domain_expired(record),
    }


@router.delete("/partner/brand/domains/{hostname}")
def revoke_brand_domain(
    hostname: str,
    release: bool = Query(False, description="If true, delete the claim completely so the hostname is released."),
    user: User = Depends(brand_profile),
    db: Session = Depends(get_db),
):
    """Stop authorizing imports from a domain.

    Existing imported media is NOT deleted: revocation governs what may be
    imported NEXT. Removing photographs that are already published is a
    separate, deliberate operation with its own consequences (live PDPs).
    """
    from backend.app.services.image_ownership import ImageOwnershipService, OwnershipError

    bp = BrandService(db).get_brand_profile_by_user(user)
    service = ImageOwnershipService(db)
    if release:
        try:
            released_host = service.release_domain(bp["id"], hostname)
        except OwnershipError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        _audit(db, user, "BRAND_DOMAIN_RELEASED", "BrandDomain", bp["id"],
               {"hostname": released_host})
        return {
            "hostname": released_host,
            "status": "released",
            "revoked_at": None,
            "note": "Domain claim removed and released. Existing materialized catalog images are unchanged.",
        }
    try:
        record = service.revoke_domain(bp["id"], hostname)
    except OwnershipError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    _audit(db, user, "BRAND_DOMAIN_REVOKED", "BrandDomain", record.id,
           {"hostname": record.hostname})
    return {
        "hostname": record.hostname,
        "status": record.status,
        "revoked_at": record.revoked_at,
        "note": "Future imports from this domain are refused. Existing images are unchanged.",
    }


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
        # Real progress from persisted state: how many rows the worker has
        # actually handled, not an estimate that drifts to completion.
        "processed_rows": job.processed_rows or 0,
        "accepted_rows": job.accepted_rows,
        "rejected_rows": job.rejected_rows,
        "duplicate_rows": job.duplicate_rows,
        "attempts": job.attempts or 0,
        # The most recent failure reason, when there is one. Present so a brand
        # (and an operator reading the same payload) can tell "still running"
        # from "died", which a bare status string cannot express.
        "last_error": job.last_error,
        "errors": errors[:50],  # Limit to 50
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "status_url": f"/api/v1/partner/catalog/imports/{job.id}",
    }


@router.post("/partner/catalog/imports/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_catalog_import(
    job_id: int,
    user: User = Depends(brand_catalog),
    db: Session = Depends(get_db),
):
    """Re-dispatch a failed import that still has its file.

    Deliberately narrow: only a job whose status is ``failed`` and whose payload
    is still stored may be retried, and the section's bounded attempt limit
    applies (claim_job enforces it). A finished job cannot be "retried" — that
    would import the same catalogue twice — so it answers 409 rather than
    pretending to do something.
    """
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    repo = BrandRepository(db)
    job = repo.get_import_job(job_id, bp["id"])
    if not job:
        raise HTTPException(status_code=404, detail=f"Import job {job_id} not found for your brand")

    catalog_service = BrandCatalogService(db)
    if job.status not in ("failed", "queued"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Import job {job_id} is {job.status}; only a failed import can be retried",
        )
    if not job.payload_text:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This import's file is no longer stored; upload it again",
        )
    if (job.attempts or 0) >= catalog_service.MAX_JOB_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=("This import has already been attempted "
                    f"{job.attempts} times; upload a corrected file instead"),
        )

    from backend.app.workers.tasks import dispatch_catalog_import_job

    job.status = "queued"
    db.commit()
    try:
        async_result = dispatch_catalog_import_job(job.id)
        job.celery_task_id = getattr(async_result, "id", None)
        db.commit()
    except Exception as exc:
        catalog_service.mark_dispatch_failed(job.id, str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The import queue is unavailable; nothing was imported. Try again later.",
        )
    return catalog_service.job_result(job)


# ============================================================================
# Feature 07 — AI product auto-tagging (FashionCLIP + GLiNER2 worker)
# ============================================================================
@router.post("/partner/products/{product_id}/auto-tag", response_model=Dict[str, Any])
@router.post("/brand/products/{product_id}/auto-tag", response_model=Dict[str, Any])
@limiter.limit("30/hour")
async def auto_tag_product(
    request: Request,
    product_id: int,
    dry_run: bool = Query(False, description="Run the models and report what would change, writing nothing."),
    user: User = Depends(brand_catalog),
    db: Session = Depends(get_db)
):
    """Auto-tag one of YOUR products with FashionCLIP (image, MIT) + GLiNER2
    (text, Apache-2.0) — per-tag confidence and provenance, unresolved axes
    reported instead of guessed. AI tags are merged append-only: existing
    human tags are never removed, and colour/material are only filled when
    empty. The category column is a suggestion, never mutated."""
    service = ProductTaggingService(db)
    result = await service.auto_tag_product(user, product_id, dry_run=dry_run)
    _audit(db, user, "BRAND_PRODUCT_AUTO_TAGGED", "Product", product_id, {
        "quality": result.get("quality"),
        "tag_count": result.get("tag_count"),
        "applied_fields": [a["field"] for a in result.get("applied", [])],
        "dry_run": dry_run,
    })
    return result


@router.put("/brand/skus/{sku_id}", response_model=ProductSKUOut)
@router.patch("/partner/skus/{sku_id}", response_model=ProductSKUOut)
@router.patch("/partner/variants/{sku_id}", response_model=ProductSKUOut)
def update_sku_inventory(
    sku_id: int,
    stock_level: int = Query(..., ge=0, le=100000, description="New stock level"),
    price_override: Optional[Decimal] = Query(None, gt=0, le=100000, max_digits=12, decimal_places=2,
                                               description="Price override (2dp, > 0)"),
    user: User = Depends(brand_inventory),
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
    user: User = Depends(brand_inventory),
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
    user: User = Depends(brand_inventory),
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
@router.get("/brand/stores")
def get_partner_stores(
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    repo = BrandRepository(db)
    stores = repo.get_brand_stores(bp["id"])
    from backend.app.models.catalog import StoreInventory
    from sqlalchemy import func

    # Fetch store inventories count for each store
    stats = (
        db.query(
            StoreInventory.store_id,
            func.count(StoreInventory.id).label("item_count"),
            func.coalesce(func.sum(StoreInventory.quantity), 0).label("total_units"),
        )
        .group_by(StoreInventory.store_id)
        .all()
    )
    stat_map = {row.store_id: (row.item_count, row.total_units) for row in stats}

    results = []
    for s in stores:
        item_count, total_units = stat_map.get(s.id, (0, 0))
        is_verified = bool(
            (s.latitude != 0.0 or s.longitude != 0.0)
            and -90 <= s.latitude <= 90
            and -180 <= s.longitude <= 180
        )
        gmaps_url = build_google_maps_url(s.address, s.latitude, s.longitude)
        results.append({
            "id": s.id,
            "brand_id": s.brand_id,
            "name": s.name,
            "name_ar": s.name_ar,
            "city": s.city,
            "country": s.country,
            "address": s.address,
            "latitude": s.latitude,
            "longitude": s.longitude,
            "phone": s.phone,
            "pickup_instructions": s.pickup_instructions,
            "is_bopis_enabled": s.is_bopis_enabled,
            "is_location_verified": is_verified,
            "inventory_items_count": item_count,
            "total_stock_units": total_units,
            "google_maps_url": gmaps_url,
            "created_at": s.created_at,
        })
    return results


@router.get("/partner/stores/{store_id}")
@router.get("/brand/stores/{store_id}")
def get_partner_store_detail(
    store_id: int,
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    from backend.app.models.catalog import StoreLocation, StoreInventory
    store = db.query(StoreLocation).filter(
        StoreLocation.id == store_id,
        StoreLocation.brand_id == bp["id"]
    ).first()
    if not store:
        raise HTTPException(status_code=404, detail=f"Store {store_id} not found for this brand.")

    item_count = db.query(StoreInventory).filter(StoreInventory.store_id == store.id).count()
    from sqlalchemy import func
    total_units = (
        db.query(func.coalesce(func.sum(StoreInventory.quantity), 0))
        .filter(StoreInventory.store_id == store.id)
        .scalar()
        or 0
    )
    is_verified = bool(
        (store.latitude != 0.0 or store.longitude != 0.0)
        and -90 <= store.latitude <= 90
        and -180 <= store.longitude <= 180
    )
    return {
        "id": store.id,
        "brand_id": store.brand_id,
        "name": store.name,
        "name_ar": store.name_ar,
        "city": store.city,
        "country": store.country,
        "address": store.address,
        "latitude": store.latitude,
        "longitude": store.longitude,
        "phone": store.phone,
        "pickup_instructions": store.pickup_instructions,
        "is_bopis_enabled": store.is_bopis_enabled,
        "is_location_verified": is_verified,
        "inventory_items_count": item_count,
        "total_stock_units": total_units,
        "google_maps_url": build_google_maps_url(store.address, store.latitude, store.longitude),
        "created_at": store.created_at,
    }


@router.post("/partner/stores", status_code=status.HTTP_201_CREATED)
@router.post("/brand/stores", status_code=status.HTTP_201_CREATED)
def create_partner_store(
    payload: StoreCreateRequest,
    user: User = Depends(brand_stores),
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
            "is_bopis_enabled": store.is_bopis_enabled,
            "google_maps_url": build_google_maps_url(store.address, store.latitude, store.longitude),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/partner/stores/{store_id}")
@router.patch("/brand/stores/{store_id}")
def patch_partner_store(
    store_id: int,
    payload: StoreUpdateRequest,
    user: User = Depends(brand_stores),
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
            "is_bopis_enabled": store.is_bopis_enabled,
            "google_maps_url": build_google_maps_url(store.address, store.latitude, store.longitude),
        }
    except ValueError as e:
        raise HTTPException(status_code=404 if "not found" in str(e).lower() else 400, detail=str(e))


@router.delete("/partner/stores/{store_id}")
@router.delete("/brand/stores/{store_id}")
def delete_partner_store(
    store_id: int,
    user: User = Depends(brand_stores),
    db: Session = Depends(get_db)
):
    service = BrandService(db)
    bp = service.get_brand_profile_by_user(user)
    repo = BrandRepository(db)
    try:
        repo.delete_store(store_id, bp["id"])
        _audit(db, user, "BRAND_STORE_DELETED", "Store", store_id, {"brand_id": bp["id"]})
        return {"status": "deleted", "store_id": store_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


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
    user: User = Depends(brand_placements),
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
    user: User = Depends(brand_placements),
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
    user: User = Depends(brand_placements),
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
    user: User = Depends(brand_billing),
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
    user: User = Depends(brand_billing),
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


@router.get("/partner/orders")
@router.get("/brand/orders")
def brand_order_lines(
    date_from: Optional[str] = Query(None, description="ISO date, inclusive"),
    date_to: Optional[str] = Query(None, description="ISO date, inclusive"),
    product_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None, description="Filter by order status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db),
):
    """Per-line sales visibility for the authenticated brand.

    Answers the operational questions the aggregate product-sales report
    cannot: which customer, which size/colour left stock, from which store,
    and — stated as three separate figures so the arithmetic is auditable —
    what the line grossed, what discount it bore, and what it netted.

    Tenant-scoped by `OrderItem.brand_id`. An order spanning several brands
    yields only this brand's lines, and the order's own totals are never
    exposed, because they describe a basket this brand only partly owns.
    """
    from backend.app.services.brand_order_lines_service import BrandOrderLinesService

    bp = BrandService(db).get_brand_profile_by_user(user)
    df, dt, _cid, pid = _report_params(date_from, date_to, None, product_id)
    data = BrandOrderLinesService(db).build_order_lines(
        bp["id"], date_from=df, date_to=dt, product_id=pid,
        status=status, limit=limit, offset=offset,
    )

    def _money(v):
        # Decimal -> str: exact on the wire. A float here would reintroduce
        # the rounding error the allocation work exists to eliminate.
        return str(v)

    return {
        **data,
        "lines": [
            {**ln,
             "placed_at": ln["placed_at"].isoformat() if ln["placed_at"] else None,
             "unit_price": _money(ln["unit_price"]),
             "gross_amount": _money(ln["gross_amount"]),
             "discount_amount": _money(ln["discount_amount"]),
             "net_amount": _money(ln["net_amount"])}
            for ln in data["lines"]
        ],
        "totals": {**data["totals"],
                   "gross_amount": _money(data["totals"]["gross_amount"]),
                   "discount_amount": _money(data["totals"]["discount_amount"]),
                   "net_amount": _money(data["totals"]["net_amount"])},
        "filters": {**data["filters"],
                    "date_from": df.isoformat() if df else None,
                    "date_to": dt.isoformat() if dt else None},
    }


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


# -------------------------------------------------------------------------
# Advanced Business Intelligence, Analytics & Export System
# -------------------------------------------------------------------------
@router.get("/partner/analytics/bi-dashboard")
@router.get("/brand/analytics/bi-dashboard")
def get_brand_bi_dashboard_endpoint(
    date_from: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD), inclusive"),
    date_to: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD), inclusive"),
    days: Optional[int] = Query(None, description="Preset window in days (e.g. 7, 30, 90)"),
    branch_id: Optional[int] = Query(None, description="Filter to a specific branch/store location"),
    category_id: Optional[int] = Query(None, description="Filter to a specific category"),
    compare: bool = Query(True, description="Compare against preceding equivalent period"),
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db),
):
    """Authoritative Business Intelligence dashboard for brand owners & branch managers."""
    from backend.app.services.business_intelligence_service import BusinessIntelligenceService
    bp = BrandService(db).get_brand_profile_by_user(user)

    # Branch managers scoped check: If user has store restrictions, enforce branch_id
    df = datetime.fromisoformat(date_from) if date_from else None
    dt = datetime.fromisoformat(date_to) if date_to else None

    # Validate that branch_id belongs to this brand if supplied
    if branch_id is not None:
        store = db.query(StoreLocation).filter(StoreLocation.id == branch_id, StoreLocation.brand_id == bp["id"]).first()
        if not store:
            raise HTTPException(status_code=404, detail="Branch location not found for this brand tenant.")

    svc = BusinessIntelligenceService(db)
    return svc.get_brand_bi_dashboard(
        brand_id=bp["id"],
        date_from=df,
        date_to=dt,
        days=days,
        branch_id=branch_id,
        category_id=category_id,
        compare=compare,
    )


@router.get("/partner/analytics/export.csv")
@router.get("/brand/analytics/export.csv")
def export_brand_bi_csv_endpoint(
    date_from: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD), inclusive"),
    date_to: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD), inclusive"),
    days: Optional[int] = Query(None, description="Preset window in days"),
    branch_id: Optional[int] = Query(None, description="Filter by branch ID"),
    category_id: Optional[int] = Query(None, description="Filter by category ID"),
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db),
):
    """Download sanitized CSV report with active reporting filters."""
    from fastapi.responses import Response
    from backend.app.services.business_intelligence_service import BusinessIntelligenceService
    bp = BrandService(db).get_brand_profile_by_user(user)

    df = datetime.fromisoformat(date_from) if date_from else None
    dt = datetime.fromisoformat(date_to) if date_to else None

    if branch_id is not None:
        store = db.query(StoreLocation).filter(StoreLocation.id == branch_id, StoreLocation.brand_id == bp["id"]).first()
        if not store:
            raise HTTPException(status_code=404, detail="Branch location not found for this brand tenant.")

    svc = BusinessIntelligenceService(db)
    csv_content = svc.export_brand_bi_csv(
        brand_id=bp["id"],
        date_from=df,
        date_to=dt,
        days=days,
        branch_id=branch_id,
        category_id=category_id,
    )

    slug = bp.get("slug") or f"brand-{bp['id']}"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="confit-bi-{slug}-{stamp}.csv"'},
    )


@router.get("/partner/analytics/export.pdf")
@router.get("/brand/analytics/export.pdf")
def export_brand_bi_pdf_endpoint(
    date_from: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD), inclusive"),
    date_to: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD), inclusive"),
    days: Optional[int] = Query(None, description="Preset window in days"),
    branch_id: Optional[int] = Query(None, description="Filter by branch ID"),
    category_id: Optional[int] = Query(None, description="Filter by category ID"),
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db),
):
    """Download executive BI PDF report with official Logo #3 vector branding."""
    from fastapi.responses import Response
    from backend.app.services.business_intelligence_service import BusinessIntelligenceService
    bp = BrandService(db).get_brand_profile_by_user(user)

    df = datetime.fromisoformat(date_from) if date_from else None
    dt = datetime.fromisoformat(date_to) if date_to else None

    if branch_id is not None:
        store = db.query(StoreLocation).filter(StoreLocation.id == branch_id, StoreLocation.brand_id == bp["id"]).first()
        if not store:
            raise HTTPException(status_code=404, detail="Branch location not found for this brand tenant.")

    svc = BusinessIntelligenceService(db)
    pdf_content = svc.render_brand_bi_pdf(
        brand_id=bp["id"],
        date_from=df,
        date_to=dt,
        days=days,
        branch_id=branch_id,
        category_id=category_id,
    )

    slug = bp.get("slug") or f"brand-{bp['id']}"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="confit-bi-report-{slug}-{stamp}.pdf"'},
    )


# ═══════════════════════════════════════════════════════════════════════════
# TEAM · brand memberships & invitations (BRD-02 · spec 005 · #150 residue)
# ═══════════════════════════════════════════════════════════════════════════
# Tenant-scoped staff management. Authoritative rules live in
# backend/app/services/brand_membership_service.py; the endpoints here add
# input validation, the uniform error envelope, the outbox email dispatch, and
# hash-chained audit rows (0020 mapper listener). Joining a brand NEVER touches
# users.role — platform roles stay separate from tenant roles.

from datetime import date as _date


def _membership_error(exc):
    from backend.app.services.brand_membership_service import BrandMembershipError
    if isinstance(exc, BrandMembershipError):
        return HTTPException(status_code=exc.status,
                             detail={"error": {"code": exc.code, "message": exc.message}})
    return exc


def _role_of(request: Request) -> str:
    access = getattr(request.state, "brand_access", None) or {}
    return access.get("role", "")


@router.get("/partner/members/me", response_model=List[MyMembershipOut],
            summary="The acting user's brand memberships (any authenticated user)")
def get_my_memberships(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Powers role-aware navigation: consumers with an invited membership see
    the partner portal, everyone else sees the gate. Empty list is the honest
    no-membership answer, never an error."""
    from backend.app.services.brand_membership_service import BrandMembershipService
    from backend.app.models.membership import BrandMembership
    svc = BrandMembershipService(db)
    rows = (
        db.query(BrandMembership, BrandProfile)
        .join(BrandProfile, BrandProfile.id == BrandMembership.brand_id)
        .filter(BrandMembership.user_id == user.id,
                BrandMembership.status == "active")
        .all()
    )
    # Legacy founder without a membership row (pre-0039 data / rollback):
    # surface the founder tenant so the portal is reachable in every state.
    # A REVOKED row suppresses the anchor (same rule as the service).
    if (user.brand_profile is not None
            and not db.query(BrandMembership).filter(
                BrandMembership.user_id == user.id).count()):
        bp = user.brand_profile
        legacy_role = {UserRole.BRAND_OWNER: "owner", UserRole.BRAND_MANAGER: "manager",
                       UserRole.BRAND_STAFF: "staff"}.get(user.role)
        if legacy_role:
            return [MyMembershipOut(brand_id=bp.id, brand_name=bp.brand_name,
                                    slug=bp.slug, role=legacy_role, status="active")]
    return [
        MyMembershipOut(brand_id=bp.id, brand_name=bp.brand_name, slug=bp.slug,
                        role=m.role, status=m.status)
        for m, bp in rows
    ]


@router.get("/partner/members", response_model=List[BrandMemberOut],
            summary="List brand team members (active; revoked rows owner-only)")
def list_brand_members(
    request: Request,
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db),
):
    from backend.app.services.brand_membership_service import (
        BrandAccessDenied, BrandMembershipService,
    )
    svc = BrandMembershipService(db)
    try:
        bp = svc.tenant_brand(user)
    except BrandAccessDenied:
        raise HTTPException(status_code=403, detail={
            "error": {"code": "BRAND_ACCESS_DENIED",
                      "message": "No active brand tenant is linked to this account."}})
    # Read-repair for legacy data: if the founder somehow has no membership row
    # (e.g. raw-SQL brand creation that bypassed provisioning), give them the
    # owner row now instead of showing an impossible empty team.
    if not svc.list_members(bp.id, include_revoked=True):
        svc.ensure_founder_membership(bp)
        db.commit()
    viewer = _role_of(request)
    show_revoked = viewer in ("owner", "admin")
    members = svc.list_members(bp.id, include_revoked=show_revoked)
    # Email is only disclosed to owner/manager (and admin oversight). Staff
    # see presence + role, which is all the floor-operations view needs.
    if viewer not in ("owner", "manager", "admin"):
        for m in members:
            m["email"] = None
    return [BrandMemberOut(**m) for m in members]


@router.post("/partner/members/invitations", response_model=BrandInvitationOut,
             status_code=status.HTTP_201_CREATED,
             summary="Invite a member (owner only; pending request is idempotent)")
@limiter.limit("20/minute")
def create_member_invitation(
    request: Request,
    payload: MemberInviteRequest,
    user: User = Depends(brand_members),
    db: Session = Depends(get_db),
):
    from backend.app.services.brand_membership_service import (
        BrandMembershipService, hash_token as _h,
    )
    from backend.app.core.config import settings as _settings
    svc = BrandMembershipService(db)
    bp = svc.tenant_brand(user)
    try:
        outcome = svc.create_invitation(brand_id=bp.id, email=payload.email,
                                       role=payload.role, actor=user)
    except Exception as exc:
        raise _membership_error(exc)
    inv = outcome["invitation"]

    # Delivery: queued through the durable outbox (exactly-once per day per
    # invitation). The provider itself may be unconfigured in demo mode — that
    # is recorded, honestly, as 'queued' vs 'sent'; nothing pretends otherwise.
    delivery = "unavailable"
    if outcome["created"] and outcome["raw_token"]:
        try:
            from backend.app.services.email_outbox import dispatch
            accept_url = (f"{_settings.FRONTEND_BASE_URL.rstrip('/')}"
                          f"/b2b/team/accept?token={outcome['raw_token']}")
            role_label = {"owner": "Owner", "manager": "Manager", "staff": "Staff"}[payload.role]
            row = dispatch(
                db,
                event_key=f"brand_invitation:{inv.id}:{_date.today().isoformat()}",
                template="brand_invitation",
                locale=(user.preferred_language or "en"),
                recipient=inv.email,
                payload={
                    "brand_name": bp.brand_name,
                    "inviter_name": user.full_name or "A brand owner",
                    "role_label": role_label,
                    "accept_url": accept_url,
                },
            )
            delivery = "sent" if getattr(row, "status", "") == "sent" else "queued"
        except Exception:
            # Outbox enqueue failure must NOT roll back the invitation; the
            # owner can still resend from the UI. Honest status, no pretense.
            delivery = "unavailable"

    _audit(db, user, "BRAND_MEMBER_INVITED", "BrandInvitation", inv.id, {
        "brand_id": bp.id, "email_domain": inv.email.split("@")[-1],
        "role": payload.role, "created": outcome["created"], "delivery": delivery,
    })
    return BrandInvitationOut.model_validate(inv)


@router.post("/partner/members/invitations/{invitation_id}/resend",
             response_model=BrandInvitationOut,
             summary="Re-issue + re-mail a pending invitation (old token dies)")
@limiter.limit("6/hour")
def resend_member_invitation(
    request: Request,
    invitation_id: int,
    user: User = Depends(brand_members),
    db: Session = Depends(get_db),
):
    import secrets as _secrets
    from backend.app.services.brand_membership_service import (
        BrandMembershipService, hash_token as _h,
    )
    from backend.app.core.config import settings as _settings
    from backend.app.services.email_outbox import dispatch
    svc = BrandMembershipService(db)
    bp = svc.tenant_brand(user)
    try:
        inv = svc.resend_invitation_email(brand_id=bp.id, invitation_id=invitation_id)
        raw = _secrets.token_urlsafe(32)
        inv.token_hash = _h(raw)  # rotation: the previous email's link stops working
        db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        raise _membership_error(exc)
    try:
        dispatch(
            db,
            event_key=f"brand_invitation:{inv.id}:resend:{_date.today().isoformat()}",
            template="brand_invitation",
            locale=(user.preferred_language or "en"),
            recipient=inv.email,
            payload={
                "brand_name": bp.brand_name,
                "inviter_name": user.full_name or "A brand owner",
                "role_label": {"owner": "Owner", "manager": "Manager", "staff": "Staff"}[inv.role],
                "accept_url": (f"{_settings.FRONTEND_BASE_URL.rstrip('/')}"
                               f"/b2b/team/accept?token={raw}"),
            },
        )
    except Exception:
        pass  # token is rotated + persisted; a same-day mail collision is benign
    _audit(db, user, "BRAND_MEMBER_INVITATION_RESENT", "BrandInvitation", inv.id,
           {"brand_id": bp.id, "role": inv.role})
    return BrandInvitationOut.model_validate(inv)


@router.get("/partner/members/invitations", response_model=List[BrandInvitationOut],
            summary="Pending invitations (owner + manager)")
def list_member_invitations(
    request: Request,
    user: User = Depends(brand_auth),
    db: Session = Depends(get_db),
):
    from backend.app.services.brand_membership_service import (
        BrandAccessDenied, BrandMembershipService,
    )
    viewer = _role_of(request)
    if viewer == "staff":
        raise HTTPException(status_code=403, detail={
            "error": {"code": "CAP_DENIED",
                      "message": "Invitations are visible to owners and managers."}})
    svc = BrandMembershipService(db)
    try:
        bp = svc.tenant_brand(user)
    except BrandAccessDenied:
        raise HTTPException(status_code=403, detail={
            "error": {"code": "BRAND_ACCESS_DENIED",
                      "message": "No active brand tenant is linked to this account."}})
    return [BrandInvitationOut.model_validate(i) for i in svc.list_invitations(bp.id)]


@router.delete("/partner/members/invitations/{invitation_id}",
               summary="Revoke a pending invitation (owner only)")
def revoke_member_invitation(
    request: Request,
    invitation_id: int,
    user: User = Depends(brand_members),
    db: Session = Depends(get_db),
):
    from backend.app.services.brand_membership_service import BrandMembershipService
    svc = BrandMembershipService(db)
    bp = svc.tenant_brand(user)
    try:
        inv = svc.revoke_invitation(brand_id=bp.id, invitation_id=invitation_id, actor=user)
    except Exception as exc:
        raise _membership_error(exc)
    _audit(db, user, "BRAND_MEMBER_INVITATION_REVOKED", "BrandInvitation", inv.id,
           {"brand_id": bp.id})
    return {"status": "revoked", "id": inv.id}


@router.post("/partner/members/invitations/accept",
             summary="Consume an invitation token for the authenticated account")
@limiter.limit("10/minute")
def accept_member_invitation(
    request: Request,
    payload: InvitationAcceptRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Acceptance is bound to the authenticated account's email and consumes
    the token exactly once. Every rejection (unknown/expired/revoked/consumed/
    email-mismatch) returns the SAME code+message — the endpoint cannot be
    used to enumerate invitation states. Re-accepting one's own consumed,
    still-active invitation is an idempotent success (safe retry)."""
    from backend.app.services.brand_membership_service import BrandMembershipService
    svc = BrandMembershipService(db)
    try:
        result = svc.accept_invitation(raw_token=payload.token, user=user)
    except HTTPException:
        raise
    except Exception as exc:
        raise _membership_error(exc)
    _audit(db, user, "BRAND_MEMBER_JOINED", "BrandMembership", result["brand_id"], {
        "brand_id": result["brand_id"], "role": result["role"],
        "already": bool(result.get("already")),
    })
    return {"brand_id": result["brand_id"], "role": result["role"],
            "already_member": bool(result.get("already"))}


@router.patch("/partner/members/{membership_id}", response_model=BrandMemberOut,
              summary="Change a member's tenant role (owner only; last-owner guarded)")
def update_member_role(
    request: Request,
    membership_id: int,
    payload: MemberRoleUpdate,
    user: User = Depends(brand_members),
    db: Session = Depends(get_db),
):
    from backend.app.services.brand_membership_service import BrandMembershipService
    svc = BrandMembershipService(db)
    bp = svc.tenant_brand(user)
    before = db.get(BrandMembership, membership_id)
    before_role = before.role if before and before.brand_id == bp.id else None
    try:
        m = svc.change_member_role(brand_id=bp.id, membership_id=membership_id,
                                   new_role=payload.role, actor=user)
    except HTTPException:
        raise
    except Exception as exc:
        raise _membership_error(exc)
    _audit(db, user, "BRAND_MEMBER_ROLE_CHANGED", "BrandMembership", m.id, {
        "brand_id": bp.id}, before={"role": before_role}, after={"role": m.role})
    u = db.get(User, m.user_id)
    return BrandMemberOut(id=m.id, brand_id=m.brand_id, user_id=m.user_id,
                          full_name=u.full_name if u else "", email=u.email if u else None,
                          role=m.role, status=m.status, created_at=m.created_at,
                          revoked_at=m.revoked_at)


@router.delete("/partner/members/{membership_id}",
               summary="Remove a member (owner only; last-owner guarded; idempotent)")
def remove_member(
    request: Request,
    membership_id: int,
    user: User = Depends(brand_members),
    db: Session = Depends(get_db),
):
    from backend.app.services.brand_membership_service import BrandMembershipService
    svc = BrandMembershipService(db)
    bp = svc.tenant_brand(user)
    before = db.get(BrandMembership, membership_id)
    before_state = ({"role": before.role, "status": before.status}
                    if before and before.brand_id == bp.id else None)
    try:
        m = svc.remove_member(brand_id=bp.id, membership_id=membership_id, actor=user)
    except HTTPException:
        raise
    except Exception as exc:
        raise _membership_error(exc)
    _audit(db, user, "BRAND_MEMBER_REMOVED", "BrandMembership", m.id,
           {"brand_id": bp.id}, before=before_state, after={"status": m.status})
    return {"status": m.status, "id": m.id}
