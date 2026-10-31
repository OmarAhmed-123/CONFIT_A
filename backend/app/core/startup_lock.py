"""Cross-worker serialisation of the development seed step.

Only the decide-and-seed block in ``main.lifespan`` uses this. Production never
reaches it (startup skips create_all/seed when ENVIRONMENT=production), so the
lock changes nothing there; it exists so that two or more uvicorn workers
booting against an empty staging/dev PostgreSQL do not interleave
``drop_all()`` with another worker's probe/schema gate.

Design notes
* ``pg_advisory_lock`` is a *session* lock, so it is taken on a dedicated
  connection with AUTOCOMMIT and released explicitly; the connection never
  touches a table, so it can never hold the FK locks that produced the
  self-deadlock fixed on 2026-10-26.
* Non-PostgreSQL dialects (SQLite in tests) get a no-op context.
* If the lock cannot be obtained for any reason the caller proceeds unlocked
  (fail-open) and the reason is logged: startup must never hang on telemetry.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import text
from sqlalchemy.engine import Engine

# Arbitrary but stable 64-bit key, namespaced to CONFIT startup seeding.
SEED_LOCK_KEY = 0x434F4E4649545F53  # "CONFIT_S"


@contextmanager
def seed_lock(engine: Engine, *, logger=None) -> Iterator[bool]:
    """Yield True while holding the PostgreSQL advisory lock, False otherwise."""
    if engine.dialect.name != "postgresql":
        yield False
        return
    conn = None
    try:
        conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": SEED_LOCK_KEY})
    except Exception as exc:  # pragma: no cover - defensive
        if logger:
            logger.warn("startup_seed_lock_unavailable", error=str(exc)[:200])
        if conn is not None:
            conn.close()
        yield False
        return
    try:
        yield True
    finally:
        try:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": SEED_LOCK_KEY})
        finally:
            conn.close()
