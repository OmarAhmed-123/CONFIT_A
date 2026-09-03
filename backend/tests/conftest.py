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

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.core.database import get_db, engine as app_engine
from backend.app.seed_data import seed_database
from backend.app.main import app

TEST_DB_URL = "sqlite:///./backend/data/confit_test.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
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
    os.makedirs("./backend/data", exist_ok=True)
    seed_database(target_engine=test_engine, force=True)  # tests intentionally reset their own throwaway DB
    # Also seed the app-level engine so tests that use SessionLocal directly
    # (i.e. not via the get_db override) have the same seed data available.
    # Both engines resolve to file-scoped SQLite DBs, so this is cheap.
    seed_database(target_engine=app_engine, force=True)
    yield


@pytest.fixture
def client():
    return TestClient(app)
