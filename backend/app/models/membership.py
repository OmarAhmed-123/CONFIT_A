"""Brand tenant membership + invitation domain (BRD-02 · spec 005 · #150 residue).

WHY THIS EXISTS
---------------
Until this module, a BrandProfile was the tenant link: ``brand_profiles.user_id`` is
UNIQUE, so exactly one global user could ever resolve a brand (``BrandService.
_resolve_brand``). Managers/staff existed only as GLOBAL ``users.role`` values, which
(a) is platform-wide privilege — the wrong shape for tenant membership — and (b) still
failed brand resolution because they had no profile row. Spec 005 (T-BRD-02) called for
``brand_members(brand_id, user_id, role)`` with invitations and last-owner protection;
that never landed and #150's close audit named it the primary genuine residue.

DESIGN RULES (enforced here and in backend/app/services/brand_membership_service.py)
-------------------------------------------------------------------------------------
* Membership is the tenant source of truth. ``brand_profiles.user_id`` remains the
  FOUNDER anchor and the legacy fallback (the repair plan's "keep owner rollback").
* Joining a brand NEVER mutates ``users.role`` — platform roles stay separate from
  tenant roles (anti global-promotion rule).
* Role ladder: staff < manager < owner. Capabilities live in CAPABILITIES below;
  servers enforce them, the UI only mirrors.
* At most ONE active membership per user (the portal has no brand switcher yet — a
  second membership is refused at acceptance, not silently resolved).
* Invitation tokens are high-entropy secrets: only the SHA-256 hash is stored; the raw
  token is returned once (delivery email) and never re-read.
* Auditability: mutations are audited by the controllers through the existing
  ``UserRepository.log_audit`` path — the 0020 HMAC mapper-chain covers every insert,
  so there is no unchained write path to forget.
"""

from datetime import datetime, timezone
from typing import FrozenSet

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)

from backend.app.core.database import Base

# ── vocabulary ───────────────────────────────────────────────────────────────

MEMBERSHIP_ROLES = ("owner", "manager", "staff")
MEMBERSHIP_STATUSES = ("active", "revoked")
INVITATION_STATUSES = ("pending", "accepted", "revoked", "expired")

ROLE_RANK = {"staff": 1, "manager": 2, "owner": 3}

# Capability matrix (server-side truth). The names double as FastAPI dependency
# parameters (``require_brand_access("catalog:write")``) so every partner route
# declares EXACTLY what it needs; there is no wildcard "any brand user" left
# on privileged mutations. ``members:manage`` additionally opts out of the
# platform-admin override (tenant governance belongs to tenant owners).
CAPABILITIES: dict[str, FrozenSet[str]] = {
    "brand:read": frozenset({"owner", "manager", "staff"}),
    "inventory:write": frozenset({"owner", "manager", "staff"}),
    "catalog:write": frozenset({"owner", "manager"}),
    "stores:write": frozenset({"owner", "manager"}),
    # Campaign OPERATIONS (bid/budget within the owner-approved envelope) are
    # manager-day-to-day; MONEY SETTLEMENT (billing statement, reconciliation)
    # stays owner-only below.
    "placements:manage": frozenset({"owner", "manager"}),
    "profile:write": frozenset({"owner"}),
    "billing:read": frozenset({"owner"}),
    "members:manage": frozenset({"owner"}),
}

INVITATION_TTL_DAYS = 7


def role_allows(role: str, capability: str) -> bool:
    return role in CAPABILITIES.get(capability, frozenset())


class BrandMembership(Base):
    """A user's tenant-scoped role inside one brand organization."""

    __tablename__ = "brand_memberships"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(
        Integer, ForeignKey("brand_profiles.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # Tenant role, deliberately NOT users.role. Values: owner|manager|staff.
    role = Column(String(20), nullable=False)
    # active | revoked. Revocation keeps the row (audit trail references it).
    status = Column(String(20), default="active", nullable=False)
    granted_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    revoked_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("brand_id", "user_id", name="uq_brand_membership_brand_user"),
    )


class BrandInvitation(Base):
    """One-time, expirable invitation to join a brand with a specific role.

    ``token_hash`` is SHA-256(raw token); the raw token exists only in the
    delivery email (and once in the create/accept flow). Lookup is by hash,
    so a stolen row cannot be replayed as a link and emails are the only
    token carrier.
    """

    __tablename__ = "brand_invitations"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(
        Integer, ForeignKey("brand_profiles.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # Normalized (stripped+lowercased) by the service before write.
    email = Column(String(255), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    token_hash = Column(String(64), unique=True, nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    invited_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    accepted_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        # Only one pending invitation per (brand, email) — enforced by a
        # partial unique index in the migration (see 0039).
        Index("ix_brand_invitations_brand_status", "brand_id", "status"),
    )
