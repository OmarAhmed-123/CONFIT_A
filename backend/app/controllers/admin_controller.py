from fastapi import APIRouter, Depends, Query, Request
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.dependencies import require_role, require_admin_recent
from backend.app.models.user import User, UserRole
from backend.app.repositories.brand_repository import BrandRepository
from backend.app.repositories.user_repository import UserRepository
from backend.app.schemas.brand import AdminPlatformAnalyticsOut
from backend.app.schemas.commerce import OrderOut, OrderTransitionRequest
from backend.app.schemas.auth import PartnerApplicationDecision
from backend.app.services.commerce_service import CommerceService
from backend.app.services import partner_service

router = APIRouter(prefix="/admin", tags=["Platform Admin Analytics & Governance"])


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "") or ""


def _audit_admin(request: Request, db: Session, user: User, action: str,
                 resource_type: str, resource_id: str,
                 before: Dict[str, Any], after: Dict[str, Any]) -> None:
    """ADMIN-01: every state-changing admin action is audited with the actor,
    action, resource, full before/after state (secret-free field subset) and
    the request correlation id."""
    UserRepository(db).log_audit(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=user.id,
        request_id=_request_id(request),
        before=before,
        after=after,
    )


@router.post("/orders/{order_number}/transition", response_model=OrderOut)
def transition_order_status(
    order_number: str,
    payload: OrderTransitionRequest,
    request: Request,
    user: User = Depends(require_admin_recent(max_age_minutes=60)),
    db: Session = Depends(get_db),
):
    """PAY-01/ADMIN-01: admin order-status transition (fulfilment lever).

    Enforced by ORDER_TRANSITIONS (invalid jumps -> 409), the fulfilment gate
    (goods move only for settled payment, COD settles at handover), a 60-min
    admin re-auth policy, and a full before/after audit row.
    """
    service = CommerceService(db)
    current = service.get_order(order_number)  # 404 if unknown — before mutation
    before = {"status": current.get("status"), "payment_status": current.get("payment_status")}
    result = service.transition_order(order_number, payload.new_status)
    after = {"status": result.get("status"), "payment_status": result.get("payment_status")}
    _audit_admin(request, db, user, "ADMIN_ORDER_TRANSITION", "Order", order_number, before, after)
    return result


@router.post("/orders/{order_number}/capture-payment", response_model=OrderOut)
def capture_order_payment(
    order_number: str,
    request: Request,
    user: User = Depends(require_admin_recent(max_age_minutes=60)),
    db: Session = Depends(get_db),
):
    """PAY-01/ADMIN-01: explicit DEMO-mode capture of an authorized payment.

    Refuses in live mode — real captures arrive via the signed provider
    webhook only. Idempotent for already-paid orders. Audited with
    before/after payment status.
    """
    service = CommerceService(db)
    current = service.get_order(order_number)
    before = {"status": current.get("status"), "payment_status": current.get("payment_status")}
    result = service.capture_demo_payment(order_number)
    after = {"status": result.get("status"), "payment_status": result.get("payment_status")}
    _audit_admin(request, db, user, "ADMIN_DEMO_CAPTURE", "Order", order_number, before, after)
    return result


@router.get("/analytics", response_model=AdminPlatformAnalyticsOut)
@router.get("/overview", response_model=AdminPlatformAnalyticsOut)
@router.get("/analytics/overview", response_model=AdminPlatformAnalyticsOut)
def get_admin_analytics(
    user: User = Depends(require_role([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    repo = BrandRepository(db)
    return repo.get_platform_admin_analytics()


@router.get("/analytics/brands")
def get_admin_brands_comparison(
    user: User = Depends(require_role([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    repo = BrandRepository(db)
    an = repo.get_platform_admin_analytics()
    return an["top_performing_brands"]


@router.get("/analytics/most-styled")
def get_most_styled_items(
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(require_role([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    """Ranking of items by outfit appearances across all users - real data"""
    repo = BrandRepository(db)
    items = repo.get_most_styled_items(limit=limit)
    return {
        "items": items,
        "methodology": "Count of OutfitItem appearances grouped by product_id, ordered by appearances DESC. Real outfit data, not fake.",
        "total_items": len(items)
    }


@router.get("/analytics/outfit-to-purchase")
def get_outfit_to_purchase_ratio(
    user: User = Depends(require_role([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    """% of saved outfits that result in purchase - measures stylist ROI"""
    repo = BrandRepository(db)
    return repo.get_outfit_to_purchase_ratio()


@router.get("/analytics/features")
@router.get("/analytics/attribution")
def get_admin_feature_attribution(
    user: User = Depends(require_role([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    repo = BrandRepository(db)
    # Real revenue attribution
    attribution = repo.get_revenue_attribution()
    return attribution


@router.get("/analytics/returns")
def get_admin_returns_overview(
    user: User = Depends(require_role([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    repo = BrandRepository(db)
    metrics = repo.get_return_reduction_metrics()
    return metrics


@router.get("/analytics/heatmaps")
def get_admin_heatmaps(
    region: str = Query("MENA", description="Region filter"),
    user: User = Depends(require_role([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    """Aggregate anonymized style preferences - never individual"""
    repo = BrandRepository(db)
    heatmaps = repo.get_user_preference_heatmaps(region=region)
    return heatmaps


@router.get("/analytics/brand-performance")
def get_brand_performance_table(
    user: User = Depends(require_role([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    """Side-by-side comparison of brand conversion rates"""
    repo = BrandRepository(db)
    analytics = repo.get_platform_admin_analytics()
    return {
        "brands": analytics["top_performing_brands"],
        "methodology": "Real data: views from RecentlyViewed, tryons from TryOnSession, orders from OrderItem, returns from ReturnRequest. Conversion = orders/views*100. Sorted by orders DESC.",
        "total_brands": len(analytics["top_performing_brands"])
    }


@router.get("/audit")
def get_audit_trail(
    user: User = Depends(require_role([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    """Real audit trail from AuditLog model - no fake data"""
    from backend.app.models.user import AuditLog
    logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(100).all()
    # Return real data only, empty list if no logs (honest, no fabricated samples)
    return [
        {
            "id": log.id,
            "action": log.action,
            "actor": f"User #{log.user_id}" if log.user_id else "system",
            "entity": (log.resource_type + f" #{log.resource_id}") if log.resource_id else log.resource_type,
            "details": log.details_json,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None
        }
        for log in logs
    ]


# ===========================================================================
# Partner onboarding approvals (BRD G6 §2.2 — "admin: partner onboarding
# approvals"). This is the trusted server-side provisioning boundary: approval
# creates the brand tenant and sets brand_owner; nothing here is client-driven.
# ===========================================================================

def _application_out(app) -> Dict[str, Any]:
    return {
        "id": app.id,
        "user_id": app.user_id,
        "status": app.status.value if hasattr(app.status, "value") else str(app.status),
        "brand_name": app.brand_name,
        "legal_name": app.legal_name,
        "website": app.website,
        "market": app.market,
        "category": app.category,
        "catalogue_size": app.catalogue_size,
        "contact_name": app.contact_name,
        "contact_email": app.contact_email,
        "contact_phone": app.contact_phone,
        "message": app.message,
        "submitted_at": app.submitted_at,
        "reviewed_at": app.reviewed_at,
        "reviewed_by_user_id": app.reviewed_by_user_id,
        "decision_note": app.decision_note,
        "brand_id": app.brand_id,
    }


@router.get("/partner-applications")
def list_partner_applications(
    request: Request,
    status: str = Query(default="pending"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_role([UserRole.ADMIN])),
    db: Session = Depends(get_db),
):
    rows = partner_service.list_applications(db, status=status or None, limit=limit, offset=offset)
    return {"items": [_application_out(a) for a in rows], "count": len(rows), "status_filter": status}


@router.post("/partner-applications/{application_id}/approve")
def approve_partner_application(
    application_id: int,
    payload: PartnerApplicationDecision,
    request: Request,
    user: User = Depends(require_admin_recent(max_age_minutes=60)),
    db: Session = Depends(get_db),
):
    """Approve → provisions the brand tenant and grants brand_owner.

    Step-up (fresh admin session) + full before/after audit, because this is a
    privilege-granting action.
    """
    before = {"status": "pending"}
    application = partner_service.review_application(
        db, application_id, user, approve=True, note=payload.note,
        request_id=_request_id(request),
    )
    _audit_admin(request, db, user, "ADMIN_PARTNER_APPLICATION_APPROVED", "PartnerApplication",
                 str(application.id), before,
                 {"status": _application_out(application)["status"], "brand_id": application.brand_id})
    return _application_out(application)


@router.post("/partner-applications/{application_id}/reject")
def reject_partner_application(
    application_id: int,
    payload: PartnerApplicationDecision,
    request: Request,
    user: User = Depends(require_admin_recent(max_age_minutes=60)),
    db: Session = Depends(get_db),
):
    before = {"status": "pending"}
    application = partner_service.review_application(
        db, application_id, user, approve=False, note=payload.note,
        request_id=_request_id(request),
    )
    _audit_admin(request, db, user, "ADMIN_PARTNER_APPLICATION_REJECTED", "PartnerApplication",
                 str(application.id), before, {"status": _application_out(application)["status"]})
    return _application_out(application)
