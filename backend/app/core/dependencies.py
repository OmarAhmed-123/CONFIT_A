from typing import Optional, List
from fastapi import Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.security import decode_token
from backend.app.models.user import User, UserRole
from backend.app.repositories.user_repository import UserRepository
from backend.app.core.exceptions import AuthenticationError, AuthorizationError

security = HTTPBearer(auto_error=False)

BRAND_ROLES = [UserRole.BRAND_OWNER, UserRole.BRAND_MANAGER, UserRole.BRAND_STAFF, UserRole.ADMIN]
ADMIN_ROLES = [UserRole.ADMIN]
CUSTOMER_ROLES = [UserRole.CONSUMER, UserRole.BRAND_OWNER, UserRole.BRAND_MANAGER, UserRole.BRAND_STAFF, UserRole.ADMIN]


def _extract_token(request: Request, credentials: Optional[HTTPAuthorizationCredentials]) -> Optional[str]:
    """Bearer header wins (API clients); otherwise the httpOnly session cookie
    set at login. The cookie is NOT readable from JavaScript, which is the
    whole point of the localStorage -> cookie migration."""
    if credentials:
        return credentials.credentials
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
        payload = decode_token(token)
        user_id = int(payload.get("sub"))
        repo = UserRepository(db)
        user = repo.get_by_id(user_id)
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
        payload = decode_token(token)
        user_id = int(payload.get("sub"))
        repo = UserRepository(db)
        user = repo.get_by_id(user_id)
        if not user or not user.is_active:
            raise AuthenticationError("User not found or account deactivated.")
        return user
    except Exception as exc:
        raise AuthenticationError(f"Authentication failed: {str(exc)}")


def require_role(allowed_roles: List[UserRole]):
    """Enforces role-based access control (RBAC) with hierarchical administrative privileges."""
    def role_checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles and user.role != UserRole.ADMIN:
            raise AuthorizationError(f"Access restricted to {', '.join(r.value for r in allowed_roles)}. Current user role: {user.role.value}")
        return user
    return role_checker


def require_brand_scope(user: User = Depends(get_current_user)) -> User:
    """Enforces that the user belongs to an active Brand Organization or is a Platform Admin."""
    if user.role == UserRole.ADMIN:
        return user
    if user.role not in [UserRole.BRAND_OWNER, UserRole.BRAND_MANAGER, UserRole.BRAND_STAFF]:
        raise AuthorizationError("Access denied: Brand Organization membership required.")
    if not user.brand_profile:
        raise AuthorizationError("Access denied: No brand organization linked to this account.")
    return user
