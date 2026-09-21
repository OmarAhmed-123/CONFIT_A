"""Tenant membership; global account roles are deliberately not promoted."""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, CheckConstraint, UniqueConstraint, Index, event
from sqlalchemy.orm import relationship
from backend.app.core.database import Base
from backend.app.models.user import BrandProfile

ROLES = ('owner', 'manager', 'staff', 'analyst', 'catalog_editor')


class BrandMembership(Base):
    __tablename__ = 'brand_memberships'
    __table_args__ = (
        UniqueConstraint('brand_id', 'user_id', name='uq_brand_membership_pair'),
        # The existing portal has one implicit tenant, not a tenant selector.
        UniqueConstraint('user_id', name='uq_brand_membership_user'),
        CheckConstraint("role IN ('owner','manager','staff','analyst','catalog_editor')", name='ck_brand_membership_role'),
        Index('ix_brand_membership_brand_id', 'brand_id', 'id'),
    )
    id = Column(Integer, primary_key=True)
    brand_id = Column(Integer, ForeignKey('brand_profiles.id', ondelete='CASCADE'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='RESTRICT'), nullable=False)
    role = Column(String(30), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    user = relationship('User', backref='brand_memberships')
    brand = relationship('BrandProfile')


class BrandInvitation(Base):
    __tablename__ = 'brand_invitations'
    __table_args__ = (
        CheckConstraint("role IN ('owner','manager','staff','analyst','catalog_editor')", name='ck_brand_invitation_role'),
        CheckConstraint("status IN ('pending','accepted','revoked','expired')", name='ck_brand_invitation_status'),
        Index('ix_brand_invitation_brand_id', 'brand_id', 'id'),
    )
    id = Column(Integer, primary_key=True)
    brand_id = Column(Integer, ForeignKey('brand_profiles.id', ondelete='CASCADE'), nullable=False)
    email = Column(String(255), nullable=False)
    role = Column(String(30), nullable=False)
    token_hash = Column(String(64), unique=True, nullable=False)
    status = Column(String(20), nullable=False, default='pending')
    invited_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


@event.listens_for(BrandProfile, 'after_insert')
def provision_founder_membership(mapper, connection, target):
    """New tenants created through existing ORM provisioning retain ownership."""
    from sqlalchemy import select
    table = BrandMembership.__table__
    if connection.execute(select(table.c.id).where(table.c.brand_id == target.id, table.c.user_id == target.user_id)).first():
        return  # PostgreSQL migration trigger also protects older app versions.
    connection.execute(BrandMembership.__table__.insert().values(
        brand_id=target.id, user_id=target.user_id, role='owner'))
