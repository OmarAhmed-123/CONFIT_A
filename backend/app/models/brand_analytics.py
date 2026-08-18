from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class SponsoredPlacement(Base):
    __tablename__ = "sponsored_placements"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    placement_type = Column(String(50), default="stylist_featured", nullable=False) # "stylist_featured", "trending_hero", "fit_recom_top"
    bid_amount_per_click = Column(Float, default=0.50, nullable=False)
    daily_budget = Column(Float, default=50.0, nullable=False)
    spent_today = Column(Float, default=12.50, nullable=False)
    status = Column(String(20), default="active", nullable=False) # "active", "paused", "budget_exhausted"

    impressions = Column(Integer, default=1420, nullable=False)
    clicks = Column(Integer, default=215, nullable=False)
    conversions = Column(Integer, default=38, nullable=False)
    revenue_generated = Column(Float, default=3420.0, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    brand = relationship("BrandProfile", back_populates="sponsored_placements")
    product = relationship("Product", back_populates="sponsored_placements")


class StyleHeatmapAggregate(Base):
    __tablename__ = "style_heatmap_aggregates"

    id = Column(Integer, primary_key=True, index=True)
    period = Column(String(50), default="monthly", nullable=False)  # "weekly", "monthly", "quarterly"
    region = Column(String(100), default="MENA", nullable=False)    # "MENA", "GCC", "Global"
    top_aesthetics_json = Column(Text, nullable=False)              # JSON: [{"name":"Old Money", "weight":35}, ...]
    top_colors_json = Column(Text, nullable=False)                  # JSON: [{"color":"Navy", "hex":"#1B1F3B", "weight":42}, ...]
    top_occasions_json = Column(Text, nullable=False)               # JSON: [{"name":"Smart Casual Work", "weight":48}, ...]
    sample_size = Column(Integer, default=12500, nullable=False)
    calculated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
