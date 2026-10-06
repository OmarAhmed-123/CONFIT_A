"""Email consent endpoints (spec 15 §8 — consent + one-click unsubscribe).

Two surfaces, two trust models:

* ``/email/preferences`` (GET/PUT) — the signed-in surface. The user id
  comes from the JWT, never from the body. GET also returns the user's own
  live unsubscribe LINKS so the account screen can show exactly what the
  email footers point at (and so end-to-end tests can exercise the real
  token path without intercepting mail).

* ``/email/unsubscribe`` (GET/POST) — the FROM-AN-EMAIL surface. No
  session: the signed, expiring token IS the authentication, scoped to one
  user + one category. GET only VALIDATES (safe for link scanners that
  prefetch URLs — a scanner must never unsubscribe anyone); the state
  change happens on POST, which is exactly the RFC 8058 one-click shape.
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user
from backend.app.core.exceptions import ValidationDomainError
from backend.app.models.user import User
from backend.app.services.email_consent import (
    SWITCHABLE_CATEGORIES,
    UnsubscribeTokenError,
    UnsubscribeTokenExpired,
    get_preferences,
    set_preference,
    unsubscribe_url_for,
    verify_unsubscribe_token,
)

router = APIRouter(tags=["Email Consent"])


class PreferencesUpdate(BaseModel):
    engagement: bool | None = None
    marketing: bool | None = None


class UnsubscribeRequest(BaseModel):
    token: str


def _serialize(row, user_id: int) -> dict:
    return {
        "engagement": bool(row.engagement),
        "marketing": bool(row.marketing),
        # The same links the email footers carry — the account UI shows the
        # truth, not a parallel mechanism.
        "links": {
            "engagement": unsubscribe_url_for(user_id, "engagement"),
            "marketing": unsubscribe_url_for(user_id, "marketing"),
        },
        "categories": {
            "transactional": {
                "switchable": False,
                "reason": "Order receipts, payment and shipping notices are "
                          "facts about your purchases, not promotions.",
            },
            "engagement": {"switchable": True},
            "marketing": {"switchable": True},
        },
    }


@router.get("/email/preferences")
def read_preferences(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return _serialize(get_preferences(db, user.id), user.id)


@router.put("/email/preferences")
def update_preferences(
    payload: PreferencesUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.engagement is None and payload.marketing is None:
        raise ValidationDomainError(
            "Provide at least one of: engagement, marketing."
        )
    if payload.engagement is not None:
        set_preference(db, user.id, "engagement", payload.engagement)
    if payload.marketing is not None:
        set_preference(db, user.id, "marketing", payload.marketing)
    return _serialize(get_preferences(db, user.id), user.id)


@router.get("/email/unsubscribe")
def validate_unsubscribe_token(token: str = Query(..., min_length=1)):
    """Validation only — NO state change on GET (prefetch-safe)."""
    try:
        _uid, category = verify_unsubscribe_token(token)
    except UnsubscribeTokenExpired:
        return {"valid": False, "reason": "expired"}
    except UnsubscribeTokenError:
        return {"valid": False, "reason": "invalid"}
    return {"valid": True, "category": category}


@router.post("/email/unsubscribe")
def one_click_unsubscribe(payload: UnsubscribeRequest, db: Session = Depends(get_db)):
    """RFC 8058-shaped: token-authenticated POST, idempotent, no session."""
    try:
        user_id, category = verify_unsubscribe_token(payload.token)
    except UnsubscribeTokenExpired:
        raise ValidationDomainError(
            "This unsubscribe link has expired. Manage preferences from your "
            "account settings instead."
        )
    except UnsubscribeTokenError:
        raise ValidationDomainError("This unsubscribe link is not valid.")
    row = set_preference(db, user_id, category, False)
    return {
        "status": "unsubscribed",
        "category": category,
        "engagement": bool(row.engagement),
        "marketing": bool(row.marketing),
    }


__all__ = ["router", "SWITCHABLE_CATEGORIES"]
