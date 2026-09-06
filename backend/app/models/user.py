import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Index
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


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(UserRoleType(), default=UserRole.CONSUMER, nullable=False)
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
