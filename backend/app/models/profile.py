from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float, Numeric
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class UserStyleProfile(Base):
    __tablename__ = "user_style_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)

    # Style Preferences (G1.2)
    style_archetypes = Column(Text, default="[]", nullable=False)  # JSON array
    preferred_colors = Column(Text, default="[]", nullable=False)  # JSON array
    avoided_colors = Column(Text, default="[]", nullable=False)    # JSON array
    fashion_aesthetics = Column(Text, default="[]", nullable=False) # JSON array
    moodboard_urls = Column(Text, default="[]", nullable=False)     # legacy — mood_boards table owns this now

    # Body Attributes — Encrypted at Rest (G1.3). Nullable: optional, privacy-first.
    encrypted_body_data = Column(Text, nullable=True)
    body_shape_tag = Column(String(50), nullable=True)

    # Budget & Occasions (G1.4) — nullable so we can honestly represent
    # "user hasn't set this yet" instead of always shipping fabricated 100/1000.
    budget_monthly_min = Column(Numeric(12, 2), nullable=True)
    budget_monthly_max = Column(Numeric(12, 2), nullable=True)
    budget_per_outfit_max = Column(Numeric(12, 2), nullable=True)
    preferred_brands = Column(Text, default="[]", nullable=False)
    blacklisted_brands = Column(Text, default="[]", nullable=False)
    occasion_weights = Column(Text, default="{}", nullable=False)

    # Size & Fit — nullable for the same "not-yet-set" honesty reason.
    size_tops = Column(String(20), nullable=True)
    size_bottoms = Column(String(20), nullable=True)
    size_shoes = Column(String(20), nullable=True)
    fit_preference = Column(String(30), nullable=True)

    # Status
    onboarding_completed = Column(Boolean, default=False, nullable=False)

    # Consent state — real persistent columns replacing the previous mock
    # `/me/consents` handler. Group 1 §17.
    privacy_consent_tryon_storage = Column(Boolean, default=False, nullable=False)
    privacy_consent_share_with_brands = Column(Boolean, default=False, nullable=False)
    consent_ai_personalization = Column(Boolean, default=True, nullable=False)
    consent_marketing_analytics = Column(Boolean, default=False, nullable=False)
    consent_policy_version = Column(Integer, default=3, nullable=False)
    consent_last_agreed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="profile")
    mood_boards = relationship("MoodBoard", back_populates="profile", cascade="all, delete-orphan")


class MoodBoard(Base):
    """Group 1 §28 — real mood-board persistence.

    Replaces the dead `moodboard_urls` column with a proper owned table.
    Items live in `mood_board_items` (JSON payload per item, so an item can
    be a URL, an uploaded photo reference, or a product SKU id without a
    destructive schema change).
    """
    __tablename__ = "mood_boards"

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("user_style_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    profile = relationship("UserStyleProfile", back_populates="mood_boards")
    items = relationship("MoodBoardItem", back_populates="board", cascade="all, delete-orphan")


class MoodBoardItem(Base):
    __tablename__ = "mood_board_items"

    id = Column(Integer, primary_key=True, index=True)
    board_id = Column(Integer, ForeignKey("mood_boards.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(30), nullable=False)  # "url" | "product" | "upload"
    payload_json = Column(Text, nullable=False, default="{}")  # {"url": "..."} | {"product_id": 123} | {"upload_id": "..."}
    position = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    board = relationship("MoodBoard", back_populates="items")
