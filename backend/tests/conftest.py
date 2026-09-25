import os

# --- VTON segmentation policy for the TEST SUITE -----------------------------
# pipeline.segmentation prefers rembg (u2net_human_seg). Loading that ONNX
# session costs ~900MB RSS, which OOM-kills small CI runners (observed: pytest
# killed with exit 137 on a 2GB box) and makes mask geometry depend on whether
# an optional dependency happens to be installed — the same test then passes in
# CI and fails locally.
#
# The suite therefore pins the DETERMINISTIC heuristic path by default so mask
# assertions are reproducible everywhere. Set CONFIT_VTON_DISABLE_REMBG=0 to
# exercise the real segmentation model locally (see
# test_vton_single_production_path.py for the model-path assertions, and the
# release report for the runtime-verified rembg evidence).
os.environ.setdefault("CONFIT_VTON_DISABLE_REMBG", "1")

# --- AI readiness probing is OFF for the test suite -------------------------
# The consumer capability endpoint can start a bounded background readiness
# refresh (services/ai_readiness.refresh_when_unmeasured) — the measured verdict
# used to exist only on whichever instance the operator probe happened to warm,
# so the shopper-facing contract answered `ai_stylist_live = false` for a
# healthy provider. Inside a test session that turns any read of
# /catalog/capabilities into a real outbound provider call; with placeholder
# keys it answers `unavailable`, and the snapshot then leaks into unrelated
# tests. MEASURED: it made a self-heal test read `unavailable` where the truth
# was `not_probed`.
#
# This must be set BEFORE backend.app.core.config is imported (settings reads
# the environment once at import), which is why it sits at the top of this file
# and not next to the limiter switch below.
#
# Tests that exercise probing mock the transport and re-enable it explicitly,
# exactly like test_rate_limiting.py does for the limiter. Production is
# unaffected: AI_PROBE_ENABLED defaults to True.
os.environ.setdefault("AI_PROBE_ENABLED", "false")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from backend.app.core.database import get_db, engine as app_engine
from backend.app.seed_data import seed_database
from backend.app.main import app

# The suite runs on SQLite by default (fast, no service to start). SQLite is NOT
# PostgreSQL: SQLAlchemy documents different transaction/concurrency behaviour for
# it, so a green SQLite run does not prove the Postgres behaviour this deployment
# actually uses. ``CONFIT_TEST_DB_URL`` therefore lets the same suite run against a
# real PostgreSQL instance — that is how the concurrency-sensitive paths
# (idempotency arbitration, stock decrement, order creation) were measured on
# Postgres instead of being asserted from SQLite. Example:
#
#   CONFIT_TEST_DB_URL=postgresql+psycopg2://confit@/confit_probe?host=/tmp \
#       python -m pytest backend/tests -q
#
# Nothing about the default changes when the variable is unset.
# Deliberately NOT an alias of ``CONFIT_TEST_PG_URL``, although the names look
# interchangeable. Measured 2026-09-23: making this variable read that one turns
# the CI step "Schema-drift gate + migration tests on PostgreSQL" red with 8
# failures — "relation \"store_locations\" does not exist" — because the drift
# tests drop and re-create tables in their target on purpose, while this engine
# also answers the application's requests. The two variables therefore name
# different things and must stay separate:
#   CONFIT_TEST_DB_URL  - a database the whole suite may read AND write (seeded);
#   CONFIT_TEST_PG_URL  - a scratch database the migration/drift tests may drop.
# Unset -> unchanged SQLite default.
TEST_DB_URL = os.environ.get("CONFIT_TEST_DB_URL", "sqlite:///./backend/data/confit_test.db")

#: Dialect-specific connection arguments live HERE and nowhere else.
#  Ten test modules used to repeat ``create_engine(TEST_DB_URL,
#  connect_args={"check_same_thread": False})``. Pointing CONFIT_TEST_DB_URL at
#  PostgreSQL then handed that SQLite-only option to psycopg2, which answers
#  "invalid dsn: invalid connection option \"check_same_thread\"" — the suite
#  reported database errors that were really one duplicated line. The factory
#  below is the single owner of that decision.
def new_test_engine(url: str = None):
    target = url or TEST_DB_URL
    if target.startswith("sqlite"):
        return create_engine(target, connect_args={"check_same_thread": False})
    # Route through the application's own URL rule, so a test can never exercise a
    # driver/SQLAlchemy default that production does not use. (SQLAlchemy 2.1 made
    # a bare `postgresql://` mean psycopg 3 rather than psycopg2 — see
    # backend/app/core/postgres_url.py.)
    from backend.app.core.postgres_url import normalise_postgres_url
    target, connect_args = normalise_postgres_url(target)
    return create_engine(target, connect_args=connect_args, pool_pre_ping=True)


def normalise_pg_url(url: str):
    """(url, connect_args) for a PostgreSQL DSN, via the application's rule."""
    from backend.app.core.postgres_url import normalise_postgres_url
    return normalise_postgres_url(url)


test_engine = new_test_engine()
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

# The suite issues far more requests per minute than the production limits
# allow (that's the point of the limits), so tests disable the limiter
# globally; test_rate_limiting.py re-enables it explicitly to prove the 429
# path works for real.
app.state.limiter.enabled = False

# Fail loudly if the switch above did not take (settings is imported once): a
# silent miss would let the suite make real provider calls.
from backend.app.core.config import settings as _settings  # noqa: E402

if getattr(_settings, "AI_PROBE_ENABLED", True):
    raise RuntimeError(
        "AI_PROBE_ENABLED must be False for the test suite; the env var was set "
        "after settings was imported. Move it above the first backend.app import."
    )



@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Seeds BOTH the test DB and the app-level dev DB at session start.

    Rationale: the majority of tests go through TestClient + override_get_db
    -> test_engine and are fully isolated. A handful of tests (dynamic try-on
    repository, group2 composer, group1 diagnostic) bypass the override and
    hit the app-level ``engine`` / ``SessionLocal`` directly. When
    ``backend/data/confit.db`` was force-tracked in git those tests picked up
    the committed seed data by accident. That tracked binary was polluting
    every local dev run (Group 4 closure prompt §13), so it is now
    ``.gitignore``d — and this fixture takes over the seed responsibility
    for the dev engine so those tests still find their expected data on a
    fresh checkout / CI runner.
    """
    if TEST_DB_URL.startswith("sqlite"):
        os.makedirs("./backend/data", exist_ok=True)
    seed_database(target_engine=test_engine, force=True)  # tests intentionally reset their own throwaway DB

    # ── Stock the throwaway DB so the suite cannot run itself out of inventory ──
    # Inventory is CONSUMED by every order the suite places, and the seeded stock for
    # some demo SKUs is smaller than the number of checkouts one session performs: the
    # clutch's only SKU ships with ``stock_level: 12`` while the order-placing helpers
    # each draw 1–2 units from whichever product the catalog lists first.
    # MEASURED 2026-09-23: after a full run that SKU sat at 0 units and seven tests in
    # two unrelated files failed with ``StopIteration`` from
    # ``next(s for s in detail["skus"] if s["is_in_stock"])`` — a harness running out of
    # stock, dressed up as a product failure. It cost real time to trace, and the same
    # run had passed only hours earlier, so the failure looked like a regression.
    # Stocking the throwaway DB makes a run repeatable. It cannot mask inventory
    # behaviour: tests that assert on stock either set their own levels through the API
    # or compare before/after values inside a session.
    # ``is_in_stock = 1`` is a SQLite-ism: there the column is an integer, while
    # PostgreSQL (the deployment's actual engine) defines it as BOOLEAN and rejects
    # the literal — measured: 50 errors, every one of them
    # "column \"is_in_stock\" is of type boolean but expression is of type integer".
    # The value is bound as a parameter with an explicit type so one statement runs
    # on both engines and the first PostgreSQL run of this suite was not a false alarm.
    with test_engine.begin() as conn:
        conn.execute(
            text("UPDATE product_skus SET stock_level = :stock, is_in_stock = :in_stock"),
            {"stock": 500, "in_stock": True},
        )
    # Also seed the app-level engine so tests that use SessionLocal directly
    # (i.e. not via the get_db override) have the same seed data available.
    # Both engines resolve to file-scoped SQLite DBs, so this is cheap.
    seed_database(target_engine=app_engine, force=True)
    yield


@pytest.fixture
def client():
    return TestClient(app)
