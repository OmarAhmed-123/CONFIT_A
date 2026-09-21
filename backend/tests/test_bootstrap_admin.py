"""G-12 — a sanctioned, safe way to create the platform's first admin.

``seed_data.py`` creates ``admin@confit.io`` with a publicly known password and
refuses to run in production. Both halves are correct, but nothing replaced it,
so production had no administrator and the audit that started this work could
not exercise the admin surface at all. The alternatives were "edit the database
by hand" or "have no admin".

``backend/scripts/bootstrap_admin.py`` is the sanctioned path. These tests pin
the properties that make it *safe* rather than merely convenient:

* it promotes an **existing, verified, active** account and never creates one;
* it refuses without a strong authorisation token and without ``--confirm``;
* it is idempotent — a retry writes no second escalation row;
* it will not leave the platform with zero admins;
* the promotion is audited, and the token never reaches the audit row.
"""

import os
import uuid

import pytest

from backend.app.models.user import AuditLog, User, UserRole
from backend.scripts.bootstrap_admin import (
    ACTION_PROMOTE,
    ACTION_REVOKE,
    MIN_TOKEN_LENGTH,
    BootstrapRefused,
    _authorise,
    bootstrap_admin,
)
from backend.tests.conftest import TestingSessionLocal

GOOD_TOKEN = "t" * 40


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def subject(db):
    """A verified, active, non-admin account that is cleaned up afterwards."""
    tag = f"bootstrap-{uuid.uuid4().hex[:10]}"
    email = f"{tag}@probe.test"
    user = User(
        email=email,
        hashed_password="not-a-real-hash",
        full_name=tag,
        role=UserRole.CONSUMER,
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    db.commit()
    yield user

    db.query(AuditLog).filter(AuditLog.user_id == user.id).delete(synchronize_session=False)
    db.query(User).filter(User.email == email).delete(synchronize_session=False)
    db.commit()


# --- authorisation ---------------------------------------------------------


def test_no_token_is_refused(monkeypatch):
    monkeypatch.delenv("ADMIN_BOOTSTRAP_TOKEN", raising=False)
    with pytest.raises(BootstrapRefused, match="not set"):
        _authorise(confirm=True)


def test_a_short_token_is_refused(monkeypatch):
    """A guessable token is worse than none: it passes while proving nothing."""
    monkeypatch.setenv("ADMIN_BOOTSTRAP_TOKEN", "short")
    with pytest.raises(BootstrapRefused, match="at least"):
        _authorise(confirm=True)


def test_a_strong_token_without_confirm_is_refused(monkeypatch):
    monkeypatch.setenv("ADMIN_BOOTSTRAP_TOKEN", GOOD_TOKEN)
    with pytest.raises(BootstrapRefused, match="--confirm"):
        _authorise(confirm=False)


def test_a_strong_token_with_confirm_is_accepted(monkeypatch):
    monkeypatch.setenv("ADMIN_BOOTSTRAP_TOKEN", GOOD_TOKEN)
    assert _authorise(confirm=True) is None
    assert MIN_TOKEN_LENGTH >= 32


# --- it promotes, it does not create --------------------------------------


def test_an_unknown_email_is_refused_and_no_user_is_created(db):
    ghost = "nobody-here@probe.test"
    before = db.query(User).count()
    with pytest.raises(BootstrapRefused, match="does not create identities"):
        bootstrap_admin(ghost, db=db)
    assert db.query(User).count() == before


def test_an_unverified_account_is_refused(db, subject):
    subject.is_verified = False
    db.commit()
    with pytest.raises(BootstrapRefused, match="not verified"):
        bootstrap_admin(subject.email, db=db)
    db.refresh(subject)
    assert subject.role == UserRole.CONSUMER


def test_a_deactivated_account_is_refused(db, subject):
    subject.is_active = False
    db.commit()
    with pytest.raises(BootstrapRefused, match="deactivated"):
        bootstrap_admin(subject.email, db=db)
    db.refresh(subject)
    assert subject.role == UserRole.CONSUMER


def test_a_verified_account_is_promoted_and_audited(db, subject):
    outcome, facts = bootstrap_admin(subject.email, db=db)
    assert outcome == "promoted"
    db.refresh(subject)
    assert subject.role == UserRole.ADMIN

    row = (
        db.query(AuditLog)
        .filter(AuditLog.user_id == subject.id, AuditLog.action == ACTION_PROMOTE)
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert row is not None, "the promotion must be audited"
    assert row.resource_type == "User"
    assert '"role": "consumer"' in (row.before_json or "")
    assert "admin" in (row.after_json or "")
    assert row.request_id and row.request_id.startswith("bootstrap-")


def test_promotion_is_idempotent_and_writes_no_second_row(db, subject):
    """A retried run must not manufacture a history of escalations."""
    assert bootstrap_admin(subject.email, db=db)[0] == "promoted"
    outcome, facts = bootstrap_admin(subject.email, db=db)
    assert outcome == "already_admin"
    assert facts["changed"] is False

    rows = (
        db.query(AuditLog)
        .filter(AuditLog.user_id == subject.id, AuditLog.action == ACTION_PROMOTE)
        .count()
    )
    assert rows == 1, f"{rows} escalation rows for one promotion"


def test_the_token_never_reaches_the_audit_row(db, subject, monkeypatch):
    monkeypatch.setenv("ADMIN_BOOTSTRAP_TOKEN", GOOD_TOKEN)
    _authorise(confirm=True)
    bootstrap_admin(subject.email, db=db)
    row = (
        db.query(AuditLog)
        .filter(AuditLog.user_id == subject.id, AuditLog.action == ACTION_PROMOTE)
        .first()
    )
    blob = " ".join(filter(None, [row.details_json, row.before_json, row.after_json]))
    assert GOOD_TOKEN not in blob, "the bootstrap token must never be persisted"


# --- dry run and revocation -----------------------------------------------


def test_dry_run_changes_nothing_and_writes_nothing(db, subject):
    outcome, facts = bootstrap_admin(subject.email, dry_run=True, db=db)
    assert outcome == "would_promote"
    db.refresh(subject)
    assert subject.role == UserRole.CONSUMER
    assert (
        db.query(AuditLog)
        .filter(AuditLog.user_id == subject.id, AuditLog.action == ACTION_PROMOTE)
        .count()
        == 0
    )


def test_revocation_is_audited_and_reversible(db, subject):
    bootstrap_admin(subject.email, db=db)
    outcome, _ = bootstrap_admin(subject.email, revoke=True, db=db)
    assert outcome == "revoked"
    db.refresh(subject)
    assert subject.role != UserRole.ADMIN
    assert (
        db.query(AuditLog)
        .filter(AuditLog.user_id == subject.id, AuditLog.action == ACTION_REVOKE)
        .count()
        == 1
    )
    # and revoking someone who is not an admin is a safe no-op
    assert bootstrap_admin(subject.email, revoke=True, db=db)[0] == "not_admin"


def test_the_last_admin_cannot_be_revoked(db, subject, monkeypatch):
    """Orphaning the platform is worse than refusing one command."""
    bootstrap_admin(subject.email, db=db)
    import backend.scripts.bootstrap_admin as mod

    monkeypatch.setattr(mod, "_count_admins", lambda _db: 1)
    with pytest.raises(BootstrapRefused, match="only active admin"):
        bootstrap_admin(subject.email, revoke=True, db=db)
    db.refresh(subject)
    assert subject.role == UserRole.ADMIN, "the refusal must not have demoted anyone"


def test_a_failed_run_leaves_no_partial_write(db, subject, monkeypatch):
    """If the audit write fails, the role change must roll back with it."""
    from backend.app.repositories.user_repository import UserRepository

    def boom(*args, **kwargs):
        raise RuntimeError("audit write failed")

    monkeypatch.setattr(UserRepository, "log_audit", boom)
    with pytest.raises(RuntimeError, match="audit write failed"):
        bootstrap_admin(subject.email, db=db)
    db.rollback()
    db.refresh(subject)
    assert subject.role == UserRole.CONSUMER, (
        "the role changed but the audit row did not — a state change with no record"
    )
