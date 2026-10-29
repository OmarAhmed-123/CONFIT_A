"""Concurrent initialisation of an EMPTY PostgreSQL database (2026-10-29).

Reproduced before the fix with the then-unlocked ``Base.metadata.create_all()``:
4 threads × 3 trials on PostgreSQL 17 → 9 failures, all
``psycopg2.errors.UniqueViolation: duplicate key value violates unique
constraint "pg_type_typname_nsp_index"`` (the create_all DDL race). The seed
step was already serialised by the startup advisory lock; create_all was not.

``initialise_dev_database`` now runs create_all AND the decide-and-seed step
inside one ``seed_lock`` critical section. Skipped without a throwaway
PostgreSQL DSN (``CONFIT_CONCURRENCY_PG_URL``) — the test wipes ``public``.
"""
from __future__ import annotations

import os
import threading

import pytest
from sqlalchemy import create_engine, text

from backend.app.core.postgres_url import normalise_postgres_url

PG_URL = os.environ.get("CONFIT_CONCURRENCY_PG_URL", "")
pytestmark = pytest.mark.skipif(
    not PG_URL.startswith(("postgresql://", "postgres://", "postgresql+")),
    reason="CONFIT_CONCURRENCY_PG_URL not set to a PostgreSQL DSN (throwaway DB required)",
)

WORKERS = 4
TRIALS = 3


def _engine():
    url, connect_args = normalise_postgres_url(PG_URL)
    return create_engine(url, connect_args=connect_args, pool_size=WORKERS * 2, max_overflow=WORKERS * 2)


def _wipe(engine):
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))


def test_concurrent_workers_initialise_empty_database_exactly_once():
    import backend.app.models  # noqa: F401  (register every table on Base)
    from backend.app.core.startup_init import initialise_dev_database
    from backend.app.models.catalog import Category

    engine = _engine()
    for trial in range(TRIALS):
        _wipe(engine)
        barrier = threading.Barrier(WORKERS)
        errors: list[str] = []
        results: list[dict] = []

        def worker(barrier=barrier, results=results, errors=errors):
            barrier.wait()
            try:
                results.append(initialise_dev_database(engine))
            except Exception as exc:  # noqa: BLE001 - the assertion below reports it
                errors.append(f"{type(exc).__name__}: {str(exc).splitlines()[0][:160]}")

        threads = [threading.Thread(target=worker, name=f"w{i}") for i in range(WORKERS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=240)
        assert not errors, f"trial {trial}: {errors}"
        assert len(results) == WORKERS
        assert all(r["locked"] for r in results), "advisory lock must be held on PostgreSQL"
        assert sum(1 for r in results if r["seeded"]) == 1, f"trial {trial}: seeded by {results}"
        # Every worker leaves behind a complete, seeded schema.
        from sqlalchemy.orm import Session
        with Session(engine) as s:
            assert s.query(Category).count() > 0
    engine.dispose()
