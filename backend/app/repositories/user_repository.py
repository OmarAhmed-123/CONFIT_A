from typing import Optional
from sqlalchemy.orm import Session
from backend.app.models.user import User, UserRole, AuditLog
from backend.app.core.security import get_password_hash
from backend.app.core.config import settings


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
            # CYCLE 4: with a real email provider configured, verification
            # must be EARNED via the emailed one-time link (starts False).
            # Without a provider there is no honest way to verify — legacy
            # behavior keeps True so the flag never lies about a check that
            # cannot exist (the 501 endpoints make the gap explicit).
            is_verified=not bool(settings.EMAIL_PROVIDER)
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
        before: Optional[dict] = None,
        after: Optional[dict] = None,
        request_id: Optional[str] = None,
    ):
        """Persist a security-relevant audit event.

        Callers must never pass sensitive values in `details`/`before`/
        `after` — passwords, tokens, OTPs, MFA secrets, decrypted body
        measurements, etc.

        That instruction used to be the *only* control, which meant the
        contract depended on all 30 call sites remembering a comment (G-06).
        It is now enforced here, on the single write path every caller
        funnels through: secret-bearing keys are replaced with
        ``[REDACTED:key=...]`` and secrets smuggled inside free-form strings
        (JWTs, bearer tokens, PEM blocks, Luhn-valid card numbers, Postgres
        DSNs) are masked before the row is built. Returns the number of
        redactions applied so callers and tests can assert on it.
        """
        import json as _json

        from backend.app.core.audit_redaction import scrub, scrub_text

        safe_before, _hits = scrub(before) if before is not None else (None, 0)
        safe_after, _h2 = scrub(after) if after is not None else (None, 0)
        safe_details, _h3 = scrub_text(details)

        log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            ip_address=ip_address,
            details_json=safe_details,
            before_json=_json.dumps(safe_before, default=str) if safe_before else None,
            after_json=_json.dumps(safe_after, default=str) if safe_after else None,
            request_id=request_id,
        )
        self.db.add(log)
        self.db.commit()
        return _hits + _h2 + _h3
