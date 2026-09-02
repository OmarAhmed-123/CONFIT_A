from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float, Numeric, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class WardrobeItem(Base):
    __tablename__ = "wardrobe_items"
    # Group 4 §24/§27: database-level guard for the sha256 duplicate-upload
    # protection — two concurrent uploads of the same bytes can no longer
    # both insert (the service catches the IntegrityError and returns the
    # canonical item as an idempotent duplicate). NULL hashes (manual/seeded
    # items) are unaffected.
    __table_args__ = (
        UniqueConstraint("user_id", "image_hash", name="uq_wardrobe_items_user_image_hash"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    category = Column(String(50), nullable=False)     # Tops, Bottoms, Outerwear, Footwear, Accessories
    subcategory = Column(String(100), nullable=True)  # e.g., "Oversized Blazer", "Oxford Shirt", "Pleated Trousers"
    color_name = Column(String(50), nullable=False)
    color_hex = Column(String(20), default="#000000", nullable=False)
    pattern = Column(String(50), default="Solid", nullable=False)
    brand_name = Column(String(100), default="Own Collection", nullable=False)
    image_url = Column(String(1000), nullable=False)

    ai_tags = Column(Text, default="[]", nullable=False)         # JSON list: ["smart_casual", "cotton", "breathable"]
    occasions = Column(Text, default="[]", nullable=False)       # JSON list: ["work", "dinner"]
    secondary_colors = Column(Text, default="[]", nullable=False) # JSON list of normalized color families
    seasonality = Column(String(30), default="All-Season", nullable=False)  # All-Season|Spring|Summer|Autumn|Winter
    wear_frequency = Column(String(30), default="regular", nullable=False) # "favorite", "regular", "rarely_worn", "seasonal"
    wear_count = Column(Integer, default=0, nullable=False)
    last_worn_date = Column(DateTime, nullable=True)
    purchase_price = Column(Numeric(12, 2), nullable=True)
    is_favorite = Column(Boolean, default=False, nullable=False)

    # Group 4 §11 item lifecycle: uploaded -> processing -> ready | failed
    # (failed is retryable). Items created with manually supplied metadata
    # are born 'ready'; image uploads start at 'uploaded' and move to
    # 'processing' while the vision provider runs, then 'ready' or 'failed'.
    processing_status = Column(String(20), default="ready", nullable=False, index=True)
    processing_error = Column(Text, nullable=True)              # last failure detail for retry UX
    ai_confidence = Column(Float, nullable=True)                # vision model confidence 0.0-1.0
    image_hash = Column(String(64), nullable=True, index=True)  # sha256 — duplicate upload protection
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="wardrobe_items")


class WardrobeGapAnalysis(Base):
    __tablename__ = "wardrobe_gap_analyses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    missing_category = Column(String(100), nullable=False)
    missing_subcategory = Column(String(100), nullable=False)
    suggested_colors = Column(Text, default="[]", nullable=False) # JSON list
    rationale = Column(Text, nullable=False)
    unlocks_outfit_count = Column(Integer, default=3, nullable=False)
    recommended_products_json = Column(Text, default="[]", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
