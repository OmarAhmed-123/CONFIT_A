"""A sanctioned, safe way to provision a partner (brand) role.

``bootstrap_admin.py`` (G-12) closed the gap for ``admin``, but left the
identical gap open for the partner roles: ``POST /auth/register`` hard-codes
``CONSUMER``, and ``seed_data.py`` refuses to run in production — correctly,
because a production database must never gain ``brand@cos.com`` with the
publicly known ``Password123!``. Nothing replaced it, so the only ways to get a
production brand account were "edit tenant rows by hand" or "have none".

Editing rows by hand is how you get a user whose ``role`` says
``brand_manager`` while ``brand_profiles`` has no row for them — precisely the
tenant-less state that makes the partner portal fail every request.

These tests pin the properties that make ``bootstrap_role.py`` *safe* rather
than merely convenient:

* it provisions an **existing, verified, active** account and never creates one;
* it refuses without a strong authorisation token and without ``--confirm``;
* a partner role and its tenant row are written **atomically** — there is no
  window where the role is granted and the profile is missing;
* it refuses to grant a partner role without a brand name to attach;
* it is idempotent — a retry writes no second escalation row;
* it will not leave the platform with zero admins, and will not delete a
  brand's profile as a side effect of a role change;
* the change is audited, and the token never reaches the audit row.
"""

import json
import os
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base
from backend.app.models.user import AuditLog, BrandProfile, User, UserRole
from backend.scripts.bootstrap_role import (
    ACTION_PROVISION,
    ACTION_REVOKE,
    MIN_TOKEN_LENGTH,
    BootstrapRefused,
    _authorise,
    _slugify,
    bootstrap_role,
)

GOOD_TOKEN = "t" * 40

#: Unique per test module run so a committed row can never collide with another.
BRAND = f"Acme Studio {uuid.uuid4().hex[:8]}"
#: A different string that normalises to the same slug as BRAND.
BRAND_VARIANT = BRAND.replace(" ", "-").upper()


@pytest.fixture
def db(tmp_path):
    """A throwaway database, deliberately NOT the seeded test database.

    ``bootstrap_role`` commits by design — a provisioning tool that could not
    commit would be pointless — so tests sharing the seeded database leak rows
    into one another: a brand name created by one test makes the next test's
    duplicate check fire, and the seeded ``admin@confit.io`` means "this is the
    only admin" is never true. A private database per test makes both
    deterministic and leaves the seeded fixture for the tests that want it.
    """
    engine = create_engine(f"sqlite:///{tmp_path / f'bootstrap-role-{uuid.uuid4().hex}.db'}")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def subject(db):
    """A verified, active consumer account, cleaned up afterwards."""
    tag = f"roleboot-{uuid.uuid4().hex[:10]}"
    user = User(
        email=f"{tag}@probe.test",
        hashed_password="not-a-real-hash",
        full_name=tag,
        role=UserRole.CONSUMER,
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    db.commit()
    # No teardown: `db` disposes of the whole database after each test, so
    # there is nothing to clean up — and cleanup after the session is closed
    # would only fail on an expired attribute.
    yield user


@pytest.fixture
def authorised(monkeypatch):
    monkeypatch.setenv("ROLE_BOOTSTRAP_TOKEN", GOOD_TOKEN)


# --------------------------------------------------------------------------
# authorisation
# --------------------------------------------------------------------------

def test_no_token_is_refused(monkeypatch):
    monkeypatch.delenv("ROLE_BOOTSTRAP_TOKEN", raising=False)
    with pytest.raises(BootstrapRefused, match="ROLE_BOOTSTRAP_TOKEN is not set"):
        _authorise(confirm=True)


def test_short_token_is_refused(monkeypatch):
    monkeypatch.setenv("ROLE_BOOTSTRAP_TOKEN", "t" * (MIN_TOKEN_LENGTH - 1))
    with pytest.raises(BootstrapRefused, match="at least"):
        _authorise(confirm=True)


def test_without_confirm_is_refused(authorised):
    with pytest.raises(BootstrapRefused, match="--confirm"):
        _authorise(confirm=False)


def test_valid_token_and_confirm_pass(authorised):
    _authorise(confirm=True)  # must not raise


# --------------------------------------------------------------------------
# the account must already exist and be trustworthy
# --------------------------------------------------------------------------

def test_unknown_email_is_refused(db, authorised):
    with pytest.raises(BootstrapRefused, match="no account exists"):
        bootstrap_role("nobody@probe.test", role="brand_manager", dry_run=True, db=db)


def test_inactive_account_is_refused(db, authorised, subject):
    subject.is_active = False
    db.commit()
    with pytest.raises(BootstrapRefused, match="deactivated"):
        bootstrap_role(subject.email, role="brand_manager", dry_run=True, db=db)


def test_unverified_account_is_refused(db, authorised, subject):
    subject.is_verified = False
    db.commit()
    with pytest.raises(BootstrapRefused, match="has not verified"):
        bootstrap_role(subject.email, role="brand_manager", dry_run=True, db=db)


def test_unknown_role_is_refused(db, authorised, subject):
    with pytest.raises(BootstrapRefused, match="unknown role"):
        bootstrap_role(subject.email, role="superuser", dry_run=True, db=db)


# --------------------------------------------------------------------------
# the tenant row is the whole point
# --------------------------------------------------------------------------

def test_partner_role_without_brand_name_is_refused(db, authorised, subject):
    """A partner role with no tenant is the broken state this script prevents."""
    with pytest.raises(BootstrapRefused, match="--brand-name"):
        bootstrap_role(subject.email, role="brand_manager", dry_run=True, db=db)


def test_provision_creates_role_and_tenant_together(db, authorised, subject):
    outcome, facts = bootstrap_role(
        subject.email, role="brand_manager", brand_name=BRAND, db=db
    )
    assert outcome == "provisioned"
    db.refresh(subject)
    assert subject.role == UserRole.BRAND_MANAGER

    profile = db.query(BrandProfile).filter(BrandProfile.user_id == subject.id).first()
    assert profile is not None, "the tenant row must exist, not just the role"
    assert profile.brand_name == BRAND
    assert profile.slug == _slugify(BRAND)
    assert facts["profile"] == "created"


def test_dry_run_writes_nothing(db, authorised, subject):
    bootstrap_role(
        subject.email, role="brand_manager", brand_name=BRAND, dry_run=True, db=db
    )
    db.refresh(subject)
    assert subject.role == UserRole.CONSUMER
    assert db.query(BrandProfile).filter(BrandProfile.user_id == subject.id).first() is None


def test_admin_role_needs_no_tenant(db, authorised, subject):
    outcome, _ = bootstrap_role(subject.email, role="admin", db=db)
    assert outcome == "provisioned"
    db.refresh(subject)
    assert subject.role == UserRole.ADMIN
    assert db.query(BrandProfile).filter(BrandProfile.user_id == subject.id).first() is None


def test_duplicate_brand_name_is_refused(db, authorised, subject):
    bootstrap_role(subject.email, role="brand_manager", brand_name=BRAND, db=db)
    other = User(
        email=f"other-{uuid.uuid4().hex[:8]}@probe.test",
        hashed_password="x",
        full_name="Other Account",
        role=UserRole.CONSUMER,
        is_active=True,
        is_verified=True,
    )
    db.add(other)
    db.commit()
    with pytest.raises(BootstrapRefused, match="already exists"):
        bootstrap_role(other.email, role="brand_manager", brand_name=BRAND, db=db)


def test_slug_collision_gets_a_suffix(db, authorised, subject):
    """A *different* brand name that slugifies to the same slug gets -2.

    brand_name is UNIQUE, so two brands cannot share a name — this is not
    reachable by repeating a name (that is refused outright, see
    test_duplicate_brand_name_is_refused). It is reachable when two distinct
    names normalise to the same slug, which is exactly why the suffix exists.
    """
    bootstrap_role(subject.email, role="brand_manager", brand_name=BRAND, db=db)
    other = User(
        email=f"other-{uuid.uuid4().hex[:8]}@probe.test",
        hashed_password="x",
        full_name="Other Account",
        role=UserRole.CONSUMER,
        is_active=True,
        is_verified=True,
    )
    db.add(other)
    db.commit()
    bootstrap_role(other.email, role="brand_staff", brand_name=BRAND_VARIANT, db=db)
    profile = db.query(BrandProfile).filter(BrandProfile.user_id == other.id).first()
    assert profile.slug == f"{_slugify(BRAND)}-2"


def test_slugify_is_url_safe():
    assert _slugify("Acme Studio") == "acme-studio"
    assert _slugify("  COS & Co.  ") == "cos-co"
    assert _slugify("عربية") == "brand"  # no ASCII survives -> a usable fallback


# --------------------------------------------------------------------------
# idempotence and audit
# --------------------------------------------------------------------------

def test_second_run_is_a_no_op_with_no_second_audit_row(db, authorised, subject):
    bootstrap_role(subject.email, role="brand_manager", brand_name=BRAND, db=db)
    outcome, facts = bootstrap_role(
        subject.email, role="brand_manager", brand_name=BRAND, db=db
    )
    assert outcome == "unchanged"
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.user_id == subject.id, AuditLog.action == ACTION_PROVISION)
        .count()
    )
    assert rows == 1, "a retried run must not manufacture a history of escalations"


def test_provision_is_audited_without_the_token(db, authorised, subject):
    bootstrap_role(subject.email, role="brand_manager", brand_name=BRAND, db=db)
    row = (
        db.query(AuditLog)
        .filter(AuditLog.user_id == subject.id, AuditLog.action == ACTION_PROVISION)
        .first()
    )
    assert row is not None
    # before_json / after_json / details_json are JSON *text* columns — the
    # model has no `before` / `after` / `details` attribute.
    assert json.loads(row.before_json)["role"] == "consumer"
    assert json.loads(row.after_json)["role"] == "brand_manager"
    audited = " ".join(
        str(x) for x in (row.details_json, row.before_json, row.after_json) if x
    )
    assert GOOD_TOKEN not in audited, "the token must never be audited"


# --------------------------------------------------------------------------
# revocation
# --------------------------------------------------------------------------

def test_revoke_demotes_but_keeps_the_brand_profile(db, authorised, subject):
    bootstrap_role(subject.email, role="brand_manager", brand_name=BRAND, db=db)
    outcome, facts = bootstrap_role(subject.email, role="", revoke=True, db=db)
    assert outcome == "revoked"
    db.refresh(subject)
    assert subject.role == UserRole.CONSUMER
    # Deleting a brand's tenant as a side effect of a role change is data loss.
    assert db.query(BrandProfile).filter(BrandProfile.user_id == subject.id).first() is not None
    assert facts["profile"] == "retained"


def test_revoke_refuses_to_orphan_the_platform(db, authorised, subject):
    bootstrap_role(subject.email, role="admin", db=db)
    with pytest.raises(BootstrapRefused, match="only active admin"):
        bootstrap_role(subject.email, role="", revoke=True, db=db)
    db.refresh(subject)
    assert subject.role == UserRole.ADMIN, "a refused revocation must not demote"


def test_revoking_a_non_admin_is_allowed(db, authorised, subject):
    bootstrap_role(subject.email, role="brand_manager", brand_name=BRAND, db=db)
    outsider = User(
        email=f"keeps-admin-{uuid.uuid4().hex[:8]}@probe.test",
        hashed_password="x",
        full_name="Standing Admin",
        role=UserRole.ADMIN,
        is_active=True,
        is_verified=True,
    )
    db.add(outsider)
    db.commit()
    try:
        outcome, _ = bootstrap_role(subject.email, role="", revoke=True, db=db)
        assert outcome == "revoked"
    finally:
        db.query(User).filter(User.id == outsider.id).delete()
        db.commit()


def test_revoking_someone_who_is_already_a_consumer_is_a_no_op(db, authorised, subject):
    outcome, facts = bootstrap_role(subject.email, role="", revoke=True, db=db)
    assert outcome == "unchanged"
    assert facts["changed"] is False
