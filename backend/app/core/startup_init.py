"""Development/CI database initialisation (create_all + first seed).

Extracted from ``main.lifespan`` on 2026-10-29 so the whole step can be
exercised by a concurrency test. Production never calls this: startup skips it
when ENVIRONMENT=production and relies on ``alembic upgrade head``.

Why the whole step is under one advisory lock
---------------------------------------------
``Base.metadata.create_all()`` is not atomic on PostgreSQL. Two or more
uvicorn workers booting against an *empty* database used to run it
concurrently and one of them failed with ``duplicate key value violates unique
constraint "pg_type_typname_nsp_index"`` / ``relation ... already exists``
(the create_all race), after which the seed decision below could observe a
half-created schema. The seed step was already serialised by
``startup_lock.seed_lock`` (2026-10-27); create_all now runs inside the same
critical section so exactly one worker creates and seeds while the others wait
and then observe a complete, seeded schema. No-op lock on SQLite.
"""
from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.app.core.startup_lock import seed_lock


def initialise_dev_database(engine: Engine, *, logger=None) -> dict:
    """Create missing tables and seed the catalogue if the database is empty.

    Returns a small dict for tests/log lines: ``{"seeded": bool, "locked": bool}``.
    Raises nothing it can avoid; the caller decides whether to swallow.
    """
    from backend.app.core.database import Base  # same metadata object main.py used
    from backend.app.models.catalog import Category

    seeded = False
    with seed_lock(engine, logger=logger) as locked:
        Base.metadata.create_all(bind=engine)
        # Decide INSIDE a short session, seed OUTSIDE it: seed_database() runs
        # drop_all() on a second connection and would self-deadlock against an
        # idle-in-transaction probe holding FK locks (verified 2026-10-26).
        with Session(engine) as s:
            needs_seed = s.query(Category).count() == 0
        if needs_seed:
            from backend.app.seed_data import seed_database
            seed_database(target_engine=engine)
            seeded = True
            if logger:
                logger.info("Database was empty — seeded the default catalogue")
    return {"seeded": seeded, "locked": bool(locked)}
