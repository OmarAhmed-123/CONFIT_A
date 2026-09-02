from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Float, Boolean, Index, CheckConstraint
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class CatalogImportJob(Base):
    __tablename__ = "catalog_import_jobs"
    __table_args__ = (
        Index("ix_catalog_import_brand_status", "brand_id", "status"),
        Index("ix_catalog_import_created", "created_at"),
        CheckConstraint("total_rows >= 0", name="ck_import_total_nonneg"),
        CheckConstraint("accepted_rows >= 0", name="ck_import_accepted_nonneg"),
        CheckConstraint("rejected_rows >= 0", name="ck_import_rejected_nonneg"),
        CheckConstraint("duplicate_rows >= 0", name="ck_import_duplicate_nonneg"),
        CheckConstraint("status IN ('queued','processing','completed','partially_completed','failed')", name="ck_import_status_valid"),
    )

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    file_name = Column(String(500), nullable=True)
    file_size = Column(Integer, nullable=True)
    status = Column(String(30), default="queued", nullable=False)  # queued, processing, completed, partially_completed, failed
    total_rows = Column(Integer, default=0, nullable=False)
    accepted_rows = Column(Integer, default=0, nullable=False)
    rejected_rows = Column(Integer, default=0, nullable=False)
    duplicate_rows = Column(Integer, default=0, nullable=False)
    errors_json = Column(Text, default="[]", nullable=False)  # JSON array of error details
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    brand = relationship("BrandProfile")


class BrandAnalyticsEvent(Base):
    """
    Canonical analytics event for B2B conversion funnel.
    Deterministic, structured, timestamped, attributable, deduplicatable.
    """
    __tablename__ = "brand_analytics_events"
    __table_args__ = (
        Index("ix_brand_analytics_brand_type_time", "brand_id", "event_type", "created_at"),
        Index("ix_brand_analytics_product", "product_id"),
        Index("ix_brand_analytics_sku", "sku_id"),
        Index("ix_brand_analytics_event_id", "event_id", unique=True),
    )

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String(100), unique=True, index=True, nullable=False)  # Idempotency key
    brand_id = Column(Integer, ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True)
    sku_id = Column(Integer, ForeignKey("product_skus.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    session_token = Column(String(100), nullable=True)
    event_type = Column(String(50), nullable=False, index=True)  # view, tryon, add_to_cart, purchase, outfit_save, outfit_purchase, return, sponsored_impression, sponsored_click
    attribution_source = Column(String(50), nullable=True)  # virtual_stylist, outfit_builder, visual_search, organic
    outfit_id = Column(Integer, ForeignKey("outfits.id", ondelete="SET NULL"), nullable=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    revenue_amount = Column(Float, nullable=True)
    event_metadata_json = Column(Text, default="{}", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
