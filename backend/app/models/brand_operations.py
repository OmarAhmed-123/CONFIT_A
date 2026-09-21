from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, CheckConstraint, Index, UniqueConstraint
from backend.app.core.database import Base


class ProductAsset(Base):
    __tablename__ = 'product_assets'
    __table_args__ = (
        CheckConstraint("state IN ('upload_pending','active','delete_pending','deleted')", name='ck_product_asset_state'),
        Index('ix_product_asset_brand_state', 'brand_id', 'state'),
    )
    id = Column(String(36), primary_key=True)
    brand_id = Column(Integer, ForeignKey('brand_profiles.id', ondelete='RESTRICT'), nullable=False)
    product_id = Column(Integer, ForeignKey('products.id', ondelete='RESTRICT'), nullable=False)
    object_key = Column(String(500), nullable=False, unique=True)
    sha256 = Column(String(64), nullable=False)
    byte_size = Column(Integer, nullable=False)
    state = Column(String(20), nullable=False, default='active')
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class CatalogImportWork(Base):
    __tablename__ = 'catalog_import_work'
    __table_args__ = (
        UniqueConstraint('brand_id', 'idempotency_key', name='uq_catalog_work_idempotency'),
        CheckConstraint('cursor >= 0 AND attempts >= 0', name='ck_catalog_work_progress'),
        Index('ix_catalog_work_retry', 'next_attempt_at', 'job_id'),
    )
    job_id = Column(Integer, ForeignKey('catalog_import_jobs.id', ondelete='CASCADE'), primary_key=True)
    brand_id = Column(Integer, ForeignKey('brand_profiles.id', ondelete='CASCADE'), nullable=False)
    actor_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    idempotency_key = Column(String(100), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    payload_json = Column(Text, nullable=False)
    cursor = Column(Integer, nullable=False, default=0)
    attempts = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
