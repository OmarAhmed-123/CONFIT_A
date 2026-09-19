"""REAL concurrency tests for the privileged lifecycle paths, on PostgreSQL.

Why this module exists (final-phase §11): the earlier suites proved the *logic*
of partner approval, invitation acceptance, duplicate application rejection and
email idempotency — but they ran serially on SQLite. SQLite serialises writers,
so a passing run proves nothing about two requests racing in production, where
PostgreSQL will happily run both and let the database constraints decide.

These tests require a real PostgreSQL server and are SKIPPED unless
``CONFIT_PG_DSN`` points at one (CI and the default suite stay on SQLite):

    CONFIT_PG_DSN=postgresql://postgres@127.0.0.1:5433/confit_pg_race \
        python -m pytest backend/tests/test_pg_concurrency_lifecycle.py -q

Each race uses a ``threading.Barrier`` so both requests are in flight before
either can commit, then asserts on the OUTCOME and on the database state that
must result — exactly one privileged effect, never two:

  * two simultaneous approvals of one application  -> one 200, one 409, one brand
  * two simultaneous acceptances of one invitation -> one 200, one 409, one membership
  * two simultaneous partner applications          -> one 201, one 409, one row
  * two simultaneous identical email sends         -> one provider message, one replay

A failure here is a genuine production race, not a test artefact.
"""
from __future__ import annotations

import os
import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.main import app
from backend.app.models.user import (
    AuditLog,
    BrandMember,
    EmailDelivery,
    BrandProfile,
    Invitation,
    PartnerApplication,
    User,
    UserRole,
)
from backend.app.seed_data import seed_database
from backend.tests.smtp_test_support import LocalSMTPSink

PG_DSN = os.getenv("CONFIT_PG_DSN")

pytestmark = pytest.mark.skipif(
    not PG_DSN,
    reason="real-concurrency tests require CONFIT_PG_DSN (PostgreSQL); SQLite cannot prove races",
)

ADMIN = {"email": "admin@confit.io", "password": "Password123!"}


# ---------------------------------------------------------------------------
# Fixtures: a real PostgreSQL schema + a get_db override pointing at it
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pg():
    engine = create_engine(PG_DSN, pool_size=8, max_overflow=8)
    # Start from a clean, migrated (head) schema. Alembic owns the real
    # production path; here we materialise the same metadata the migration
    # produces so the constraints under test are the production constraints.
    from backend.app.core.database import Base

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    seed_database(target_engine=engine, force=True)

    def override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override
    try:
        yield engine, SessionLocal
    finally:
        if previous is not None:
            app.dependency_overrides[get_db] = previous
        engine.dispose()


@pytest.fixture()
def email_on(monkeypatch, pg):
    """A configured provider whose transport is a real loopback SMTP server."""
    sink = LocalSMTPSink()   # binds + serves on construction
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "smtp", raising=False)
    monkeypatch.setattr(settings, "SMTP_HOST", "127.0.0.1", raising=False)
    monkeypatch.setattr(settings, "SMTP_PORT", sink.port, raising=False)
    monkeypatch.setattr(settings, "SMTP_USERNAME", None, raising=False)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", None, raising=False)
    monkeypatch.setattr(settings, "SMTP_TLS_MODE", "none", raising=False)
    monkeypatch.setattr(settings, "EMAIL_FROM_ADDRESS", "CONFIT <no-reply@confit.test>", raising=False)
    monkeypatch.setattr(settings, "FRONTEND_BASE_URL", "https://confit-a.vercel.app", raising=False)
    try:
        yield sink
    finally:
        sink.close()


def _csrf(client: TestClient) -> dict:
    token = client.cookies.get("confit_csrf")
    return {"X-CSRF-Token": token} if token else {}


def _register(client: TestClient, email: str, intent: str = "consumer") -> dict:
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": "Race Tester",
              "registration_intent": intent},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _verify_email(client: TestClient, email: str, sink: LocalSMTPSink) -> None:
    """Complete verification through the API using the token that really arrived."""
    from backend.tests.smtp_test_support import _plain_text, _token_from

    client.post("/api/v1/auth/verify-email/request", json={"email": email}, headers=_csrf(client))
    token = _token_from(_plain_text(sink.messages[-1]))
    r = client.post("/api/v1/auth/verify-email", json={"token": token}, headers=_csrf(client))
    assert r.status_code == 200, r.text


def _race(fn_a, fn_b):
    """Run two requests as simultaneously as threads allow; return both responses."""
    barrier = threading.Barrier(2)
    out: dict[str, object] = {}

    def wrap(name, fn):
        client = TestClient(app)          # one client per thread: no shared cookie jar
        barrier.wait()
        try:
            out[name] = fn(client)
        except Exception as exc:          # surfaced, never swallowed
            out[name] = exc

    threads = [threading.Thread(target=wrap, args=("a", fn_a)),
               threading.Thread(target=wrap, args=("b", fn_b))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return out["a"], out["b"]


# ---------------------------------------------------------------------------
# 1. Two simultaneous approvals of the same application
# ---------------------------------------------------------------------------

def test_concurrent_partner_approval_provisions_exactly_one_brand(pg, email_on):
    engine, Session = pg
    applicant = TestClient(app)
    _register(applicant, "race-approve@example.com", intent="brand_partner")
    _verify_email(applicant, "race-approve@example.com", email_on)
    created = applicant.post(
        "/api/v1/auth/partner-applications",
        json={"brand_name": "Race Approval Atelier", "market": "EG", "contact_name": "Race"},
        headers=_csrf(applicant),
    )
    assert created.status_code == 201, created.text
    application_id = created.json()["id"]

    admin = TestClient(app)
    login = admin.post("/api/v1/auth/login", json=ADMIN)
    assert login.status_code == 200, login.text
    auth = {"Authorization": f"Bearer {login.json()['access_token']}"}

    def approve(client):
        client.post("/api/v1/auth/login", json=ADMIN)
        token = client.cookies.get("confit_csrf")
        headers = dict(auth)
        if token:
            headers["X-CSRF-Token"] = token
        return client.post(
            f"/api/v1/admin/partner-applications/{application_id}/approve",
            json={"note": "race"},
            headers=headers,
        )

    ra, rb = _race(approve, approve)
    statuses = sorted([getattr(ra, "status_code", 500), getattr(rb, "status_code", 500)])
    assert statuses == [200, 409], f"expected exactly one winner, got {statuses}: {ra} / {rb}"
    loser = ra if getattr(ra, "status_code", None) == 409 else rb
    assert loser.json()["error"]["code"] == "APPLICATION_ALREADY_REVIEWED"

    db = Session()
    try:
        app_row = db.query(PartnerApplication).filter(PartnerApplication.id == application_id).one()
        assert app_row.status.value == "approved"
        user = db.query(User).filter(User.email == "race-approve@example.com").one()
        assert user.role == UserRole.BRAND_OWNER
        brands = db.query(BrandProfile).filter(BrandProfile.user_id == user.id).all()
        assert len(brands) == 1, f"exactly one tenant must be provisioned, found {len(brands)}"
        assert app_row.brand_id == brands[0].id
        approvals = (
            db.query(AuditLog)
            .filter(AuditLog.action == "PARTNER_APPLICATION_APPROVED",
                    AuditLog.resource_id == str(application_id))
            .count()
        )
        assert approvals == 1, f"exactly one approval audit row expected, found {approvals}"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 2. Two simultaneous acceptances of the same invitation
# ---------------------------------------------------------------------------

def test_concurrent_invitation_acceptance_creates_one_membership(pg, email_on):
    engine, Session = pg
    owner = TestClient(app)
    _register(owner, "race-owner@example.com", intent="brand_partner")
    db = Session()
    try:
        user = db.query(User).filter(User.email == "race-owner@example.com").one()
        user.role = UserRole.BRAND_OWNER
        brand = BrandProfile(user_id=user.id, brand_name="Race Owner Brand", slug="race-owner-brand",
                             is_verified=True)
        db.add(brand)
        db.commit()
        brand_id = brand.id
    finally:
        db.close()

    created = owner.post(
        "/api/v1/brand/invitations",
        json={"email": "race-invitee@example.com", "role": "brand_manager"},
        headers=_csrf(owner),
    )
    assert created.status_code in (200, 201), created.text
    token = created.json()["accept_path"].split("token=", 1)[1]

    def accept(client):
        return client.post(
            "/api/v1/auth/invitations/accept",
            json={"token": token, "full_name": "Race Invitee", "password": "Password123!"},
        )

    ra, rb = _race(accept, accept)
    statuses = sorted([getattr(ra, "status_code", 500), getattr(rb, "status_code", 500)])
    assert statuses == [200, 409], f"expected one acceptance, got {statuses}: {ra} / {rb}"
    loser = ra if getattr(ra, "status_code", None) == 409 else rb
    assert loser.json()["error"]["code"] == "INVITATION_ALREADY_ACCEPTED"

    db = Session()
    try:
        invitee = db.query(User).filter(User.email == "race-invitee@example.com").one()
        memberships = db.query(BrandMember).filter(BrandMember.user_id == invitee.id).all()
        assert len(memberships) == 1, f"one membership expected, found {len(memberships)}"
        assert memberships[0].brand_id == brand_id
        assert memberships[0].role == UserRole.BRAND_MANAGER
        invite = db.query(Invitation).filter(Invitation.brand_id == brand_id).one()
        assert invite.status.value == "accepted"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 3. Two simultaneous partner applications from one account
# ---------------------------------------------------------------------------

def test_concurrent_partner_applications_yield_one_pending_row(pg, email_on):
    engine, Session = pg
    applicant = TestClient(app)
    _register(applicant, "race-applicant@example.com", intent="brand_partner")
    _verify_email(applicant, "race-applicant@example.com", email_on)

    def submit(client):
        client.post("/api/v1/auth/login",
                    json={"email": "race-applicant@example.com", "password": "Password123!"})
        csrf = client.cookies.get("confit_csrf")
        headers = {"X-CSRF-Token": csrf} if csrf else {}
        return client.post(
            "/api/v1/auth/partner-applications",
            json={"brand_name": "Race Duplicate Atelier", "market": "EG", "contact_name": "Race"},
            headers=headers,
        )

    ra, rb = _race(submit, submit)
    statuses = sorted([getattr(ra, "status_code", 500), getattr(rb, "status_code", 500)])
    assert statuses == [201, 409], f"expected one application, got {statuses}: {ra} / {rb}"
    loser = ra if getattr(ra, "status_code", None) == 409 else rb
    assert loser.json()["error"]["code"] == "PARTNER_APPLICATION_PENDING"

    db = Session()
    try:
        user = db.query(User).filter(User.email == "race-applicant@example.com").one()
        rows = db.query(PartnerApplication).filter(PartnerApplication.user_id == user.id).count()
        assert rows == 1, f"exactly one application row expected, found {rows}"
        # The partial unique index is the guarantee, not application code.
        with engine.connect() as c:
            idx = c.execute(text(
                "select indexdef from pg_indexes where indexname='uq_partner_applications_user_pending'"
            )).scalar()
        assert idx and "WHERE" in idx, "the pending-application unique index must be partial"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 4. Two simultaneous identical email deliveries
# ---------------------------------------------------------------------------

def test_concurrent_identical_email_sends_reach_the_provider_once(pg, email_on):
    from backend.app.services import email_service

    engine, Session = pg
    sink = email_on
    db = Session()
    try:
        results: list = []
        barrier = threading.Barrier(2)

        def send():
            session = Session()
            try:
                barrier.wait()
                results.append(email_service.send_transactional(
                    session,
                    to="race-mail@example.com",
                    subject="Race",
                    html="<b>race</b>",
                    text="race",
                    purpose="race_probe",
                    dedupe_key="race-identical-key",
                ))
            except Exception as exc:      # a lost idempotency race surfaces here
                results.append(exc)
            finally:
                session.close()

        threads = [threading.Thread(target=send) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        errors = [r for r in results if isinstance(r, Exception)]
        assert not errors, f"concurrent identical sends must not raise: {errors}"
        # The contract: exactly ONE caller performs the send; the other is told
        # it is a replay. Both legitimately report the provider's acceptance —
        # `accepted` describes the message, `idempotent_replay` describes who sent it.
        originals = [r for r in results if not getattr(r, "idempotent_replay", True)]
        replays = [r for r in results if getattr(r, "idempotent_replay", False)]
        assert len(originals) == 1, f"exactly one caller may perform the send, got {len(originals)}"
        assert len(replays) == 1, f"the other caller must observe a replay, got {len(replays)}"
        # The loser must NEVER claim a fresh success of its own: it either sees
        # the winner's outcome (SUCCEEDED) or, if the winner is still talking to
        # the provider, an honest RETRYING — never a second accepted send.
        loser = replays[0]
        assert loser.status.value in ("succeeded", "retrying"), loser.status
        assert getattr(loser, "accepted", False) is (loser.status.value == "succeeded")
        # The stored key is "<purpose>:<dedupe_key>" (see email_service.send_transactional).
        deliveries = (
            db.query(EmailDelivery).filter_by(idempotency_key="race_probe:race-identical-key").count()
        )
        assert deliveries == 1, f"one ledger row expected, found {deliveries}"
        assert len(sink.messages) == 1, f"the provider must see exactly one message, saw {len(sink.messages)}"

        # Once the winner has finished, a later identical request is a clean
        # replay of the settled outcome — the claim row is never left dangling.
        again = email_service.send_transactional(
            db, to="race-mail@example.com", subject="Race", html="<b>race</b>", text="race",
            purpose="race_probe", dedupe_key="race-identical-key",
        )
        assert again.idempotent_replay is True
        assert again.status.value == "succeeded", again.status
        assert len(sink.messages) == 1, "a settled replay must not touch the provider"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 5. Two simultaneous registrations of the SAME address
# ---------------------------------------------------------------------------

def test_concurrent_registration_of_one_address_creates_one_account(pg, email_on):
    """The check-then-insert shape: both callers pass the pre-check, the unique
    index decides, and the loser must get a domain 409 — never an unhandled
    IntegrityError (500)."""
    engine, Session = pg

    def register(client):
        return client.post(
            "/api/v1/auth/register",
            json={"email": "race-same-address@example.com", "password": "Password123!",
                  "full_name": "Race Same", "registration_intent": "consumer"},
        )

    ra, rb = _race(register, register)
    statuses = sorted([getattr(ra, "status_code", 500), getattr(rb, "status_code", 500)])
    assert statuses == [201, 409], f"expected one account, got {statuses}: {ra} / {rb}"
    loser = ra if getattr(ra, "status_code", None) == 409 else rb
    assert loser.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"

    db = Session()
    try:
        users = db.query(User).filter(User.email == "race-same-address@example.com").all()
        assert len(users) == 1, f"exactly one account expected, found {len(users)}"
        assert users[0].role == UserRole.CONSUMER
    finally:
        db.close()
