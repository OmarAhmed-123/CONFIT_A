"""Shared one-time-token primitives (DRY across the auth lifecycle).

Before this module every flow re-implemented issuance/consumption: password
reset, email verification and (later) email change each hand-rolled
``secrets.token_urlsafe`` + ``sha256`` + expiry checks. Duplicated security
primitives drift; these are the shared ones.

Contract enforced here (task §5, §6, §12):
  * 32 bytes of CSPRNG entropy, URL-safe encoding;
  * ONLY the SHA-256 hex digest is persisted — the plaintext token exists in
    memory for the duration of the request and inside the email body;
  * expiry is enforced on every read, in UTC, regardless of the DB's tzinfo;
  * single-use is enforced by a status transition written in the same commit
    that mutates the account, so a replay after a crash window still fails;
  * unknown / expired / already-used tokens are reported to callers as a
    single ``OneTimeTokenError`` with a reason code — callers map that to a
    user-facing message without leaking which case occurred.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple

TOKEN_BYTES = 32


class OneTimeTokenError(Exception):
    """Raised for unknown, expired or already-consumed tokens."""

    def __init__(self, reason: str = "invalid"):
        self.reason = reason  # invalid | expired | used
        super().__init__(reason)


def generate_token() -> str:
    """A fresh 256-bit URL-safe token (43 chars)."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(raw: str) -> str:
    """SHA-256 hex digest of a token — the only form that is persisted."""
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """SQLite returns naive datetimes; treat stored values as UTC always."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def issue_token(
    db,
    *,
    model: Any,
    user_id: int,
    ttl: timedelta,
    extra_fields: Optional[dict] = None,
    token_field: str = "token_hash",
) -> Tuple[Any, str]:
    """Create a token row and return ``(row, plaintext_token)``.

    ``db.commit()`` is intentionally left to the caller so the token row and
    the surrounding state change (e.g. the email-change record) commit
    atomically.
    """
    raw = generate_token()
    row = model(
        user_id=user_id,
        expires_at=utcnow() + ttl,
        **{token_field: hash_token(raw)},
        **(extra_fields or {}),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, raw


def lookup_token(db, *, model: Any, raw: str, token_field: str = "token_hash"):
    """Return the token row or ``None`` (no information leak on the reason)."""
    if not raw or not isinstance(raw, str):
        return None
    return (
        db.query(model)
        .filter(getattr(model, token_field) == hash_token(raw))
        .first()
    )


def assert_usable(row: Any, *, now: Optional[datetime] = None) -> None:
    """Raise ``OneTimeTokenError`` unless the row is present, unused, unexpired."""
    if row is None:
        raise OneTimeTokenError("invalid")
    if getattr(row, "used_at", None) is not None:
        raise OneTimeTokenError("used")
    if _as_utc(row.expires_at) < (now or utcnow()):
        raise OneTimeTokenError("expired")


def consume(db, *, model: Any, raw: str, token_field: str = "token_hash"):
    """Look up + validate + mark ``used_at`` (caller commits with its own change).

    Returns the row. Raises ``OneTimeTokenError`` for invalid/expired/used.
    """
    row = lookup_token(db, model=model, raw=raw, token_field=token_field)
    assert_usable(row)
    row.used_at = utcnow()
    return row


def invalidate_open_tokens(db, *, model: Any, user_id: int, token_field: str = "token_hash") -> int:
    """Invalidate every outstanding (unused) token of a family for one user.

    Used so a second "resend" cannot leave two live tokens, and so issuing a
    new token after a completed flow does not extend an old one's power.
    """
    rows = (
        db.query(model)
        .filter(getattr(model, "user_id") == user_id, getattr(model, "used_at").is_(None))
        .all()
    )
    now = utcnow()
    for row in rows:
        row.used_at = now
    return len(rows)
