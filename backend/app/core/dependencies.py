import re
from typing import Optional, List
from fastapi import Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.security import decode_token
from backend.app.models.user import User, UserRole
from backend.app.repositories.user_repository import UserRepository
from backend.app.core.exceptions import AuthenticationError, AuthorizationError, AdminReauthRequiredError

security = HTTPBearer(auto_error=False)

BRAND_ROLES = [UserRole.BRAND_OWNER, UserRole.BRAND_MANAGER, UserRole.BRAND_STAFF, UserRole.ADMIN]
ADMIN_ROLES = [UserRole.ADMIN]
CUSTOMER_ROLES = [UserRole.CONSUMER, UserRole.BRAND_OWNER, UserRole.BRAND_MANAGER, UserRole.BRAND_STAFF, UserRole.ADMIN]

# --- Vercel Authorization-header redaction (production-verified 2026-09-05) ---
# Vercel's edge rewrites the Authorization header value for some serverless
# functions before it reaches the app: "Bearer <jwt>" arrives as "***<jwt>"
# (the "Bearer " scheme prefix is replaced by "***"); low-entropy values
# arrive as bare "***". The JWT payload itself survives intact. Verified in
# production with an in-scope byte probe (scope headers hex), while the
# identical request to a sibling function in the same deployment arrived
# unredacted. HTTPBearer therefore sees no scheme and returns None, which
# made every bearer-authenticated API client 401 in production while the
# cookie flow (unaffected) kept working.
#
# The recovery below accepts ONLY the platform's own redaction marker in
# place of the Bearer scheme; the recovered token still passes the exact
# same signature/expiry/subject validation. A bare "***" (no token) never
# authenticates, and cookies remain the fallback.
_REDACTED_BEARER_MARKER = "***"


def _extract_token(request: Request, credentials: Optional[HTTPAuthorizationCredentials]) -> Optional[str]:
    """Bearer header wins (API clients); otherwise the httpOnly session cookie
    set at login. The cookie is NOT readable from JavaScript, which is the
    whole point of the localStorage -> cookie migration.

    Also recovers bearer tokens whose scheme prefix was rewritten to the
    Vercel redaction marker (see note above) — the token itself is intact
    and is validated exactly as before."""
    if credentials:
        return credentials.credentials
    auth = request.headers.get("authorization")
    if auth:
        parts = re.split(r"\s+", auth, maxsplit=1)
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
            return parts[1].strip()
        if auth.startswith(_REDACTED_BEARER_MARKER):
            rest = auth[len(_REDACTED_BEARER_MARKER):].strip()
            if rest:
                return rest
    return request.cookies.get("confit_token")


def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[User]:
    token = _extract_token(request, credentials)
    if not token:
        return None
    try:
        payload = decode_token(token, expected_type="access")
        user_id = int(payload.get("sub"))
        repo = UserRepository(db)
        user = repo.get_by_id(user_id)
        if user and not user.is_active:
            return None
        return user
    except Exception:
        return None


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    token = _extract_token(request, credentials)
    if not token:
        raise AuthenticationError("Authorization bearer token required.")
    try:
        payload = decode_token(token, expected_type="access")
        user_id = int(payload.get("sub"))
        repo = UserRepository(db)
        user = repo.get_by_id(user_id)
        if not user or not user.is_active:
            raise AuthenticationError("User not found or account deactivated.")
        return user
    except AuthenticationError:
        raise
    except Exception as exc:
        raise AuthenticationError(f"Authentication failed: {str(exc)}")


def require_role(allowed_roles: List[UserRole]):
    """Enforces role-based access control (RBAC) with hierarchical administrative privileges."""
    def role_checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles and user.role != UserRole.ADMIN:
            raise AuthorizationError(f"Access restricted to {', '.join(r.value for r in allowed_roles)}. Current user role: {user.role.value}")
        return user
    return role_checker


def require_admin_recent(max_age_minutes: int = 60):
    """ADMIN-01 step-up policy: sensitive admin mutations need a FRESH sign-in.

    Wraps require_role([ADMIN]) and additionally refuses access tokens whose
    `iat` is older than the freshness window (default 60 min) with
    401 ADMIN_REAUTH_REQUIRED — the admin must re-authenticate before
    continuing. Read-only admin views are intentionally left on plain
    require_role so dashboards keep working; the re-auth cost applies only
    to state-changing admin actions.
    """
    from datetime import datetime, timezone, timedelta

    def checker(
        request: Request,
        user: User = Depends(require_role([UserRole.ADMIN])),
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    ) -> User:
        token = credentials.credentials if credentials else (request.cookies.get("confit_token") or "")
        try:
            payload = decode_token(token, expected_type="access")
            iat = int(payload.get("iat") or 0)
        except Exception:
            raise AuthenticationError("Authentication failed: invalid token.")
        age = datetime.now(timezone.utc) - datetime.fromtimestamp(iat, tz=timezone.utc)
        if age > timedelta(minutes=max_age_minutes):
            raise AdminReauthRequiredError(int(age.total_seconds() // 60), max_age_minutes)
        return user

    return checker


def require_brand_scope(user: User = Depends(get_current_user)) -> User:
    """Enforces that the user belongs to an active Brand Organization or is a Platform Admin."""
    if user.role == UserRole.ADMIN:
        return user
    if user.role not in [UserRole.BRAND_OWNER, UserRole.BRAND_MANAGER, UserRole.BRAND_STAFF]:
        raise AuthorizationError("Access denied: Brand Organization membership required.")
    if not user.brand_profile:
        raise AuthorizationError("Access denied: No brand organization linked to this account.")
    return user
