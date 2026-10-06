"""Consent resolution + signed unsubscribe links (spec 15 §8/§9).

Token design ("links signed/expiring where needed", §9):

    v1.<base64url(json {uid, cat, exp})>.<hex hmac-sha256>

* The signing key is DERIVED with a dedicated label from the strongest
  secret the deployment has (AUDIT_HMAC_KEY first, SECRET_KEY otherwise) —
  never used raw, so an email-link token can never be replayed against the
  audit chain or JWTs, and vice versa.
* ``exp`` makes every link self-expiring (default 60 days — long enough
  for an inbox, short enough to bound abuse of a leaked link).
* The payload names the CATEGORY, so an engagement unsubscribe link can
  never silence transactional mail, and a tampered category fails the HMAC.

One-click unsubscribe (RFC 8058) needs exactly this shape: a POST with no
session that authenticates by the token alone.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.models.email_preference import EmailPreference

SWITCHABLE_CATEGORIES = ("engagement", "marketing")
_TOKEN_VERSION = "v1"
_DERIVE_LABEL = b"confit-email-links-v1"
DEFAULT_TTL_SECONDS = 60 * 24 * 3600  # 60 days


class UnsubscribeTokenError(Exception):
    """Invalid, tampered or malformed token."""


class UnsubscribeTokenExpired(UnsubscribeTokenError):
    """Structurally valid and authentic, but past its exp."""


def _link_key() -> bytes:
    base = (settings.AUDIT_HMAC_KEY or "").strip() or settings.SECRET_KEY
    return hmac.new(base.encode("utf-8"), _DERIVE_LABEL, hashlib.sha256).digest()


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def make_unsubscribe_token(
    user_id: int, category: str, ttl_seconds: int = DEFAULT_TTL_SECONDS
) -> str:
    if category not in SWITCHABLE_CATEGORIES:
        raise UnsubscribeTokenError(
            f"Category '{category}' has no unsubscribe switch "
            f"(switchable: {', '.join(SWITCHABLE_CATEGORIES)})."
        )
    payload = _b64e(
        json.dumps(
            {"uid": int(user_id), "cat": category, "exp": int(time.time()) + ttl_seconds},
            separators=(",", ":"),
        ).encode("utf-8")
    )
    body = f"{_TOKEN_VERSION}.{payload}"
    sig = hmac.new(_link_key(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_unsubscribe_token(token: str) -> tuple[int, str]:
    """Return (user_id, category) or raise. Never guesses."""
    parts = (token or "").split(".")
    if len(parts) != 3 or parts[0] != _TOKEN_VERSION:
        raise UnsubscribeTokenError("Malformed unsubscribe token.")
    body = f"{parts[0]}.{parts[1]}"
    expected = hmac.new(_link_key(), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, parts[2]):
        raise UnsubscribeTokenError("Unsubscribe token signature mismatch.")
    try:
        data = json.loads(_b64d(parts[1]))
        uid, cat, exp = int(data["uid"]), str(data["cat"]), int(data["exp"])
    except Exception as exc:  # noqa: BLE001 — any shape problem is the same answer
        raise UnsubscribeTokenError("Unsubscribe token payload unreadable.") from exc
    if cat not in SWITCHABLE_CATEGORIES:
        raise UnsubscribeTokenError("Unsubscribe token category unknown.")
    if time.time() > exp:
        raise UnsubscribeTokenExpired("Unsubscribe link expired.")
    return uid, cat


def unsubscribe_url_for(user_id: int, category: str) -> str:
    base = settings.FRONTEND_BASE_URL.rstrip("/")
    return f"{base}/email/unsubscribe?token={make_unsubscribe_token(user_id, category)}"


# ---------------------------------------------------------------------------
# Preference store
# ---------------------------------------------------------------------------

def get_preferences(db: Session, user_id: int) -> EmailPreference:
    """Lazy row-per-user; defaults are all-allowed (opt-OUT model)."""
    row = (
        db.query(EmailPreference)
        .filter(EmailPreference.user_id == user_id)
        .first()
    )
    if row is None:
        row = EmailPreference(user_id=user_id, engagement=True, marketing=True)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def set_preference(db: Session, user_id: int, category: str, allowed: bool) -> EmailPreference:
    if category not in SWITCHABLE_CATEGORIES:
        raise UnsubscribeTokenError(
            f"Category '{category}' is not switchable."
        )
    row = get_preferences(db, user_id)
    setattr(row, category, bool(allowed))
    db.commit()
    db.refresh(row)
    return row


def is_allowed(db: Session, user_id: int, category: str) -> bool:
    """Transactional is always allowed; switchable categories consult the row."""
    if category not in SWITCHABLE_CATEGORIES:
        return True
    row = get_preferences(db, user_id)
    return bool(getattr(row, category))
