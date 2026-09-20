"""Partner lifecycle: applications → admin review → brand provisioning, and
brand invitations (BRD G6 §2.1 "user invitations", §2.2 "partner onboarding
approvals").

Security invariants (task §0.11, §0.12, §8):
  * A consumer's request for brand access creates a PENDING application and
    nothing else. No role, no tenant, no portal access is granted by a
    client-supplied payload.
  * The resulting role/brand is written ONLY by
    :func:`review_application` (platform admin, BRD G6 §2.2) or by
    :func:`accept_invitation` using a server-issued, hashed, single-use,
    expiring invitation token whose role and brand were recorded by the brand
    owner or an admin.
  * Invitations can never be issued with the ``admin`` role, and an invitation
    for one brand cannot be redeemed into another (cross-tenant conflict).
  * Every state change is audited with a request correlation id.
"""
from __future__ import annotations

import re
from datetime import timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    EmailVerificationRequiredError,
    ResourceNotFoundError,
    ValidationDomainError,
)
from backend.app.core.config import settings
from backend.app.core.security import get_password_hash, validate_password_policy
from backend.app.models.user import (
    BrandMember,
    BrandProfile,
    Invitation,
    InvitationStatus,
    PartnerApplication,
    PartnerApplicationStatus,
    RegistrationIntent,
    User,
    UserRole,
)
from backend.app.repositories.user_repository import UserRepository
from backend.app.services import email_service
from backend.app.services import token_service
from backend.app.services.brand_scope_service import member_brand, owned_brand

INVITATION_TTL = timedelta(hours=72)
INVITABLE_ROLES = (UserRole.BRAND_OWNER, UserRole.BRAND_MANAGER, UserRole.BRAND_STAFF)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def _audit(db: Session, user_id: Optional[int], action: str, resource_type: str,
           resource_id: Any, *, request_id: Optional[str] = None,
           details: Optional[dict] = None) -> None:
    import json
    UserRepository(db).log_audit(
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        user_id=user_id,
        request_id=request_id,
        details=json.dumps(details or {}, default=str)[:2000],
    )


def _role_value(role) -> str:
    return role.value if isinstance(role, UserRole) else str(role)


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug or "brand"


def _unique_slug(db: Session, name: str) -> str:
    base = _slugify(name)
    slug, n = base, 1
    while db.query(BrandProfile).filter(BrandProfile.slug == slug).first() is not None:
        n += 1
        slug = f"{base}-{n}"
    return slug


def mask_email(address: str) -> str:
    """`owner@brand.com` → `o***@brand.com` (never echo a full address publicly)."""
    local, _, domain = (address or "").partition("@")
    if not domain:
        return "***"
    keep = local[:1]
    return f"{keep}***@{domain}"


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

def submit_application(
    db: Session,
    user: User,
    payload: Dict[str, Any],
    *,
    request_id: Optional[str] = None,
    email_provider_configured: Optional[bool] = None,
) -> PartnerApplication:
    """Create a PENDING partner application. Grants nothing."""
    if user.role == UserRole.ADMIN:
        raise ConflictError("Platform administrators do not need partner access.", code="ALREADY_PRIVILEGED")
    if _role_value(user.role) in ("brand_owner", "brand_manager", "brand_staff"):
        raise ConflictError(
            "This account already has brand access.", code="ALREADY_PARTNER"
        )

    # --- the verification gate, and the explicit exception to it -----------
    # DECISION (§16, recorded in docs/audits/PHASE_3_6_...): the address must be
    # verified before an application is accepted WHENEVER verification is
    # possible in this deployment. If no email provider is configured then no
    # address can be verified at all (`is_verified` stays False for every
    # account and the verification endpoints answer 501), so requiring it would
    # be a permanent dead end rather than a control. In that case the
    # application is accepted and the *reviewer* is told explicitly that the
    # address is unverified and that verification was unavailable — a human
    # decision replaces an automated check that cannot run. The exception is
    # recorded in the audit trail below, never hidden.
    configured = email_service.is_email_configured() if email_provider_configured is None else email_provider_configured
    verification_unavailable = not configured
    if configured and user.is_verified is not True:
        # The workflow depends on a mailbox we can reach; make the dependency
        # explicit instead of silently accepting an unreachable application.
        raise EmailVerificationRequiredError(
            "Verify your email address before applying for partner access."
        )

    existing = (
        db.query(PartnerApplication)
        .filter(
            PartnerApplication.user_id == user.id,
            PartnerApplication.status == PartnerApplicationStatus.PENDING,
        )
        .first()
    )
    if existing is not None:
        raise ConflictError(
            "A partner application for this account is already in review.",
            code="PARTNER_APPLICATION_PENDING",
            details={"application_id": existing.id, "submitted_at": existing.submitted_at.isoformat()},
        )

    brand_name = (payload.get("brand_name") or "").strip()
    contact_name = (payload.get("contact_name") or user.full_name or "").strip()
    if len(brand_name) < 2:
        raise ValidationDomainError("A brand name is required.", {"brand_name": "required"})
    if len(contact_name) < 2:
        raise ValidationDomainError("A contact name is required.", {"contact_name": "required"})

    application = PartnerApplication(
        user_id=user.id,
        status=PartnerApplicationStatus.PENDING,
        brand_name=brand_name[:255],
        legal_name=(payload.get("legal_name") or None),
        website=(payload.get("website") or None),
        market=(payload.get("market") or "EG")[:8],
        category=(payload.get("category") or None),
        catalogue_size=(payload.get("catalogue_size") or None),
        contact_name=contact_name[:255],
        # The account address is authoritative; a free-text address on the form
        # must never become the identity the decision is emailed to.
        contact_email=user.email,
        contact_phone=(payload.get("contact_phone") or user.phone),
        message=(payload.get("message") or None),
        request_id=request_id,
    )
    db.add(application)
    try:
        db.commit()
    except IntegrityError:
        # Partial unique index lost the race with a concurrent submit.
        db.rollback()
        raise ConflictError("A partner application for this account is already in review.", code="PARTNER_APPLICATION_PENDING")
    db.refresh(application)

    _audit(db, user.id, "PARTNER_APPLICATION_SUBMITTED", "PartnerApplication", application.id,
           request_id=request_id,
           details={
               "brand_name": application.brand_name,
               "market": application.market,
               # Recorded so the accepted-without-verification exception (§16) is
               # auditable after the fact instead of being invisible.
               "email_verified": bool(user.is_verified),
               "verification_unavailable": verification_unavailable,
           })

    if email_service.is_email_configured():
        subject, html, text = email_service.render_partner_application_received_email(
            user.full_name or "", application.brand_name
        )
        email_service.send_transactional(
            db,
            to=user.email,
            subject=subject,
            html=html,
            text=text,
            purpose=email_service.PURPOSE_PARTNER_APPLICATION_RECEIVED,
            user_id=user.id,
            dedupe_key=f"app-received:{application.id}",
            request_id=request_id,
        )
    return application


def list_my_applications(db: Session, user: User) -> List[PartnerApplication]:
    return (
        db.query(PartnerApplication)
        .filter(PartnerApplication.user_id == user.id)
        .order_by(PartnerApplication.id.desc())
        .all()
    )


def withdraw_application(db: Session, user: User, application_id: int, *, request_id: Optional[str] = None) -> PartnerApplication:
    application = db.query(PartnerApplication).filter(PartnerApplication.id == application_id).first()
    if application is None or application.user_id != user.id:
        raise ResourceNotFoundError("PartnerApplication", application_id)
    if application.status != PartnerApplicationStatus.PENDING:
        raise ConflictError(
            f"An application in state '{_role_value(application.status)}' cannot be withdrawn.",
            code="INVALID_STATE_TRANSITION",
        )
    application.status = PartnerApplicationStatus.WITHDRAWN
    db.commit()
    db.refresh(application)
    _audit(db, user.id, "PARTNER_APPLICATION_WITHDRAWN", "PartnerApplication", application.id, request_id=request_id)
    return application


def list_applications(db: Session, status: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[PartnerApplication]:
    q = db.query(PartnerApplication)
    if status:
        q = q.filter(PartnerApplication.status == status)
    return q.order_by(PartnerApplication.submitted_at.desc(), PartnerApplication.id.desc()).limit(limit).offset(offset).all()


def review_application(
    db: Session,
    application_id: int,
    reviewer: User,
    *,
    approve: bool,
    note: Optional[str] = None,
    request_id: Optional[str] = None,
) -> PartnerApplication:
    """Approve/reject a pending application. THE trusted provisioning point."""
    application = db.query(PartnerApplication).filter(PartnerApplication.id == application_id).first()
    if application is None:
        raise ResourceNotFoundError("PartnerApplication", application_id)
    if application.status != PartnerApplicationStatus.PENDING:
        raise ConflictError(
            f"This application was already {_role_value(application.status)}.",
            code="APPLICATION_ALREADY_REVIEWED",
        )

    applicant = db.query(User).filter(User.id == application.user_id).first()
    if applicant is None:
        raise ResourceNotFoundError("User", application.user_id)

    if approve:
        if _role_value(applicant.role) not in ("consumer",):
            raise ConflictError(
                "The applicant already holds a privileged role; resolve that manually.",
                code="APPLICANT_NOT_ELIGIBLE",
            )
        try:
            brand, created = _provision_brand(db, applicant, application)
            applicant.role = UserRole.BRAND_OWNER
            application.status = PartnerApplicationStatus.APPROVED
            application.brand_id = brand.id
        except IntegrityError:
            # REAL RACE (PostgreSQL concurrency suite): two admins approved the
            # same application at once; both read `pending` and both provisioned
            # a tenant. The database settled it (`brand_profiles.user_id` is
            # unique). Roll back everything this request wrote, then describe the
            # state we can actually OBSERVE rather than guessing a cause.
            db.rollback()
            fresh = (
                db.query(PartnerApplication)
                .filter(PartnerApplication.id == application_id)
                .first()
            )
            if fresh is not None and _role_value(fresh.status) != "pending":
                raise ConflictError(
                    "This application was reviewed by another administrator.",
                    code="APPLICATION_ALREADY_REVIEWED",
                )
            raise ConflictError(
                "The brand could not be provisioned because another record changed "
                "at the same time. Retry the review.",
                code="PROVISIONING_CONFLICT",
            )
        _audit(db, reviewer.id, "PARTNER_APPLICATION_APPROVED", "PartnerApplication", application.id,
               request_id=request_id,
               details={"brand_id": brand.id, "brand_created": created, "applicant_user_id": applicant.id})
        if created:
            _audit(db, reviewer.id, "PARTNER_BRAND_PROVISIONED", "BrandProfile", brand.id,
                   request_id=request_id, details={"owner_user_id": applicant.id})
    else:
        application.status = PartnerApplicationStatus.REJECTED
        _audit(db, reviewer.id, "PARTNER_APPLICATION_REJECTED", "PartnerApplication", application.id,
               request_id=request_id, details={"applicant_user_id": applicant.id})

    application.reviewed_at = token_service.utcnow()
    application.reviewed_by_user_id = reviewer.id
    application.decision_note = (note or None)
    try:
        db.commit()
    except IntegrityError:
        # Backstop for a race on the final write (status transition / audit).
        db.rollback()
        fresh = db.query(PartnerApplication).filter(PartnerApplication.id == application_id).first()
        if fresh is not None and fresh.status != PartnerApplicationStatus.PENDING:
            raise ConflictError(
                f"This application was already {_role_value(fresh.status)}.",
                code="APPLICATION_ALREADY_REVIEWED",
            )
        raise ConflictError(
            "Another review of this application is in progress; retry in a moment.",
            code="APPLICATION_REVIEW_IN_PROGRESS",
        )
    db.refresh(application)

    if email_service.is_email_configured():
        subject, html, text = email_service.render_partner_application_decision_email(
            applicant.full_name or "",
            application.brand_name,
            approve,
            note or "",
            f"{settings.FRONTEND_BASE_URL.rstrip('/')}/b2b",
        )
        email_service.send_transactional(
            db,
            to=applicant.email,
            subject=subject,
            html=html,
            text=text,
            purpose=email_service.PURPOSE_PARTNER_APPLICATION_DECISION,
            user_id=applicant.id,
            dedupe_key=f"app-decision:{application.id}:{_role_value(application.status)}",
            request_id=request_id,
        )
    return application


def _provision_brand(db: Session, applicant: User, application: PartnerApplication):
    """Create the brand tenant, or attach the applicant to the existing one.

    If a brand with that name already exists on CONFIT the applicant is
    attached to it as owner *by explicit admin decision* — never automatically:
    an approval is a human authorisation recorded in the audit log.
    """
    existing = (
        db.query(BrandProfile)
        .filter(func.lower(BrandProfile.brand_name) == application.brand_name.lower())
        .first()
    )
    owns = owned_brand(db, applicant)
    if owns is not None:
        raise ConflictError("This account already owns a brand profile.", code="BRAND_ALREADY_OWNED")

    if existing is not None:
        membership = (
            db.query(BrandMember)
            .filter(BrandMember.user_id == applicant.id, BrandMember.brand_id == existing.id)
            .first()
        )
        if membership is None:
            db.add(BrandMember(
                user_id=applicant.id,
                brand_id=existing.id,
                role=UserRole.BRAND_OWNER,
                invitation_id=None,
            ))
        return existing, False

    brand = BrandProfile(
        user_id=applicant.id,
        brand_name=application.brand_name[:255],
        slug=_unique_slug(db, application.brand_name),
        description=application.message or None,
        website=application.website or None,
        is_verified=True,
    )
    db.add(brand)
    db.flush()
    return brand, True


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------

def _inviter_may_invite(db: Session, inviter: User, brand_id: int) -> None:
    if inviter.role == UserRole.ADMIN:
        return
    owned = owned_brand(db, inviter)
    if owned is None or owned.id != brand_id:
        raise AuthorizationError(
            "Only the brand owner (or a platform admin) may invite team members."
        )


def create_invitation(
    db: Session,
    inviter: User,
    *,
    brand_id: int,
    email: str,
    role: str,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    email = (email or "").strip().lower()
    if not _EMAIL_RE.match(email):
        raise ValidationDomainError("A valid email address is required.", {"email": "invalid"})

    try:
        invited_role = UserRole((role or "").lower())
    except ValueError:
        raise ValidationDomainError(
            "Role must be one of: brand_owner, brand_manager, brand_staff.",
            {"role": "unsupported"},
        )
    if invited_role not in INVITABLE_ROLES:
        # Escalation guard: an invitation can never mint platform admins.
        raise ValidationDomainError("The admin role cannot be granted by invitation.", {"role": "forbidden"})

    brand = db.query(BrandProfile).filter(BrandProfile.id == brand_id).first()
    if brand is None:
        raise ResourceNotFoundError("BrandProfile", brand_id)
    _inviter_may_invite(db, inviter, brand_id)

    invitee = db.query(User).filter(User.email == email).first()
    if invitee is not None:
        if invitee.role == UserRole.ADMIN:
            raise ConflictError("This address belongs to a platform administrator.", code="INVITEE_NOT_ELIGIBLE")
        existing_brand = owned_brand(db, invitee) or member_brand(db, invitee)
        if existing_brand is not None:
            raise ConflictError(
                "This address already belongs to a brand workspace on CONFIT.",
                code="INVITEE_ALREADY_MEMBER",
                details={"brand_id": existing_brand.id},
            )

    # Re-issuing replaces the previous pending invitation (no dead links, no
    # two live tokens for the same seat).
    now = token_service.utcnow()
    for stale in (
        db.query(Invitation)
        .filter(
            Invitation.email == email,
            Invitation.brand_id == brand_id,
            Invitation.status == InvitationStatus.PENDING,
        )
        .all()
    ):
        stale.status = InvitationStatus.REVOKED
    db.commit()

    raw = token_service.generate_token()
    invitation = Invitation(
        token_hash=token_service.hash_token(raw),
        email=email,
        role=invited_role,
        brand_id=brand_id,
        invited_by_user_id=inviter.id,
        status=InvitationStatus.PENDING,
        expires_at=now + INVITATION_TTL,
        request_id=request_id,
    )
    db.add(invitation)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("An invitation for this address is already pending.", code="INVITATION_ALREADY_PENDING")
    db.refresh(invitation)

    accept_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/invite?token={raw}"
    delivery = None
    if email_service.is_email_configured():
        subject, html, text = email_service.render_partner_invitation_email(
            invitee.full_name if invitee else "",
            brand.brand_name,
            inviter.full_name or "The brand owner",
            _role_value(invited_role),
            accept_url,
            int(INVITATION_TTL.total_seconds() // 3600),
        )
        result = email_service.send_transactional(
            db,
            to=email,
            subject=subject,
            html=html,
            text=text,
            purpose=email_service.PURPOSE_PARTNER_INVITATION,
            user_id=invitee.id if invitee else None,
            dedupe_key=invitation.token_hash,
            request_id=request_id,
        )
        delivery = result.as_dict()

    _audit(db, inviter.id, "PARTNER_INVITATION_SENT", "Invitation", invitation.id,
           request_id=request_id,
           details={"brand_id": brand_id, "role": _role_value(invited_role), "email_masked": mask_email(email),
                    "delivery_status": (delivery or {}).get("status")})

    # The plaintext token is returned to the caller ONLY so the API response can
    # be used by tests/ops tooling in environments without email configured; it
    # is never persisted and never logged.
    return {
        "invitation": invitation,
        "token": raw,
        "accept_path": f"/invite?token={raw}",
        "delivery": delivery,
    }


def list_invitations(db: Session, brand_id: int, *, include_closed: bool = False) -> List[Invitation]:
    q = db.query(Invitation).filter(Invitation.brand_id == brand_id)
    if not include_closed:
        q = q.filter(Invitation.status == InvitationStatus.PENDING)
    return q.order_by(Invitation.id.desc()).all()


def revoke_invitation(db: Session, inviter: User, invitation_id: int, *, request_id: Optional[str] = None) -> Invitation:
    invitation = db.query(Invitation).filter(Invitation.id == invitation_id).first()
    if invitation is None:
        raise ResourceNotFoundError("Invitation", invitation_id)
    _inviter_may_invite(db, inviter, invitation.brand_id)
    if invitation.status != InvitationStatus.PENDING:
        raise ConflictError(
            f"This invitation is already {_role_value(invitation.status)}.",
            code="INVITATION_NOT_PENDING",
        )
    invitation.status = InvitationStatus.REVOKED
    db.commit()
    db.refresh(invitation)
    _audit(db, inviter.id, "PARTNER_INVITATION_REVOKED", "Invitation", invitation.id, request_id=request_id)
    return invitation


def preview_invitation(db: Session, raw_token: str) -> Dict[str, Any]:
    """Public, non-privileged preview so the accept page can render honestly.

    Returns status only — the token itself is never echoed back, and the
    invited address is masked.
    """
    invitation = token_service.lookup_token(db, model=Invitation, raw=raw_token)
    if invitation is None:
        return {"status": "unknown", "valid": False}
    brand = db.query(BrandProfile).filter(BrandProfile.id == invitation.brand_id).first()
    payload = {
        "status": "pending",
        "valid": True,
        "email_masked": mask_email(invitation.email),
        "brand_name": brand.brand_name if brand else None,
        "role": _role_value(invitation.role),
        "expires_at": invitation.expires_at.isoformat() if invitation.expires_at else None,
    }
    if invitation.status == InvitationStatus.ACCEPTED:
        payload.update(status="accepted", valid=False)
    elif invitation.status == InvitationStatus.REVOKED:
        payload.update(status="revoked", valid=False)
    elif token_service._as_utc(invitation.expires_at) < token_service.utcnow():
        payload.update(status="expired", valid=False)
    return payload


def accept_invitation(
    db: Session,
    raw_token: str,
    *,
    full_name: Optional[str] = None,
    password: Optional[str] = None,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Redeem an invitation. The ONLY inputs the invitee controls are their own
    name/password (for a new account); role and brand come from the token row."""
    invitation = token_service.lookup_token(db, model=Invitation, raw=raw_token)
    if invitation is None:
        raise ConflictError("This invitation link is not valid.", code="INVITATION_INVALID")
    if invitation.status == InvitationStatus.ACCEPTED:
        raise ConflictError("This invitation has already been accepted.", code="INVITATION_ALREADY_ACCEPTED")
    if invitation.status == InvitationStatus.REVOKED:
        raise ConflictError("This invitation was revoked. Ask the brand owner for a new one.", code="INVITATION_REVOKED")
    if token_service._as_utc(invitation.expires_at) < token_service.utcnow():
        raise ConflictError("This invitation has expired. Ask the brand owner for a new one.", code="INVITATION_EXPIRED")

    brand = db.query(BrandProfile).filter(BrandProfile.id == invitation.brand_id).first()
    if brand is None:
        raise ConflictError("The brand for this invitation no longer exists.", code="INVITATION_BRAND_MISSING")

    user = db.query(User).filter(User.email == invitation.email).first()
    created_account = False
    if user is None:
        if not full_name or len(full_name.strip()) < 2:
            raise ValidationDomainError("Your full name is required to accept this invitation.", {"full_name": "required"})
        validate_password_policy(password or "")
        user = User(
            email=invitation.email,
            hashed_password=get_password_hash(password),
            full_name=full_name.strip()[:255],
            role=invitation.role,
            registration_intent=RegistrationIntent.BRAND_PARTNER,
            is_active=True,
            # The invitation WAS delivered to this address by the brand owner's
            # action, so the mailbox is proven — no second verification loop.
            is_verified=True,
        )
        db.add(user)
        try:
            db.flush()
        except IntegrityError:
            # REAL RACE (found by the PostgreSQL concurrency suite): two
            # simultaneous acceptances of the same invitation both saw "no
            # account yet" and both tried to create it. `ix_users_email` let
            # exactly one through; the loser must NOT surface as a 500.
            # Re-read the authoritative state and answer precisely.
            db.rollback()
            fresh = token_service.lookup_token(db, model=Invitation, raw=raw_token)
            if fresh is not None and fresh.status == InvitationStatus.ACCEPTED:
                raise ConflictError(
                    "This invitation has already been accepted.",
                    code="INVITATION_ALREADY_ACCEPTED",
                )
            raise ConflictError(
                "Another acceptance of this invitation is in progress; retry in a moment.",
                code="INVITATION_ACCEPTANCE_IN_PROGRESS",
            )
        created_account = True
    else:
        if user.role == UserRole.ADMIN:
            raise ConflictError("This address belongs to a platform administrator.", code="INVITEE_NOT_ELIGIBLE")
        existing_brand = owned_brand(db, user) or member_brand(db, user)
        if existing_brand is not None and existing_brand.id != brand.id:
            raise ConflictError(
                "This account already belongs to a different brand workspace.",
                code="CROSS_TENANT_CONFLICT",
            )
        user.role = invitation.role

    membership = (
        db.query(BrandMember)
        .filter(BrandMember.user_id == user.id, BrandMember.brand_id == brand.id)
        .first()
    )
    if membership is None:
        db.add(BrandMember(
            user_id=user.id,
            brand_id=brand.id,
            role=invitation.role,
            invited_by_user_id=invitation.invited_by_user_id,
            invitation_id=invitation.id,
        ))
    else:
        membership.role = invitation.role

    invitation.status = InvitationStatus.ACCEPTED
    invitation.accepted_at = token_service.utcnow()
    invitation.accepted_by_user_id = user.id
    try:
        db.commit()
    except IntegrityError:
        # Lost the race on a unique constraint (membership or invitation
        # status). Nothing of ours may survive: roll back and report the state
        # the winner produced, never an unhandled 500.
        db.rollback()
        fresh = token_service.lookup_token(db, model=Invitation, raw=raw_token)
        if fresh is not None and fresh.status == InvitationStatus.ACCEPTED:
            raise ConflictError(
                "This invitation has already been accepted.",
                code="INVITATION_ALREADY_ACCEPTED",
            )
        raise ConflictError(
            "Another acceptance of this invitation is in progress; retry in a moment.",
            code="INVITATION_ACCEPTANCE_IN_PROGRESS",
        )
    db.refresh(user)
    db.refresh(invitation)

    _audit(db, user.id, "PARTNER_INVITATION_ACCEPTED", "Invitation", invitation.id,
           request_id=request_id,
           details={"brand_id": brand.id, "role": _role_value(invitation.role), "account_created": created_account})

    return {"user": user, "invitation": invitation, "brand": brand, "account_created": created_account}
