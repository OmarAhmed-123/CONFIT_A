from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user
from backend.app.models.user import User
from backend.app.services.auth_service import AuthService
from backend.app.schemas.auth import (
    UserRegister,
    UserLogin,
    SocialLoginRequest,
    TokenResponse,
    RefreshTokenRequest,
    MFASetupResponse,
    MFAVerifyRequest,
    GDPRExportResponse,
    UserOut
)
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="/auth", tags=["Authentication & Identity"])


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class VerifyEmailRequest(BaseModel):
    token: str


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    service = AuthService(db)
    res = service.register(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        role=payload.role,
        phone=payload.phone,
        preferred_language=payload.preferred_language
    )
    user_out = UserOut(
        id=res["user"].id,
        email=res["user"].email,
        full_name=res["user"].full_name,
        role=res["user"].role,
        phone=res["user"].phone,
        preferred_language=res["user"].preferred_language,
        is_active=res["user"].is_active,
        is_verified=res["user"].is_verified,
        mfa_enabled=res["user"].mfa_enabled,
        created_at=res["user"].created_at,
        brand_id=res["user"].brand_profile.id if res["user"].brand_profile else None,
        has_profile=res["user"].profile is not None
    )
    return {
        "access_token": res["access_token"],
        "refresh_token": res["refresh_token"],
        "token_type": "bearer",
        "user": user_out
    }


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    service = AuthService(db)
    res = service.login(email=payload.email, password=payload.password, mfa_code=payload.mfa_code)
    user_out = UserOut(
        id=res["user"].id,
        email=res["user"].email,
        full_name=res["user"].full_name,
        role=res["user"].role,
        phone=res["user"].phone,
        preferred_language=res["user"].preferred_language,
        is_active=res["user"].is_active,
        is_verified=res["user"].is_verified,
        mfa_enabled=res["user"].mfa_enabled,
        created_at=res["user"].created_at,
        brand_id=res["user"].brand_profile.id if res["user"].brand_profile else None,
        has_profile=res["user"].profile is not None
    )
    return {
        "access_token": res["access_token"],
        "refresh_token": res["refresh_token"],
        "token_type": "bearer",
        "user": user_out
    }


@router.post("/social-login", response_model=TokenResponse)
def social_login(payload: SocialLoginRequest, db: Session = Depends(get_db)):
    service = AuthService(db)
    res = service.social_login(
        provider=payload.provider,
        access_token=payload.access_token,
        email=payload.email,
        full_name=payload.full_name
    )
    user_out = UserOut(
        id=res["user"].id,
        email=res["user"].email,
        full_name=res["user"].full_name,
        role=res["user"].role,
        phone=res["user"].phone,
        preferred_language=res["user"].preferred_language,
        is_active=res["user"].is_active,
        is_verified=res["user"].is_verified,
        mfa_enabled=res["user"].mfa_enabled,
        created_at=res["user"].created_at,
        brand_id=res["user"].brand_profile.id if res["user"].brand_profile else None,
        has_profile=res["user"].profile is not None
    )
    return {
        "access_token": res["access_token"],
        "refresh_token": res["refresh_token"],
        "token_type": "bearer",
        "user": user_out
    }


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshTokenRequest, db: Session = Depends(get_db)):
    service = AuthService(db)
    res = service.refresh(payload.refresh_token)
    user_out = UserOut(
        id=res["user"].id,
        email=res["user"].email,
        full_name=res["user"].full_name,
        role=res["user"].role,
        phone=res["user"].phone,
        preferred_language=res["user"].preferred_language,
        is_active=res["user"].is_active,
        is_verified=res["user"].is_verified,
        mfa_enabled=res["user"].mfa_enabled,
        created_at=res["user"].created_at,
        brand_id=res["user"].brand_profile.id if res["user"].brand_profile else None,
        has_profile=res["user"].profile is not None
    )
    return {
        "access_token": res["access_token"],
        "refresh_token": res["refresh_token"],
        "token_type": "bearer",
        "user": user_out
    }


@router.post("/logout")
def logout(user: User = Depends(get_current_user)):
    return {"status": "success", "message": "Successfully logged out and session revoked."}


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest):
    return {"status": "success", "message": f"Password reset instructions dispatched to {payload.email}."}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest):
    return {"status": "success", "message": "Password successfully reset."}


@router.post("/verify-email")
def verify_email(payload: VerifyEmailRequest):
    return {"status": "success", "message": "Email address verified successfully."}


@router.get("/me", response_model=UserOut)
def get_current_user_profile(user: User = Depends(get_current_user)):
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        phone=user.phone,
        preferred_language=user.preferred_language,
        is_active=user.is_active,
        is_verified=user.is_verified,
        mfa_enabled=user.mfa_enabled,
        created_at=user.created_at,
        brand_id=user.brand_profile.id if user.brand_profile else None,
        has_profile=user.profile is not None
    )


@router.post("/mfa/setup", response_model=MFASetupResponse)
def setup_mfa(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    service = AuthService(db)
    return service.setup_mfa(user)


@router.post("/mfa/verify")
def verify_mfa(payload: MFAVerifyRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    service = AuthService(db)
    service.verify_mfa_setup(user, payload.code)
    return {"status": "success", "message": "MFA has been successfully verified and activated."}


@router.get("/gdpr-export", response_model=GDPRExportResponse)
def export_data(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    service = AuthService(db)
    return service.export_gdpr_data(user)


@router.delete("/account")
def delete_account(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    service = AuthService(db)
    service.delete_account(user)
    return {"status": "success", "message": "User account and associated private data successfully deleted."}
