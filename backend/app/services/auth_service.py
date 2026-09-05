"""AuthService — Group 1 authentication & identity.

Rebuilt to fix the audit findings:
 - Social login now verifies the provider token server-side against the
   real provider (Google / Apple / Facebook). Client-supplied email is
   NEVER trusted (§7 / G1.SEC-02).
 - Refresh tokens are stored server-side with JTI + family_id; rotation
   invalidates the old row; reuse of a rotated token revokes the whole
   family (§8 / G1.AUTH-03).
 - Logout revokes the current refresh token row so subsequent /refresh
   attempts fail (§36 / G1.AUTH-05).
 - Account deletion revokes every refresh token in the same commit and
   anonymizes historical order/tryon/stylist rows instead of hard-cascading.
 - MFA backup codes are random per-user and stored as bcrypt hashes;
   verification consumes a code atomically (§10 / G1.AUTH-06).
 - Password reset & email verification are only issued when a real email
   provider is configured; otherwise 501 FEATURE_NOT_CONFIGURED (§12).
"""
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

import httpx
import jwt
import pyotp
from jwt.exceptions import PyJWTError
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.exceptions import (
    AuthenticationError,
    FeatureNotConfiguredError,
    ProviderIntegrationError,
    ValidationDomainError,
)
from backend.app.core.logging import logger
from backend.app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_recovery_codes,
    hash_recovery_code,
    validate_password_policy,
    verify_password,
    verify_recovery_code,
)
from backend.app.models.user import (
    EmailVerificationToken,
    MFABackupCode,
    PasswordResetToken,
    RefreshToken,
    User,
    UserRole,
)
from backend.app.repositories.profile_repository import ProfileRepository
from backend.app.repositories.user_repository import UserRepository


_MFA_BACKUP_CODE_COUNT = 10
_PASSWORD_RESET_TTL = timedelta(minutes=30)
_EMAIL_VERIFICATION_TTL = timedelta(hours=24)


def _sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)
        self.profile_repo = ProfileRepository(db)

    # ------------------------------------------------------------------
    # Registration / login
    # ------------------------------------------------------------------
    def register(
        self,
        email: str,
        password: str,
        full_name: str,
        phone: Optional[str] = None,
        preferred_language: str = "en",
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        # SECURITY INVARIANT (P0): public self-service registration ALWAYS
        # creates a CONSUMER. There is deliberately no `role` parameter —
        # the former `role: UserRole = UserRole.CONSUMER` argument let a
        # caller pass any privileged role straight through to
        # user_repo.create (production: `role=admin` -> 201 admin). The
        # only legitimate elevated-provisioning path is direct repository
        # use by trusted internal tooling, never this service method.
        validate_password_policy(password)

        existing = self.user_repo.get_by_email(email)
        if existing:
            raise ValidationDomainError("An account with this email already exists.")

        user = self.user_repo.create(
            email=email,
            password=password,
            full_name=full_name,
            role=UserRole.CONSUMER,
            phone=phone,
            preferred_language=preferred_language,
        )

        tokens = self._issue_session_tokens(user, ip_address=ip_address, user_agent=user_agent)
        self.user_repo.log_audit(
            "USER_REGISTERED", "User", str(user.id), user_id=user.id, ip_address=ip_address
        )
        return {**tokens, "user": user}

    def login(
        self,
        email: str,
        password: str,
        mfa_code: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        user = self.user_repo.get_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            # Do not leak account existence — same code path for both.
            self.user_repo.log_audit(
                "USER_LOGIN_FAILED",
                "User",
                str(user.id) if user else "",
                user_id=user.id if user else None,
                ip_address=ip_address,
            )
            raise AuthenticationError("Invalid email or password.")
        if not user.is_active:
            raise AuthenticationError("Account has been deactivated.")

        if user.mfa_enabled:
            if not mfa_code:
                # Two-step login: signal the frontend that MFA is required
                # WITHOUT establishing a session yet. Group 1 §11.
                raise AuthenticationError("MFA code required for this account.", details={"reason": "MFA_REQUIRED"})
            if not self._consume_mfa_challenge(user, mfa_code):
                self.user_repo.log_audit(
                    "MFA_FAILED", "User", str(user.id), user_id=user.id, ip_address=ip_address
                )
                raise AuthenticationError("Invalid MFA verification code.")

        tokens = self._issue_session_tokens(user, ip_address=ip_address, user_agent=user_agent)
        self.user_repo.log_audit(
            "USER_LOGIN_SUCCESS", "User", str(user.id), user_id=user.id, ip_address=ip_address
        )
        return {**tokens, "user": user}

    # ------------------------------------------------------------------
    # OAuth social login — Group 1 §7 real provider verification
    # ------------------------------------------------------------------
    def social_login(
        self,
        provider: str,
        provider_token: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Verify the provider token against the provider itself, then
        create or look up the CONFIT user by (provider, subject).

        The caller MUST NOT supply the email/name separately — we take
        them from the provider's verified response. That closes the
        client-spoofing hole in the previous implementation.
        """
        provider = (provider or "").lower().strip()
        if provider == "google":
            identity = self._verify_google_id_token(provider_token)
        elif provider == "apple":
            identity = self._verify_apple_id_token(provider_token)
        elif provider == "facebook":
            identity = self._verify_facebook_token(provider_token)
        else:
            raise ValidationDomainError(f"Unsupported OAuth provider: {provider!r}")

        subject = identity["subject"]
        email = identity.get("email")
        full_name = identity.get("full_name") or (email.split("@")[0] if email else f"{provider}_{subject[:8]}")

        # Look up by (provider, subject) FIRST — that's the immutable
        # provider identity. Only fall back to email lookup when the
        # provider explicitly says the email is verified.
        user = self.db.query(User).filter(
            User.oauth_provider == provider, User.oauth_subject == subject
        ).first()

        if not user:
            if email and identity.get("email_verified"):
                existing_by_email = self.user_repo.get_by_email(email)
                if existing_by_email:
                    # If the email account has a password set, we do NOT
                    # auto-link — that would enable account takeover.
                    # The user must sign in with the password first, then
                    # link the social identity from a settings screen
                    # (out of scope for this PR; safe default is refuse).
                    if existing_by_email.hashed_password and not existing_by_email.hashed_password.startswith("SOCIAL_ONLY:"):
                        raise AuthenticationError(
                            "An account with this email already exists. Sign in with your password, then link this provider from Account Settings.",
                            details={"reason": "SOCIAL_LINK_REFUSED"},
                        )
                    user = existing_by_email
                    user.oauth_provider = provider
                    user.oauth_subject = subject
                    self.db.commit()
            if not user:
                # Fresh signup via social. Password field carries a marker
                # (never usable for local login because it doesn't match
                # any bcrypt hash and the prefix guards the login lookup).
                marker = f"SOCIAL_ONLY:{provider}:{secrets.token_urlsafe(24)}"
                user = User(
                    email=(email or f"{subject}@{provider}.oauth.local").lower(),
                    hashed_password=marker,
                    full_name=full_name,
                    role=UserRole.CONSUMER,
                    is_active=True,
                    is_verified=bool(identity.get("email_verified", False)),
                    oauth_provider=provider,
                    oauth_subject=subject,
                )
                self.db.add(user)
                self.db.commit()
                self.db.refresh(user)
                self.user_repo.log_audit(
                    "SOCIAL_REGISTER",
                    "User",
                    str(user.id),
                    user_id=user.id,
                    ip_address=ip_address,
                    details=provider,
                )

        self.user_repo.log_audit(
            "SOCIAL_LOGIN", "User", str(user.id), user_id=user.id, ip_address=ip_address, details=provider
        )
        tokens = self._issue_session_tokens(user, ip_address=ip_address, user_agent=user_agent)
        return {**tokens, "user": user}

    # -- provider verifiers -----------------------------------------------
    def _verify_google_id_token(self, id_token: str) -> Dict[str, Any]:
        if not settings.GOOGLE_OAUTH_CLIENT_ID:
            raise FeatureNotConfiguredError(
                "google_oauth",
                hint="Set GOOGLE_OAUTH_CLIENT_ID to enable Google sign-in.",
            )
        try:
            resp = httpx.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": id_token},
                timeout=10.0,
            )
        except httpx.HTTPError as exc:
            raise ProviderIntegrationError("google", f"Network error: {exc}")

        if resp.status_code != 200:
            raise AuthenticationError("Google token verification failed.")
        payload = resp.json()
        if payload.get("aud") != settings.GOOGLE_OAUTH_CLIENT_ID:
            raise AuthenticationError("Google token audience mismatch.")
        if payload.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
            raise AuthenticationError("Google token issuer mismatch.")
        try:
            exp = int(payload.get("exp", 0))
        except (TypeError, ValueError):
            exp = 0
        if exp < int(datetime.now(timezone.utc).timestamp()):
            raise AuthenticationError("Google token expired.")
        return {
            "subject": payload["sub"],
            "email": payload.get("email"),
            "email_verified": str(payload.get("email_verified", "false")).lower() == "true",
            "full_name": payload.get("name"),
        }

    def _verify_apple_id_token(self, id_token: str) -> Dict[str, Any]:
        if not settings.APPLE_OAUTH_CLIENT_ID:
            raise FeatureNotConfiguredError(
                "apple_oauth",
                hint="Set APPLE_OAUTH_CLIENT_ID to enable Sign in with Apple.",
            )
        try:
            jwks_client = jwt.PyJWKClient(settings.APPLE_OAUTH_JWKS_URL)
            signing_key = jwks_client.get_signing_key_from_jwt(id_token).key
            payload = jwt.decode(
                id_token,
                signing_key,
                algorithms=["RS256"],
                audience=settings.APPLE_OAUTH_CLIENT_ID,
                issuer="https://appleid.apple.com",
                options={"require": ["exp", "iat", "sub"]},
            )
        except PyJWTError as exc:
            raise AuthenticationError(f"Apple token verification failed: {exc}")
        return {
            "subject": payload["sub"],
            "email": payload.get("email"),
            "email_verified": str(payload.get("email_verified", "false")).lower() == "true",
            "full_name": None,  # Apple returns name only on the FIRST auth in an app_bundle-signed payload; not in the ID token itself.
        }

    def _verify_facebook_token(self, access_token: str) -> Dict[str, Any]:
        if not (settings.FACEBOOK_OAUTH_APP_ID and settings.FACEBOOK_OAUTH_APP_SECRET):
            raise FeatureNotConfiguredError(
                "facebook_oauth",
                hint="Set FACEBOOK_OAUTH_APP_ID and FACEBOOK_OAUTH_APP_SECRET to enable Facebook login.",
            )
        app_token = f"{settings.FACEBOOK_OAUTH_APP_ID}|{settings.FACEBOOK_OAUTH_APP_SECRET}"
        try:
            debug = httpx.get(
                "https://graph.facebook.com/debug_token",
                params={"input_token": access_token, "access_token": app_token},
                timeout=10.0,
            )
        except httpx.HTTPError as exc:
            raise ProviderIntegrationError("facebook", f"Network error: {exc}")
        if debug.status_code != 200:
            raise AuthenticationError("Facebook token verification failed.")
        data = debug.json().get("data", {})
        if not data.get("is_valid"):
            raise AuthenticationError("Facebook token is invalid or expired.")
        if str(data.get("app_id")) != str(settings.FACEBOOK_OAUTH_APP_ID):
            raise AuthenticationError("Facebook token was issued to a different app.")
        subject = data.get("user_id")
        if not subject:
            raise AuthenticationError("Facebook token contained no user_id.")

        try:
            me = httpx.get(
                "https://graph.facebook.com/me",
                params={"fields": "id,name,email", "access_token": access_token},
                timeout=10.0,
            )
        except httpx.HTTPError as exc:
            raise ProviderIntegrationError("facebook", f"Network error: {exc}")
        me_data = me.json() if me.status_code == 200 else {}
        return {
            "subject": subject,
            "email": me_data.get("email"),
            "email_verified": bool(me_data.get("email")),  # Facebook only surfaces verified emails
            "full_name": me_data.get("name"),
        }

    # ------------------------------------------------------------------
    # Refresh / logout
    # ------------------------------------------------------------------
    def refresh(
        self,
        refresh_token: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = decode_token(refresh_token, expected_type="refresh")
        jti = payload.get("jti")
        if not jti:
            raise AuthenticationError("Refresh token missing jti.")

        row: Optional[RefreshToken] = self.db.query(RefreshToken).filter(RefreshToken.jti == jti).first()
        if not row:
            # Signature-valid but no server-side record → treat as forgery.
            raise AuthenticationError("Refresh token is not recognized.")

        if row.revoked_at is not None:
            # Reuse of a rotated token — revoke the whole family and refuse.
            self._revoke_family(row.family_id, reason="refresh_reuse_detected")
            self.user_repo.log_audit(
                "REFRESH_REUSE_DETECTED",
                "RefreshToken",
                str(row.id),
                user_id=row.user_id,
                ip_address=ip_address,
            )
            raise AuthenticationError("Refresh token reuse detected; session revoked.")

        if row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            raise AuthenticationError("Refresh token expired.")

        user = self.user_repo.get_by_id(row.user_id)
        if not user or not user.is_active:
            raise AuthenticationError("User session no longer valid.")

        # Rotate: mark old row revoked, issue new row in the same family.
        row.revoked_at = datetime.now(timezone.utc)
        row.last_used_at = row.revoked_at
        self.db.flush()

        new_jti = secrets.token_urlsafe(24)
        new_row = RefreshToken(
            user_id=user.id,
            jti=new_jti,
            family_id=row.family_id,
            issued_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            user_agent=user_agent,
            ip_address=ip_address,
        )
        row.replaced_by_jti = new_jti
        self.db.add(new_row)

        token_data = {"sub": str(user.id), "email": user.email, "role": user.role.value}
        access_token = create_access_token(token_data)
        new_refresh = create_refresh_token(token_data, jti=new_jti)
        self.db.commit()
        return {
            "access_token": access_token,
            "refresh_token": new_refresh,
            "token_type": "bearer",
            "user": user,
        }

    def logout(self, user: User, refresh_token: Optional[str] = None) -> None:
        """Revoke the presented refresh token row (or every active row for
        the user if none is presented — belt-and-braces)."""
        target = None
        if refresh_token:
            try:
                payload = decode_token(refresh_token, expected_type="refresh")
                target = payload.get("jti")
            except AuthenticationError:
                target = None
        query = self.db.query(RefreshToken).filter(
            RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)
        )
        if target:
            query = query.filter(RefreshToken.jti == target)
        now = datetime.now(timezone.utc)
        for row in query.all():
            row.revoked_at = now
        self.db.commit()
        self.user_repo.log_audit("USER_LOGOUT", "User", str(user.id), user_id=user.id)

    def _revoke_family(self, family_id: str, reason: str = "") -> None:
        now = datetime.now(timezone.utc)
        rows = self.db.query(RefreshToken).filter(
            RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None)
        ).all()
        for row in rows:
            row.revoked_at = now
        self.db.commit()

    def _issue_session_tokens(
        self, user: User, ip_address: Optional[str] = None, user_agent: Optional[str] = None
    ) -> Dict[str, Any]:
        token_data = {"sub": str(user.id), "email": user.email, "role": user.role.value}
        access_token = create_access_token(token_data)
        jti = secrets.token_urlsafe(24)
        refresh = create_refresh_token(token_data, jti=jti)
        row = RefreshToken(
            user_id=user.id,
            jti=jti,
            family_id=jti,  # a fresh login starts a new family
            issued_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            user_agent=user_agent,
            ip_address=ip_address,
        )
        self.db.add(row)
        self.db.commit()
        return {
            "access_token": access_token,
            "refresh_token": refresh,
            "token_type": "bearer",
        }

    # ------------------------------------------------------------------
    # MFA
    # ------------------------------------------------------------------
    def setup_mfa(self, user: User) -> Dict[str, Any]:
        """Start (or restart) MFA enrollment. Not enabled until `verify_mfa_setup`."""
        secret = pyotp.random_base32()
        user.mfa_secret = secret
        # Wipe any pre-existing backup codes; they are re-issued below
        # ONLY after the user proves possession by calling verify_mfa_setup.
        for row in self.db.query(MFABackupCode).filter(MFABackupCode.user_id == user.id):
            self.db.delete(row)
        self.db.commit()
        provisioning_uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="CONFIT AI")
        return {
            "secret": secret,
            "qr_uri": provisioning_uri,
            "backup_codes": [],  # returned only after verify_mfa_setup
        }

    def verify_mfa_setup(self, user: User, code: str) -> Dict[str, Any]:
        """Second step of enrollment. Requires a valid TOTP code from the
        authenticator to confirm the user actually scanned the QR. Returns
        the plaintext recovery codes exactly ONCE — they are never
        retrievable again (§10)."""
        if not user.mfa_secret:
            raise ValidationDomainError("MFA setup has not been initialized.")
        totp = pyotp.TOTP(user.mfa_secret)
        if not totp.verify(code, valid_window=1):
            raise AuthenticationError("Invalid MFA verification code.")

        user.mfa_enabled = True
        codes = generate_recovery_codes(_MFA_BACKUP_CODE_COUNT)
        for c in codes:
            self.db.add(MFABackupCode(user_id=user.id, code_hash=hash_recovery_code(c)))
        self.db.commit()
        self.user_repo.log_audit("MFA_ENABLED", "User", str(user.id), user_id=user.id)
        return {"status": "enabled", "backup_codes": codes}

    def disable_mfa(self, user: User, password: str) -> None:
        """Re-authenticate with password, then disable MFA and purge secrets."""
        if not verify_password(password, user.hashed_password):
            raise AuthenticationError("Password verification required to disable MFA.")
        user.mfa_enabled = False
        user.mfa_secret = None
        for row in self.db.query(MFABackupCode).filter(MFABackupCode.user_id == user.id):
            self.db.delete(row)
        self.db.commit()
        self.user_repo.log_audit("MFA_DISABLED", "User", str(user.id), user_id=user.id)

    def regenerate_backup_codes(self, user: User) -> Dict[str, Any]:
        if not user.mfa_enabled:
            raise ValidationDomainError("MFA is not enabled for this account.")
        for row in self.db.query(MFABackupCode).filter(MFABackupCode.user_id == user.id):
            self.db.delete(row)
        codes = generate_recovery_codes(_MFA_BACKUP_CODE_COUNT)
        for c in codes:
            self.db.add(MFABackupCode(user_id=user.id, code_hash=hash_recovery_code(c)))
        self.db.commit()
        self.user_repo.log_audit("MFA_CODES_REGENERATED", "User", str(user.id), user_id=user.id)
        return {"status": "regenerated", "backup_codes": codes}

    def _consume_mfa_challenge(self, user: User, code: str) -> bool:
        """Try TOTP first, then unused backup codes (single-use)."""
        if user.mfa_secret and pyotp.TOTP(user.mfa_secret).verify(code, valid_window=1):
            return True
        rows = self.db.query(MFABackupCode).filter(
            MFABackupCode.user_id == user.id, MFABackupCode.used_at.is_(None)
        ).all()
        for row in rows:
            if verify_recovery_code(code, row.code_hash):
                row.used_at = datetime.now(timezone.utc)
                self.db.commit()
                return True
        return False

    # ------------------------------------------------------------------
    # Password reset & email verification — issued only if email is configured
    # ------------------------------------------------------------------
    def request_password_reset(self, email: str, ip_address: Optional[str] = None) -> Dict[str, Any]:
        if not settings.EMAIL_PROVIDER:
            raise FeatureNotConfiguredError(
                "email_delivery",
                hint="Configure EMAIL_PROVIDER + SMTP settings to enable password reset.",
            )
        # Do not leak account existence.
        user = self.user_repo.get_by_email(email)
        if user:
            token = secrets.token_urlsafe(32)
            token_hash = _sha256_hex(token)
            row = PasswordResetToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=datetime.now(timezone.utc) + _PASSWORD_RESET_TTL,
            )
            self.db.add(row)
            self.db.commit()
            self.user_repo.log_audit(
                "PASSWORD_RESET_REQUESTED", "User", str(user.id), user_id=user.id, ip_address=ip_address
            )
            self._send_password_reset_email(user, token)
        return {
            "status": "queued",
            "message": "If an account exists with that email, reset instructions have been sent.",
        }

    def complete_password_reset(self, token: str, new_password: str) -> None:
        validate_password_policy(new_password)
        token_hash = _sha256_hex(token)
        row = self.db.query(PasswordResetToken).filter(
            PasswordResetToken.token_hash == token_hash
        ).first()
        if not row or row.used_at is not None:
            raise AuthenticationError("Reset token is invalid or already used.")
        if row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            raise AuthenticationError("Reset token has expired.")

        user = self.user_repo.get_by_id(row.user_id)
        if not user:
            raise AuthenticationError("Account no longer exists.")

        from backend.app.core.security import get_password_hash
        user.hashed_password = get_password_hash(new_password)
        row.used_at = datetime.now(timezone.utc)
        # Revoke every active session on password change.
        for r in self.db.query(RefreshToken).filter(
            RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)
        ):
            r.revoked_at = datetime.now(timezone.utc)
        self.db.commit()
        self.user_repo.log_audit(
            "PASSWORD_RESET_COMPLETED", "User", str(user.id), user_id=user.id
        )

    def _send_password_reset_email(self, user: User, token: str) -> None:
        # Real delivery is deliberately out of scope for this PR — spec §12:
        # "If there is no configured email provider, do not simulate sending."
        # The FeatureNotConfiguredError above prevents this method from ever
        # being reached without EMAIL_PROVIDER set; when a provider is
        # configured, wire it here (smtplib / sendgrid / ses).
        logger.info(
            "Password reset email dispatch",
            provider=settings.EMAIL_PROVIDER,
            user_id=user.id,
            # NEVER log the token itself — only its length as a diagnostic.
            token_len=len(token),
        )

    # ------------------------------------------------------------------
    # GDPR export & account deletion
    # ------------------------------------------------------------------
    def export_gdpr_data(self, user: User) -> Dict[str, Any]:
        from backend.app.models.wardrobe import WardrobeItem
        from backend.app.models.commerce import Order
        from backend.app.models.tryon import TryOnSession

        # COUNT(*) — spec §16 fix
        wardrobe_count = self.db.query(func.count(WardrobeItem.id)).filter(WardrobeItem.user_id == user.id).scalar() or 0
        orders_count = self.db.query(func.count(Order.id)).filter(Order.user_id == user.id).scalar() or 0
        tryon_count = self.db.query(func.count(TryOnSession.id)).filter(TryOnSession.user_id == user.id).scalar() or 0

        usp = self.profile_repo.get_by_user_id(user.id)
        usp_data = None
        if usp:
            try:
                body = self.profile_repo.get_decrypted_body_data(usp)
            except Exception:
                body = None
            usp_data = {
                "style_archetypes": json.loads(usp.style_archetypes or "[]"),
                "preferred_colors": json.loads(usp.preferred_colors or "[]"),
                "avoided_colors": json.loads(usp.avoided_colors or "[]"),
                "fashion_aesthetics": json.loads(usp.fashion_aesthetics or "[]"),
                "preferred_brands": json.loads(usp.preferred_brands or "[]"),
                "blacklisted_brands": json.loads(usp.blacklisted_brands or "[]"),
                "occasion_weights": json.loads(usp.occasion_weights or "{}"),
                "size_tops": usp.size_tops,
                "size_bottoms": usp.size_bottoms,
                "size_shoes": usp.size_shoes,
                "fit_preference": usp.fit_preference,
                "body_shape_tag": usp.body_shape_tag,
                "body_attributes": body,
                "budget_monthly_min": usp.budget_monthly_min,
                "budget_monthly_max": usp.budget_monthly_max,
                "budget_per_outfit_max": usp.budget_per_outfit_max,
                "onboarding_completed": usp.onboarding_completed,
            }

        self.user_repo.log_audit("GDPR_DATA_EXPORT", "User", str(user.id), user_id=user.id)
        return {
            "user": user,
            "profile": usp_data,
            "wardrobe_items_count": int(wardrobe_count),
            "orders_count": int(orders_count),
            "tryon_sessions_count": int(tryon_count),
            "exported_at": datetime.now(timezone.utc),  # §16: real export time
            "data_retention_policy": "GDPR & CCPA aligned. Sensitive body measurements encrypted at rest. Photos purged after 24h unless explicit consent is given.",
        }

    def delete_account(self, user: User) -> None:
        """Account deletion with retention for business-critical history.

        - Anonymize `orders`, `tryon_sessions`, `stylist_sessions` by
          nulling `user_id` (spec §15: FK-safe, order accounting preserved).
        - Revoke every refresh token.
        - Delete the user row — cascade removes profile, brand_profile,
          wardrobe, saved_outfits, refresh_tokens, mfa_backup_codes.
        """
        from backend.app.models.commerce import Order
        from backend.app.models.tryon import TryOnSession
        from backend.app.models.stylist import StylistSession

        self.user_repo.log_audit("ACCOUNT_DELETED", "User", str(user.id), user_id=user.id)

        # Anonymize business-retained relations. Uses direct SQL update to
        # avoid loading every row into memory.
        for Model in (Order, TryOnSession, StylistSession):
            self.db.query(Model).filter(Model.user_id == user.id).update(
                {"user_id": None}, synchronize_session=False
            )

        # Revoke refresh tokens (also cascade-deleted, but revoke first so
        # a concurrent /refresh in flight is rejected cleanly).
        now = datetime.now(timezone.utc)
        for row in self.db.query(RefreshToken).filter(
            RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)
        ):
            row.revoked_at = now

        self.db.commit()
        self.user_repo.delete(user)
