from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user, get_current_user_optional
from backend.app.models.user import User
from backend.app.services.profile_service import ProfileService
from backend.app.services.auth_service import AuthService
from backend.app.schemas.profile import StyleQuizInput, USPResponse
from pydantic import BaseModel

router = APIRouter(tags=["User Style Profile (USP) & Account Context"])


class ConsentUpdateRequest(BaseModel):
    photo_storage: bool = True
    ai_personalization: bool = True
    marketing_analytics: bool = False
    policy_version: int = 3


# 1. Primary Profile Routes
@router.get("/profile/me", response_model=USPResponse)
def get_user_usp(user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    service = ProfileService(db)
    user_id = user.id if user else 1
    usp = service.get_profile(user_id)
    if not usp:
        return service.save_quiz_and_preferences(user_id, {
            "style_archetypes": ["Smart Casual", "Quiet Luxury"],
            "preferred_colors": ["Navy", "Beige", "Black", "White"],
            "fashion_aesthetics": ["Old Money", "Modern Tailored"],
            "budget_monthly_min": 200.0,
            "budget_monthly_max": 1200.0,
            "budget_per_outfit_max": 400.0,
            "preferred_brands": ["Massimo Dutti", "COS", "Zara", "Reiss"],
            "size_tops": "M",
            "size_bottoms": "32",
            "size_shoes": "42",
            "fit_preference": "regular"
        })
    return usp


@router.post("/profile/onboarding-quiz", response_model=USPResponse)
def submit_onboarding_quiz(
    payload: StyleQuizInput,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = ProfileService(db)
    user_id = user.id if user else 1
    return service.save_quiz_and_preferences(user_id, payload.model_dump())


@router.put("/profile/preferences", response_model=USPResponse)
@router.patch("/profile/preferences", response_model=USPResponse)
def update_preferences(
    payload: StyleQuizInput,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = ProfileService(db)
    user_id = user.id if user else 1
    return service.save_quiz_and_preferences(user_id, payload.model_dump())


# 2. Documented `/me` Endpoints (Specification 04 & 06)
@router.get("/me", response_model=Dict[str, Any])
def get_me_composite(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    service = ProfileService(db)
    usp = service.get_profile(user.id)
    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "phone": user.phone,
            "preferred_language": user.preferred_language,
            "is_active": user.is_active,
            "mfa_enabled": user.mfa_enabled
        },
        "style_profile": usp
    }


@router.patch("/me/profile", response_model=Dict[str, Any])
def patch_me_profile(payload: Dict[str, Any], user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if "full_name" in payload:
        user.full_name = payload["full_name"]
    if "phone" in payload:
        user.phone = payload["phone"]
    if "preferred_language" in payload:
        user.preferred_language = payload["preferred_language"]
    db.commit()
    return {"status": "success", "user_id": user.id, "updated": True}


@router.patch("/me/style-profile", response_model=USPResponse)
def patch_me_style_profile(payload: StyleQuizInput, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    service = ProfileService(db)
    return service.save_quiz_and_preferences(user.id, payload.model_dump())


@router.patch("/me/body-profile", response_model=USPResponse)
def patch_me_body_profile(payload: StyleQuizInput, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    service = ProfileService(db)
    return service.save_quiz_and_preferences(user.id, payload.model_dump())


@router.patch("/me/preferences", response_model=USPResponse)
def patch_me_preferences(payload: StyleQuizInput, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    service = ProfileService(db)
    return service.save_quiz_and_preferences(user.id, payload.model_dump())


@router.get("/me/consents")
def get_me_consents(user: Optional[User] = Depends(get_current_user_optional)):
    return {
        "user_id": user.id if user else 1,
        "photo_storage": True,
        "ai_personalization": True,
        "marketing_analytics": False,
        "policy_version": 3,
        "last_agreed_at": user.created_at if user else "2026-08-17T16:00:00Z"
    }


@router.patch("/me/consents")
def patch_me_consents(payload: ConsentUpdateRequest, user: User = Depends(get_current_user)):
    return {
        "status": "success",
        "user_id": user.id,
        "consents": payload.model_dump(),
        "acknowledged_at": user.updated_at
    }


@router.post("/me/export")
def post_me_export(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    auth_srv = AuthService(db)
    return auth_srv.export_gdpr_data(user)


@router.delete("/me")
def delete_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    auth_srv = AuthService(db)
    auth_srv.delete_account(user)
    return {"status": "success", "message": "Account deleted."}
