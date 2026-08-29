import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.core.database import get_db
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
    os.makedirs("./backend/data", exist_ok=True)
    seed_database(target_engine=test_engine, force=True)  # tests intentionally reset their own throwaway DB
    yield


@pytest.fixture
def client():
    return TestClient(app)
