import pyotp
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.app.models.user import User, UserRole, BrandProfile
from backend.app.repositories.user_repository import UserRepository
from backend.app.repositories.profile_repository import ProfileRepository
from backend.app.core.security import verify_password, create_access_token, create_refresh_token, decode_token
from backend.app.core.exceptions import AuthenticationError, ValidationDomainError


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)
        self.profile_repo = ProfileRepository(db)

    def register(
        self,
        email: str,
        password: str,
        full_name: str,
        role: UserRole = UserRole.CONSUMER,
        phone: Optional[str] = None,
        preferred_language: str = "en"
    ) -> Dict[str, Any]:
        existing = self.user_repo.get_by_email(email)
        if existing:
            raise ValidationDomainError("An account with this email already exists.")

        user = self.user_repo.create(
            email=email,
            password=password,
            full_name=full_name,
            role=role,
            phone=phone,
            preferred_language=preferred_language
        )

        # If user registered as brand manager, create a BrandProfile stub
        if role == UserRole.BRAND_MANAGER:
            brand_name = full_name if "Brand" in full_name else f"{full_name} Atelier"
            slug = brand_name.lower().replace(" ", "-")
            bp = BrandProfile(
                user_id=user.id,
                brand_name=brand_name,
                slug=slug,
                description="Contemporary fashion house on CONFIT.",
                commission_rate=15,
                return_rate_benchmark=28,
                current_return_rate=11
            )
            self.db.add(bp)
            self.db.commit()

        # Generate tokens
        token_data = {"sub": str(user.id), "email": user.email, "role": user.role.value}
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)

        self.user_repo.log_audit("USER_REGISTERED", "User", str(user.id), user_id=user.id)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": user
        }

    def login(self, email: str, password: str, mfa_code: Optional[str] = None) -> Dict[str, Any]:
        user = self.user_repo.get_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            raise AuthenticationError("Invalid email or password.")

        if not user.is_active:
            raise AuthenticationError("Account has been deactivated.")

        # MFA check if enabled
        if user.mfa_enabled:
            if not mfa_code:
                raise AuthenticationError("MFA code required for this account.")
            totp = pyotp.TOTP(user.mfa_secret)
            if not totp.verify(mfa_code):
                raise AuthenticationError("Invalid MFA verification code.")

        token_data = {"sub": str(user.id), "email": user.email, "role": user.role.value}
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)

        self.user_repo.log_audit("USER_LOGIN_SUCCESS", "User", str(user.id), user_id=user.id)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": user
        }

    def social_login(self, provider: str, access_token: str, email: str, full_name: str) -> Dict[str, Any]:
        user = self.user_repo.get_by_email(email)
        if not user:
            # Create user on first social login
            user = self.user_repo.create(
                email=email,
                password=f"SocialAuth_{provider}_{email}",
                full_name=full_name,
                role=UserRole.CONSUMER
            )
            self.user_repo.log_audit("SOCIAL_REGISTER", "User", str(user.id), user_id=user.id, details=provider)
        else:
            self.user_repo.log_audit("SOCIAL_LOGIN", "User", str(user.id), user_id=user.id, details=provider)

        token_data = {"sub": str(user.id), "email": user.email, "role": user.role.value}
        return {
            "access_token": create_access_token(token_data),
            "refresh_token": create_refresh_token(token_data),
            "token_type": "bearer",
            "user": user
        }

    def refresh(self, refresh_token: str) -> Dict[str, Any]:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise AuthenticationError("Invalid refresh token type.")

        user_id = int(payload.get("sub"))
        user = self.user_repo.get_by_id(user_id)
        if not user or not user.is_active:
            raise AuthenticationError("User session no longer valid.")

        token_data = {"sub": str(user.id), "email": user.email, "role": user.role.value}
        return {
            "access_token": create_access_token(token_data),
            "refresh_token": create_refresh_token(token_data),
            "token_type": "bearer",
            "user": user
        }

    def setup_mfa(self, user: User) -> Dict[str, Any]:
        secret = pyotp.random_base32()
        user.mfa_secret = secret
        self.db.commit()
        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(name=user.email, issuer_name="CONFIT AI")
        return {
            "secret": secret,
            "qr_uri": provisioning_uri,
            "backup_codes": ["CONFIT-9281", "CONFIT-4482", "CONFIT-7721", "CONFIT-3319"]
        }

    def verify_mfa_setup(self, user: User, code: str) -> bool:
        if not user.mfa_secret:
            raise ValidationDomainError("MFA setup has not been initialized.")
        totp = pyotp.TOTP(user.mfa_secret)
        if totp.verify(code):
            user.mfa_enabled = True
            self.db.commit()
            self.user_repo.log_audit("MFA_ENABLED", "User", str(user.id), user_id=user.id)
            return True
        raise AuthenticationError("Invalid MFA verification code.")

    def export_gdpr_data(self, user: User) -> Dict[str, Any]:
        usp = self.profile_repo.get_by_user_id(user.id)
        usp_data = None
        if usp:
            body = self.profile_repo.get_decrypted_body_data(usp)
            usp_data = {
                "style_archetypes": usp.style_archetypes,
                "preferred_colors": usp.preferred_colors,
                "body_attributes": body,
                "budget_range": f"${usp.budget_monthly_min} - ${usp.budget_monthly_max}"
            }

        self.user_repo.log_audit("GDPR_DATA_EXPORT", "User", str(user.id), user_id=user.id)

        return {
            "user": user,
            "profile": usp_data,
            "wardrobe_items_count": len(user.wardrobe_items),
            "orders_count": len(user.orders),
            "tryon_sessions_count": len(user.tryon_sessions),
            "exported_at": user.created_at,
            "data_retention_policy": "GDPR & CCPA Compliant. Sensitive body measurements encrypted at rest. Photos purged after 24h unless explicit consent is given."
        }

    def delete_account(self, user: User) -> None:
        self.user_repo.log_audit("ACCOUNT_DELETED", "User", str(user.id), user_id=user.id)
        self.user_repo.delete(user)
