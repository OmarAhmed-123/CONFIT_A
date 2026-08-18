from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class StylistSession(Base):
    __tablename__ = "stylist_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_title = Column(String(255), default="Personal Styling Session", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="stylist_sessions")
    messages = relationship("StylistMessage", back_populates="session", cascade="all, delete-orphan")


class StylistMessage(Base):
    __tablename__ = "stylist_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("stylist_sessions.id", ondelete="CASCADE"), nullable=False)
    sender = Column(String(20), nullable=False)  # "user", "assistant", "system"
    content = Column(Text, nullable=False)
    audio_url = Column(String(1000), nullable=True)
    intent_json = Column(Text, default="{}", nullable=False)            # Extracted occasion, budget, style constraints
    recommendations_json = Column(Text, default="[]", nullable=False)   # List of recommended outfit/product objects
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    session = relationship("StylistSession", back_populates="messages")


class Outfit(Base):
    __tablename__ = "outfits"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    occasion = Column(String(100), default="Casual", nullable=False)
    total_price = Column(Float, default=0.0, nullable=False)
    compatibility_score = Column(Integer, default=90, nullable=False)  # Calculated color/style score %
    color_palette = Column(Text, default="[]", nullable=False)         # JSON list of hex colors
    style_tags = Column(Text, default="[]", nullable=False)            # JSON list
    is_saved = Column(Boolean, default=False, nullable=False)
    is_system_curated = Column(Boolean, default=False, nullable=False)
    share_token = Column(String(100), unique=True, index=True, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="saved_outfits")
    items = relationship("OutfitItem", back_populates="outfit", cascade="all, delete-orphan")


class OutfitItem(Base):
    __tablename__ = "outfit_items"

    id = Column(Integer, primary_key=True, index=True)
    outfit_id = Column(Integer, ForeignKey("outfits.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    product_sku_id = Column(Integer, ForeignKey("product_skus.id", ondelete="SET NULL"), nullable=True)
    position = Column(String(50), nullable=False)  # "top", "bottom", "outerwear", "shoes", "accessory"
    sort_order = Column(Integer, default=0, nullable=False)

    outfit = relationship("Outfit", back_populates="items")
    product = relationship("Product")
    sku = relationship("ProductSKU")
