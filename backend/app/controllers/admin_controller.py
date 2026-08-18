from typing import Dict, Any, List
from fastapi import APIRouter, Depends
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


@router.get("/analytics/features")
@router.get("/analytics/attribution")
def get_admin_feature_attribution(
    user: User = Depends(require_role([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    repo = BrandRepository(db)
    an = repo.get_platform_admin_analytics()
    return an["revenue_attribution"]


@router.get("/analytics/returns")
def get_admin_returns_overview(
    user: User = Depends(require_role([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    repo = BrandRepository(db)
    an = repo.get_platform_admin_analytics()
    return {
        "platform_avg_return_rate": an["platform_avg_return_rate"],
        "return_rate_tryon_users": an["return_rate_tryon_users"],
        "return_rate_non_tryon_users": an["return_rate_non_tryon_users"]
    }


@router.get("/audit")
def get_audit_trail(user: User = Depends(require_role([UserRole.ADMIN]))):
    return [
        {"id": 1, "action": "MFA_ENABLED", "actor": "shopper@confit.io", "entity": "User #1", "timestamp": "2026-08-17T16:00:00Z"},
        {"id": 2, "action": "SKU_STOCK_UPDATED", "actor": "brand@massimodutti.com", "entity": "SKU #MD-BLZ-NVY-M", "timestamp": "2026-08-17T16:05:00Z"},
        {"id": 3, "action": "GDPR_DATA_EXPORT", "actor": "shopper@confit.io", "entity": "User #1", "timestamp": "2026-08-17T16:10:00Z"}
    ]
