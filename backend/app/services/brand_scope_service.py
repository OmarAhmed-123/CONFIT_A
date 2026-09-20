"""Single resolution point for "which brand tenant does this user belong to?".

Before invitations existed, every B2B call site answered that question with
``user.brand_profile`` — correct while a brand could only have one account.
Invited teammates (BRD G6 §2.1) have no ``brand_profiles`` row of their own, so
membership is resolved here instead, and the three call sites that used to read
``user.brand_profile`` directly now go through this module (DRY, one tenant
boundary instead of three ad-hoc ones).

Ownership keeps priority: a user who owns a brand profile is scoped to it.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from backend.app.core.exceptions import AuthorizationError
from backend.app.models.user import BrandMember, BrandProfile, User, UserRole


def owned_brand(db: Session, user: User) -> Optional[BrandProfile]:
    return db.query(BrandProfile).filter(BrandProfile.user_id == user.id).first()


def member_brand(db: Session, user: User) -> Optional[BrandProfile]:
    row = (
        db.query(BrandMember)
        .filter(BrandMember.user_id == user.id)
        .order_by(BrandMember.id.asc())
        .first()
    )
    if row is None:
        return None
    return db.query(BrandProfile).filter(BrandProfile.id == row.brand_id).first()


def resolve_brand(db: Session, user: User) -> Optional[BrandProfile]:
    """The brand tenant this user acts for, or ``None`` if they have none.

    Platform admins have no tenant of their own; callers that need one for an
    admin must ask for an explicit brand id (unchanged behaviour).
    """
    brand = owned_brand(db, user)
    if brand is not None:
        return brand
    return member_brand(db, user)


def resolve_brand_id(db: Session, user: User) -> Optional[int]:
    brand = resolve_brand(db, user)
    return brand.id if brand is not None else None


def membership_role(db: Session, user: User, brand_id: int) -> Optional[str]:
    row = (
        db.query(BrandMember)
        .filter(BrandMember.user_id == user.id, BrandMember.brand_id == brand_id)
        .first()
    )
    if row is None:
        return None
    return row.role.value if isinstance(row.role, UserRole) else str(row.role)


def assert_brand_access(db: Session, user: User, brand_id: int) -> None:
    """Raise 403 unless the user owns the brand, is a member, or is an admin."""
    if is_admin(user):
        return
    if owned_brand_id(db, user) == brand_id or membership_role(db, user, brand_id):
        return
    raise AuthorizationError(
        f"Access denied: user is not associated with Brand Organization {brand_id}."
    )


def owned_brand_id(db: Session, user: User) -> Optional[int]:
    brand = owned_brand(db, user)
    return brand.id if brand is not None else None


def is_admin(user: User) -> bool:
    return user.role == UserRole.ADMIN
