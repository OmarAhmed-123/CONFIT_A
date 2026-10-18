"""Brand membership service — tenant resolution, capability enforcement,
invitation lifecycle, and last-owner protection (BRD-02 · spec 005).

SECURITY MODEL (server-authoritative; the UI mirrors but never grants)
----------------------------------------------------------------------
* ``resolve_access(user, capability)`` is the ONLY way a partner route decides
  what the acting user may do. Client-supplied brand ids never enter the
  picture: the tenant is derived from ACTIVE membership rows for the validated
  JWT subject.
* ``members:manage`` deliberately has NO platform-admin override: platform
  governance (admin console) and tenant governance (who belongs to a brand)
  are separate powers (brief §5.2; Constitution P3 "fails closed").
* Invitation acceptance is the only PUBLIC-facing mutation surface here and it
  consumes an unguessable 256-bit one-time token bound to a lowercased email,
  then fails closed with a single uniform error code for every rejection
  reason (unknown token, expired, revoked, already consumed, email mismatch)
  so the endpoint cannot enumerate invitation states.
* Last-owner protection is serialized through SELECT … FOR UPDATE on the brand
  row (PostgreSQL). SQLite test runs pin the logic; CI's postgres job pins the
  locking semantics.

Every status change below is audited by the calling controller through the
existing hash-chained ``UserRepository.log_audit`` path (0020 mapper listener).
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from backend.app.models.membership import (
    CAPABILITIES,
    INVITATION_TTL_DAYS,
    MEMBERSHIP_ROLES,
    role_allows,
    BrandInvitation,
    BrandMembership,
)
from backend.app.models.user import BrandProfile, User, UserRole

logger = logging.getLogger(__name__)

# Uniform, non-enumerating failure for every accept rejection (see module doc).
INVITATION_NOT_APPLICABLE = "INVITATION_NOT_APPLICABLE"


class BrandMembershipError(Exception):
    """Domain error carrying an HTTP-mappable code."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class BrandAccessDenied(BrandMembershipError):
    def __init__(self, message: str = "Brand tenant access denied."):
        super().__init__("BRAND_ACCESS_DENIED", message, 403)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _naive(dt: datetime) -> datetime:
    """Storage parity: the legacy columns are naive-UTC on both engines."""
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class BrandMembershipService:
    def __init__(self, db: Session):
        self.db = db

    # ── tenant resolution ────────────────────────────────────────────────
    def active_memberships(self, user: User) -> List[BrandMembership]:
        return (
            self.db.query(BrandMembership)
            .join(BrandProfile, BrandProfile.id == BrandMembership.brand_id)
            .filter(
                BrandMembership.user_id == user.id,
                BrandMembership.status == "active",
            )
            .all()
        )

    def _membership_rows_any_status(self, user: User) -> List[BrandMembership]:
        return (
            self.db.query(BrandMembership)
            .filter(BrandMembership.user_id == user.id)
            .all()
        )

    def resolve_role(self, user: User, *, brand_id: Optional[int] = None) -> str:
        """Role of `user` in a tenant: membership row first, legacy founder
        fallback second. Returns "admin" for platform admins (read/manage of
        other surfaces still checks per-capability)."""
        if user.role == UserRole.ADMIN:
            return "admin"
        q = self.db.query(BrandMembership).filter(
            BrandMembership.user_id == user.id,
            BrandMembership.status == "active",
        )
        if brand_id is not None:
            q = q.filter(BrandMembership.brand_id == brand_id)
        row = q.first()
        if row:
            return row.role
        # Legacy: single-owner 1:1 profile (pre-0039 model; also the rollback
        # path if the migration rows were ever dropped). A revoked membership
        # row suppresses the anchor (see resolve_access). Role-aware like
        # resolve_access: a legacy BRAND_MANAGER anchor resolves 'manager'.
        if user.brand_profile is not None and not self._membership_rows_any_status(user):
            return {
                UserRole.BRAND_OWNER: "owner",
                UserRole.BRAND_MANAGER: "manager",
                UserRole.BRAND_STAFF: "staff",
                UserRole.ADMIN: "admin",
            }.get(user.role, "owner")
        raise BrandAccessDenied()

    def resolve_access(self, user: User, capability: str, *,
                       allow_admin: bool = True) -> Dict[str, Any]:
        """Gate: does the acting user's TENANT role satisfy the capability?

        Admin override exists only where it existed before (allow_admin=True on
        read/manage surfaces that already accepted ADMIN); members:manage sets
        allow_admin=False — platform admin is not a brand member and cannot
        govern tenants through the partner API.
        """
        if user.role == UserRole.ADMIN and allow_admin:
            return {"role": "admin", "capability": capability}
        memberships = self.active_memberships(user)
        if memberships:
            # Single-brand invariant (enforced at acceptance); multi-row data
            # (e.g. hand-edited rows) must not silently pick one: fail closed.
            if len({m.brand_id for m in memberships}) > 1:
                raise BrandAccessDenied(
                    "This account holds memberships in multiple brands; the partner "
                    "portal supports one brand per account today. An administrator "
                    "must consolidate the memberships."
                )
            role = memberships[0].role
            if not role_allows(role, capability):
                raise BrandAccessDenied(
                    f"Brand role '{role}' may not perform '{capability}'."
                )
            return {"role": role, "capability": capability,
                    "brand_id": memberships[0].brand_id}
        # Legacy fallback — the 1:1 anchor only, and ONLY for pre-membership
        # data (no rows at all). A revoked membership row suppresses the
        # anchor: removal means removal. The acting role is the user's global
        # BRAND_* role projected onto the tenant (pre-0039 behavior for the
        # seeded/demo dataset and the documented rollback path), so capabilities
        # now DIFFERENTIMATE by role here too — a legacy BRAND_MANAGER gets
        # manager, not owner.
        if user.brand_profile is not None and not self._membership_rows_any_status(user):
            legacy_role = {
                UserRole.BRAND_OWNER: "owner",
                UserRole.BRAND_MANAGER: "manager",
                UserRole.BRAND_STAFF: "staff",
            }.get(user.role)
            if legacy_role is not None:
                if not role_allows(legacy_role, capability):
                    raise BrandAccessDenied(
                        f"Brand role '{legacy_role}' may not perform '{capability}'."
                    )
                return {"role": legacy_role, "capability": capability,
                        "brand_id": user.brand_profile.id}
        # No membership and no anchor: nothing to resolve (pre-0039, these
        # users failed brand resolution too — same denial shape).
        raise BrandAccessDenied(
            "No brand tenant linked to this account. Request partner onboarding; "
            "administrators must use explicit admin routes."
        )

    def tenant_brand(self, user: User) -> BrandProfile:
        """The brand the acting user may operate on (membership first, founder
        fallback second). Raises fail-closed. Used by BrandService._resolve_brand."""
        if user.role == UserRole.ADMIN:
            pass  # admins never own a tenant; fall through to membership below
        rows = self.active_memberships(user)
        if not rows and self._membership_rows_any_status(user):
            raise BrandAccessDenied(
                "Your brand membership for this organization has been revoked."
            )
        if len({r.brand_id for r in rows}) > 1:
            raise BrandAccessDenied(
                "Multiple active brand memberships are not supported by the partner "
                "portal; an administrator must consolidate them."
            )
        if rows:
            bp = self.db.get(BrandProfile, rows[0].brand_id)
            if bp is None:  # pragma: no cover - FK cascade makes this unreachable
                raise BrandAccessDenied()
            return bp
        bp = None
        if not self._membership_rows_any_status(user):
            bp = self.db.query(BrandProfile).filter(BrandProfile.user_id == user.id).first()
        if bp is None:
            raise BrandAccessDenied(
                "No Brand Organization linked to this account. Request partner "
                "onboarding; administrators must use explicit admin routes."
            )
        return bp

    # ── membership management (owner-gated; controllers enforce capability) ──
    def list_members(self, brand_id: int, *, include_revoked: bool) -> List[Dict[str, Any]]:
        q = (
            self.db.query(BrandMembership, User)
            .join(User, User.id == BrandMembership.user_id)
            .filter(BrandMembership.brand_id == brand_id)
        )
        if not include_revoked:
            q = q.filter(BrandMembership.status == "active")
        out: List[Dict[str, Any]] = []
        for m, u in q.order_by(BrandMembership.created_at.asc()).all():
            out.append({
                "id": m.id,
                "brand_id": m.brand_id,
                "user_id": u.id,
                "full_name": u.full_name,
                "email": u.email,
                "role": m.role,
                "status": m.status,
                "created_at": m.created_at,
                "revoked_at": m.revoked_at,
            })
        return out

    def _brand_row_for_update(self, brand_id: int) -> BrandProfile:
        """Serialize membership mutations per brand. PostgreSQL locks the row;
        SQLite (test engine) has no FOR UPDATE, and single-writer locking makes
        the same guarantee transactionally."""
        dialect = self.db.bind.dialect.name if self.db.bind is not None else ""
        q = self.db.query(BrandProfile).filter(BrandProfile.id == brand_id)
        if dialect == "postgresql":
            q = q.with_for_update()
        bp = q.first()
        if bp is None:
            raise BrandMembershipError("BRAND_NOT_FOUND", "Brand organization not found.", 404)
        return bp

    def _active_owner_count(self, brand_id: int) -> int:
        return (
            self.db.query(func.count(BrandMembership.id))
            .filter(
                BrandMembership.brand_id == brand_id,
                BrandMembership.status == "active",
                BrandMembership.role == "owner",
            )
            .scalar()
            or 0
        )

    def _require_not_last_owner(self, brand_id: int, membership: BrandMembership) -> None:
        """Removing or demoting the LAST active owner is refused (409).

        Also treats the founder anchor as an owner: if the profile's own user
        still stands, removing another 'owner' row can't orphan governance —
        but when the founder's membership IS the row being touched and it is
        the only active owner, the guard fires (which is the whole point)."""
        if membership.role != "owner":
            return
        if self._active_owner_count(brand_id) <= 1:
            raise BrandMembershipError(
                "LAST_ACTIVE_OWNER",
                "This is the brand's last active owner. Promote another member to "
                "owner first — a brand may never be left without an owner.",
                409,
            )

    def change_member_role(self, *, brand_id: int, membership_id: int,
                           new_role: str, actor: User) -> BrandMembership:
        if new_role not in MEMBERSHIP_ROLES:
            raise BrandMembershipError("INVALID_ROLE", "Unknown membership role.", 422)
        self._brand_row_for_update(brand_id)
        m = self.db.get(BrandMembership, membership_id)
        if m is None or m.brand_id != brand_id:
            # 404, not 403: a cross-tenant probe must not confirm existence.
            raise BrandMembershipError("MEMBER_NOT_FOUND", "Membership not found.", 404)
        if m.status != "active":
            raise BrandMembershipError("MEMBER_INACTIVE",
                                       "Only active members can be modified.", 409)
        if new_role == m.role:
            return m
        if m.role == "owner":
            self._require_not_last_owner(brand_id, m)  # demotion check BEFORE change
        old_role = m.role
        m.role = new_role
        m.updated_at = _utcnow()
        self.db.commit()
        self.db.refresh(m)
        logger.info("brand_member_role_changed brand=%s membership=%s %s->%s actor=%s",
                    brand_id, m.id, old_role, new_role, actor.id)
        return m

    def remove_member(self, *, brand_id: int, membership_id: int,
                      actor: User) -> BrandMembership:
        self._brand_row_for_update(brand_id)
        m = self.db.get(BrandMembership, membership_id)
        if m is None or m.brand_id != brand_id:
            raise BrandMembershipError("MEMBER_NOT_FOUND", "Membership not found.", 404)
        if m.status != "active":
            return m  # idempotent removal of an already-revoked member
        self._require_not_last_owner(brand_id, m)
        m.status = "revoked"
        m.revoked_at = _utcnow()
        m.updated_at = _utcnow()
        self.db.commit()
        self.db.refresh(m)
        logger.info("brand_member_removed brand=%s membership=%s actor=%s",
                    brand_id, m.id, actor.id)
        return m

    def ensure_founder_membership(self, bp: BrandProfile) -> Optional[BrandMembership]:
        """Idempotent founder row for brand provisioning (register + admin
        creation). Existing rows (backfilled or prior call) are returned as-is."""
        if bp.user_id is None:
            return None
        existing = (
            self.db.query(BrandMembership)
            .filter(BrandMembership.brand_id == bp.id,
                    BrandMembership.user_id == bp.user_id)
            .first()
        )
        if existing is not None:
            return existing
        m = BrandMembership(
            brand_id=bp.id, user_id=bp.user_id, role="owner", status="active",
        )
        self.db.add(m)
        try:
            self.db.flush()
        except Exception:
            # Unique-constraint race (another path just created it): benign.
            self.db.rollback()
            return (
                self.db.query(BrandMembership)
                .filter(BrandMembership.brand_id == bp.id,
                        BrandMembership.user_id == bp.user_id)
                .first()
            )
        return m

    # ── invitations ─────────────────────────────────────────────────────
    def create_invitation(self, *, brand_id: int, email: str, role: str,
                          actor: User) -> Dict[str, Any]:
        """Create (or reuse) a pending invitation; returns the RAW token once.

        Idempotency: a repeat request for the same (brand, email) while pending
        returns the same invitation (delivery re-attempt is a separate, daily-
        idempotent email dispatch). If the account is already an ACTIVE member
        of this brand the request is refused with a clear code.
        """
        email = (email or "").strip().lower()
        role = (role or "").strip().lower()
        if role not in MEMBERSHIP_ROLES:
            raise BrandMembershipError("INVALID_ROLE",
                                       "Invitation role must be owner, manager or staff.", 422)
        existing_user = self.db.query(User).filter(User.email == email).first()
        if existing_user is not None:
            already = (
                self.db.query(BrandMembership)
                .filter(BrandMembership.brand_id == brand_id,
                        BrandMembership.user_id == existing_user.id,
                        BrandMembership.status == "active")
                .first()
            )
            if already is not None:
                raise BrandMembershipError(
                    "ALREADY_MEMBER", "That account is already a member of this brand.", 409)

        pending = (
            self.db.query(BrandInvitation)
            .filter(BrandInvitation.brand_id == brand_id,
                    BrandInvitation.email == email,
                    BrandInvitation.status == "pending")
            .first()
        )
        if pending is not None and pending.expires_at > _naive(_utcnow()):
            return {"invitation": pending, "raw_token": None, "created": False}

        if pending is not None:
            # Expired pending row: expire it explicitly, then issue a fresh one.
            pending.status = "expired"
            self.db.flush()

        raw_token = secrets.token_urlsafe(32)
        inv = BrandInvitation(
            brand_id=brand_id,
            email=email,
            role=role,
            token_hash=hash_token(raw_token),
            status="pending",
            invited_by=actor.id,
            expires_at=_naive(_utcnow() + timedelta(days=INVITATION_TTL_DAYS)),
        )
        self.db.add(inv)
        try:
            self.db.commit()
        except Exception:
            # Partial-unique race with a concurrent identical request: fetch
            # and return the winner's pending row instead of double-mailing.
            self.db.rollback()
            winner = (
                self.db.query(BrandInvitation)
                .filter(BrandInvitation.brand_id == brand_id,
                        BrandInvitation.email == email,
                        BrandInvitation.status == "pending")
                .first()
            )
            if winner is not None:
                return {"invitation": winner, "raw_token": None, "created": False}
            raise
        self.db.refresh(inv)
        return {"invitation": inv, "raw_token": raw_token, "created": True}

    def resend_invitation_email(self, *, brand_id: int, invitation_id: int) -> BrandInvitation:
        inv = self.db.get(BrandInvitation, invitation_id)
        if inv is None or inv.brand_id != brand_id or inv.status != "pending":
            raise BrandMembershipError("INVITATION_NOT_FOUND", "No pending invitation with that id.", 404)
        if inv.expires_at <= _naive(_utcnow()):
            inv.status = "expired"
            self.db.commit()
            raise BrandMembershipError("INVITATION_EXPIRED",
                                       "That invitation expired; create a fresh one.", 409)
        return inv

    def list_invitations(self, brand_id: int) -> List[BrandInvitation]:
        return (
            self.db.query(BrandInvitation)
            .filter(BrandInvitation.brand_id == brand_id,
                    BrandInvitation.status.in_(("pending",)))
            .order_by(BrandInvitation.created_at.desc())
            .all()
        )

    def revoke_invitation(self, *, brand_id: int, invitation_id: int,
                          actor: User) -> BrandInvitation:
        inv = self.db.get(BrandInvitation, invitation_id)
        if inv is None or inv.brand_id != brand_id:
            raise BrandMembershipError("INVITATION_NOT_FOUND", "Invitation not found.", 404)
        if inv.status != "pending":
            return inv  # idempotent
        inv.status = "revoked"
        inv.revoked_at = _utcnow()
        self.db.commit()
        self.db.refresh(inv)
        logger.info("brand_invitation_revoked brand=%s inv=%s actor=%s",
                    brand_id, inv.id, actor.id)
        return inv

    def accept_invitation(self, *, raw_token: str, user: User) -> Dict[str, Any]:
        """Consume an invitation for the authenticated user.

        Rejections (unknown/expired/revoked/consumed/email-mismatch) all
        collapse to one code+message pair. The only replay exception: the same
        user re-accepting their own CONSUMED invitation is an idempotent
        success (safe retry behavior) while their membership is still active.
        """
        token_hash = hash_token((raw_token or "").strip())
        inv = (
            self.db.query(BrandInvitation)
            .filter(BrandInvitation.token_hash == token_hash)
            .first()
        )
        denied = BrandMembershipError(
            INVITATION_NOT_APPLICABLE,
            "This invitation is not valid for your account. Ask the brand owner to "
            "send a new invitation.", 400)
        if inv is None:
            raise denied
        email_ok = (user.email or "").strip().lower() == inv.email
        if inv.status == "accepted":
            if email_ok and inv.accepted_by == user.id and user.id and (
                self.db.query(BrandMembership).filter(
                    BrandMembership.user_id == user.id,
                    BrandMembership.brand_id == inv.brand_id,
                    BrandMembership.status == "active").first()
            ):
                return {"brand_id": inv.brand_id, "role": inv.role, "already": True}
            raise denied
        if inv.status != "pending" or not email_ok:
            raise denied
        if inv.expires_at <= _naive(_utcnow()):
            inv.status = "expired"
            self.db.commit()
            raise denied

        self._brand_row_for_update(inv.brand_id)

        # Single-brand invariant: refuse a second concurrent membership with a
        # clear 409 (portal has no brand switcher yet) BEFORE consuming.
        existing = self.active_memberships(user)
        if any(m.brand_id != inv.brand_id for m in existing):
            raise BrandMembershipError(
                "MULTI_BRAND_NOT_SUPPORTED",
                "Your account already belongs to another brand. The partner portal "
                "supports one brand per account today; ask that brand's owner to "
                "remove your membership first.", 409)
        m = next((x for x in existing if x.brand_id == inv.brand_id), None)
        if m is None:
            m = BrandMembership(brand_id=inv.brand_id, user_id=user.id,
                                role=inv.role, status="active",
                                granted_by=inv.invited_by)
            self.db.add(m)
        elif m.status == "revoked":
            m.status = "active"
            m.role = inv.role
            m.revoked_at = None
            m.updated_at = _utcnow()
        # NOTE: users.role is deliberately NOT touched — joining a brand must
        # never promote a consumer's platform role (brief §5.1).

        inv.status = "accepted"
        inv.accepted_by = user.id
        inv.accepted_at = _utcnow()
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise denied
        self.db.refresh(m)
        return {"brand_id": inv.brand_id, "role": m.role, "already": False}
