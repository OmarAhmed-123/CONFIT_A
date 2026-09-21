"""G-15 — the admin analytics time window is real, not a parameter that lies.

Before this change ``/admin/analytics`` had no time dimension at all: every
figure was lifetime-only, so the dashboard could not answer "this month" — the
one question a dashboard exists for. Accepting a parameter and then ignoring it
would have been worse than not accepting one, so these tests assert the window
actually changes the numbers, that its boundary semantics match the contract
``/admin/audit`` already publishes, and that an empty window reports zeros
rather than falling back to invented values.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app.core.timeutils import TimeRange, TimeRangeError
from backend.app.models.commerce import Order
from backend.app.repositories.brand_repository import BrandRepository
from backend.tests.conftest import TestingSessionLocal

PREFIX = "timerange-probe"


def _login(client: TestClient, email: str) -> str:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def admin(client: TestClient):
    return {"Authorization": f"Bearer {_login(client, 'admin@confit.io')}"}


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _cleanup(db):
    db.query(Order).filter(Order.order_number.like(f"{PREFIX}%")).delete(
        synchronize_session=False
    )
    db.commit()


@pytest.fixture
def orders(db):
    """Create orders with explicit created_at values, then delete them."""
    _cleanup(db)
    made = []

    def add(age_days, amount, status="delivered", tag=""):
        when = datetime.now(timezone.utc) - timedelta(days=age_days)
        o = Order(
            order_number=f"{PREFIX}-{tag}-{age_days}-{len(made)}",
            total_amount=amount,
            subtotal_amount=amount,
            status=status,
            created_at=when,
            updated_at=when,
        )
        db.add(o)
        made.append(o)
        db.commit()
        return o

    yield add
    _cleanup(db)


# --- the value object -------------------------------------------------------


def test_an_unbounded_window_reports_itself_as_all_time():
    assert TimeRange.resolve().is_all_time is True
    assert TimeRange.resolve().describe()["source"] == "all_time"


def test_days_produces_a_real_lower_bound():
    window = TimeRange.resolve(days=7)
    assert window.date_from is not None
    assert window.date_to is None
    delta = datetime.now(timezone.utc).replace(tzinfo=None) - window.date_from
    assert timedelta(days=6, hours=23) < delta < timedelta(days=7, hours=1)


def test_days_zero_or_negative_is_rejected():
    for bad in (0, -1, -365):
        with pytest.raises(TimeRangeError):
            TimeRange.resolve(days=bad)


def test_days_and_an_explicit_range_cannot_both_be_given():
    with pytest.raises(TimeRangeError, match="not both"):
        TimeRange.resolve(days=7, date_from=datetime(2026, 1, 1))


def test_an_inverted_range_is_rejected():
    with pytest.raises(TimeRangeError, match="must not be before"):
        TimeRange.resolve(date_from=datetime(2026, 2, 1), date_to=datetime(2026, 1, 1))


def test_a_same_day_range_is_valid_and_inclusive():
    """Midnight-to-midnight of one day must match, not return nothing."""
    day = datetime(2026, 3, 5)
    window = TimeRange.resolve(date_from=day, date_to=day)
    assert window.is_all_time is False
    assert window.describe()["date_to_inclusive"] is True


def test_aware_timestamps_are_normalised_to_naive_utc():
    """SQLite stores naive; an aware bound would silently match nothing."""
    window = TimeRange.resolve(
        date_from=datetime(2026, 1, 1, 12, tzinfo=timezone.utc),
        date_to=datetime(2026, 2, 1, 12, tzinfo=timezone.utc),
    )
    assert window.date_from.tzinfo is None
    assert window.date_to.tzinfo is None


def test_the_boundary_contract_matches_the_audit_endpoint():
    """/admin/audit filters ``timestamp <= date_to``; analytics must agree.

    Two endpoints on one admin surface with different boundary meanings is an
    API-contract gap, so this pins the operator rather than trusting a docstring.
    """
    from sqlalchemy import Column, DateTime

    column = Column("created_at", DateTime)
    rendered = [str(c) for c in TimeRange.resolve(
        date_from=datetime(2026, 1, 1), date_to=datetime(2026, 2, 1)
    ).bound(column)]
    assert any(">=" in r for r in rendered), rendered
    assert any("<=" in r for r in rendered), rendered


# --- the window must actually reach the SQL --------------------------------


def test_the_window_changes_the_numbers(db, orders):
    orders(400, 100, tag="old")
    orders(1, 250, tag="new")

    repo = BrandRepository(db)
    everything = repo.get_platform_admin_analytics()
    recent = repo.get_platform_admin_analytics(TimeRange.resolve(days=30))

    assert recent["total_orders"] < everything["total_orders"], (
        "a 30-day window returned the all-time order count — the filter is not applied"
    )
    # The database is shared for the whole session, so assert the *difference*:
    # the 400-day-old order must be exactly what the window removes.
    assert everything["total_gmv"] - recent["total_gmv"] == pytest.approx(100.0, abs=0.01), (
        "the 400-day-old order was not excluded by the 30-day window"
    )
    assert everything["total_orders"] - recent["total_orders"] == 1


def test_an_empty_window_returns_zeros_and_says_so(db, orders):
    """The honesty property: no data means no numbers, never invented ones."""
    orders(2, 500, tag="recent")
    payload = BrandRepository(db).get_platform_admin_analytics(
        TimeRange.resolve(date_from=datetime(2001, 1, 1), date_to=datetime(2001, 12, 31))
    )
    assert payload["total_orders"] == 0, "a 2001 window must contain no orders"
    assert payload["total_gmv"] == 0.0
    assert payload["most_styled_items"] == []
    assert payload["style_preference_heatmap"]["data_available"] is False
    assert payload["time_range"]["is_all_time"] is False


def test_the_payload_reports_the_window_it_actually_used(db, orders):
    payload = BrandRepository(db).get_platform_admin_analytics(TimeRange.resolve(days=90))
    assert payload["time_range"]["source"] == "last_90_days"
    assert payload["methodology"]["time_window"]["source"] == "last_90_days"
    assert "inclusive" in payload["methodology"]["boundary_semantics"]


def test_date_to_is_inclusive_at_the_boundary(db, orders):
    """An order inside the window but at its edge must be counted.

    Read the timestamp back from the database rather than recomputing it: the
    ORM writes aware UTC while SQLite stores naive, and guessing here would
    make the test pass for the wrong reason.
    """
    from backend.app.core.timeutils import to_naive_utc

    o = orders(10, 321, tag="boundary")
    db.refresh(o)
    placed_at = to_naive_utc(o.created_at)
    assert placed_at is not None

    repo = BrandRepository(db)
    just_before = repo.get_platform_admin_analytics(
        TimeRange.resolve(date_from=placed_at - timedelta(hours=1),
                          date_to=placed_at - timedelta(seconds=1))
    )["total_gmv"]
    including = repo.get_platform_admin_analytics(
        TimeRange.resolve(date_from=placed_at - timedelta(hours=1), date_to=placed_at)
    )["total_gmv"]

    assert including - just_before == pytest.approx(321.0, abs=0.01), (
        "an order exactly on the inclusive upper bound was excluded"
    )


# --- through the real HTTP surface -----------------------------------------


def test_the_endpoint_accepts_days(client: TestClient, admin, db, orders):
    orders(400, 100, tag="old")
    orders(1, 250, tag="new")

    all_time = client.get("/api/v1/admin/analytics", headers=admin)
    assert all_time.status_code == 200, all_time.text
    assert all_time.json()["time_range"]["is_all_time"] is True

    windowed = client.get("/api/v1/admin/analytics?days=30", headers=admin)
    assert windowed.status_code == 200, windowed.text
    body = windowed.json()
    assert body["time_range"]["source"] == "last_30_days"
    assert body["total_orders"] < all_time.json()["total_orders"]


def test_the_endpoint_accepts_an_explicit_range(client: TestClient, admin, db, orders):
    orders(1, 77, tag="new")
    r = client.get(
        "/api/v1/admin/analytics?date_from=2000-01-01T00:00:00Z&date_to=2000-12-31T00:00:00Z",
        headers=admin,
    )
    assert r.status_code == 200, r.text
    assert r.json()["total_orders"] == 0


def test_conflicting_parameters_are_rejected_with_422(client: TestClient, admin):
    r = client.get(
        "/api/v1/admin/analytics?days=7&date_from=2026-01-01T00:00:00Z", headers=admin
    )
    assert r.status_code == 422, r.text


def test_an_inverted_range_is_rejected_with_422(client: TestClient, admin):
    r = client.get(
        "/api/v1/admin/analytics?date_from=2026-06-01T00:00:00Z&date_to=2026-01-01T00:00:00Z",
        headers=admin,
    )
    assert r.status_code == 422, r.text


def test_days_outside_the_accepted_range_is_rejected(client: TestClient, admin):
    assert client.get("/api/v1/admin/analytics?days=0", headers=admin).status_code == 422
    assert client.get("/api/v1/admin/analytics?days=99999", headers=admin).status_code == 422


def test_all_three_analytics_aliases_honour_the_window(client: TestClient, admin, db, orders):
    """/analytics, /overview and /analytics/overview are one handler, one contract."""
    orders(400, 100, tag="old")
    orders(1, 250, tag="new")
    for path in ("/api/v1/admin/analytics", "/api/v1/admin/overview",
                 "/api/v1/admin/analytics/overview"):
        r = client.get(f"{path}?days=30", headers=admin)
        assert r.status_code == 200, (path, r.text)
        assert r.json()["time_range"]["source"] == "last_30_days", path


def test_the_window_is_not_available_to_a_consumer(client: TestClient):
    """A new parameter must not become a new way past the admin gate."""
    r = client.get("/api/v1/admin/analytics?days=30")
    assert r.status_code in (401, 403), r.text
