from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Float, CheckConstraint
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class SponsoredPlacement(Base):
    __tablename__ = "sponsored_placements"
    __table_args__ = (
        CheckConstraint("bid_amount_per_click > 0", name="ck_sponsored_bid_positive"),
        CheckConstraint("daily_budget > 0", name="ck_sponsored_budget_positive"),
        CheckConstraint("bid_amount_per_click <= daily_budget", name="ck_sponsored_bid_lte_budget"),
        CheckConstraint("bid_amount_per_click <= 100", name="ck_sponsored_bid_max"),
        CheckConstraint("daily_budget <= 10000", name="ck_sponsored_budget_max"),
        CheckConstraint("spent_today >= 0", name="ck_sponsored_spent_nonneg"),
        CheckConstraint("spent_today <= daily_budget", name="ck_sponsored_spent_lte_budget"),
        CheckConstraint("impressions >= 0", name="ck_sponsored_impressions_nonneg"),
        CheckConstraint("clicks >= 0", name="ck_sponsored_clicks_nonneg"),
        CheckConstraint("conversions >= 0", name="ck_sponsored_conversions_nonneg"),
        CheckConstraint("revenue_generated >= 0", name="ck_sponsored_revenue_nonneg"),
        CheckConstraint("status IN ('active','paused','budget_exhausted','completed','cancelled')", name="ck_sponsored_status_valid"),
    )

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    placement_type = Column(String(50), default="stylist_featured", nullable=False, index=True) # "stylist_featured", "trending_hero", "fit_recom_top"
    bid_amount_per_click = Column(Float, default=0.50, nullable=False)
    daily_budget = Column(Float, default=50.0, nullable=False)
    spent_today = Column(Float, default=0.0, nullable=False)
    status = Column(String(20), default="active", nullable=False, index=True) # "active", "paused", "budget_exhausted"

    impressions = Column(Integer, default=0, nullable=False)
    clicks = Column(Integer, default=0, nullable=False)
    conversions = Column(Integer, default=0, nullable=False)
    revenue_generated = Column(Float, default=0.0, nullable=False)

    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

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
