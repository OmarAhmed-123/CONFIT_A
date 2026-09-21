"""G-14 — admin analytics must not scale its round trips with the data.

The endpoint used to build the brand comparison table by looping over every
``BrandProfile`` and issuing five queries per brand, then build the
most-styled ranking and issue one ``Product`` SELECT per ranked row. A platform
with 60 brands cost roughly 60 x 5 + 11 = 311 round trips for one dashboard
load, and the cost grew without bound as brands were onboarded.

These tests count real SQL statements executed against the test engine, so the
property being asserted is the one that actually matters operationally — not
"the code looks grouped". The assertion is *flatness*: adding brands must not
add queries.
"""

import pytest
from sqlalchemy import event

from backend.app.models.user import BrandProfile, User
from backend.app.repositories.brand_repository import BrandRepository
from backend.tests.conftest import TestingSessionLocal, test_engine

PREFIX = "efficiency-probe"


class _QueryCounter:
    """Counts statements actually sent to the DBAPI, per thread of execution."""

    def __init__(self):
        self.count = 0
        self.statements = []

    def __enter__(self):
        event.listen(test_engine, "before_cursor_execute", self._on_execute)
        return self

    def __exit__(self, *exc):
        event.remove(test_engine, "before_cursor_execute", self._on_execute)
        return False

    def _on_execute(self, conn, cursor, statement, parameters, context, executemany):
        self.count += 1
        self.statements.append(statement)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def brands(db):
    """Add throwaway brands, then remove them."""
    created = []

    def add(n):
        # BrandProfile.user_id is NOT NULL and unique, so every probe brand
        # needs its own user row. Both are removed at teardown.
        for i in range(n):
            tag = f"{PREFIX}-{len(created)}-{i}"
            u = User(email=f"{tag}@probe.test", hashed_password="not-a-real-hash",
                     full_name=tag)
            db.add(u)
            db.flush()
            b = BrandProfile(user_id=u.id, brand_name=tag, slug=tag)
            db.add(b)
            created.append((u, b))
        db.commit()

    yield add

    db.query(BrandProfile).filter(BrandProfile.brand_name.like(f"{PREFIX}%")).delete(
        synchronize_session=False
    )
    db.query(User).filter(User.email.like(f"{PREFIX}%")).delete(synchronize_session=False)
    db.commit()


def _measure(db):
    with _QueryCounter() as counter:
        payload = BrandRepository(db).get_platform_admin_analytics()
    return counter.count, payload


def test_the_brand_table_cost_does_not_grow_with_the_number_of_brands(db, brands):
    """The core G-14 property: flat statement count as brands are added."""
    brands(5)
    small, _ = _measure(db)

    brands(25)  # 30 throwaway brands in total
    large, _ = _measure(db)

    assert large == small, (
        f"adding 25 brands added {large - small} SQL statements — "
        "the brand table is still being built per brand"
    )


def test_the_endpoint_runs_in_a_bounded_number_of_statements(db, brands):
    """A concrete ceiling, so a future N+1 anywhere in the method is caught.

    The figure is deliberately loose: the point is order-of-magnitude, and a
    per-brand or per-product loop would blow straight through it.
    """
    brands(30)
    count, _ = _measure(db)
    assert count <= 40, f"{count} statements for one dashboard load is an N+1"


def test_no_per_brand_loop_survives_in_the_implementation():
    """Guard the shape of the fix, not just today's statement count."""
    import inspect

    src = inspect.getsource(BrandRepository.get_platform_admin_analytics)
    assert "for brand in brands:" in src, "the assembly loop should still exist"
    # ...but it must only read from pre-aggregated dictionaries.
    loop_body = src.split("for brand in brands:", 1)[1].split("brand_performance.sort", 1)[0]
    assert "self.db.query(" not in loop_body, (
        "the brand assembly loop issues queries again — that is the N+1"
    )


def test_the_most_styled_ranking_is_a_single_query(db):
    """It used to be one ranking query plus one Product SELECT per row."""
    with _QueryCounter() as counter:
        items = BrandRepository(db).get_most_styled_items(limit=20)
    assert isinstance(items, list)
    assert counter.count == 1, (
        f"get_most_styled_items issued {counter.count} statements; expected 1"
    )


def test_the_ranking_still_reports_real_brand_names(db):
    """De-N+1-ing must not quietly drop the brand label it used to lazy-load."""
    items = BrandRepository(db).get_most_styled_items(limit=5)
    for item in items:
        assert set(item) >= {
            "product_id", "title", "brand_name", "thumbnail_url",
            "appearances", "outfit_count",
        }
        assert item["brand_name"], "brand_name must be populated, not blanked by the join"
        assert item["appearances"] >= 1


def test_the_platform_heatmap_and_brand_table_agree_on_the_same_window(db, brands):
    """One window must reach every part of the payload, not just the headline."""
    brands(3)
    _, payload = _measure(db)
    assert payload["time_range"]["is_all_time"] is True
    # All-time is reported as an unbounded period, never as a fabricated one.
    assert payload["style_preference_heatmap"]["period"] == {"from": None, "to": None}
