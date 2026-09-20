import enum
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Index, text
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class UserRole(str, enum.Enum):
    CONSUMER = "consumer"
    BRAND_OWNER = "brand_owner"
    BRAND_MANAGER = "brand_manager"
    BRAND_STAFF = "brand_staff"
    ADMIN = "admin"


class UserRoleType(TypeDecorator):
    impl = String(50)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, UserRole):
            return value.name
        return str(value).upper()

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        val_str = str(value)
        try:
            return UserRole[val_str.upper()]
        except KeyError:
            try:
                return UserRole(val_str.lower())
            except ValueError:
                return UserRole.CONSUMER


class RegistrationIntent(str, enum.Enum):
    """What the registrant asked for. Never a privilege."""
    CONSUMER = "consumer"
    BRAND_PARTNER = "brand_partner"


class PartnerApplicationStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class InvitationStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"


class EmailDeliveryStatus(str, enum.Enum):
    """Outcome vocabulary of a real send attempt (task §13)."""
    SUCCEEDED = "succeeded"   # provider accepted the message
    FAILED = "failed"         # provider/transport rejected it
    RETRYING = "retrying"     # transient failure, retry scheduled/attempted
    BLOCKED = "blocked"       # no provider configured (nothing was sent)
    UNVERIFIED = "unverified"  # accepted locally, no provider receipt available
    # TERMINAL, honest: an attempt claimed this key and then the process died
    # before the provider's answer was recorded. Whether the message was
    # transmitted is genuinely unknown, so neither success nor failure may be
    # claimed. Resolved by email_service.resolve_stale_delivery_claims().
    UNKNOWN = "unknown"


class _LowerEnumType(TypeDecorator):
    """Persist a `str` enum by its `.value` and coerce reads back to the enum.

    Explicit subclasses below (no constructor args) keep SQLAlchemy's type
    copying behaviour trivially safe.
    """
    impl = String(40)
    cache_ok = True
    enum_class: Any = None

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, self.enum_class):
            return value.value
        return self.enum_class(str(value).lower()).value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return self.enum_class(str(value).lower())
        except ValueError:
            return next(iter(self.enum_class))


class RegistrationIntentType(_LowerEnumType):
    cache_ok = True
    enum_class = RegistrationIntent


class PartnerApplicationStatusType(_LowerEnumType):
    cache_ok = True
    enum_class = PartnerApplicationStatus


class InvitationStatusType(_LowerEnumType):
    cache_ok = True
    enum_class = InvitationStatus


class EmailDeliveryStatusType(_LowerEnumType):
    cache_ok = True
    enum_class = EmailDeliveryStatus


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(UserRoleType(), default=UserRole.CONSUMER, nullable=False)
    # What the person asked for at registration ("consumer" | "brand_partner").
    # DATA, never authorization: `role` above remains the only privilege field
    # and is written exclusively by trusted server-side provisioning paths.
    registration_intent = Column(RegistrationIntentType(), default=RegistrationIntent.CONSUMER,
                                 nullable=False, server_default="consumer")
    phone = Column(String(50), nullable=True)
    preferred_language = Column(String(10), default="en", nullable=False)  # 'en' or 'ar'
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    mfa_enabled = Column(Boolean, default=False, nullable=False)
    mfa_secret = Column(String(255), nullable=True)
    # OAuth provider linking — Group 1 §7. `oauth_provider` is the name of
    # the verified upstream provider (google/apple/facebook) and
    # `oauth_subject` is the provider's stable user id. Unique together so
    # the same social account cannot silently link into a second CONFIT row.
    oauth_provider = Column(String(50), nullable=True, index=True)
    oauth_subject = Column(String(255), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    profile = relationship("UserStyleProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    brand_profile = relationship("BrandProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    wardrobe_items = relationship("WardrobeItem", back_populates="user", cascade="all, delete-orphan")
    saved_outfits = relationship("Outfit", back_populates="user", cascade="all, delete-orphan")
    # Group 1 §15: business-critical history is NOT hard-cascaded. Account
    # deletion is handled by `AuthService.delete_account` which anonymizes
    # these rows (order accounting must be retained for tax/audit).
    orders = relationship("Order", back_populates="user")
    tryon_sessions = relationship("TryOnSession", back_populates="user")
    stylist_sessions = relationship("StylistSession", back_populates="user")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    mfa_backup_codes = relationship("MFABackupCode", back_populates="user", cascade="all, delete-orphan")


class BrandProfile(Base):
    __tablename__ = "brand_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    brand_name = Column(String(255), nullable=False, unique=True, index=True)
    slug = Column(String(255), nullable=False, unique=True, index=True)
    logo_url = Column(String(1000), nullable=True)
    banner_url = Column(String(1000), nullable=True)
    description = Column(Text, nullable=True)
    description_ar = Column(Text, nullable=True)
    website = Column(String(500), nullable=True)
    commission_rate = Column(Integer, default=15)
    return_rate_benchmark = Column(Integer, default=28)
    current_return_rate = Column(Integer, default=11)
    is_verified = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="brand_profile")
    products = relationship("Product", back_populates="brand")
    stores = relationship("StoreLocation", back_populates="brand")
    sponsored_placements = relationship("SponsoredPlacement", back_populates="brand")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    action = Column(String(255), nullable=False, index=True)
    resource_type = Column(String(100), nullable=False)
    resource_id = Column(String(100), nullable=True)
    ip_address = Column(String(50), nullable=True)
    details_json = Column(Text, nullable=True)
    # ADMIN-01: full-state audit — the resource state before/after the action
    # (JSON, secret-free) and the X-Request-Id correlation id of the HTTP
    # request that produced the event.
    before_json = Column(Text, nullable=True)
    after_json = Column(Text, nullable=True)
    request_id = Column(String(64), nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class RefreshToken(Base):
    """Server-tracked refresh tokens with rotation + reuse detection.

    Group 1 §8: the `family_id` groups every token that descends from a
    single login; on reuse of an already-rotated token, the whole family
    is revoked (`revoked_at` set on every row with the same family_id).
    We store only the SHA-256 fingerprint of the JTI, never the raw JWT.
    """
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    jti = Column(String(64), nullable=False, unique=True, index=True)
    family_id = Column(String(64), nullable=False, index=True)
    issued_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    replaced_by_jti = Column(String(64), nullable=True)
    user_agent = Column(String(500), nullable=True)
    ip_address = Column(String(50), nullable=True)

    user = relationship("User", back_populates="refresh_tokens")


class PasswordResetToken(Base):
    """Group 1 §12. Store only the SHA-256 hash of the token, never plaintext."""
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(128), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(128), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class MFABackupCode(Base):
    """Per-user random single-use MFA recovery codes. Only the bcrypt hash
    of each code is stored — the plaintext codes are returned exactly ONCE
    at generation time and never again (Group 1 §10)."""
    __tablename__ = "mfa_backup_codes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    code_hash = Column(String(255), nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="mfa_backup_codes")




Index("ix_refresh_tokens_user_active", RefreshToken.user_id, RefreshToken.revoked_at)


# ===========================================================================
# Onboarding, partner provisioning & transactional-email lifecycle
# (2026-09-19 — auth/registration/onboarding/email scope)
#
# Design invariants encoded below:
#  * `registration_intent` is DATA about what the person asked for. It is
#    NEVER an authorization input — authorization still comes only from the
#    server-side provisioning paths (admin approval / invitation acceptance).
#  * Partner-application and invitation tokens are stored hashed, single-use,
#    expiring, and DB-guarded against duplicates by partial unique indexes so
#    concurrent submissions cannot create parallel pending states.
#  * `email_deliveries` is the delivery ledger: the backend records what the
#    provider actually accepted. No code path may claim "sent" without a row
#    here (task §15/§33).
# ===========================================================================

class PartnerApplication(Base):
    """A brand/partner access request awaiting trusted server-side review.

    Approval (Platform Admin, BRD G6 §2.2) is the ONLY self-service path from
    a consumer account to a brand role. The applicant's own payload can never
    set the resulting role or brand.
    """
    __tablename__ = "partner_applications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(PartnerApplicationStatusType(), default=PartnerApplicationStatus.PENDING, nullable=False, index=True)

    brand_name = Column(String(255), nullable=False)
    legal_name = Column(String(255), nullable=True)
    website = Column(String(500), nullable=True)
    market = Column(String(8), nullable=False, default="EG")
    category = Column(String(120), nullable=True)
    catalogue_size = Column(String(40), nullable=True)
    contact_name = Column(String(255), nullable=False)
    contact_email = Column(String(255), nullable=False)
    contact_phone = Column(String(50), nullable=True)
    message = Column(Text, nullable=True)

    submitted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decision_note = Column(Text, nullable=True)
    # Set on approval: the tenant the account is provisioned into.
    brand_id = Column(Integer, ForeignKey("brand_profiles.id", ondelete="SET NULL"), nullable=True)
    request_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", foreign_keys=[user_id])


class Invitation(Base):
    """Server-issued, single-use brand-team invitation (BRD G6 §2.1).

    The role and the brand are recorded HERE, by the issuing brand account or
    admin — accepting the token is the only thing the invitee controls.
    """
    __tablename__ = "invitations"

    id = Column(Integer, primary_key=True, index=True)
    token_hash = Column(String(128), nullable=False, unique=True, index=True)
    email = Column(String(255), nullable=False, index=True)
    role = Column(UserRoleType(), nullable=False)
    brand_id = Column(Integer, ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    invited_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(InvitationStatusType(), default=InvitationStatus.PENDING, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    accepted_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    request_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class EmailChangeRequest(Base):
    """Two-step email change: verify ownership of the NEW address first."""
    __tablename__ = "email_change_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    new_email = Column(String(255), nullable=False)
    token_hash = Column(String(128), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class EmailDelivery(Base):
    """Delivery ledger — the single source of truth for "was it sent?".

    Stores no message body, no token and no plaintext address (SHA-256 prefix
    hash only), so the ledger can be audited without becoming a PII store.
    """
    __tablename__ = "email_deliveries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    purpose = Column(String(40), nullable=False, index=True)
    idempotency_key = Column(String(160), nullable=False, unique=True, index=True)
    status = Column(EmailDeliveryStatusType(), nullable=False, index=True)
    provider = Column(String(40), nullable=True)
    provider_message_id = Column(String(255), nullable=True)
    error_class = Column(String(120), nullable=True)
    attempts = Column(Integer, default=0, nullable=False)
    recipient_hash = Column(String(64), nullable=True)
    request_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


# One *pending* partner application per user — enforced by the database so two
# concurrent submissions cannot create parallel review items.
Index(
    "uq_partner_applications_user_pending",
    PartnerApplication.user_id,
    unique=True,
    sqlite_where=text("status = 'pending'"),
    postgresql_where=text("status = 'pending'"),
)
# One *pending* invitation per (email, brand).
Index(
    "uq_invitations_pending_email_brand",
    Invitation.email,
    Invitation.brand_id,
    unique=True,
    sqlite_where=text("status = 'pending'"),
    postgresql_where=text("status = 'pending'"),
)
# One open email-change request per user.
Index(
    "uq_email_change_open_user",
    EmailChangeRequest.user_id,
    unique=True,
    sqlite_where=text("used_at IS NULL"),
    postgresql_where=text("used_at IS NULL"),
)


class BrandMember(Base):
    """Membership of a user in a brand workspace (multi-user brands).

    The original tenancy model was one `brand_profiles` row per *account*
    (`brand_profiles.user_id` is UNIQUE) — which cannot express a second
    person working in the same brand, so the BRD's "user invitations"
    (G6 §2.1) had nowhere to live. Ownership is still expressed by
    `brand_profiles.user_id`; this table records additional members.
    """
    __tablename__ = "brand_members"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    brand_id = Column(Integer, ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(UserRoleType(), nullable=False)
    invited_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    invitation_id = Column(Integer, ForeignKey("invitations.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", foreign_keys=[user_id])
    brand = relationship("BrandProfile")


Index("uq_brand_members_user_brand", BrandMember.user_id, BrandMember.brand_id, unique=True)
