"""Query-count budget and single-definition tests for the brand analytics reads.

WHY A QUERY-COUNT TEST AND NOT A TIMING TEST
The audit measured /brand/analytics at ~4.8s and /partner/analytics/conversion at
~6.1s against the deployed app. Profiling the production database showed the
cause was NOT slow SQL: every statement costs roughly the same network round
trip regardless of what it touches, and the tables involved hold tens of rows.
Latency was therefore a function of HOW MANY round trips a request makes.

A wall-clock assertion would be useless here -- it passes trivially against a
local SQLite file and is flaky in CI. The durable, engine-independent invariant
is the number of statements issued. These tests pin that number, so the N+1
patterns and the redundant tenant lookups that caused the original latency
cannot silently return. If a change legitimately needs another query, the budget
must be raised deliberately, in review, with a reason.

They also pin the thing that makes the speedup safe: the dashboard and the
conversion endpoint must keep reading their shared counters from ONE definition.
"""
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import Base

from backend.app.models.catalog import Category, Product, ProductSKU
from backend.app.models.user import BrandProfile, User, UserRole
from backend.app.repositories.brand_repository import BrandRepository
from backend.app.services.brand_service import BrandService


class QueryCounter:
    """Counts SQL statements issued on a session's connection."""

    def __init__(self, session):
        self.session = session
        self.statements = []

    def __enter__(self):
        self._bind = self.session.get_bind()
        event.listen(self._bind, "after_cursor_execute", self._record)
        return self

    def __exit__(self, *exc):
        event.remove(self._bind, "after_cursor_execute", self._record)
        return False

    def _record(self, conn, cursor, statement, params, context, executemany):
        self.statements.append(" ".join(statement.split()))

    def __len__(self):
        return len(self.statements)

    def report(self):
        return "\n".join(f"  {i + 1}. {s[:110]}" for i, s in enumerate(self.statements))


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    yield db
    db.close()


@pytest.fixture
def tenant(db_session):
    """A brand with a handful of products, enough to expose per-product N+1s."""
    user = User(email="budget-brand@confit-portal-qa.example.com",
                hashed_password="x", full_name="Budget Brand",
                role=UserRole.BRAND_MANAGER, preferred_language="en",
                is_active=True, is_verified=True)
    db_session.add(user)
    db_session.flush()

    bp = BrandProfile(user_id=user.id, brand_name="Budget Brand",
                      slug="budget-brand", is_verified=True)
    db_session.add(bp)
    db_session.flush()

    cat = Category(name="Budget Cat", name_ar="فئة", slug="budget-cat")
    db_session.add(cat)
    db_session.flush()

    for i in range(5):
        p = Product(brand_id=bp.id, category_id=cat.id,
                    title=f"Budget Product {i}", title_ar=f"منتج {i}",
                    slug=f"budget-product-{i}", description="d", description_ar="d",
                    base_price=100, currency="AED", color_family="Navy",
                    thumbnail_url="https://example.com/a.jpg", is_active=True)
        db_session.add(p)
        db_session.flush()
        db_session.add(ProductSKU(product_id=p.id, brand_id=bp.id,
                                  sku_code=f"BUD-{i}", size="M", color="Navy",
                                  stock_level=5, is_in_stock=True))
    db_session.commit()
    return user, bp


class TestQueryBudget:
    """The number of round trips is the latency. Pin it."""

    def test_brand_analytics_stays_within_its_round_trip_budget(self, db_session, tenant):
        user, bp = tenant
        repo = BrandRepository(db_session)
        db_session.expire_all()

        with QueryCounter(db_session) as q:
            repo.get_brand_analytics(bp.id)

        # Measured budget for the current implementation. The point is the
        # CEILING: a per-product loop would blow straight past it.
        assert len(q) <= 8, (
            f"get_brand_analytics issued {len(q)} queries, budget is 8.\n"
            f"Each one is a network round trip in production.\n{q.report()}"
        )

    def test_conversion_endpoint_does_not_build_the_whole_dashboard(self, db_session, tenant):
        """The regression that made /conversion the slowest endpoint in the portal.

        It used to call the full dashboard to read six fields, paying for outfit
        rankings, return cohorts, BOPIS fulfilment and ad totals it then threw
        away. The snapshot must cost strictly less than the dashboard.
        """
        user, bp = tenant
        repo = BrandRepository(db_session)

        db_session.expire_all()
        with QueryCounter(db_session) as q_dash:
            repo.get_brand_analytics(bp.id)

        db_session.expire_all()
        with QueryCounter(db_session) as q_snap:
            repo.get_activity_snapshot(bp.id)

        assert len(q_snap) < len(q_dash), (
            f"activity snapshot issued {len(q_snap)} queries and the full dashboard "
            f"{len(q_dash)}. The snapshot exists precisely to be cheaper; if it is "
            f"not, /partner/analytics/conversion has regressed to building the "
            f"entire dashboard again."
        )
        assert len(q_snap) <= 3, f"snapshot budget is 3 queries, got {len(q_snap)}\n{q_snap.report()}"

    def test_tenant_resolution_is_not_repeated_within_one_request(self, db_session, tenant):
        """The brand_profiles row was being fetched three times per request."""
        user, bp = tenant
        db_session.expire_all()
        service = BrandService(db_session)

        with QueryCounter(db_session) as q:
            service.get_brand_profile_by_user(user)
            service.assert_brand_ownership(user, bp.id)
            service.get_brand_profile_by_user(user)

        brand_lookups = [s for s in q.statements
                         if "FROM brand_profiles" in s or "FROM brand_profiles".lower() in s.lower()]
        assert len(brand_lookups) <= 1, (
            f"resolved the tenant {len(brand_lookups)} times in one request; it must be "
            f"resolved once and reused.\n{q.report()}"
        )


class TestSharedDefinition:
    """Speed must not come at the cost of two screens disagreeing."""

    def test_dashboard_and_snapshot_report_the_same_counters(self, db_session, tenant):
        user, bp = tenant
        repo = BrandRepository(db_session)

        dash = repo.get_brand_analytics(bp.id)
        snap = repo.get_activity_snapshot(bp.id)

        for field in ("total_views", "total_tryons", "total_add_to_carts",
                      "total_purchases", "funnel_conversion_rate", "methodology"):
            assert dash[field] == snap[field], (
                f"{field} differs between the dashboard ({dash[field]!r}) and the "
                f"activity snapshot ({snap[field]!r}). These must come from one "
                f"definition, or /brand/analytics and /partner/analytics/conversion "
                f"will show the user contradictory numbers."
            )

    def test_zero_views_yields_none_not_zero_percent(self, db_session, tenant):
        """An undefined rate is not 0%. It stays None all the way out."""
        user, bp = tenant
        snap = BrandRepository(db_session).get_activity_snapshot(bp.id)

        assert snap["total_views"] == 0, "fixture assumption: no view rows"
        assert snap["funnel_conversion_rate"] is None, (
            "with zero views the conversion rate is undefined and must be None. "
            "Returning 0.0 asserts 'nobody converted', which is a different and "
            "unproven claim from 'there is nothing to divide by'."
        )

    def test_snapshot_is_tenant_scoped(self, db_session, tenant):
        """A brand with no products must not inherit another brand's counters."""
        user, bp = tenant
        other_user = User(email="budget-other@confit-portal-qa.example.com",
                          hashed_password="x", full_name="Other",
                          role=UserRole.BRAND_MANAGER, preferred_language="en",
                          is_active=True, is_verified=True)
        db_session.add(other_user)
        db_session.flush()
        other_bp = BrandProfile(user_id=other_user.id, brand_name="Other Budget Brand",
                                slug="other-budget-brand", is_verified=True)
        db_session.add(other_bp)
        db_session.commit()

        snap = BrandRepository(db_session).get_activity_snapshot(other_bp.id)
        assert snap["total_views"] == 0
        assert snap["total_tryons"] == 0
        assert snap["total_add_to_carts"] == 0
        assert snap["total_purchases"] == 0
        assert snap["funnel_conversion_rate"] is None
