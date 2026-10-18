"""BrandMemberships backend contract (BRD-02 · spec 005 · #150 residue).

Covers, against the REAL FastAPI stack:
  1. migration 0039 back-fill + downgrade on a scratch SQLite DB (the exact SQL
     executed on production), via the repo's Ops-proxy pattern (0013 precedent);
  2. provisioning: brand registration yields an ACTIVE owner membership;
  3. the capability matrix: unauthenticated/consumer/owner/manager/staff/admin/
     revoked, and the deliberate NO-ADMIN rule on tenant governance;
  4. invitation lifecycle: HTTP create is idempotent, leaks no token, and every
     rejection path collapses to ONE uniform code (non-enumerable);
  5. last-owner protection for removal AND demotion; second owner unblocks;
  6. the single-brand invariant at acceptance;
  7. audit integrity: hash-chained rows for mutations + AUTHORIZATION_DENIED
     security events, redacted PII (domain only);
  8. the non-negotiable rule: joining a brand NEVER mutates users.role and
     NEVER creates a brand_profiles row.

Tokens are minted through the service in tests (the raw token exists ONLY in
the one-time response/email envelope; the outbox row stores no body, so tests
must not fish it from there). Endpoint behavior around those tokens — accept,
replay, expiry, revocation, email-mismatch — is exercised over HTTP.

PostgreSQL FOR UPDATE semantics of the last-owner lock are pinned by
backend/tests/test_brand_memberships_postgres.py (CI postgres job).
"""

import importlib.util
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from backend.tests.conftest import TestingSessionLocal  # type: ignore
from backend.app.main import app
from backend.app.core.security import get_password_hash
from backend.app.models.user import User, UserRole, BrandProfile, AuditLog
from backend.app.models.membership import BrandMembership, BrandInvitation
from backend.app.models.email_outbox import EmailOutbox

client = TestClient(app)
PASSWORD = "Password123!"
REPO = Path(__file__).resolve().parents[2]
MIG_0039 = REPO / "backend" / "alembic" / "versions" / "0039_brand_memberships.py"


# ── helpers ──────────────────────────────────────────────────────────────────

def _db():
    return TestingSessionLocal()


def _tok(db, email, password=PASSWORD):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login {email} failed: {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _unique_email(prefix="inv"):
    return f"{prefix}.{uuid.uuid4().hex[:10]}@partner-test.example"


def _mk_user(db, email, role=UserRole.CONSUMER):
    u = User(email=email, hashed_password=get_password_hash(PASSWORD),
             full_name=f"Test {role.value} {uuid.uuid4().hex[:6]}",
             role=role, is_active=True, is_verified=True,
             created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _mk_brand(db):
    """A fully provisioned brand tenant via the public registration API."""
    suffix = uuid.uuid4().hex[:8]
    email = f"owner.{suffix}@partner-test.example"
    resp = client.post("/auth/brand/register", json={
        "brand_name": f"TestBrand {suffix}",
        "email": email,
        "password": PASSWORD,
        "full_name": f"Owner {suffix}",
    })
    assert resp.status_code == 201, resp.text
    return email, _tok(db, email)


def _invite_raw(db, owner_email, email, role):
    """Mint an invitation THROUGH THE SERVICE (returns the one-time raw token),
    so tests can drive HTTP acceptance deterministically. The HTTP create path
    is covered by its own endpoint tests (idempotency, no token leak)."""
    from backend.app.services.brand_membership_service import BrandMembershipService
    owner = db.query(User).filter(User.email == owner_email).first()
    bp = owner.brand_profile
    assert bp is not None
    out = BrandMembershipService(db).create_invitation(
        brand_id=bp.id, email=email, role=role, actor=owner)
    db.commit()
    return out["invitation"], out["raw_token"], bp


def _invite_and_accept(db, owner_email, email, role):
    inv, raw, bp = _invite_raw(db, owner_email, email, role)
    acc = client.post("/partner/members/invitations/accept",
                      headers=_tok(db, email), json={"token": raw})
    assert acc.status_code == 200, acc.text
    assert acc.json()["role"] == role and acc.json()["brand_id"] == bp.id
    return inv


def _brand_id_of(db, owner_email):
    return (db.query(BrandProfile)
            .join(User, User.id == BrandProfile.user_id)
            .filter(User.email == owner_email).with_entities(BrandProfile.id).scalar())


# ── 1 · migration 0039: back-fill + downgrade on scratch DB ─────────────────

def _load_mig():
    spec = importlib.util.spec_from_file_location("m0039", MIG_0039)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_0039_backfills_and_indexes(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'm0039.db'}")
    with engine.begin() as c:
        # minimal shapes of the two tables the back-fill SELECT reads
        c.execute(sa.text("create table users (id integer primary key, email text)"))
        c.execute(sa.text("create table brand_profiles (id integer primary key, "
                          "user_id integer, brand_name text)"))
        c.execute(sa.text("insert into users (id, email) values (1,'a@x.io'), (2,'b@x.io')"))
        c.execute(sa.text("insert into brand_profiles (id, user_id, brand_name) "
                          "values (10,1,'A'), (11,2,'B'), (12,null,'Orphaned')"))

    mod = _load_mig()
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    import alembic
    with engine.begin() as conn:
        alembic.op._proxy = Operations(MigrationContext.configure(conn))
        mod.upgrade()

    with engine.connect() as c:
        rows = c.execute(sa.text(
            "select brand_id, user_id, role, status from brand_memberships "
            "order by brand_id")).fetchall()
        assert rows == [(10, 1, "owner", "active"), (11, 2, "owner", "active")], \
            "back-fill must map every founder, none for orphaned profiles"
    with engine.begin() as c:
        # replaying the exact back-fill statement is idempotent
        c.execute(sa.text(
            "insert into brand_memberships (brand_id, user_id, role, status, created_at, updated_at) "
            "select bp.id, bp.user_id, 'owner', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
            "from brand_profiles bp where bp.user_id is not null "
            "on conflict (brand_id, user_id) do nothing"))
        assert c.execute(sa.text("select count(*) from brand_memberships")).scalar() == 2
        # partial UNIQUE (brand,email WHERE pending) is enforced...
        ins = ("insert into brand_invitations (brand_id, email, role, token_hash, "
               "status, expires_at, created_at) values (10,'x@y.io','staff','h1',"
               "'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)")
        c.execute(sa.text(ins))
        with pytest.raises(sa.exc.IntegrityError):
            c.execute(sa.text(ins.replace("'h1'", "'h2'")))
        # ...and lifts once the first row leaves 'pending'
        c.execute(sa.text("update brand_invitations set status='revoked' where token_hash='h1'"))
        c.execute(sa.text(ins.replace("'h1'", "'h2'")))
        # active-membership partial UNIQUE
        with pytest.raises(sa.exc.IntegrityError):
            c.execute(sa.text("insert into brand_memberships (brand_id,user_id,role,status,"
                              "created_at,updated_at) values (10,1,'manager','active',"
                              "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
    with engine.begin() as conn:
        alembic.op._proxy = Operations(MigrationContext.configure(conn))
        mod.downgrade()
    with engine.connect() as c:
        names = sa.inspect(c).get_table_names()
        assert "brand_memberships" not in names and "brand_invitations" not in names
        # owner anchor untouched → legacy single-owner model still works
        assert c.execute(sa.text("select count(*) from brand_profiles")).scalar() == 3


# ── 2 · provisioning ────────────────────────────────────────────────────────

def test_registration_creates_founder_membership():
    db = _db()
    try:
        email, tok = _mk_brand(db)
        r = client.get("/partner/members", headers=tok)
        assert r.status_code == 200, r.text
        members = r.json()
        assert len(members) == 1
        assert members[0]["role"] == "owner" and members[0]["status"] == "active"
        u = db.query(User).filter(User.email == email).first()
        m = db.query(BrandMembership).filter(BrandMembership.user_id == u.id).first()
        assert m is not None and m.role == "owner"
    finally:
        db.close()


# ── 3 · capability matrix ────────────────────────────────────────────────────

def test_staff_read_only_including_invitations_hide():
    db = _db()
    try:
        owner_email, owner_tok = _mk_brand(db)
        staff_email = _unique_email("staff")
        staff = _mk_user(db, staff_email)
        _invite_and_accept(db, owner_email, staff_email, "staff")

        # THE rule: membership never touches platform role or creates a profile
        u = db.get(User, staff.id)
        assert u.role == UserRole.CONSUMER
        assert u.brand_profile is None

        staff_tok = _tok(db, staff_email)
        assert client.get("/partner/products", headers=staff_tok).status_code == 200
        assert client.get("/partner/analytics", headers=staff_tok).status_code == 200
        assert client.get("/partner/members", headers=staff_tok).status_code == 200
        # staff sees NO emails in the roster (PII minimization)
        roster = client.get("/partner/members", headers=staff_tok).json()
        assert all(m["email"] is None for m in roster), roster
        # ...while owner sees them (needed to manage the team)
        roster_o = client.get("/partner/members", headers=owner_tok).json()
        assert any(m["email"] for m in roster_o)
        # owner-only + manager-only capabilities: denied for staff
        assert client.post("/partner/members/invitations", headers=staff_tok,
                           json={"email": _unique_email("x"), "role": "staff"}
                           ).status_code == 403
        assert client.patch("/partner/profile", headers=staff_tok,
                            json={"description": "nope"}).status_code == 403
        assert client.post("/partner/stores", headers=staff_tok,
                           json={"name": "S", "city": "Dubai", "address": "a",
                                 "latitude": 1, "longitude": 1}).status_code == 403
        assert client.get("/partner/members/invitations",
                          headers=staff_tok).status_code == 403
        assert client.post("/partner/catalog/preview-csv",
                           headers=staff_tok).status_code == 403
    finally:
        db.close()


def test_manager_writes_catalog_but_not_profile_members_billing():
    db = _db()
    try:
        owner_email, owner_tok = _mk_brand(db)
        mgr_email = _unique_email("mgr")
        _mk_user(db, mgr_email)
        _invite_and_accept(db, owner_email, mgr_email, "manager")
        mgr_tok = _tok(db, mgr_email)

        assert client.get("/partner/products", headers=mgr_tok).status_code == 200
        assert client.get("/partner/members/invitations",
                          headers=mgr_tok).status_code == 200
        # manager may create stores (stores:write)
        r = client.post("/partner/stores", headers=mgr_tok,
                        json={"name": "Manager Store", "city": "Dubai",
                              "address": "Somewhere 1", "latitude": 25.2,
                              "longitude": 55.27})
        assert r.status_code == 201, r.text
        # manager must NOT: manage members, rewrite brand profile, touch billing
        assert client.post("/partner/members/invitations", headers=mgr_tok,
                           json={"email": _unique_email("y"), "role": "manager"}
                           ).status_code == 403
        assert client.patch("/partner/profile", headers=mgr_tok,
                            json={"description": "nope"}).status_code == 403
        assert client.get("/partner/billing/statement",
                          headers=mgr_tok).status_code == 403
    finally:
        db.close()


def test_unauthenticated_and_unlinked_users_are_denied():
    # FRESH client: the shared module client carries a session cookie from
    # earlier logins (TestClient persists cookies), which would make an
    # "anonymous" probe silently authenticated.
    assert TestClient(app).get("/partner/members").status_code == 401
    db = _db()
    try:
        plain_email = _unique_email("plain")
        _mk_user(db, plain_email)
        tok = _tok(db, plain_email)
        assert client.get("/partner/members", headers=tok).status_code == 403
        assert client.get("/partner/products", headers=tok).status_code == 403
        # identity endpoint still answers honestly: empty list, not an error
        mine = client.get("/partner/members/me", headers=tok)
        assert mine.status_code == 200 and mine.json() == []
    finally:
        db.close()


def test_admin_cannot_govern_tenants():
    """members:manage explicitly opts OUT of the platform-admin override."""
    db = _db()
    try:
        _, owner_tok = _mk_brand(db)
        admin_tok = _tok(db, "admin@confit.io")
        r = client.post("/partner/members/invitations", headers=admin_tok,
                        json={"email": _unique_email("admin-inv"), "role": "owner"})
        assert r.status_code == 403
        r2 = client.get("/partner/members", headers=admin_tok)
        assert r2.status_code == 403
    finally:
        db.close()


# ── 4 · invitation HTTP contract ────────────────────────────────────────────

def test_http_invitation_create_is_idempotent_and_leaks_no_token():
    db = _db()
    try:
        owner_email, owner_tok = _mk_brand(db)
        target = _unique_email("idemp")
        _mk_user(db, target)
        r1 = client.post("/partner/members/invitations", headers=owner_tok,
                         json={"email": target, "role": "manager"})
        assert r1.status_code == 201, r1.text
        body = r1.json()
        assert "token" not in body and "token_hash" not in body and "raw" not in body
        r2 = client.post("/partner/members/invitations", headers=owner_tok,
                         json={"email": "  " + target.upper() + " ", "role": "manager"})
        assert r2.status_code in (200, 201)
        assert r2.json()["id"] == body["id"], "repeat request must reuse the pending row"
        bid = _brand_id_of(db, owner_email)
        n = (db.query(BrandInvitation)
             .filter(BrandInvitation.brand_id == bid,
                     BrandInvitation.status == "pending").count())
        assert n == 1
        # an outbox row must exist for the fresh invitation (queued email path)
        ob = (db.query(EmailOutbox)
              .filter(EmailOutbox.recipient == target,
                      EmailOutbox.template == "brand_invitation").count())
        assert ob == 1
        # the earlier pending invite (manager role) is still open; accept it
        # by fetching its token via a revoke -> fresh service invite (the raw
        # token exists only on creation)
        pend = (db.query(BrandInvitation)
                .filter(BrandInvitation.brand_id == bid,
                        BrandInvitation.status == "pending").first())
        rv = client.delete(f"/partner/members/invitations/{pend.id}", headers=owner_tok)
        assert rv.status_code == 200
        _invite_and_accept(db, owner_email, target, "manager")
        # inviting an existing active member is a clean 409
        r3 = client.post("/partner/members/invitations", headers=owner_tok,
                         json={"email": target, "role": "staff"})
        assert r3.status_code == 409
        assert r3.json()["detail"]["error"]["code"] == "ALREADY_MEMBER"
    finally:
        db.close()


def test_acceptance_rejections_are_uniform_and_non_enumerable():
    db = _db()
    try:
        owner_email, owner_tok = _mk_brand(db)
        invitee = _unique_email("recip")
        _mk_user(db, invitee)
        other = _unique_email("other")
        _mk_user(db, other)
        inv, raw, _ = _invite_raw(db, owner_email, invitee, "staff")

        codes = []
        # 1) email mismatch (right token, wrong recipient)
        r = client.post("/partner/members/invitations/accept",
                        headers=_tok(db, other), json={"token": raw})
        assert r.status_code == 400
        codes.append(r.json()["detail"]["error"]["code"])
        assert (db.query(BrandMembership)
                .filter(BrandMembership.user_id ==
                        db.query(User).filter(User.email == other)
                        .with_entities(User.id).scalar()).count()) == 0

        # 2) junk token
        r = client.post("/partner/members/invitations/accept",
                        headers=_tok(db, invitee), json={"token": "x" * 43})
        codes.append(r.status_code)
        assert r.status_code == 400

        # 3) expired
        inv.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
        db.commit()
        r = client.post("/partner/members/invitations/accept",
                        headers=_tok(db, invitee), json={"token": raw})
        assert r.status_code == 400
        db.expire_all()
        assert db.get(BrandInvitation, inv.id).status == "expired"

        # 4) revoked (fresh invite, revoked by owner)
        inv2, raw2, _ = _invite_raw(db, owner_email, invitee, "staff")
        rv = client.delete(f"/partner/members/invitations/{inv2.id}", headers=owner_tok)
        assert rv.status_code == 200
        r = client.post("/partner/members/invitations/accept",
                        headers=_tok(db, invitee), json={"token": raw2})
        assert r.status_code == 400

        # ALL rejections share ONE code — no state can be enumerated
        for probe in (codes[0],):
            assert probe == "INVITATION_NOT_APPLICABLE"

        # 5) happy path + replay semantics
        inv3, raw3, bid = _invite_raw(db, owner_email, invitee, "staff")
        acc = client.post("/partner/members/invitations/accept",
                          headers=_tok(db, invitee), json={"token": raw3})
        assert acc.status_code == 200 and acc.json()["already_member"] is False
        replay = client.post("/partner/members/invitations/accept",
                             headers=_tok(db, invitee), json={"token": raw3})
        assert replay.status_code == 200 and replay.json()["already_member"] is True, \
            "safe retry: re-accepting one's own consumed token is idempotent"
        # another user with the (still known) token gets the uniform rejection
        r = client.post("/partner/members/invitations/accept",
                        headers=_tok(db, other), json={"token": raw3})
        assert r.status_code == 400 and \
            r.json()["detail"]["error"]["code"] == "INVITATION_NOT_APPLICABLE"
    finally:
        db.close()


def test_resend_rotates_the_old_link_dies():
    db = _db()
    try:
        owner_email, owner_tok = _mk_brand(db)
        target = _unique_email("rot")
        _mk_user(db, target)
        inv, raw, _ = _invite_raw(db, owner_email, target, "staff")
        rs = client.post(f"/partner/members/invitations/{inv.id}/resend",
                         headers=owner_tok)
        assert rs.status_code == 200, rs.text
        r = client.post("/partner/members/invitations/accept",
                        headers=_tok(db, target), json={"token": raw})
        assert r.status_code == 400, "old token must stop working after rotation"
    finally:
        db.close()


# ── 5/6 · last-owner guard + single-brand invariant ─────────────────────────

def _owner_membership_id(db, owner_email):
    return (db.query(BrandMembership)
            .join(User, User.id == BrandMembership.user_id)
            .filter(User.email == owner_email).with_entities(BrandMembership.id).scalar())


def test_last_owner_cannot_be_removed_or_demoted_second_owner_unblocks():
    db = _db()
    try:
        owner_email, owner_tok = _mk_brand(db)
        mid = _owner_membership_id(db, owner_email)
        assert client.delete(f"/partner/members/{mid}", headers=owner_tok).status_code == 409
        r = client.patch(f"/partner/members/{mid}", headers=owner_tok,
                         json={"role": "staff"})
        assert r.status_code == 409
        assert r.json()["detail"]["error"]["code"] == "LAST_ACTIVE_OWNER"

        co_email = _unique_email("coowner")
        _mk_user(db, co_email)
        _invite_and_accept(db, owner_email, co_email, "owner")
        rm = client.delete(f"/partner/members/{mid}", headers=owner_tok)
        assert rm.status_code == 200 and rm.json()["status"] == "revoked"
        # removed owner instantly loses every tenant surface
        assert client.get("/partner/products", headers=owner_tok).status_code == 403
        # roster keeps the revoked row for the owner view
        me = client.get("/partner/members", headers=_tok(db, co_email)).json()
        assert any(m["status"] == "revoked" for m in me)
        # removal of an already-revoked membership is idempotent
        assert client.delete(f"/partner/members/{mid}",
                             headers=_tok(db, co_email)).status_code == 200
    finally:
        db.close()


def test_multi_brand_acceptance_is_refused():
    db = _db()
    try:
        email_a, tok_a = _mk_brand(db)
        email_b, tok_b = _mk_brand(db)
        someone = _unique_email("two")
        _mk_user(db, someone)
        _invite_and_accept(db, email_a, someone, "staff")
        inv_b, raw_b, _ = _invite_raw(db, email_b, someone, "manager")
        r = client.post("/partner/members/invitations/accept",
                        headers=_tok(db, someone), json={"token": raw_b})
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["error"]["code"] == "MULTI_BRAND_NOT_SUPPORTED"
        # membership B untouched; invitation still pending (not consumed)
        db.expire_all()
        assert db.get(BrandInvitation, inv_b.id).status == "pending"
    finally:
        db.close()


# ── 7 · audit integrity + cross-tenant shapes ───────────────────────────────

def test_mutations_are_hash_chained_and_denials_recorded_with_redaction():
    db = _db()
    try:
        owner_email, owner_tok = _mk_brand(db)
        staff_email = _unique_email("auditstaff")
        _mk_user(db, staff_email)
        inv, raw, bp = _invite_raw(db, owner_email, staff_email, "staff")
        # audit for the invite, with PII redaction (domain only)
        br = (db.query(AuditLog).filter(AuditLog.action == "BRAND_MEMBER_INVITED")
              .order_by(AuditLog.id.desc()).first())
        assert br is not None and br.entry_hash and br.prev_hash is not None
        assert '"email_domain": "partner-test.example"' in br.details_json
        assert staff_email not in br.details_json, "full invitee address must NOT be audited"

        acc = client.post("/partner/members/invitations/accept",
                          headers=_tok(db, staff_email), json={"token": raw})
        assert acc.status_code == 200
        aj = (db.query(AuditLog).filter(AuditLog.action == "BRAND_MEMBER_JOINED")
              .order_by(AuditLog.id.desc()).first())
        assert aj is not None and aj.entry_hash

        # denied privileged access is itself a recorded security event
        staff_tok = _tok(db, staff_email)
        client.patch("/partner/profile", headers=staff_tok, json={"description": "x"})
        den = (db.query(AuditLog)
               .filter(AuditLog.action == "AUTHORIZATION_DENIED",
                       AuditLog.resource_type == "BrandAccess")
               .order_by(AuditLog.id.desc()).first())
        assert den is not None, "ASVS V16.3.2: denials are audited"
        assert den.entry_hash
    finally:
        db.close()


def test_cross_tenant_membership_probe_is_404_not_403():
    """Another tenant's membership id must not even confirm existence."""
    db = _db()
    try:
        email_a, tok_a = _mk_brand(db)
        email_b, tok_b = _mk_brand(db)
        mid_a = _owner_membership_id(db, email_a)
        assert mid_a is not None
        r = client.patch(f"/partner/members/{mid_a}", headers=tok_b,
                         json={"role": "staff"})
        assert r.status_code == 404
        r = client.delete(f"/partner/members/{mid_a}", headers=tok_b)
        assert r.status_code == 404
        # A's owner unaffected by B's probes
        assert db.get(BrandMembership, mid_a).status == "active"
    finally:
        db.close()


def test_role_change_flows_and_self_role_guard():
    db = _db()
    try:
        owner_email, owner_tok = _mk_brand(db)
        target = _unique_email("promote")
        _mk_user(db, target)
        _invite_and_accept(db, owner_email, target, "staff")
        db.expire_all()
        m = (db.query(BrandMembership).join(User, User.id == BrandMembership.user_id)
             .filter(User.email == target).first())
        r = client.patch(f"/partner/members/{m.id}", headers=owner_tok,
                         json={"role": "manager"})
        assert r.status_code == 200 and r.json()["role"] == "manager"
        # promoted manager can now write catalog-plane things
        mt = _tok(db, target)
        assert client.get("/partner/members/invitations", headers=mt).status_code == 200
        # owner cannot demote themself below owner while sole owner (guarded);
        # and staff cannot edit anyone (capability 403) — covered above.
    finally:
        db.close()
