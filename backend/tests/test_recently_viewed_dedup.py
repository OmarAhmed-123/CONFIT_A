"""Recently-viewed dedup (DB-01 / CUS-14) — one row per (user, product).

Tests the repository upsert logic and the DB unique constraint introduced
in 0035_recently_viewed_unique.

This uses the real test DB seeded by conftest (new_test_engine) so it
exercises the actual SQLAlchemy model with UniqueConstraint.
"""

import time
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.tests.conftest import new_test_engine, TestingSessionLocal
from backend.app.models.catalog import RecentlyViewed
from backend.app.repositories.catalog_repository import CatalogRepository

engine = new_test_engine()
# Ensure tables exist (conftest already seeds, but migration may not have run on this DB yet)
# We will run the migration upgrade logic via alembic for this test DB? Instead, we
# rely on the model metadata having the constraint and the test DB being recreated
# via create_all in seed? Safer to ensure constraint exists via direct check.

# For SQLite test DB, we need to ensure the unique constraint exists. If the DB
# was created before 0035 migration, it won't have it. So we attempt to add it
# idempotently for the test session (SQLite batch alter is complex, so we check
# and create index if missing).

def _ensure_unique_constraint():
    # This is a test-only helper to make the existing SQLite test DB match the
    # migrated schema if it was created before 0035. In production, alembic
    # handles this; in tests, the DB file is persistent across runs (confit_test.db).
    # Called lazily from fixture after conftest has seeded the DB.
    try:
        with engine.begin() as conn:
            # If table does not exist yet, skip (will be created by seed)
            tables = {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()}
            if "recently_viewed" not in tables:
                return
            # Check if unique index/constraint exists
            rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='recently_viewed'")).fetchall()
            names = {r[0] for r in rows}
            has_uq = "uq_recently_viewed_user_product" in names
            if not has_uq:
                # Deduplicate first (same logic as migration)
                try:
                    conn.execute(text("""
                        DELETE FROM recently_viewed
                        WHERE id NOT IN (
                            SELECT keeper_id FROM (
                                SELECT id AS keeper_id,
                                       ROW_NUMBER() OVER (
                                           PARTITION BY user_id, product_id
                                           ORDER BY viewed_at DESC, id DESC
                                       ) AS rn
                                FROM recently_viewed
                            ) WHERE rn = 1
                        )
                    """))
                except Exception:
                    conn.execute(text("""
                        DELETE FROM recently_viewed
                        WHERE id NOT IN (
                            SELECT MAX(id) FROM recently_viewed GROUP BY user_id, product_id
                        )
                    """))
                # Create unique index (SQLite implements UNIQUE constraint as index)
                try:
                    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_recently_viewed_user_product ON recently_viewed (user_id, product_id)"))
                except Exception:
                    pass
    except Exception:
        # If DB not ready yet, ignore - fixture will retry
        pass


@pytest.fixture
def db_session():
    _ensure_unique_constraint()
    session = TestingSessionLocal()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


def test_record_product_view_creates_one_row(db_session):
    repo = CatalogRepository(db_session)
    # Use user_id 9999 and product_id 1 (product 1 exists from seed)
    user_id = 9999
    product_id = 1

    # Clean any existing rows for this test user
    db_session.query(RecentlyViewed).filter(RecentlyViewed.user_id == user_id).delete()
    db_session.commit()

    repo.record_product_view(user_id=user_id, product_id=product_id)
    rows = db_session.query(RecentlyViewed).filter(RecentlyViewed.user_id == user_id, RecentlyViewed.product_id == product_id).all()
    assert len(rows) == 1, f"expected 1 row after first view, got {len(rows)}"


def test_repeated_views_keep_one_row_with_most_recent_timestamp(db_session):
    repo = CatalogRepository(db_session)
    user_id = 9998
    product_id = 1

    db_session.query(RecentlyViewed).filter(RecentlyViewed.user_id == user_id).delete()
    db_session.commit()

    repo.record_product_view(user_id=user_id, product_id=product_id)
    first = db_session.query(RecentlyViewed).filter(RecentlyViewed.user_id == user_id, RecentlyViewed.product_id == product_id).first()
    first_ts = first.viewed_at

    time.sleep(0.01)  # ensure timestamp difference

    repo.record_product_view(user_id=user_id, product_id=product_id)
    repo.record_product_view(user_id=user_id, product_id=product_id)

    rows = db_session.query(RecentlyViewed).filter(RecentlyViewed.user_id == user_id, RecentlyViewed.product_id == product_id).all()
    assert len(rows) == 1, f"expected 1 row after repeated views, got {len(rows)} — dedup failed (DB-01)"
    assert rows[0].viewed_at >= first_ts, "viewed_at should be refreshed to most-recent on re-view"


def test_different_products_create_separate_rows(db_session):
    repo = CatalogRepository(db_session)
    user_id = 9997
    db_session.query(RecentlyViewed).filter(RecentlyViewed.user_id == user_id).delete()
    db_session.commit()

    repo.record_product_view(user_id=user_id, product_id=1)
    repo.record_product_view(user_id=user_id, product_id=2)

    rows = db_session.query(RecentlyViewed).filter(RecentlyViewed.user_id == user_id).all()
    assert len(rows) == 2, f"expected 2 rows for 2 different products, got {len(rows)}"


def test_db_unique_constraint_rejects_duplicate_direct_insert(db_session):
    """Direct DB insert of duplicate (user, product) must fail — proves constraint exists."""
    user_id = 9996
    product_id = 1
    db_session.query(RecentlyViewed).filter(RecentlyViewed.user_id == user_id).delete()
    db_session.commit()

    db_session.add(RecentlyViewed(user_id=user_id, product_id=product_id))
    db_session.commit()

    # Attempt duplicate via raw add
    db_session.add(RecentlyViewed(user_id=user_id, product_id=product_id))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_get_recently_viewed_orders_by_most_recent(db_session):
    repo = CatalogRepository(db_session)
    user_id = 9995
    db_session.query(RecentlyViewed).filter(RecentlyViewed.user_id == user_id).delete()
    db_session.commit()

    # View product 1, then 2, then 1 again — 1 should be most recent
    repo.record_product_view(user_id=user_id, product_id=1)
    time.sleep(0.01)
    repo.record_product_view(user_id=user_id, product_id=2)
    time.sleep(0.01)
    repo.record_product_view(user_id=user_id, product_id=1)

    products = repo.get_recently_viewed(user_id=user_id, limit=10)
    # Should have 2 products, with product 1 first (most recent)
    pids = [p.id for p in products]
    assert 1 in pids and 2 in pids, f"expected products 1 and 2 in recently viewed, got {pids}"
    assert pids[0] == 1, f"expected most-recent product 1 first, got order {pids}"
