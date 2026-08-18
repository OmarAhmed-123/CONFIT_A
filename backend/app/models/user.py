import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, ForeignKey, Text
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class UserRole(str, enum.Enum):
    CONSUMER = "consumer"
    BRAND_MANAGER = "brand_manager"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.CONSUMER, nullable=False)
    phone = Column(String(50), nullable=True)
    preferred_language = Column(String(10), default="en", nullable=False)  # 'en' or 'ar'
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    mfa_enabled = Column(Boolean, default=False, nullable=False)
    mfa_secret = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    profile = relationship("UserStyleProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    brand_profile = relationship("BrandProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    wardrobe_items = relationship("WardrobeItem", back_populates="user", cascade="all, delete-orphan")
    saved_outfits = relationship("Outfit", back_populates="user", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="user")
    tryon_sessions = relationship("TryOnSession", back_populates="user")
    stylist_sessions = relationship("StylistSession", back_populates="user")


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
    commission_rate = Column(Integer, default=15)  # e.g., 15%
    return_rate_benchmark = Column(Integer, default=28)  # e.g., 28% pre-VTON
    current_return_rate = Column(Integer, default=11)   # e.g., 11% post-VTON
    is_verified = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="brand_profile")
    products = relationship("Product", back_populates="brand")
    stores = relationship("StoreLocation", back_populates="brand")
    sponsored_placements = relationship("SponsoredPlacement", back_populates="brand")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)
    action = Column(String(255), nullable=False, index=True)
    resource_type = Column(String(100), nullable=False)
    resource_id = Column(String(100), nullable=True)
    ip_address = Column(String(50), nullable=True)
    details_json = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
