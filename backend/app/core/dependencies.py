from typing import Optional
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.security import decode_token
from backend.app.models.user import User, UserRole
from backend.app.repositories.user_repository import UserRepository
from backend.app.core.exceptions import AuthenticationError, AuthorizationError

security = HTTPBearer(auto_error=False)


def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[User]:
    if not credentials:
        return None
    try:
        payload = decode_token(credentials.credentials)
        user_id = int(payload.get("sub"))
        repo = UserRepository(db)
        user = repo.get_by_id(user_id)
        return user
    except Exception:
        return None


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    if not credentials:
        raise AuthenticationError("Authorization bearer token required.")
    try:
        payload = decode_token(credentials.credentials)
        user_id = int(payload.get("sub"))
        repo = UserRepository(db)
        user = repo.get_by_id(user_id)
        if not user or not user.is_active:
            raise AuthenticationError("User not found or account deactivated.")
        return user
    except Exception as exc:
        raise AuthenticationError(f"Authentication failed: {str(exc)}")


def require_role(allowed_roles: list[UserRole]):
    def role_checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles and user.role != UserRole.ADMIN:
            raise AuthorizationError(f"Access restricted to {', '.join(r.value for r in allowed_roles)}.")
        return user
    return role_checker
