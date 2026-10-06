"""Per-user email consent (spec 15 §8 — respect consent and unsubscribe).

One row per user, created lazily on first read. Two switchable categories:

    engagement  saved looks, outfit ready, fit results
    marketing   price drops, newsletter

TRANSACTIONAL mail (order receipts, payment failures, shipping, partner
approvals, admin alerts) is deliberately NOT represented here: a shopper
cannot opt out of being told what happened to their money or their order,
and offering that switch would only manufacture disputes. This mirrors the
template registry's category assignment in ``email_templates.TEMPLATES``.

The table stores booleans only — never tokens, never addresses (the user's
address lives on ``users``); nothing here is a secret.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer

from backend.app.core.database import Base


class EmailPreference(Base):
    __tablename__ = "email_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    engagement = Column(Boolean, nullable=False, default=True)
    marketing = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
