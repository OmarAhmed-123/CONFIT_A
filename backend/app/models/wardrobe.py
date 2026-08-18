from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class WardrobeItem(Base):
    __tablename__ = "wardrobe_items"

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
    wear_frequency = Column(String(30), default="regular", nullable=False) # "favorite", "regular", "rarely_worn", "seasonal"
    wear_count = Column(Integer, default=0, nullable=False)
    last_worn_date = Column(DateTime, nullable=True)
    purchase_price = Column(Float, nullable=True)
    is_favorite = Column(Boolean, default=False, nullable=False)
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
