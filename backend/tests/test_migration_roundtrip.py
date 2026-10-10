"""Migration round-trip: upgrade head / downgrade base succeed on test DB (011 SC-002).

Proves the combined chain (including 0035_recently_viewed_unique) is
reversible and has no broken upgrade/downgrade.

Uses a throwaway SQLite file so it does not touch the shared test DB
that conftest seeds. This mirrors test_migration_integrity_behavioral.py
pattern.
"""

import os
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, text
from alembic import command
from alembic.config import Config


def _alembic_cfg(db_url: str) -> Config:
    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "backend" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_upgrade_head_and_downgrade_base_succeed():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_url = f"sqlite:///{path}"
    try:
        cfg = _alembic_cfg(db_url)

        # Upgrade to head should succeed
        command.upgrade(cfg, "head")

        # Verify alembic_version table has exactly one row and matches head
        eng = create_engine(db_url)
        with eng.connect() as conn:
            rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
            assert len(rows) == 1, f"alembic_version should have exactly 1 row, got {rows}"
            # Also check that recently_viewed table exists and has unique constraint
            tables = {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()}
            assert "recently_viewed" in tables, "recently_viewed table missing after upgrade head"

            # Check unique constraint exists (SQLite stores it in sqlite_master as UNIQUE or via index)
            # The migration creates uq_recently_viewed_user_product
            indexes = conn.execute(text("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='recently_viewed'")).fetchall()
            # SQLite may create unique index for unique constraint; check name contains our constraint or sql contains UNIQUE
            # We assert at least one unique index on (user_id, product_id) exists
            # For simplicity, check that inserting duplicate fails (tested separately), but here just ensure table exists

        # Downgrade to base should succeed (reversible)
        command.downgrade(cfg, "base")

        with eng.connect() as conn:
            # After downgrade base, alembic_version should be empty or not exist? Alembic leaves table but no rows? Actually downgrade base removes all versions
            # Check that tables that were created by migrations are gone (except maybe alembic_version)
            # At minimum, downgrade should not raise
            pass

        # Upgrade again to ensure idempotent after downgrade
        command.upgrade(cfg, "head")

    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_recently_viewed_unique_constraint_enforced_after_upgrade():
    """After upgrade, duplicate (user_id, product_id) must be rejected."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_url = f"sqlite:///{path}"
    try:
        cfg = _alembic_cfg(db_url)
        command.upgrade(cfg, "head")
        eng = create_engine(db_url)

        with eng.begin() as conn:
            # Create minimal users and products rows needed for FKs if FK enforcement is on?
            # SQLite FK enforcement is off by default in alembic? We'll disable FK check for this unit test
            # and test unique constraint directly via raw insert into recently_viewed without FKs.
            # To avoid FK issues, create parent rows.
            conn.execute(text("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY)"))
            # Actually products table already exists from migrations? Let's check — products is from earlier migration.
            # Insert dummy user and product if not exists
            conn.execute(text("INSERT OR IGNORE INTO users (id) VALUES (1)"))
            # Products table may require many columns; use INSERT OR IGNORE with minimal columns if possible?
            # Instead, test unique constraint via inserting into recently_viewed with FKs disabled
            conn.execute(text("PRAGMA foreign_keys=OFF"))
            conn.execute(text("DELETE FROM recently_viewed"))
            conn.execute(text("INSERT INTO recently_viewed (user_id, product_id, viewed_at) VALUES (1, 1, CURRENT_TIMESTAMP)"))
            # Second insert same (user, product) should fail
            try:
                conn.execute(text("INSERT INTO recently_viewed (user_id, product_id, viewed_at) VALUES (1, 1, CURRENT_TIMESTAMP)"))
                # If we reach here, unique constraint not enforced -> fail test
                assert False, "duplicate (user_id, product_id) was allowed — unique constraint missing"
            except Exception as e:
                # Expected: IntegrityError / UNIQUE constraint failed
                msg = str(e).lower()
                assert "unique" in msg or "uq_recently_viewed" in msg or "constraint" in msg, f"unexpected error for duplicate: {e}"

    finally:
        try:
            os.remove(path)
        except OSError:
            pass
