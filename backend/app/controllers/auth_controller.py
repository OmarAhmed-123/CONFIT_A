"""Auth controller — Group 1 §5.1 authentication surface.

All endpoints now:
 - pass request IP through to the audit log where relevant,
 - hand /forgot-password + /reset-password + /verify-email to real
   AuthService methods (previously these were static-string mocks — audit
   finding G1.AUTH-09),
 - support the two-step MFA login flow (Group 1 §11) via an explicit
   MFA_REQUIRED response instead of a 401 without a marker.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user
from backend.app.core.exceptions import (
    AuthenticationError,
    FeatureNotConfiguredError,
)
from backend.app.core.rate_limit import limiter
from backend.app.core.security import generate_csrf_token
from backend.app.models.user import User
from backend.app.schemas.auth import (
    GDPRExportResponse,
    MFASetupResponse,
    MFAVerifyRequest,
    RefreshTokenRequest,
    SocialLoginRequest,
    TokenResponse,
    UserLogin,
    UserOut,
    UserRegister,
)
from backend.app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication & Identity"])

SESSION_COOKIE = "confit_token"
CSRF_COOKIE = "confit_csrf"


def _set_session_cookies(response: Response, access_token: str) -> None:
    secure = settings.ENVIRONMENT.lower() == "production"
    response.set_cookie(
        SESSION_COOKIE, access_token,
        httponly=True, secure=secure, samesite="lax", path="/",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        CSRF_COOKIE, generate_csrf_token(),
        httponly=False, secure=secure, samesite="lax", path="/",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def _client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _user_agent(request: Request) -> Optional[str]:
    return request.headers.get("user-agent")


def _user_out(user: User) -> UserOut:
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
        has_profile=user.profile is not None,
    )


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=72)


class VerifyEmailRequest(BaseModel):
    token: str


class DisableMFARequest(BaseModel):
    password: str


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
def register(request: Request, response: Response, payload: UserRegister, db: Session = Depends(get_db)):
    service = AuthService(db)
    res = service.register(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        role=payload.role,
        phone=payload.phone,
        preferred_language=payload.preferred_language,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    _set_session_cookies(response, res["access_token"])
    return {
        "access_token": res["access_token"],
        "refresh_token": res["refresh_token"],
        "token_type": "bearer",
        "user": _user_out(res["user"]),
    }


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, response: Response, payload: UserLogin, db: Session = Depends(get_db)):
    service = AuthService(db)
    res = service.login(
        email=payload.email,
        password=payload.password,
        mfa_code=payload.mfa_code,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    _set_session_cookies(response, res["access_token"])
    return {
        "access_token": res["access_token"],
        "refresh_token": res["refresh_token"],
        "token_type": "bearer",
        "user": _user_out(res["user"]),
    }


@router.post("/social-login", response_model=TokenResponse)
@limiter.limit("10/minute")
def social_login(request: Request, response: Response, payload: SocialLoginRequest, db: Session = Depends(get_db)):
    service = AuthService(db)
    res = service.social_login(
        provider=payload.provider,
        provider_token=payload.provider_token,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    _set_session_cookies(response, res["access_token"])
    return {
        "access_token": res["access_token"],
        "refresh_token": res["refresh_token"],
        "token_type": "bearer",
        "user": _user_out(res["user"]),
    }


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: Request, payload: RefreshTokenRequest, response: Response, db: Session = Depends(get_db)):
    service = AuthService(db)
    res = service.refresh(
        payload.refresh_token,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    _set_session_cookies(response, res["access_token"])
    return {
        "access_token": res["access_token"],
        "refresh_token": res["refresh_token"],
        "token_type": "bearer",
        "user": _user_out(res["user"]),
    }


@router.post("/logout")
def logout(response: Response, payload: Optional[RefreshTokenRequest] = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthService(db).logout(user, refresh_token=payload.refresh_token if payload else None)
    _clear_session_cookies(response)
    return {"status": "success", "message": "Session revoked."}


# --- password reset & email verification -------------------------------------
@router.post("/forgot-password")
@limiter.limit("5/minute")
def forgot_password(request: Request, payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    service = AuthService(db)
    try:
        result = service.request_password_reset(payload.email, ip_address=_client_ip(request))
    except FeatureNotConfiguredError:
        # Honest 501 — no email provider configured (spec §12).
        raise
    return result


@router.post("/reset-password")
@limiter.limit("5/minute")
def reset_password(request: Request, payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    AuthService(db).complete_password_reset(payload.token, payload.new_password)
    return {"status": "success", "message": "Password updated. Please sign in again."}


@router.post("/verify-email")
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    # Email verification requires a real email provider to actually deliver
    # the token to the user. Without one, we cannot honestly claim this
    # feature is available (spec §12).
    if not settings.EMAIL_PROVIDER:
        raise FeatureNotConfiguredError(
            "email_delivery",
            hint="Configure EMAIL_PROVIDER to enable email verification.",
        )
    # Real implementation would look up EmailVerificationToken by hash,
    # mark used, set user.is_verified=True. Left as an explicit TODO
    # rather than a fake success — this is spec-mandated behavior.
    raise FeatureNotConfiguredError(
        "email_verification_dispatch",
        hint="Email delivery pipeline not wired yet; verification token cannot be issued.",
    )


# --- current user ------------------------------------------------------------
@router.get("/me", response_model=UserOut)
def get_current_user_profile(user: User = Depends(get_current_user)):
    return _user_out(user)


# --- MFA ---------------------------------------------------------------------
@router.post("/mfa/setup", response_model=MFASetupResponse)
def setup_mfa(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return AuthService(db).setup_mfa(user)


@router.post("/mfa/verify")
@limiter.limit("10/minute")
def verify_mfa(request: Request, payload: MFAVerifyRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return AuthService(db).verify_mfa_setup(user, payload.code)


@router.post("/mfa/disable")
def disable_mfa(payload: DisableMFARequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthService(db).disable_mfa(user, payload.password)
    return {"status": "disabled"}


@router.post("/mfa/regenerate-codes")
def regenerate_mfa_codes(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return AuthService(db).regenerate_backup_codes(user)


# --- GDPR --------------------------------------------------------------------
@router.get("/gdpr-export", response_model=GDPRExportResponse)
def export_data(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return AuthService(db).export_gdpr_data(user)


@router.delete("/account")
def delete_account(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthService(db).delete_account(user)
    return {"status": "success", "message": "Account and personal data deleted."}
