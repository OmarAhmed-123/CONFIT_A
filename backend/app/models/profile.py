from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class UserStyleProfile(Base):
    __tablename__ = "user_style_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)

    # Style Preferences (G1.2)
    style_archetypes = Column(Text, default="[]", nullable=False)  # JSON array: ["casual", "streetwear", "minimalist"]
    preferred_colors = Column(Text, default="[]", nullable=False)  # JSON array: ["navy", "beige", "forest_green"]
    avoided_colors = Column(Text, default="[]", nullable=False)    # JSON array: ["neon_yellow"]
    fashion_aesthetics = Column(Text, default="[]", nullable=False) # JSON array: ["Old Money", "Modern Tailored", "Quiet Luxury"]
    moodboard_urls = Column(Text, default="[]", nullable=False)

    # Body Attributes - Encrypted at Rest (G1.3)
    encrypted_body_data = Column(Text, nullable=True)  # Fernet encrypted JSON string {height_cm, weight_kg, body_shape, chest_cm, waist_cm, hip_cm, inseam_cm}
    body_shape_tag = Column(String(50), nullable=True) # e.g. "Hourglass", "Athletic", "Rectangle", "Inverted Triangle", "Pear"

    # Budget & Occasions (G1.4)
    budget_monthly_min = Column(Float, default=100.0)
    budget_monthly_max = Column(Float, default=1000.0)
    budget_per_outfit_max = Column(Float, default=400.0)
    preferred_brands = Column(Text, default="[]", nullable=False)   # JSON whitelist
    blacklisted_brands = Column(Text, default="[]", nullable=False) # JSON blacklist
    occasion_weights = Column(Text, default='{"work":0.3,"casual":0.4,"party":0.2,"sports":0.1}', nullable=False)

    # Size & Fit Defaults
    size_tops = Column(String(20), default="M")
    size_bottoms = Column(String(20), default="32")
    size_shoes = Column(String(20), default="42")
    fit_preference = Column(String(30), default="regular")  # "slim", "regular", "oversized"

    # Status & Privacy Consents
    onboarding_completed = Column(Boolean, default=False, nullable=False)
    privacy_consent_tryon_storage = Column(Boolean, default=False, nullable=False)
    privacy_consent_share_with_brands = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="profile")
