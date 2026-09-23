"""Session-linked funnel semantics for the brand portal.

WHY THIS EXISTS
The audit found the portal rendering "3500%" as a conversion rate. That number
came from dividing 35 try-on rows by 0 retained product-view rows -- two counts
from two unrelated tables, with no session linking them. A ratio of independent
aggregates is not a funnel, and no amount of denominator patching makes it one.

get_attributed_funnel() counts SESSIONS instead of rows. Every stage is a subset
of the stage before it, so the sequence is monotonically non-increasing BY
CONSTRUCTION and a rate cannot exceed 100%. These tests pin that structural
property, the tenant scoping, and the coverage honesty -- because a funnel built
on a fifth of the traffic must not look as authoritative as a complete one.

They are written against observable output, never against source text.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import Base
from backend.app.models.catalog import Category, Product, ProductSKU
from backend.app.models.catalog_import import BrandAnalyticsEvent
from backend.app.models.commerce import Cart
from backend.app.models.tryon import TryOnSession
from backend.app.models.user import BrandProfile, User, UserRole
from backend.app.repositories.brand_repository import BrandRepository


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _brand(db, name, slug):
    user = User(email=f"{slug}@confit-portal-qa.example.com", hashed_password="x",
                full_name=name, role=UserRole.BRAND_MANAGER, preferred_language="en",
                is_active=True, is_verified=True)
    db.add(user)
    db.flush()
    bp = BrandProfile(user_id=user.id, brand_name=name, slug=slug)
    db.add(bp)
    db.flush()
    return bp


def _product(db, bp, title):
    cat = db.query(Category).first()
    if not cat:
        cat = Category(name="C", name_ar="ج", slug="c")
        db.add(cat)
        db.flush()
    p = Product(brand_id=bp.id, category_id=cat.id, title=title, title_ar=title,
                slug=f"{bp.id}-{title}".lower().replace(" ", "-"),
                description="d", description_ar="d", base_price=100, currency="AED",
                color_family="Navy", thumbnail_url="https://example.com/a.jpg",
                is_active=True)
    db.add(p)
    db.flush()
    return p


def _view(db, bp, product, token, n=1):
    for i in range(n):
        db.add(BrandAnalyticsEvent(
            event_id=f"v-{bp.id}-{product.id}-{token}-{i}", brand_id=bp.id,
            product_id=product.id, session_token=token, event_type="view",
            created_at=datetime.now(timezone.utc)))
    db.flush()


def _tryon(db, product, token):
    db.add(TryOnSession(product_id=product.id, guest_session_token=token,
                        status="completed", created_at=datetime.now(timezone.utc)))
    db.flush()


def _cart(db, token):
    db.add(Cart(session_token=token, status="active"))
    db.flush()


def _purchase(db, bp, product, token, order_item_id):
    db.add(BrandAnalyticsEvent(
        event_id=f"p-{bp.id}-{token}", brand_id=bp.id, product_id=product.id,
        session_token=token, event_type="purchase", order_item_id=order_item_id,
        created_at=datetime.now(timezone.utc)))
    db.flush()


class TestFunnelIsStructurallySound:
    """The 3500% class of bug must be impossible, not merely absent today."""

    def test_stages_never_increase_down_the_funnel(self, db):
        bp = _brand(db, "Mono Brand", "mono")
        prod = _product(db, bp, "Coat")
        # Deliberately hostile shape: far MORE try-on rows than view sessions,
        # which is exactly what produced 3500% under the old aggregate ratio.
        for i in range(3):
            _view(db, bp, prod, f"s{i}")
        for i in range(40):
            _tryon(db, prod, f"unrelated-{i}")
        db.commit()

        f = BrandRepository(db).get_attributed_funnel(bp.id)
        counts = [s["sessions"] for s in f["stages"]]
        assert counts == sorted(counts, reverse=True), (
            f"funnel stages increased down the funnel: {counts}. Each stage must be "
            f"a subset of the previous one."
        )

    def test_no_rate_can_exceed_one_hundred_percent(self, db):
        bp = _brand(db, "Rate Brand", "rate")
        prod = _product(db, bp, "Shoe")
        _view(db, bp, prod, "only-session")
        for i in range(25):
            _tryon(db, prod, f"ghost-{i}")
        db.commit()

        f = BrandRepository(db).get_attributed_funnel(bp.id)
        for key in ("try_on_rate", "add_to_cart_rate", "purchase_rate"):
            if f[key] is not None:
                assert f[key] <= 100.0, (
                    f"{key} came out at {f[key]}% -- the exact class of bug "
                    f"(3500%) this funnel exists to make impossible."
                )

    def test_a_real_session_journey_is_counted_at_every_stage(self, db):
        """Not vacuous: the funnel must actually FIND a complete journey."""
        bp = _brand(db, "Journey Brand", "journey")
        prod = _product(db, bp, "Jacket")
        _view(db, bp, prod, "sess-complete")
        _tryon(db, prod, "sess-complete")
        _cart(db, "sess-complete")
        _purchase(db, bp, prod, "sess-complete", order_item_id=None)
        db.commit()

        f = BrandRepository(db).get_attributed_funnel(bp.id)
        assert f["view_sessions"] == 1
        assert f["tryon_sessions"] == 1, "try-on stage did not join the session"
        assert f["cart_sessions"] == 1, "cart stage did not join the session"
        assert f["purchase_sessions"] == 1, "purchase stage did not join the session"
        assert f["purchase_rate"] == 100.0


class TestZeroDenominatorIsNeverZeroPercent:
    def test_brand_with_no_attributable_views_reports_na_not_zero(self, db):
        bp = _brand(db, "Empty Brand", "empty")
        db.commit()
        f = BrandRepository(db).get_attributed_funnel(bp.id)

        assert f["available"] is False
        assert f["view_sessions"] == 0
        for key in ("try_on_rate", "add_to_cart_rate", "purchase_rate"):
            assert f[key] is None, (
                f"{key} is {f[key]!r} with a zero denominator. Undefined must be None "
                f"(rendered N/A); 0% asserts 'nobody converted', which is a different "
                f"and unproven claim from 'there is nothing to divide by'."
            )

    def test_views_without_session_tokens_are_not_attributable(self, db):
        """Anonymous activity must not silently inflate the denominator."""
        bp = _brand(db, "Anon Brand", "anon")
        prod = _product(db, bp, "Hat")
        db.add(BrandAnalyticsEvent(event_id="anon-1", brand_id=bp.id,
                                   product_id=prod.id, session_token=None,
                                   event_type="view",
                                   created_at=datetime.now(timezone.utc)))
        db.commit()

        f = BrandRepository(db).get_attributed_funnel(bp.id)
        assert f["view_sessions"] == 0, "a session-less view entered the funnel"
        assert f["view_events_total"] == 1
        assert f["attributable_view_coverage"] == 0.0, (
            "coverage must reveal that none of the traffic was attributable"
        )


class TestCoverageIsReportedHonestly:
    def test_partial_coverage_is_surfaced(self, db):
        """A funnel built on a fraction of traffic must say so."""
        bp = _brand(db, "Partial Brand", "partial")
        prod = _product(db, bp, "Scarf")
        _view(db, bp, prod, "tracked")
        for i in range(3):
            db.add(BrandAnalyticsEvent(event_id=f"untracked-{i}", brand_id=bp.id,
                                       product_id=prod.id, session_token=None,
                                       event_type="view",
                                       created_at=datetime.now(timezone.utc)))
        db.commit()

        f = BrandRepository(db).get_attributed_funnel(bp.id)
        assert f["view_events_total"] == 4
        assert f["view_events_attributable"] == 1
        assert f["attributable_view_coverage"] == 25.0, (
            "coverage must be reported so a 25%-coverage funnel is not mistaken "
            "for a complete one"
        )


class TestTenantIsolation:
    def test_another_brands_tryon_is_not_credited_to_this_brand(self, db):
        """tryon_sessions has no brand column; scoping goes through the product."""
        a = _brand(db, "Tenant A", "tenant-a")
        b = _brand(db, "Tenant B", "tenant-b")
        pa = _product(db, a, "A Coat")
        pb = _product(db, b, "B Coat")

        # One shared session token that viewed A's product but tried on B's.
        _view(db, a, pa, "shared-token")
        _tryon(db, pb, "shared-token")
        db.commit()

        f = BrandRepository(db).get_attributed_funnel(a.id)
        assert f["view_sessions"] == 1
        assert f["tryon_sessions"] == 0, (
            "a try-on of ANOTHER tenant's product was credited to this brand. "
            "The try-on join must be scoped through products.brand_id."
        )

    def test_another_brands_views_do_not_enter_the_denominator(self, db):
        a = _brand(db, "Tenant C", "tenant-c")
        b = _brand(db, "Tenant D", "tenant-d")
        pb = _product(db, b, "D Coat")
        _view(db, b, pb, "d-session")
        db.commit()

        f = BrandRepository(db).get_attributed_funnel(a.id)
        assert f["view_sessions"] == 0, "another tenant's view sessions leaked in"
        assert f["available"] is False


class TestSnapshotAndFunnelStaySeparate:
    def test_funnel_declares_session_grain(self, db):
        """The two must never be conflated: one is rows, one is sessions."""
        bp = _brand(db, "Grain Brand", "grain")
        prod = _product(db, bp, "Belt")
        _view(db, bp, prod, "g1")
        db.commit()

        repo = BrandRepository(db)
        funnel = repo.get_attributed_funnel(bp.id)
        snapshot = repo.get_activity_snapshot(bp.id)

        assert funnel["grain"] == "session"
        assert "not a causal claim" in funnel["methodology"].lower()
        # The snapshot must keep disclaiming that it is not a funnel.
        assert "not a session-linked conversion funnel" in snapshot["methodology"].lower()
