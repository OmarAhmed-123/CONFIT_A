"""User Style Profile (USP) & Account-Context endpoints — Group 1 §5.4/§17/§26/§27/§33.

Prior state had three critical faults which are ALL fixed here:
  1. `user_id = user.id if user else 1` fell through to user #1 for every
     unauthenticated request → anonymous read + write of a real user's
     encrypted body_attributes. Now every `/profile/*` and `/me/*` endpoint
     requires authentication (`Depends(get_current_user)`) and 401s otherwise.
  2. `GET /profile/me` used to synthesize a "default" USP and WRITE IT to the
     database on a missing profile — a fabricated preference set the user
     never chose. Now it returns 200 with an explicit "not_completed" state
     so the frontend can route to onboarding; creation only ever happens
     through an explicit onboarding POST/PATCH.
  3. `/me/consents` was a hardcoded object + no-op echo. Now GET reads and
     PATCH persists to the existing `user_style_profiles.privacy_consent_*`
     columns transactionally, with a domain-typed schema and audit event.
"""
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user
from backend.app.core.logging import logger
from backend.app.models.user import User
from backend.app.repositories.user_repository import UserRepository
from backend.app.services.profile_service import ProfileService
from backend.app.services.auth_service import AuthService
from backend.app.schemas.profile import (
    ConsentState,
    ConsentUpdate,
    BodyAttributesInput,
    BodyAttributesOutput,
    StylePreferencesInput,
    BudgetPreferencesInput,
    BrandPreferencesInput,
    OccasionPreferencesInput,
    SizeFitPreferencesInput,
    OnboardingQuizInput,
    USPResponse,
)

router = APIRouter(tags=["User Style Profile (USP) & Account Context"])


# -----------------------------------------------------------------------------
# Primary USP routes
# -----------------------------------------------------------------------------
@router.get("/profile/me")
def get_user_usp(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Return the authenticated user's USP.

    Never writes on a missing profile — see class-level notes. Returns an
    explicit not_completed state so the frontend can decide to redirect to
    /onboarding. Cross-user access is impossible: the user identity comes
    from the JWT subject via `get_current_user`, never from a request param.
    """
    service = ProfileService(db)
    usp = service.get_profile(user.id)
    if usp is None:
        return {
            "user_id": user.id,
            "onboarding_completed": False,
            "state": "not_completed",
            "message": "No style profile yet. Complete onboarding to create one.",
        }
    return usp


@router.post("/profile/onboarding-quiz", response_model=USPResponse)
def submit_onboarding_quiz(
    request: Request,
    payload: OnboardingQuizInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Persist the full 5-step wizard payload for the authenticated user.

    - Runs in a single transaction (via the repository's `create_or_update_profile`).
    - Body attributes are OPTIONAL: `payload.body_attributes is None` means
      the user skipped step 3 — the DB stores NULL, never fabricated numbers.
    - `onboarding_completed=True` is set atomically alongside the payload.
    """
    service = ProfileService(db)
    result = service.save_quiz_and_preferences(user.id, payload.model_dump(exclude_unset=True))
    UserRepository(db).log_audit(
        "ONBOARDING_COMPLETED",
        "UserStyleProfile",
        str(user.id),
        user_id=user.id,
        ip_address=(request.client.host if request.client else None),
    )
    return result


# -----------------------------------------------------------------------------
# Split PATCH endpoints — Group 1 §31: separate DTOs so an update to one
# concern (e.g. body attributes) cannot accidentally overwrite unrelated
# fields (budget, brands) with schema defaults.
# -----------------------------------------------------------------------------
@router.patch("/me/style-profile", response_model=USPResponse)
def patch_style_preferences(
    payload: StylePreferencesInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ProfileService(db)
    return service.save_quiz_and_preferences(user.id, payload.model_dump(exclude_unset=True))


@router.patch("/me/body-profile", response_model=USPResponse)
def patch_body_attributes(
    payload: BodyAttributesInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update ONLY the encrypted body attributes for the authenticated user.

    Fields that the caller does not send are preserved server-side. The
    encryption path is the existing Fernet helper; failures now raise
    EncryptionError instead of leaking ciphertext.
    """
    service = ProfileService(db)
    return service.save_quiz_and_preferences(user.id, {"body_attributes": payload.model_dump(exclude_unset=True)})


@router.delete("/me/body-profile")
def delete_body_attributes(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Group 1 §18: real "delete my measurements" flow, distinct from
    account deletion. Nulls the encrypted_body_data column."""
    service = ProfileService(db)
    service.delete_body_attributes(user.id)
    UserRepository(db).log_audit(
        "BODY_ATTRIBUTES_DELETED", "UserStyleProfile", str(user.id), user_id=user.id
    )
    return {"status": "success", "message": "Body attributes deleted."}


@router.patch("/me/budget", response_model=USPResponse)
def patch_budget(
    payload: BudgetPreferencesInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ProfileService(db)
    return service.save_quiz_and_preferences(user.id, payload.model_dump(exclude_unset=True))


@router.patch("/me/brands", response_model=USPResponse)
def patch_brand_preferences(
    payload: BrandPreferencesInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ProfileService(db)
    return service.save_quiz_and_preferences(user.id, payload.model_dump(exclude_unset=True))


@router.patch("/me/occasions", response_model=USPResponse)
def patch_occasion_preferences(
    payload: OccasionPreferencesInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ProfileService(db)
    return service.save_quiz_and_preferences(user.id, payload.model_dump(exclude_unset=True))


@router.patch("/me/size-fit", response_model=USPResponse)
def patch_size_fit(
    payload: SizeFitPreferencesInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ProfileService(db)
    return service.save_quiz_and_preferences(user.id, payload.model_dump(exclude_unset=True))


# Legacy PUT/PATCH /profile/preferences — kept for the existing frontend
# call site (`profileService.updateProfile`). Accepts the full onboarding
# payload so old clients continue to work; new code should call the split
# endpoints above.
@router.put("/profile/preferences", response_model=USPResponse)
@router.patch("/profile/preferences", response_model=USPResponse)
def update_preferences(
    payload: OnboardingQuizInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ProfileService(db)
    return service.save_quiz_and_preferences(user.id, payload.model_dump(exclude_unset=True))


# -----------------------------------------------------------------------------
# Composite /me — used by the frontend header/profile-page bootstrap.
# -----------------------------------------------------------------------------
@router.get("/me", response_model=Dict[str, Any])
def get_me_composite(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    service = ProfileService(db)
    usp = service.get_profile(user.id)
    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "phone": user.phone,
            "preferred_language": user.preferred_language,
            "is_active": user.is_active,
            "mfa_enabled": user.mfa_enabled,
            "has_profile": usp is not None,
        },
        "style_profile": usp,
    }


@router.patch("/me/profile", response_model=Dict[str, Any])
def patch_me_profile(payload: Dict[str, Any], user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Update basic account attributes on the authenticated user's own row.

    Explicit allow-list of mutable fields — the user cannot escalate their
    role or reactivate a deactivated account by passing extra keys.
    """
    ALLOWED = {"full_name", "phone", "preferred_language"}
    changed = False
    for key in ALLOWED:
        if key in payload and payload[key] is not None:
            setattr(user, key, payload[key])
            changed = True
    if changed:
        db.commit()
    return {"status": "success", "user_id": user.id, "updated": changed}


# -----------------------------------------------------------------------------
# Consent — Group 1 §17 real persistence
# -----------------------------------------------------------------------------
@router.get("/me/consents", response_model=ConsentState)
def get_me_consents(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    service = ProfileService(db)
    return service.get_consents(user.id)


@router.patch("/me/consents", response_model=ConsentState)
def patch_me_consents(
    request: Request,
    payload: ConsentUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ProfileService(db)
    updated = service.update_consents(user.id, payload.model_dump(exclude_unset=True))
    UserRepository(db).log_audit(
        "CONSENT_CHANGED",
        "UserStyleProfile",
        str(user.id),
        user_id=user.id,
        ip_address=(request.client.host if request.client else None),
        details=",".join(f"{k}={v}" for k, v in payload.model_dump(exclude_unset=True).items()),
    )
    return updated


# -----------------------------------------------------------------------------
# GDPR export & account deletion
# -----------------------------------------------------------------------------
@router.post("/me/export")
def post_me_export(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return AuthService(db).export_gdpr_data(user)


@router.delete("/me")
def delete_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthService(db).delete_account(user)
    return {"status": "success", "message": "Account deleted."}
