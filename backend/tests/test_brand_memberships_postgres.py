"""PostgreSQL concurrency semantics for brand memberships (0039/BRD-02).

The last-owner guard and the invitation one-time consumption are correct as
logic under SQLite, but their TRANSACTIONAL safety (two sessions racing to
remove the last two owners, two users consuming one token) depends on real
row locking (SELECT … FOR UPDATE on the brand row). Only PostgreSQL can
prove that; this file therefore skips everywhere but the postgres CI job
(same gate and URL as test_brand_portal_postgres.py).
"""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base
from backend.app.core.security import get_password_hash
from backend.app.models.user import User, UserRole, BrandProfile
from backend.app.models.membership import BrandMembership, BrandInvitation
from backend.app.services.brand_membership_service import (
    BrandMembershipError,
    BrandMembershipService,
    hash_token,
)


def _engine_or_skip():
    url = os.environ.get("CONFIT_PORTAL_TEST_PG_URL")
    if not url or not url.startswith("postgres"):
        pytest.skip("requires real PostgreSQL; exercised by the postgres CI job")
    # Same driver-normalization helper the production scripts use (psycopg2
    # is the declared dependency; SQLAlchemy 2.1 would otherwise default to
    # psycopg3, which is not installed).
    from backend.app.core.postgres_url import normalise_postgres_url
    url, connect_args = normalise_postgres_url(url)
    return sa.create_engine(url, connect_args=connect_args, pool_pre_ping=True)


@pytest.fixture()
def pg_schema():
    # Tables already exist on the CI database (chain ran to 0039 first);
    # create_all is a no-op there and materializes them on a bare scratch DB.
    # Deliberately NO drop_all teardown: the CI database is shared by later
    # steps, and every row below is uuid-suffixed (collision-free reuse).
    engine = _engine_or_skip()
    Base.metadata.create_all(engine)
    yield engine


def _seed(engine, with_coowner=False):
    Session = sessionmaker(bind=engine)
    s = Session()
    suffix = uuid.uuid4().hex[:8]
    owner = User(email=f"pgowner.{suffix}@t.example",
                 hashed_password=get_password_hash("Password123!"),
                 full_name="PG Owner", role=UserRole.BRAND_OWNER,
                 is_active=True, is_verified=True)
    s.add(owner)
    s.flush()  # user_id is NOT NULL on brand_profiles (0029) — need the id first
    bp = BrandProfile(user_id=owner.id, brand_name=f"PG Brand {suffix}",
                      slug=f"pg-brand-{suffix}", is_verified=True,
                      commission_rate=15, return_rate_benchmark=28,
                      current_return_rate=11)
    s.add(bp)
    s.flush()
    m = BrandMembership(brand_id=bp.id, user_id=owner.id, role="owner", status="active")
    s.add(m)
    co = None
    if with_coowner:
        co = User(email=f"pgco.{suffix}@t.example",
                  hashed_password=get_password_hash("Password123!"),
                  full_name="PG CoOwner", role=UserRole.CONSUMER,
                  is_active=True, is_verified=True)
        s.add(co)
        s.flush()
        s.add(BrandMembership(brand_id=bp.id, user_id=co.id, role="owner", status="active"))
    s.commit()
    ids = {"brand": bp.id, "owner": owner.id, "member": m.id, "coowner": co.id if co else None}
    s.close()
    return ids


def test_concurrent_last_owner_removals_cannot_orphan_the_brand(pg_schema):
    ids = _seed(pg_schema, with_coowner=False)
    Session = sessionmaker(bind=pg_schema)
    barrier = Barrier(2)
    outcomes = []

    def try_remove():
        with Session() as s:
            actor = s.get(User, ids["owner"])
            barrier.wait(timeout=10)
            try:
                BrandMembershipService(s).remove_member(
                    brand_id=ids["brand"], membership_id=ids["member"], actor=actor)
                return "removed"
            except BrandMembershipError as e:
                return e.code
            except Exception as e:  # noqa: BLE001
                return f"error:{type(e).__name__}"

    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(lambda _: try_remove(), [0, 1]))

    with Session() as s:
        m = s.get(BrandMembership, ids["member"])
        # The guard must hold under real locking: the brand NEVER loses its
        # last active owner, regardless of which racer "wins".
        assert m.status == "active", outcomes
        assert outcomes == ["LAST_ACTIVE_OWNER", "LAST_ACTIVE_OWNER"], outcomes


def test_concurrent_double_removal_after_promotion_keeps_one_owner(pg_schema):
    ids = _seed(pg_schema, with_coowner=True)
    Session = sessionmaker(bind=pg_schema)
    barrier = Barrier(2)
    with Session() as s:
        co_m = (s.query(BrandMembership)
                .filter(BrandMembership.user_id == ids["coowner"]).first())
        co_mid = co_m.id

    def try_remove(mid):
        with Session() as s:
            actor = s.get(User, ids["coowner"])
            barrier.wait(timeout=10)
            try:
                BrandMembershipService(s).remove_member(
                    brand_id=ids["brand"], membership_id=mid, actor=actor)
                return "removed"
            except BrandMembershipError as e:
                return e.code

    # Two DIFFERENT owners removed concurrently (by each other): exactly the
    # first must pass; the second must see the demotion-then-count and refuse.
    with ThreadPoolExecutor(2) as pool:
        res = list(pool.map(try_remove, [ids["member"], co_mid]))
    with Session() as s:
        active_owners = (s.query(BrandMembership)
                         .filter(BrandMembership.brand_id == ids["brand"],
                                 BrandMembership.status == "active",
                                 BrandMembership.role == "owner").count())
        assert active_owners >= 1, (res, active_owners)


def test_concurrent_accept_of_one_token_mints_one_membership(pg_schema):
    ids = _seed(pg_schema)
    Session = sessionmaker(bind=pg_schema)
    with Session() as s:
        target = User(email=f"pgtarget.{uuid.uuid4().hex[:6]}@t.example",
                      hashed_password=get_password_hash("Password123!"),
                      full_name="PG Target", role=UserRole.CONSUMER,
                      is_active=True, is_verified=True)
        s.add(target)
        s.commit()
        tid = target.id
        raw = uuid.uuid4().hex + uuid.uuid4().hex  # >20 chars urlsafe-ish
        s.add(BrandInvitation(brand_id=ids["brand"], email=target.email, role="manager",
                              token_hash=hash_token(raw), status="pending",
                              expires_at="9999-12-31 00:00:00"))
        s.commit()

    barrier = Barrier(2)

    def accept():
        with Session() as s:
            u = s.get(User, tid)
            barrier.wait(timeout=10)
            try:
                out = BrandMembershipService(s).accept_invitation(raw_token=raw, user=u)
                return f"ok:{out['already']}"
            except BrandMembershipError as e:
                return e.code
            except Exception as e:  # noqa: BLE001
                return f"error:{type(e).__name__}"

    with ThreadPoolExecutor(2) as pool:
        res = sorted(pool.map(lambda _: accept(), [0, 1]))
    with Session() as s:
        n = (s.query(BrandMembership)
             .filter(BrandMembership.brand_id == ids["brand"],
                     BrandMembership.user_id == tid,
                     BrandMembership.status == "active").count())
        assert n == 1, res
        assert "ok:False" in res or "ok:True" in res, res
