from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.dependencies import require_role, require_admin_recent
from backend.app.core.exceptions import ValidationDomainError
from backend.app.core.timeutils import TimeRange, TimeRangeError
from backend.app.core.request_context import client_ip, request_id as current_request_id
from backend.app.models.user import User, UserRole
from backend.app.repositories.audit_repository import AuditQuery
from backend.app.repositories.brand_repository import BrandRepository
from backend.app.repositories.user_repository import UserRepository
from backend.app.schemas.audit import AuditFacetsOut, AuditIntegrityOut, AuditStatsOut, AuditTrailPage
from backend.app.schemas.brand import AdminPlatformAnalyticsOut
from backend.app.schemas.commerce import OrderOut, OrderTransitionRequest
from backend.app.services.audit_service import AuditTrailService
from backend.app.services.commerce_service import CommerceService

router = APIRouter(prefix="/admin", tags=["Platform Admin Analytics & Governance"])


def _request_id(request: Request) -> str:
    return current_request_id(request)


def _audit_admin(request: Request, db: Session, user: User, action: str,
                 resource_type: str, resource_id: str,
                 before: Dict[str, Any], after: Dict[str, Any]) -> None:
    """ADMIN-01: every state-changing admin action is audited with the actor,
    action, resource, full before/after state (secret-free field subset), the
    actor's address and the request correlation id.

    The client address was missing entirely until G-05: ``ip_address`` was
    never passed, so the column was NULL for every admin action and the trail
    could not answer "from where".
    """
    UserRepository(db).log_audit(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=user.id,
        ip_address=client_ip(request),
        request_id=_request_id(request),
        before=before,
        after=after,
    )


def _audit_read(request: Request, db: Session, user: User, action: str,
                resource_type: str, details: Dict[str, Any]) -> None:
    """Audit a privileged READ.

    Reading the audit trail discloses every other privileged action on the
    platform, so it is itself a governance event (G-05). Aggregate-only
    endpoints (facets / stats) are deliberately not audited: they disclose no
    row content, and auditing them would bury the signal in its own noise.
    """
    UserRepository(db).log_audit(
        action=action,
        resource_type=resource_type,
        user_id=user.id,
        ip_address=client_ip(request),
        request_id=_request_id(request),
        before=None,
        after=details,
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
    days: Optional[int] = Query(
        None, ge=1, le=3650,
        description="Rolling window in days. Mutually exclusive with date_from/date_to.",
    ),
    date_from: Optional[datetime] = Query(
        None, description="ISO-8601 lower bound, inclusive (applied to every aggregate)."
    ),
    date_to: Optional[datetime] = Query(
        None,
        description=(
            "ISO-8601 upper bound, inclusive — same boundary contract as /admin/audit. "
            "Applied to every aggregate; a parameter that is accepted and then ignored "
            "would be worse than no parameter at all."
        ),
    ),
    user: User = Depends(require_role([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    """Platform KPIs over a real time window (G-15), from real tables.

    Without a parameter the window is all-time, which is what this endpoint
    always returned — so existing consumers are unaffected. The resolved window
    and its boundary semantics are echoed in the payload.
    """
    try:
        window = TimeRange.resolve(days=days, date_from=date_from, date_to=date_to)
    except TimeRangeError as exc:
        raise ValidationDomainError(str(exc))
    return BrandRepository(db).get_platform_admin_analytics(time_range=window)


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
    region: Optional[str] = Query(
        None,
        description=(
            "Accepted but NOT applied, and reported as such: the platform stores no "
            "region attribute on users or outfits, so a region-filtered number would "
            "be fabricated. The response echoes requested_region and sets "
            "region_filter_applied=false (same contract as the partner endpoint)."
        ),
    ),
    date_from: Optional[datetime] = Query(None, description="ISO-8601 lower bound on Outfit.created_at"),
    date_to: Optional[datetime] = Query(None, description="ISO-8601 upper bound on Outfit.created_at"),
    user: User = Depends(require_role([UserRole.ADMIN])),
    db: Session = Depends(get_db),
):
    """Aggregate anonymised style signals from real outfits - never individual.

    Shares one implementation with ``/admin/analytics`` (``style_preference_
    heatmap``) and ``/partner/analytics/heatmaps``: the same wire shape, the
    same k-anonymity floor, and no fabricated rows when the sample is thin.
    """
    return BrandRepository(db).get_user_preference_heatmaps(
        region=region, date_from=date_from, date_to=date_to
    )


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


@router.get("/audit", response_model=AuditTrailPage)
def get_audit_trail(
    request: Request,
    page: int = Query(1, ge=1, description="1-based page number"),
    page_size: int = Query(50, ge=1, le=200, description="Rows per page (max 200)"),
    action: Optional[str] = Query(None, description="Exact action, e.g. ADMIN_ORDER_TRANSITION"),
    resource_type: Optional[str] = Query(None, description="Exact resource type, e.g. Order"),
    resource_id: Optional[str] = Query(None, description="Exact resource id, e.g. an order number"),
    actor_id: Optional[int] = Query(None, description="Actor user id"),
    search: Optional[str] = Query(None, max_length=200, description="Free-text over action/resource/details"),
    date_from: Optional[datetime] = Query(None, description="ISO-8601 lower bound (inclusive)"),
    date_to: Optional[datetime] = Query(None, description="ISO-8601 upper bound (inclusive)"),
    only_admin_actions: bool = Query(False, description="Restrict to the ADMIN_* privileged namespace"),
    include_facets: bool = Query(False, description="Also return the filter vocabulary for the UI"),
    user: User = Depends(require_role([UserRole.ADMIN])),
    db: Session = Depends(get_db),
):
    """Real audit trail from the ``audit_logs`` table — no synthetic rows.

    Replaces the previous endpoint, which returned a bare list of 100 rows with
    five of the row's columns thrown away (``before``/``after``/``request_id``/
    ``ip_address``), an actor rendered as the string ``"User #7"``, no filters
    and no total — so the trail could not answer *what changed*, *who*, *from
    where* or *which request* (G-05).

    Reading the trail is itself audited as ``ADMIN_AUDIT_VIEW``.
    """
    query = AuditQuery(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_id=actor_id,
        search=search,
        date_from=date_from,
        date_to=date_to,
        only_admin_actions=only_admin_actions,
    )
    rid = _request_id(request)
    payload = AuditTrailService(db).trail(
        query, page=page, page_size=page_size, include_facets=include_facets, request_id=rid
    )
    _audit_read(request, db, user, "ADMIN_AUDIT_VIEW", "AuditLog",
                {"page": page, "page_size": page_size, "filters": payload["filters"],
                 "returned": len(payload["items"]), "total": payload["meta"]["total"]})
    return payload


@router.get("/audit/facets", response_model=AuditFacetsOut)
def get_audit_facets(
    request: Request,
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    user: User = Depends(require_role([UserRole.ADMIN])),
    db: Session = Depends(get_db),
):
    """Filter vocabulary derived from real rows, so the UI can never offer a
    filter value the data does not contain."""
    query = AuditQuery(action=action, resource_type=resource_type, date_from=date_from, date_to=date_to)
    return AuditTrailService(db).facets(query)


@router.get("/audit/stats", response_model=AuditStatsOut)
def get_audit_stats(
    request: Request,
    window_days: int = Query(30, ge=1, le=365),
    only_admin_actions: bool = Query(False),
    user: User = Depends(require_role([UserRole.ADMIN])),
    db: Session = Depends(get_db),
):
    """Governance rollup over real ``audit_logs`` rows: who did what, how
    often, per day, and how much of it was privileged."""
    query = AuditQuery(only_admin_actions=only_admin_actions)
    return AuditTrailService(db).stats(query, window_days=window_days)


@router.get("/audit/integrity", response_model=AuditIntegrityOut)
def get_audit_integrity(
    request: Request,
    window_days: int = Query(30, ge=1, le=365),
    user: User = Depends(require_role([UserRole.ADMIN])),
    db: Session = Depends(get_db),
):
    """Structural self-check + hash-chain verification, with stated limits.

    Since migration 0020 every audit insert carries an HMAC-SHA256 hash chain
    (core/audit_chain.py), and this endpoint RECOMPUTES it over the sampled
    window: a modified row fails its own HMAC, a deleted/reordered row breaks
    its successor's link. ``tamper_evident`` is computed from that
    verification — never asserted from configuration — and the residual
    limits (key compromise, tail truncation across runs, pre-migration rows)
    are named in ``limitations``.
    """
    result = AuditTrailService(db).integrity(
        window_days=window_days, actor_id=user.id, request_id=_request_id(request)
    )
    _audit_read(request, db, user, "ADMIN_AUDIT_INTEGRITY_CHECK", "AuditLog",
                {"window_days": window_days, "verdict": result["verdict"],
                 "tamper_evident": result["tamper_evident"],
                 "truncation": result["truncation_check"]["verdict"]})
    return result

