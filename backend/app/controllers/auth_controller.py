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
    RefreshTokenOptionalRequest,
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
REFRESH_COOKIE = "confit_refresh"


def _set_session_cookies(response: Response, access_token: str, refresh_token: Optional[str] = None) -> None:
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
    # CYCLE-3 (BLOCKER J): the refresh token was previously only returned in
    # the response body — which the browser frontend deliberately discards
    # (no token-shaped value may reach web storage). Storing it in an
    # httpOnly cookie lets the SPA transparently refresh a short-lived access
    # cookie; rotation + server-side reuse detection remain authoritative.
    if refresh_token:
        response.set_cookie(
            REFRESH_COOKIE, refresh_token,
            httponly=True, secure=secure, samesite="lax", path="/",
            max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/")


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


class EmailVerificationRequest(BaseModel):
    email: EmailStr


class VerifyEmailRequest(BaseModel):
    token: str


class DisableMFARequest(BaseModel):
    password: str


class ChangePasswordRequest(BaseModel):
    """Authenticated password rotation (cycle 9).

    Context: the email reset flow was previously the ONLY way to change a
    password, and it honestly 501s while no email provider is provisioned —
    which made the admin handover ("sign in once with the temporary
    password, then change it") impossible in-product. This endpoint is the
    in-product rotation path; MFA-enabled accounts must also present a
    current TOTP / recovery code.
    """

    current_password: str
    new_password: str = Field(min_length=8, max_length=72)
    mfa_code: Optional[str] = None


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
def register(request: Request, response: Response, payload: UserRegister, db: Session = Depends(get_db)):
    service = AuthService(db)
    # NOTE: no `role` is passed — `AuthService.register` hard-codes
    # CONSUMER (P0 security invariant; see the method docstring).
    res = service.register(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        phone=payload.phone,
        preferred_language=payload.preferred_language,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    _set_session_cookies(response, res["access_token"], refresh_token=res.get("refresh_token"))
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
    _set_session_cookies(response, res["access_token"], refresh_token=res.get("refresh_token"))
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
    _set_session_cookies(response, res["access_token"], refresh_token=res.get("refresh_token"))
    return {
        "access_token": res["access_token"],
        "refresh_token": res["refresh_token"],
        "token_type": "bearer",
        "user": _user_out(res["user"]),
    }


def _refresh_rejected(message: str):
    """401 with the standard error envelope AND a cleared refresh cookie.

    Built as a direct response (instead of raising) because the global
    exception handler constructs a fresh JSONResponse and would silently
    drop the Set-Cookie deletion — leaving the browser retrying a dead
    cookie forever.
    """
    from fastapi.responses import JSONResponse as _JSONResponse

    resp = _JSONResponse(
        status_code=401,
        content={"error": {"code": "AUTH_FAILED", "message": message, "details": {}}},
    )
    resp.delete_cookie(REFRESH_COOKIE, path="/")
    return resp


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    payload: Optional[RefreshTokenOptionalRequest] = None,
):
    # Token source precedence: explicit body (API/mobile clients, unchanged
    # contract) → httpOnly cookie (browser SPA). Never both silently: the body
    # wins only because pre-cookie clients cannot send one.
    token = payload.refresh_token if payload and payload.refresh_token else request.cookies.get(REFRESH_COOKIE)
    if not token:
        # Honest failure — and drop any stale refresh cookie so the browser
        # client does not hammer this endpoint on every 401. The error is
        # returned directly (not raised) because the global exception handler
        # rebuilds the response and would discard the Set-Cookie header.
        return _refresh_rejected("Refresh token not provided.")
    service = AuthService(db)
    try:
        res = service.refresh(
            token,
            ip_address=_client_ip(request),
            user_agent=_user_agent(request),
        )
    except AuthenticationError as exc:
        # Expired/reused/unknown refresh token: kill the cookie too, then
        # surface the honest failure (no silent session extension).
        return _refresh_rejected(str(exc))

    _set_session_cookies(response, res["access_token"], refresh_token=res["refresh_token"])
    return {
        "access_token": res["access_token"],
        "refresh_token": res["refresh_token"],
        "token_type": "bearer",
        "user": _user_out(res["user"]),
    }


@router.post("/logout")
def logout(response: Response, payload: Optional[RefreshTokenOptionalRequest] = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
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


@router.post("/change-password")
@limiter.limit("10/minute")
def change_password(request: Request, payload: ChangePasswordRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Rotate the signed-in user's password (cycle 9).

    Requires the current password (and an MFA code when MFA is enabled);
    revokes every active session on success. Rate-limited to blunt
    brute-force attempts against ``current_password``.
    """
    AuthService(db).change_password(
        user,
        payload.current_password,
        payload.new_password,
        mfa_code=payload.mfa_code,
    )
    return {
        "status": "success",
        "message": "Password updated. All sessions were revoked — please sign in again.",
    }


@router.post("/verify-email/request")
@limiter.limit("5/minute")
def request_email_verification(request: Request, payload: EmailVerificationRequest, db: Session = Depends(get_db)):
    """Issue (or re-issue) a verification email. Non-committal response by
    design: never reveals whether the address exists or still needs
    verification. Rate-limited per IP."""
    return AuthService(db).request_email_verification(payload.email, ip_address=_client_ip(request))


@router.post("/verify-email")
@limiter.limit("10/minute")
def verify_email(request: Request, payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    # Redemption is real as of cycle 4: hashed one-time token, 24 h expiry,
    # flips user.is_verified. Unconfigured environments still get the honest
    # 501 — there would be no way to deliver the token in the first place.
    return AuthService(db).complete_email_verification(payload.token)


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
