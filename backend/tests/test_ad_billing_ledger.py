"""P1 regression: sponsored placements must be a real billing system.

The audit's finding was that placements "prove saving settings and counters,
not ad delivery or real billing". These tests pin the four properties that
separate a counter from a ledger:

  1. DAILY WINDOW   — spent_today actually resets on a new UTC day, so a daily
                      budget is not silently a lifetime budget.
  2. IDEMPOTENCY    — a replayed click (at-least-once HTTP delivery) is charged
                      exactly once.
  3. RECONCILIATION — the cached counter always equals the append-only ledger.
  4. FRAUD CONTROL  — repeated clicks from one actor are recorded but not billed,
                      and the budget is a hard ceiling under concurrency.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import Base
from backend.app.models.brand_analytics import AdLedgerEntry, SponsoredPlacement
from backend.app.models.catalog import Category, Product, ProductSKU
from backend.app.models.user import BrandProfile, User, UserRole
from backend.app.services.ad_billing_service import AdBillingError, AdBillingService, utc_today


@pytest.fixture
def billing():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        u = User(email=f"b-{uuid.uuid4().hex}@t", full_name="B", hashed_password="x",
                 role=UserRole.BRAND_MANAGER)
        db.add(u)
        db.flush()
        bp = BrandProfile(user_id=u.id, brand_name="Ledger Co", slug=f"ledger-{uuid.uuid4().hex[:6]}")
        cat = Category(name="C", name_ar="س", slug=f"c-{uuid.uuid4().hex[:6]}")
        db.add_all([bp, cat])
        db.flush()
        p = Product(brand_id=bp.id, category_id=cat.id, title="Coat", title_ar="م",
                    slug=f"coat-{uuid.uuid4().hex[:6]}", description="d", description_ar="د",
                    base_price=100, color_family="Navy", thumbnail_url="http://x/i.jpg")
        db.add(p)
        db.flush()
        plc = SponsoredPlacement(
            brand_id=bp.id, product_id=p.id, placement_type="stylist_featured",
            bid_amount_per_click=Decimal("2.00"), daily_budget=Decimal("10.00"),
            spent_today=Decimal("0.00"), status="active", spend_date=utc_today(),
        )
        db.add(plc)
        db.commit()
        ctx = {"brand_id": bp.id, "placement_id": plc.id, "user_id": u.id}
    yield factory, ctx


def test_click_is_charged_once_and_written_to_ledger(billing):
    factory, ctx = billing
    with factory() as db:
        svc = AdBillingService(db)
        out = svc.record_event(ctx["placement_id"], ctx["brand_id"], "click",
                               event_key="evt-1", actor_user_id=ctx["user_id"])
        assert out["status"] == "recorded"
        assert out["charged"] == "2.00"
        assert out["spent_today"] == "2.00"
        assert out["remaining_budget"] == "8.00"

        entries = db.query(AdLedgerEntry).all()
        assert len(entries) == 1
        assert entries[0].entry_type == "click"
        assert Decimal(str(entries[0].amount)) == Decimal("2.00")
        # The rate is snapshotted, so re-pricing later cannot rewrite history.
        assert Decimal(str(entries[0].bid_at_event)) == Decimal("2.00")
        # Raw IP must never be persisted.
        assert entries[0].ip_hash is None or len(entries[0].ip_hash) == 64


def test_replayed_event_key_is_not_charged_twice(billing):
    """At-least-once delivery must produce exactly-once billing."""
    factory, ctx = billing
    with factory() as db:
        svc = AdBillingService(db)
        first = svc.record_event(ctx["placement_id"], ctx["brand_id"], "click",
                                 event_key="retry-me", actor_user_id=ctx["user_id"])
        second = svc.record_event(ctx["placement_id"], ctx["brand_id"], "click",
                                  event_key="retry-me", actor_user_id=ctx["user_id"])

        assert first["status"] == "recorded"
        assert second["status"] == "duplicate"
        assert second["charged"] == "0.00"

        plc = db.query(SponsoredPlacement).get(ctx["placement_id"])
        assert Decimal(str(plc.spent_today)) == Decimal("2.00"), "Charged twice for one event"
        assert db.query(AdLedgerEntry).count() == 1


def test_repeat_click_from_same_actor_is_recorded_but_not_billed(billing):
    """Click-fraud control: the event is kept for forensics, not charged."""
    factory, ctx = billing
    with factory() as db:
        svc = AdBillingService(db)
        svc.record_event(ctx["placement_id"], ctx["brand_id"], "click",
                         event_key="k1", actor_user_id=ctx["user_id"], ip="10.0.0.1")
        second = svc.record_event(ctx["placement_id"], ctx["brand_id"], "click",
                                  event_key="k2", actor_user_id=ctx["user_id"], ip="10.0.0.1")

        assert second["status"] == "recorded_not_billable"
        assert second["charged"] == "0.00"
        assert "deduplicated" in second["reason"]

        plc = db.query(SponsoredPlacement).get(ctx["placement_id"])
        assert Decimal(str(plc.spent_today)) == Decimal("2.00")
        assert plc.clicks == 1, "A deduplicated click must not inflate the click counter"
        # ...but the evidence is retained.
        assert db.query(AdLedgerEntry).count() == 2
        assert db.query(AdLedgerEntry).filter(AdLedgerEntry.billable.is_(False)).count() == 1


def test_daily_budget_is_a_hard_ceiling(billing):
    """Budget 10.00 at 2.00/click => at most 5 billable clicks, then refusal."""
    factory, ctx = billing
    with factory() as db:
        svc = AdBillingService(db)
        for i in range(5):
            # Distinct actors so the fraud dedup window does not interfere.
            svc.record_event(ctx["placement_id"], ctx["brand_id"], "click",
                             event_key=f"c{i}", actor_user_id=1000 + i)

        plc = db.query(SponsoredPlacement).get(ctx["placement_id"])
        assert Decimal(str(plc.spent_today)) == Decimal("10.00")
        assert plc.status == "budget_exhausted"

        with pytest.raises(AdBillingError) as exc:
            svc.record_event(ctx["placement_id"], ctx["brand_id"], "click",
                             event_key="overspend", actor_user_id=9999)
        assert exc.value.code in ("BUDGET_EXHAUSTED", "PLACEMENT_CLOSED")

        # Never overspent.
        plc = db.query(SponsoredPlacement).get(ctx["placement_id"])
        assert Decimal(str(plc.spent_today)) <= Decimal(str(plc.daily_budget))


def test_new_day_resets_spend_and_reactivates_exhausted_placement(billing):
    """THE daily-window bug: without spend_date, a daily budget was a lifetime
    budget and an exhausted placement never served again."""
    factory, ctx = billing
    with factory() as db:
        svc = AdBillingService(db)
        for i in range(5):
            svc.record_event(ctx["placement_id"], ctx["brand_id"], "click",
                             event_key=f"d{i}", actor_user_id=2000 + i)

        plc = db.query(SponsoredPlacement).get(ctx["placement_id"])
        assert plc.status == "budget_exhausted"

        # Simulate the rollover honestly: yesterday's spend belongs to
        # YESTERDAY in the ledger too, not just on the counter. (Backdating
        # only the counter is rejected by design — the ledger is the authority,
        # so you cannot fake a reset by editing the cached column. That is
        # exactly the property we want.)
        yesterday = utc_today() - timedelta(days=1)
        plc.spend_date = yesterday
        db.query(AdLedgerEntry).filter(
            AdLedgerEntry.placement_id == ctx["placement_id"]
        ).update({AdLedgerEntry.spend_date: yesterday}, synchronize_session=False)
        db.commit()

        out = svc.record_event(ctx["placement_id"], ctx["brand_id"], "click",
                               event_key="today-1", actor_user_id=3001)
        assert out["status"] == "recorded", "New day must restore serving"
        assert out["spent_today"] == "2.00", "Spend must restart at the new day"

        plc = db.query(SponsoredPlacement).get(ctx["placement_id"])
        assert plc.status == "active"
        assert plc.spend_date == utc_today()


def test_human_paused_placement_is_not_reactivated_by_rollover(billing):
    """Operator intent outranks the scheduler."""
    factory, ctx = billing
    with factory() as db:
        svc = AdBillingService(db)
        plc = db.query(SponsoredPlacement).get(ctx["placement_id"])
        plc.status = "paused"
        plc.spend_date = utc_today() - timedelta(days=1)
        db.commit()

        with pytest.raises(AdBillingError) as exc:
            svc.record_event(ctx["placement_id"], ctx["brand_id"], "click",
                             event_key="p1", actor_user_id=4001)
        assert exc.value.code == "PLACEMENT_PAUSED"


def test_counter_always_reconciles_with_the_ledger(billing):
    """The control that makes the spend figure defensible."""
    factory, ctx = billing
    with factory() as db:
        svc = AdBillingService(db)
        for i in range(3):
            svc.record_event(ctx["placement_id"], ctx["brand_id"], "click",
                             event_key=f"r{i}", actor_user_id=5000 + i)
        svc.record_event(ctx["placement_id"], ctx["brand_id"], "impression",
                         event_key="imp-1", actor_user_id=5100)

        rec = svc.reconcile(ctx["placement_id"])
        assert rec["comparable"] is True
        assert rec["balanced"] is True, f"Ledger and counter diverged: {rec}"
        assert rec["ledger_total"] == "6.00"
        assert rec["counter_spent_today"] == "6.00"
        assert rec["difference"] == "0.00"
        assert rec["billable_clicks"] == 3


def test_impressions_are_recorded_but_free_under_cpc(billing):
    factory, ctx = billing
    with factory() as db:
        svc = AdBillingService(db)
        out = svc.record_event(ctx["placement_id"], ctx["brand_id"], "impression",
                               event_key="i1", actor_user_id=6001)
        assert out["charged"] == "0.00"
        assert out["spent_today"] == "0.00"
        plc = db.query(SponsoredPlacement).get(ctx["placement_id"])
        assert plc.impressions == 1


def test_tenant_cannot_bill_another_brands_placement(billing):
    factory, ctx = billing
    with factory() as db:
        svc = AdBillingService(db)
        with pytest.raises(AdBillingError) as exc:
            svc.record_event(ctx["placement_id"], brand_id=ctx["brand_id"] + 999,
                             entry_type="click", event_key="x1", actor_user_id=7001)
        assert exc.value.code == "PLACEMENT_NOT_FOUND"


def test_statement_is_derived_from_the_ledger_only(billing):
    """An invoice must come from the journal, never from mutable counters."""
    factory, ctx = billing
    with factory() as db:
        svc = AdBillingService(db)
        for i in range(2):
            svc.record_event(ctx["placement_id"], ctx["brand_id"], "click",
                             event_key=f"s{i}", actor_user_id=8000 + i)

        today = utc_today()
        stmt = svc.brand_statement(ctx["brand_id"], today, today)
        assert stmt["total_charged"] == "4.00"
        assert len(stmt["days"]) == 1
        assert stmt["days"][0]["clicks"] == 2

        # Drift the cached counter (staying inside the
        # ck_sponsored_spent_lte_budget CHECK, which the DB rightly enforces —
        # an out-of-range value is refused by the schema, a second line of
        # defence we are not trying to defeat here).
        plc = db.query(SponsoredPlacement).get(ctx["placement_id"])
        plc.spent_today = Decimal("9.00")
        db.commit()

        stmt2 = svc.brand_statement(ctx["brand_id"], today, today)
        assert stmt2["total_charged"] == "4.00", "Statement must not trust the counter"

        # ...and reconciliation must REPORT the drift rather than hide it.
        rec = svc.reconcile(ctx["placement_id"])
        assert rec["balanced"] is False
        assert rec["ledger_total"] == "4.00"
        assert rec["difference"] == "5.00"


def test_billed_placement_is_cancelled_not_erased(billing):
    """Financial records must survive a delete.

    A hard DELETE cascades to ad_ledger_entries and destroys the evidence for
    money that was actually charged; worse, a later placement reusing the id
    would inherit the orphaned rows. A journal you can delete is not a journal.
    """
    from fastapi.testclient import TestClient
    from backend.app.core.database import get_db
    from backend.app.core.security import create_access_token
    from backend.app.main import app

    factory, ctx = billing
    with factory() as db:
        AdBillingService(db).record_event(ctx["placement_id"], ctx["brand_id"], "click",
                                          event_key="keep-me", actor_user_id=ctx["user_id"])

    previous = app.dependency_overrides.get(get_db)

    def _session():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = _session
    try:
        client = TestClient(app)
        token = create_access_token({"sub": str(ctx["user_id"])})
        resp = client.delete(f"/api/v1/partner/placements/{ctx['placement_id']}",
                             headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "cancelled", "A billed placement must not be hard-deleted"
        assert body["ledger_entries_retained"] == 1
    finally:
        if previous:
            app.dependency_overrides[get_db] = previous
        else:
            app.dependency_overrides.pop(get_db, None)

    with factory() as db:
        plc = db.query(SponsoredPlacement).get(ctx["placement_id"])
        assert plc is not None, "Placement row must be retained"
        assert plc.status == "cancelled", "Cancelled placements must stop serving"
        assert db.query(AdLedgerEntry).count() == 1, "Billing history must survive"

    # ...and a cancelled placement must refuse to bill further.
    with factory() as db:
        with pytest.raises(AdBillingError) as exc:
            AdBillingService(db).record_event(ctx["placement_id"], ctx["brand_id"], "click",
                                              event_key="after-cancel", actor_user_id=123456)
        assert exc.value.code == "PLACEMENT_CLOSED"


def test_unbilled_placement_can_still_be_deleted(billing):
    """The retention rule must not block housekeeping: a placement with no
    financial history has nothing to protect."""
    from fastapi.testclient import TestClient
    from backend.app.core.database import get_db
    from backend.app.core.security import create_access_token
    from backend.app.main import app

    factory, ctx = billing
    previous = app.dependency_overrides.get(get_db)

    def _session():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = _session
    try:
        client = TestClient(app)
        token = create_access_token({"sub": str(ctx["user_id"])})
        resp = client.delete(f"/api/v1/partner/placements/{ctx['placement_id']}",
                             headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "deleted"
    finally:
        if previous:
            app.dependency_overrides[get_db] = previous
        else:
            app.dependency_overrides.pop(get_db, None)

    with factory() as db:
        assert db.query(SponsoredPlacement).get(ctx["placement_id"]) is None
