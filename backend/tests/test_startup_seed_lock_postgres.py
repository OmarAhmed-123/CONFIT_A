"""Two workers booting against an EMPTY PostgreSQL must not interleave the
development seeder's drop_all() with each other's probe/schema gate.

Reproduced 2026-10-27 (PostgreSQL 17, uvicorn --workers 2, fresh `alembic
upgrade head`): 3/3 runs logged `relation "categories" does not exist` and a
false `schema_gate verdict=drift` on one worker. Fixed with a session-level
advisory lock (backend/app/core/startup_lock.py). Skipped without a throwaway
PostgreSQL DSN, exactly like test_mfa_concurrency_postgres.py.
"""
from __future__ import annotations

import os
import threading
import time

import pytest
from sqlalchemy import create_engine, text

from backend.app.core.startup_lock import SEED_LOCK_KEY, seed_lock

PG_URL = os.environ.get("CONFIT_CONCURRENCY_PG_URL", "")
pytestmark = pytest.mark.skipif(
    not PG_URL.startswith(("postgresql://", "postgres://", "postgresql+")),
    reason="CONFIT_CONCURRENCY_PG_URL not set to a PostgreSQL DSN (throwaway DB required)",
)


def test_seed_lock_serialises_concurrent_holders_and_releases():
    engine = create_engine(PG_URL, pool_pre_ping=True)
    order: list[str] = []
    inside = threading.Semaphore(1)

    def worker(name: str, hold: float):
        with seed_lock(engine) as held:
            assert held is True
            assert inside.acquire(blocking=False), "two workers inside the seed step at once"
            order.append(f"{name}:in")
            time.sleep(hold)
            order.append(f"{name}:out")
            inside.release()

    t1 = threading.Thread(target=worker, args=("a", 0.6))
    t2 = threading.Thread(target=worker, args=("b", 0.1))
    t1.start(); time.sleep(0.1); t2.start(); t1.join(); t2.join()
    assert order == ["a:in", "a:out", "b:in", "b:out"]
    # released: a third party can take it immediately
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        assert c.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": SEED_LOCK_KEY}).scalar() is True
        c.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": SEED_LOCK_KEY})
    engine.dispose()


def test_seed_lock_connection_holds_no_table_locks():
    """The lock connection must never block a concurrent DROP/ALTER (the
    2026-10-26 self-deadlock class)."""
    engine = create_engine(PG_URL, pool_pre_ping=True)
    with engine.begin() as c:
        c.execute(text("CREATE TABLE IF NOT EXISTS _seed_lock_probe (id int)"))
    with seed_lock(engine):
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            c.execute(text("SET lock_timeout = '2s'"))
            c.execute(text("DROP TABLE _seed_lock_probe"))  # would raise lock_not_available if blocked
    engine.dispose()


def test_seed_lock_is_noop_on_sqlite(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/x.db")
    with seed_lock(engine) as held:
        assert held is False
