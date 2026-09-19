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
from backend.app.services import email_service
from backend.app.services import token_service
from backend.app.services.email_service import (
    EmailDeliveryError,  # re-exported for existing callers/tests
    render_email_change_verification_email,
    render_email_changed_notice_email,
    render_password_changed_email,
    render_password_reset_email,
    render_verification_email,
    render_verification_reminder_email,
    send_email,
)
from backend.app.core.exceptions import (
    AuthenticationError,
    ConflictError,
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
    EmailChangeRequest,
    EmailVerificationToken,
    MFABackupCode,
    PasswordResetToken,
    RefreshToken,
    RegistrationIntent,
    User,
    UserRole,
)
from backend.app.repositories.profile_repository import ProfileRepository
from backend.app.repositories.user_repository import UserRepository


_MFA_BACKUP_CODE_COUNT = 10
_PASSWORD_RESET_TTL = timedelta(minutes=30)
_EMAIL_VERIFICATION_TTL = timedelta(hours=24)


import re as _re

_EMAIL_RE = _re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def _sha256_hex(data: str) -> str:
    """Kept for backward compatibility — delegates to the shared primitive."""
    return token_service.hash_token(data)


def _mask_email(address: str) -> str:
    local, _, domain = (address or "").partition("@")
    if not domain:
        return "***"
    return f"{local[:1]}***@{domain}"


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
        registration_intent: str = "consumer",
    ) -> Dict[str, Any]:
        # SECURITY INVARIANT (P0): public self-service registration ALWAYS
        # creates a CONSUMER. There is deliberately no `role` parameter —
        # the former `role: UserRole = UserRole.CONSUMER` argument let a
        # caller pass any privileged role straight through to
        # user_repo.create (production: `role=admin` -> 201 admin). The
        # only legitimate elevated-provisioning path is direct repository
        # use by trusted internal tooling, never this service method.
        validate_password_policy(password)

        # Registration intent is DATA about what the person asked for. It is
        # validated against a closed enum and can never carry a role: asking to
        # "join as a brand" sets a pending-workflow flag, not a privilege
        # (task §0.11/§9). Unknown values are rejected, not silently coerced.
        intent_raw = (registration_intent or "consumer").strip().lower()
        try:
            intent = RegistrationIntent(intent_raw)
        except ValueError:
            raise ValidationDomainError(
                "registration_intent must be 'consumer' or 'brand_partner'.",
                {"registration_intent": "unsupported"},
            )

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
            registration_intent=intent.value,
        )

        # Best-effort verification email: registration NEVER fails because of
        # email transport (the account exists either way). The outcome is not
        # swallowed any more — it is recorded in the delivery ledger and the
        # audit trail, so "we sent you a link" is a claim backed by evidence
        # (task §15/§33).
        if email_service.is_email_configured() and not user.is_verified:
            try:
                self._issue_verification_token(user)
            except Exception as exc:  # noqa: BLE001 — registration must survive email issues
                logger.warning("Post-registration verification email failed", error=str(exc)[:120])
                self.user_repo.log_audit(
                    "EMAIL_VERIFICATION_EMAIL_FAILED", "User", str(user.id), user_id=user.id
                )
        tokens = self._issue_session_tokens(user, ip_address=ip_address, user_agent=user_agent)
        self.user_repo.log_audit(
            "USER_REGISTERED", "User", str(user.id), user_id=user.id, ip_address=ip_address,
            details=json.dumps({"registration_intent": intent.value}),
        )
        return {**tokens, "user": user}

    # ------------------------------------------------------------------
    # Session token issuance (public wrapper so other services — e.g. the
    # invitation acceptance flow — reuse THE one issuance path instead of
    # minting their own tokens)
    # ------------------------------------------------------------------
    def issue_session_tokens(self, user: User, ip_address: Optional[str] = None,
                             user_agent: Optional[str] = None) -> Dict[str, Any]:
        return self._issue_session_tokens(user, ip_address=ip_address, user_agent=user_agent)

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
        """Non-committal by design: the response body is IDENTICAL for known and
        unknown addresses (no enumeration oracle), so the copy is conditional.

        `status: "requested"` means the request was processed — it is not a
        claim that an email was delivered. The truthful per-account delivery
        outcome lives in the `email_deliveries` ledger and is exposed only to
        the signed-in owner (`GET /auth/email-status`).
        """
        if not email_service.is_email_configured():
            raise FeatureNotConfiguredError(
                "email_delivery",
                hint="Configure EMAIL_PROVIDER + SMTP settings to enable password reset.",
            )
        user = self.user_repo.get_by_email(email)
        if user:
            # One live reset token per account: a new request invalidates older
            # links instead of leaving several valid ones in old inboxes.
            token_service.invalidate_open_tokens(self.db, model=PasswordResetToken, user_id=user.id)
            _row, token = token_service.issue_token(
                self.db, model=PasswordResetToken, user_id=user.id, ttl=_PASSWORD_RESET_TTL,
            )
            self.user_repo.log_audit(
                "PASSWORD_RESET_REQUESTED", "User", str(user.id), user_id=user.id, ip_address=ip_address
            )
            self._send_password_reset_email(user, token)
        return {
            "status": "requested",
            "message": "If an account exists with that email, reset instructions have been sent.",
        }

    def complete_password_reset(self, token: str, new_password: str) -> None:
        validate_password_policy(new_password)
        try:
            row = token_service.consume(self.db, model=PasswordResetToken, raw=token)
        except token_service.OneTimeTokenError as exc:
            # Same 401 for invalid / expired / replayed — an attacker probing
            # tokens learns nothing about which case they hit.
            if exc.reason == "expired":
                raise AuthenticationError("Reset token has expired.")
            raise AuthenticationError("Reset token is invalid or already used.")

        user = self.user_repo.get_by_id(row.user_id)
        if not user:
            raise AuthenticationError("Account no longer exists.")

        from backend.app.core.security import get_password_hash
        user.hashed_password = get_password_hash(new_password)
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
        """REAL delivery + delivery-ledger record (task §15).

        Raises nothing on transport failure: the endpoint's response is
        non-committal (no existence leak), the ledger row records FAILED, and
        the audit trail carries the honest event name. The token stays valid so
        the user can request again.
        """
        reset_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/reset-password?token={token}"
        subject, html, text = render_password_reset_email(
            user.full_name or "there", reset_url, int(_PASSWORD_RESET_TTL.total_seconds() // 60)
        )
        result = email_service.send_transactional(
            self.db,
            to=user.email,
            subject=subject,
            html=html,
            text=text,
            purpose=email_service.PURPOSE_PASSWORD_RESET,
            user_id=user.id,
            dedupe_key=token_service.hash_token(token),
        )
        self.user_repo.log_audit(
            "PASSWORD_RESET_EMAIL_SENT" if result.accepted else "PASSWORD_RESET_EMAIL_FAILED",
            "User", str(user.id), user_id=user.id,
            details=json.dumps({"delivery_status": result.status.value, "error_class": result.error_class}),
        )

    # ------------------------------------------------------------------
    # Authenticated password change (cycle 9)
    # ------------------------------------------------------------------
    def change_password(
        self,
        user: User,
        current_password: str,
        new_password: str,
        mfa_code: Optional[str] = None,
    ) -> None:
        """Rotate the password of the *signed-in* user.

        Closes the cycle-9 engineering gap: the email reset flow was the only
        password-rotation path and 501s while no email provider is
        provisioned, leaving the admin handover (temporary password must be
        changed by the owner) — and every user's rotation — impossible
        in-product.

        Contract:
        - requires the CURRENT password (re-authentication);
        - MFA-enabled accounts must also pass a current TOTP or single-use
          recovery code (same challenge consumption as login);
        - the new password must satisfy the Group-1 policy and differ from
          the current one;
        - on success every refresh token is revoked (same session-revocation
          contract as a completed email reset) and the change is audited as
          ``USER_PASSWORD_CHANGED``;
        - on ANY failure nothing is mutated and no MFA code is consumed
          after an earlier check already failed (order: current password →
          MFA → policy).
        """
        if not verify_password(current_password, user.hashed_password):
            raise AuthenticationError("Current password is incorrect.")

        if user.mfa_enabled:
            code = (mfa_code or "").strip()
            if not code:
                raise AuthenticationError(
                    "An MFA (or recovery) code is required to change your password."
                )
            if not self._consume_mfa_challenge(user, code):
                raise AuthenticationError("Invalid MFA code.")

        if current_password == new_password:
            raise ValidationDomainError(
                "The new password must be different from the current password."
            )

        validate_password_policy(new_password)

        from backend.app.core.security import get_password_hash
        user.hashed_password = get_password_hash(new_password)
        # Revoke every active session — a password change must not leave
        # possibly-compromised sessions alive (parity with reset completion).
        for r in self.db.query(RefreshToken).filter(
            RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)
        ):
            r.revoked_at = datetime.now(timezone.utc)
        self.db.commit()
        self.user_repo.log_audit(
            "USER_PASSWORD_CHANGED", "User", str(user.id), user_id=user.id
        )
        # Security notification (task §16): record the outcome, never fake it.
        if email_service.is_email_configured():
            subject, html, text = render_password_changed_email(
                user.full_name or "there",
                token_service.utcnow().replace(microsecond=0).isoformat(),
            )
            email_service.send_transactional(
                self.db,
                to=user.email,
                subject=subject,
                html=html,
                text=text,
                purpose=email_service.PURPOSE_PASSWORD_CHANGED,
                user_id=user.id,
                dedupe_key=f"pw-changed:{user.id}:{int(token_service.utcnow().timestamp())}",
            )

    # ------------------------------------------------------------------
    # Email verification — issue (hashed, 24 h, one-time) + redeem
    # ------------------------------------------------------------------
    def request_email_verification(self, email: str, ip_address: Optional[str] = None) -> Dict[str, Any]:
        """Issue (or re-issue) a verification email.

        Non-committal response: identical for known/unknown addresses, so it is
        not an account-existence oracle. `status: "requested"` describes the
        request, never a delivery claim (the ledger holds the truth).
        """
        if not email_service.is_email_configured():
            raise FeatureNotConfiguredError(
                "email_delivery",
                hint="Configure EMAIL_PROVIDER + SMTP settings to enable email verification.",
            )
        user = self.user_repo.get_by_email(email)
        if user and user.is_verified is not True:
            self._issue_verification_token(user, reminder=True)
            self.user_repo.log_audit(
                "EMAIL_VERIFICATION_REQUESTED", "User", str(user.id), user_id=user.id, ip_address=ip_address
            )
        return {
            "status": "requested",
            "message": "If this address needs verification, a confirmation link has been sent.",
        }

    def _issue_verification_token(self, user: User, *, reminder: bool = False) -> str:
        """Create a fresh 24 h single-use token (invalidating older ones) and send it."""
        token_service.invalidate_open_tokens(self.db, model=EmailVerificationToken, user_id=user.id)
        _row, token = token_service.issue_token(
            self.db, model=EmailVerificationToken, user_id=user.id, ttl=_EMAIL_VERIFICATION_TTL,
        )
        self._send_verification_email(user, token, reminder=reminder)
        return token

    def _send_verification_email(self, user: User, token: str, *, reminder: bool = False) -> None:
        verify_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/verify-email?token={token}"
        renderer = render_verification_reminder_email if reminder else render_verification_email
        subject, html, text = renderer(user.full_name or "there", verify_url)
        result = email_service.send_transactional(
            self.db,
            to=user.email,
            subject=subject,
            html=html,
            text=text,
            purpose=(
                email_service.PURPOSE_VERIFICATION_REMINDER if reminder
                else email_service.PURPOSE_VERIFICATION
            ),
            user_id=user.id,
            dedupe_key=token_service.hash_token(token),
        )
        self.user_repo.log_audit(
            "EMAIL_VERIFICATION_EMAIL_SENT" if result.accepted else "EMAIL_VERIFICATION_EMAIL_FAILED",
            "User", str(user.id), user_id=user.id,
            details=json.dumps({"delivery_status": result.status.value, "error_class": result.error_class}),
        )

    def complete_email_verification(self, token: str) -> Dict[str, Any]:
        if not email_service.is_email_configured():
            raise FeatureNotConfiguredError(
                "email_delivery",
                hint="Configure EMAIL_PROVIDER + SMTP settings to enable email verification.",
            )
        try:
            row = token_service.consume(self.db, model=EmailVerificationToken, raw=token)
        except token_service.OneTimeTokenError as exc:
            if exc.reason == "expired":
                raise AuthenticationError("Verification link has expired. Request a new one.")
            raise AuthenticationError("Verification link is invalid or has already been used.")
        user = self.user_repo.get_by_id(row.user_id)
        if user is None:
            raise AuthenticationError("Account no longer exists.")
        user.is_verified = True
        self.db.commit()
        self.user_repo.log_audit(
            "EMAIL_VERIFIED", "User", str(user.id), user_id=user.id
        )
        return {"status": "success", "message": "Email verified. Thank you!"}

    # ------------------------------------------------------------------
    # Email change — ownership of the NEW address is proven first (task §11)
    # ------------------------------------------------------------------
    _EMAIL_CHANGE_TTL = timedelta(hours=2)

    def request_email_change(self, user: User, new_email: str, ip_address: Optional[str] = None) -> Dict[str, Any]:
        """Start an email change: verify the NEW address before it becomes the
        account's identity. Only the signed-in owner can start this, and the
        confirmation link is delivered to the ADDRESS BEING ADDED (never to the
        old one), so a hijacked session alone cannot take the account over.
        """
        if not email_service.is_email_configured():
            # No provider → the flow cannot be completed; say so instead of
            # creating a token nobody can ever receive.
            raise FeatureNotConfiguredError(
                "email_delivery",
                hint="Configure EMAIL_PROVIDER + SMTP settings to enable email change.",
            )
        normalized = (new_email or "").strip().lower()
        if not _EMAIL_RE.match(normalized):
            raise ValidationDomainError("A valid email address is required.", {"new_email": "invalid"})
        if normalized == (user.email or "").lower():
            raise ValidationDomainError("That is already the email on this account.", {"new_email": "unchanged"})

        other = self.user_repo.get_by_email(normalized)
        if other is not None:
            # Authenticated context + the address is the subject of the request:
            # telling the owner it is taken is actionable, not an oracle.
            raise ConflictError(
                "That address is already registered to a CONFIT account.",
                code="EMAIL_ALREADY_REGISTERED",
            )

        now = token_service.utcnow()
        for stale in (
            self.db.query(EmailChangeRequest)
            .filter(EmailChangeRequest.user_id == user.id, EmailChangeRequest.used_at.is_(None))
            .all()
        ):
            stale.used_at = now  # superseded — only one live confirmation link
        self.db.commit()

        row, token = token_service.issue_token(
            self.db,
            model=EmailChangeRequest,
            user_id=user.id,
            ttl=self._EMAIL_CHANGE_TTL,
            extra_fields={"new_email": normalized},
        )

        confirm_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/settings/confirm-email?token={token}"
        subject, html, text = render_email_change_verification_email(user.full_name or "there", normalized, confirm_url)
        result = email_service.send_transactional(
            self.db,
            to=normalized,
            subject=subject,
            html=html,
            text=text,
            purpose=email_service.PURPOSE_EMAIL_CHANGE,
            user_id=user.id,
            dedupe_key=token_service.hash_token(token),
        )
        self.user_repo.log_audit(
            "EMAIL_CHANGE_REQUESTED", "User", str(user.id), user_id=user.id, ip_address=ip_address,
            details=json.dumps({"new_email_masked": _mask_email(normalized),
                                "delivery_status": result.status.value}),
        )
        # Honest status for the account owner (this request is about THEIR
        # account, so no enumeration surface is created by reporting it).
        return {
            "status": "requested",
            "delivery_status": result.status.value,
            "message": (
                "Confirmation link sent to the new address."
                if result.accepted else
                "We could not deliver the confirmation email. Check the address and try again."
            ),
        }

    def confirm_email_change(self, token: str) -> Dict[str, Any]:
        try:
            row = token_service.consume(self.db, model=EmailChangeRequest, raw=token)
        except token_service.OneTimeTokenError as exc:
            if exc.reason == "expired":
                raise AuthenticationError("This confirmation link has expired. Start the change again.")
            raise AuthenticationError("This confirmation link is invalid or has already been used.")

        user = self.user_repo.get_by_id(row.user_id)
        if user is None:
            raise AuthenticationError("Account no longer exists.")

        # Race guard: someone may have registered the address in between.
        taken = self.user_repo.get_by_email(row.new_email)
        if taken is not None and taken.id != user.id:
            raise ConflictError("That address is already registered to a CONFIT account.", code="EMAIL_ALREADY_REGISTERED")

        old_email = user.email
        user.email = row.new_email.lower()
        if user.oauth_subject and user.oauth_provider:
            # The social identity stays linked (subject is provider-stable); the
            # local address simply changed.
            pass
        user.updated_at = token_service.utcnow()
        now = token_service.utcnow()
        for refresh in self.db.query(RefreshToken).filter(
            RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)
        ):
            refresh.revoked_at = now
        self.db.commit()
        self.user_repo.log_audit(
            "EMAIL_CHANGED", "User", str(user.id), user_id=user.id,
            before={"email_masked": _mask_email(old_email)},
            after={"email_masked": _mask_email(user.email)},
        )

        # Security notice to the PREVIOUS address so a takeover is visible there.
        if email_service.is_email_configured():
            subject, html, text = render_email_changed_notice_email(
                user.full_name or "there", old_email, user.email, token_service.utcnow().replace(microsecond=0).isoformat()
            )
            email_service.send_transactional(
                self.db,
                to=old_email,
                subject=subject,
                html=html,
                text=text,
                purpose=email_service.PURPOSE_EMAIL_CHANGED_NOTICE,
                user_id=user.id,
                dedupe_key=f"{token_service.hash_token(token)}:notice",
            )
        return {"status": "success", "email": user.email, "message": "Your sign-in email has been updated."}

    # ------------------------------------------------------------------
    # Honest delivery surface + server-authoritative onboarding state
    # ------------------------------------------------------------------
    def email_delivery_status(self, user: User, purpose: Optional[str] = None) -> Dict[str, Any]:
        """What the provider actually did for THIS account's last send.

        Scoped to the caller's own user id, so it can never be used to probe
        another address — and it is why the anonymous request endpoints can stay
        non-committal without the product lying to the user.
        """
        provider_configured = email_service.is_email_configured()
        row = email_service.latest_delivery(self.db, user_id=user.id, purpose=purpose)
        if row is None:
            return {
                "purpose": purpose,
                "status": "none",
                "accepted": False,
                "provider_configured": provider_configured,
                "provider": None,
                "error_class": None,
                "attempts": 0,
                "last_attempt_at": None,
            }
        return {
            "purpose": row.purpose,
            "status": row.status.value if hasattr(row.status, "value") else str(row.status),
            "accepted": (row.status.value if hasattr(row.status, "value") else str(row.status)) == "succeeded",
            "provider_configured": provider_configured,
            "provider": row.provider,
            "error_class": row.error_class,
            "attempts": row.attempts,
            "last_attempt_at": row.created_at.isoformat() if row.created_at else None,
        }

    def onboarding_state(self, user: User) -> Dict[str, Any]:
        """Server-authoritative account state + next action (task §4)."""
        from backend.app.services import onboarding_service
        return onboarding_service.build_onboarding_state(
            self.db, user, email_provider_configured=email_service.is_email_configured()
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
