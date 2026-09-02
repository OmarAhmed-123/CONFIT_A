from fastapi import APIRouter, Depends, Query
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.dependencies import require_role
from backend.app.models.user import User, UserRole
from backend.app.repositories.brand_repository import BrandRepository
from backend.app.schemas.brand import AdminPlatformAnalyticsOut

router = APIRouter(prefix="/admin", tags=["Platform Admin Analytics & Governance"])


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
