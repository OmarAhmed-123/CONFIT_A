"""Startup dev-seed must not hold the catalogue-probe session open while seeding.

Regression for a PostgreSQL startup hang found 2026-10-26 while running the
stylist load test against PostgreSQL 16 with uvicorn workers (1 and 2):

    lifespan() opened ``Session(engine)``, ran ``Category.count()`` (which on
    PostgreSQL leaves the connection idle-in-transaction holding an
    AccessShareLock on ``categories``) and — still inside that ``with`` block —
    called ``seed_database(target_engine=engine)``. The seeder opens a SECOND
    connection and runs ``drop_all()``; ``DROP TABLE products`` needs an
    AccessExclusiveLock on the FK-referenced ``categories`` table, which the
    first (idle) connection blocks forever. PostgreSQL cannot detect it as a
    deadlock because the idle session is not *waiting*, so the worker never
    binds its port. SQLite has no table-level locking, so this was invisible
    in the test suite and in local sqlite development.

The behavioural contract this test pins: when ``seed_database`` is invoked
from the lifespan, the application engine has ZERO checked-out connections.
"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool


@pytest.fixture
def empty_engine(tmp_path):
    # A real QueuePool (like the PostgreSQL engine) so ``pool.checkedout()``
    # reflects connections still held by an open Session.
    eng = create_engine(
        f"sqlite:///{tmp_path / 'startup.db'}",
        connect_args={"check_same_thread": False},
        poolclass=QueuePool,
    )
    yield eng
    eng.dispose()


def test_seed_is_called_only_after_probe_session_is_closed(monkeypatch, empty_engine):
    import backend.app.main as main_mod
    from backend.app.core import schema_gate
    from backend.app.core.database import Base

    # The lifespan's dev path runs create_all() on the engine it is given.
    Base.metadata.create_all(bind=empty_engine)
    monkeypatch.setattr(main_mod, "engine", empty_engine)
    monkeypatch.setattr(main_mod.settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(schema_gate, "enforce_at_startup", lambda *a, **k: None)

    observed: dict = {}

    def fake_seed(target_engine=None, force=False):
        # The deadlock precondition: a connection still checked out from the
        # pool (the probe session) at the moment the seeder starts.
        observed["checked_out"] = target_engine.pool.checkedout()
        observed["engine_is_app_engine"] = target_engine is empty_engine

    import backend.app.seed_data as seed_mod
    monkeypatch.setattr(seed_mod, "seed_database", fake_seed)

    async def run():
        async with main_mod.lifespan(main_mod.app):
            pass

    asyncio.run(run())

    assert observed, "empty catalogue must trigger the dev seed"
    assert observed["engine_is_app_engine"] is True
    assert observed["checked_out"] == 0, (
        "probe session must be closed before seed_database() runs "
        "(PostgreSQL self-deadlock: idle-in-transaction AccessShareLock on "
        "categories blocks the seeder's DROP TABLE products)"
    )


def test_populated_catalogue_does_not_seed(monkeypatch, empty_engine):
    from sqlalchemy.orm import Session

    import backend.app.main as main_mod
    from backend.app.core import schema_gate
    from backend.app.core.database import Base
    from backend.app.models.catalog import Category

    Base.metadata.create_all(bind=empty_engine)
    with Session(empty_engine) as s:
        s.add(Category(name="Tops", name_ar="قمصان", slug="tops"))
        s.commit()
    monkeypatch.setattr(main_mod, "engine", empty_engine)
    monkeypatch.setattr(main_mod.settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(schema_gate, "enforce_at_startup", lambda *a, **k: None)

    called = []
    import backend.app.seed_data as seed_mod
    monkeypatch.setattr(seed_mod, "seed_database", lambda **kw: called.append(kw))

    async def run():
        async with main_mod.lifespan(main_mod.app):
            pass

    asyncio.run(run())
    assert called == []
