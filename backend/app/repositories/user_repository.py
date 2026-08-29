from typing import Optional
from sqlalchemy.orm import Session
from backend.app.models.user import User, UserRole, AuditLog
from backend.app.core.security import get_password_hash


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: int) -> Optional[User]:
        return self.db.query(User).filter(User.id == user_id).first()

    def get_by_email(self, email: str) -> Optional[User]:
        return self.db.query(User).filter(User.email == email.lower()).first()

    def create(
        self,
        email: str,
        password: str,
        full_name: str,
        role: UserRole = UserRole.CONSUMER,
        phone: Optional[str] = None,
        preferred_language: str = "en"
    ) -> User:
        user = User(
            email=email.lower(),
            hashed_password=get_password_hash(password),
            full_name=full_name,
            role=role,
            phone=phone,
            preferred_language=preferred_language,
            is_active=True,
            is_verified=True
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update(self, user: User) -> User:
        self.db.commit()
        self.db.refresh(user)
        return user

    def delete(self, user: User) -> None:
        self.db.delete(user)
        self.db.commit()

    def log_audit(
        self,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        details: Optional[str] = None,
    ):
        """Persist a security-relevant audit event.

        Callers must never pass sensitive values in `details` — passwords,
        tokens, OTPs, MFA secrets, decrypted body measurements, etc. This
        is the contract audited in tests.
        """
        log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            ip_address=ip_address,
            details_json=details,
        )
        self.db.add(log)
        self.db.commit()
