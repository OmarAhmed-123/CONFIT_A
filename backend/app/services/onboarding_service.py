"""Server-authoritative onboarding / account state machine (task §4).

The 403 in the incident screenshot existed because the ONLY onboarding state
the server ever exposed was ``has_profile``. Routing therefore could not see
"email not verified", "partner application pending", "suspended", … and the
frontend had to guess — ending in a dead-end page.

This module is the single source of truth. Both the API payload
(``UserOut.onboarding``) and the dedicated ``GET /auth/onboarding-state``
endpoint are built from :func:`build_onboarding_state`, so the frontend can
route deterministically while the backend stays authoritative about what is
allowed.

States
------
``SUSPENDED``                  account deactivated — nothing is allowed
``EMAIL_VERIFICATION_REQUIRED`` provider configured and the address is unverified
``PARTNER_APPLICATION_PENDING`` a brand access request is being reviewed
``PARTNER_ACCESS_REQUIRED``     alias, in a
``ONBOARDING_REQUIRED``         consumer without a style profile
``ACTIVE``                      nothing is outstanding

``next_action`` is what the user should do next (and where the SPA should send
them). It is derived from server state only — no client hint may influence it.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.app.models.user import (
    Invitation,
    InvitationStatus,
    PartnerApplication,
    PartnerApplicationStatus,
    RegistrationIntent,
    User,
    UserRole,
)

BRAND_ROLE_VALUES = ("brand_owner", "brand_manager", "brand_staff")

#: Ordered state vocabulary — also the client's allowed values.
STATE_SUSPENDED = "SUSPENDED"
STATE_EMAIL_VERIFICATION_REQUIRED = "EMAIL_VERIFICATION_REQUIRED"
STATE_PARTNER_APPLICATION_PENDING = "PARTNER_APPLICATION_PENDING"
STATE_ONBOARDING_REQUIRED = "ONBOARDING_REQUIRED"
STATE_ACTIVE = "ACTIVE"


def _role_value(user: User) -> str:
    role = user.role
    return role.value if isinstance(role, UserRole) else str(role)


def is_brand_role(user: User) -> bool:
    return _role_value(user) in BRAND_ROLE_VALUES


def is_admin(user: User) -> bool:
    return _role_value(user) == UserRole.ADMIN.value


def latest_application(db, user_id: int) -> Optional[PartnerApplication]:
    return (
        db.query(PartnerApplication)
        .filter(PartnerApplication.user_id == user_id)
        .order_by(PartnerApplication.id.desc())
        .first()
    )


def pending_invitation_for_email(db, email: str) -> Optional[Invitation]:
    return (
        db.query(Invitation)
        .filter(Invitation.email == (email or "").lower(), Invitation.status == InvitationStatus.PENDING)
        .order_by(Invitation.id.desc())
        .first()
    )


def build_onboarding_state(
    db,
    user: User,
    *,
    email_provider_configured: bool,
    application: Optional[PartnerApplication] = None,
    include_routes: bool = True,
) -> Dict[str, Any]:
    """Compute the account state + next action for one user.

    ``db`` is only used to look up the partner application when the caller did
    not already load it (avoids an extra query on hot paths that pass it in).
    """
    role = _role_value(user)
    intent = getattr(user, "registration_intent", None)
    intent_value = intent.value if isinstance(intent, RegistrationIntent) else (str(intent) if intent else RegistrationIntent.CONSUMER.value)

    if application is None:
        application = latest_application(db, user.id)

    app_status = None
    if application is not None:
        app_status = application.status.value if isinstance(application.status, PartnerApplicationStatus) else str(application.status)

    invitation = None if is_brand_role(user) or is_admin(user) else pending_invitation_for_email(db, user.email)
    invitation_payload = None
    if invitation is not None:
        invitation_payload = {
            "id": invitation.id,
            "brand_id": invitation.brand_id,
            "role": invitation.role.value if isinstance(invitation.role, UserRole) else str(invitation.role),
            "expires_at": invitation.expires_at.isoformat() if invitation.expires_at else None,
        }

    # --- state resolution (order is the priority order) ---------------------
    if not user.is_active:
        state = STATE_SUSPENDED
        next_action = {"type": "contact_support", "route": None, "label": "Contact support about this account"}
    elif email_provider_configured and user.is_verified is not True:
        state = STATE_EMAIL_VERIFICATION_REQUIRED
        next_action = {"type": "verify_email", "route": "/verify-email", "label": "Verify your email address"}
    elif app_status == PartnerApplicationStatus.PENDING.value:
        state = STATE_PARTNER_APPLICATION_PENDING
        next_action = {"type": "await_partner_review", "route": "/partner/status", "label": "Partner application in review"}
    elif is_admin(user):
        state = STATE_ACTIVE
        next_action = {"type": "none", "route": "/admin", "label": "Open platform governance"}
    elif is_brand_role(user):
        # Brand members are not routed through the consumer style quiz.
        state = STATE_ACTIVE
        next_action = {"type": "none", "route": "/b2b", "label": "Open the brand portal"}
    elif invitation_payload is not None:
        state = STATE_ACTIVE
        next_action = {"type": "accept_invitation", "route": f"/invite?token_pending=1", "label": "You have a brand invitation"}
    elif intent_value == RegistrationIntent.BRAND_PARTNER.value:
        state = STATE_ACTIVE
        next_action = {"type": "apply_for_partner", "route": "/partner/apply", "label": "Apply for partner access"}
    elif not has_completed_profile(user):
        state = STATE_ONBOARDING_REQUIRED
        next_action = {"type": "complete_profile", "route": "/profile?onboarding=1", "label": "Complete your style profile"}
    else:
        state = STATE_ACTIVE
        next_action = {"type": "none", "route": "/", "label": "Browse CONFIT"}

    payload: Dict[str, Any] = {
        "account_state": state,
        "role": role,
        "registration_intent": intent_value,
        "email_verified": bool(user.is_verified),
        "is_active": bool(user.is_active),
        "profile_completed": has_completed_profile(user),
        "partner_application_status": app_status,
        "partner_access": _partner_access(role, app_status),
        "next_action": next_action,
    }
    if invitation_payload is not None:
        payload["pending_invitation"] = invitation_payload
    if include_routes:
        payload["allowed_areas"] = _allowed_areas(role)
    return payload


def has_completed_profile(user: User) -> bool:
    """A completed style profile — the only consumer onboarding artefact."""
    try:
        return bool(user.profile is not None)
    except Exception:  # detached instance / lazy-load outside a session
        return False


def _partner_access(role: str, app_status: Optional[str]) -> str:
    if role in BRAND_ROLE_VALUES:
        return "approved"
    if role == UserRole.ADMIN.value:
        return "admin"
    if app_status == PartnerApplicationStatus.PENDING.value:
        return "pending"
    if app_status == PartnerApplicationStatus.REJECTED.value:
        return "rejected"
    return "none"


def _allowed_areas(role: str) -> List[str]:
    if role == UserRole.ADMIN.value:
        return ["storefront", "b2b", "admin"]
    if role in BRAND_ROLE_VALUES:
        return ["storefront", "b2b"]
    return ["storefront"]
