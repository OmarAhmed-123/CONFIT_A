"""Item-grain attribution ledger — conservation invariant through REAL endpoints.

Migration 0014 gives BrandAnalyticsEvent an ``order_item_id`` FK. These tests
drive the production code paths (HTTP checkout, HTTP return creation, HTTP
return rejection, repository ledger) and assert, after every mutation:

    Σvisual + Σoutfit + Σstylist + Σorganic == Σ eligible NET OrderItem revenue

where NET nets out returned items at ITEM grain ("Brand A returned 300 /
Brand B keeps 700"). Scenarios: plain multi-brand order, partial return,
return rejected (reverts), full order cancel, duplicate instrumentation,
guest -> authenticated stitching of visual-search lineage, and legacy rows
without a purchase event.

No test re-implements the attribution rule: every figure comes from
``BrandRepository.compute_item_grain_attribution`` / ``get_revenue_attribution``
and the conservation base is recomputed independently from ``order_items``.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app.core.money import to_decimal, money_sum
from backend.app.models.catalog_import import BrandAnalyticsEvent
from backend.app.repositories.brand_repository import BrandRepository
from backend.tests.conftest import TestingSessionLocal

CHECKOUT = {
    "payment_method": "cod",
    "fulfillment_type": "delivery",
    "shipping_method": "standard",
    "recipient_name": "Ledger Test",
    "phone": "+971500000000",
    "address_line": "1 Test St",
    "city": "Dubai",
    "country": "UAE",
}


def _login(client, email, session_token):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}", "X-Session-Token": session_token}


def _empty_cart(client, headers):
    r = client.get("/api/v1/commerce/cart", headers=headers)
    if r.status_code != 200:
        return
    for it in r.json().get("items", []):
        cid = it.get("id") or it.get("cart_item_id")
        if cid:
            client.delete(f"/api/v1/commerce/cart/items/{cid}", headers=headers)


def _multi_brand_skus(db, want=2):
    rows = db.execute(text("""
        select s.id as sku_id, p.id as product_id, p.brand_id
        from product_skus s join products p on p.id = s.product_id
        where s.stock_level > 5 order by p.brand_id, s.id
    """)).mappings().all()
    seen, out = set(), []
    for r in rows:
        if r["brand_id"] in seen:
            continue
        seen.add(r["brand_id"])
        out.append(dict(r))
        if len(out) == want:
            break
    return out


def _checkout(client, headers, skus, qty=None):
    _empty_cart(client, headers)
    for i, s in enumerate(skus):
        r = client.post("/api/v1/commerce/cart/items", headers=headers,
                        json={"product_sku_id": s["sku_id"], "quantity": (qty or {}).get(i, 1)})
        assert r.status_code in (200, 201), r.text
    r = client.post("/api/v1/commerce/checkout", headers=headers, json=CHECKOUT)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _independent_net(db) -> Decimal:
    """Conservation base recomputed from order_items ONLY (not from the ledger
    summary), netting items that have a 'return' ledger event."""
    rows = db.execute(text("""
        select oi.id, oi.subtotal,
               exists(select 1 from brand_analytics_events e
                      where e.order_item_id = oi.id and e.event_type = 'return') as returned
        from order_items oi join orders o on o.id = oi.order_id
        where o.status not in ('cancelled', 'refunded', 'failed')
    """)).mappings().all()
    return money_sum([to_decimal(r["subtotal"]) for r in rows if not r["returned"]])


def _assert_conserved(db):
    repo = BrandRepository(db)
    ledger = repo.compute_item_grain_attribution()
    parts = money_sum(ledger["channels"].values())
    assert ledger["conserved"] is True, ledger
    assert parts == ledger["net_item_revenue"], ledger
    assert ledger["net_item_revenue"] == _independent_net(db), (ledger, _independent_net(db))
    # JSON view reconciles too
    view = repo.get_revenue_attribution()
    rb = view["revenue_attribution"]
    assert money_sum(rb.values()) == to_decimal(view["attribution_base_item_subtotal"])
    assert view["conservation_holds"] is True
    return ledger


def _set_order_status(db, order_id, status):
    db.execute(text("update orders set status=:s where id=:o"), {"s": status, "o": order_id})
    db.commit()


class TestPurchaseLedgerLineage:
    def test_checkout_writes_one_purchase_event_per_item_with_order_item_id(self, client: TestClient):
        db = TestingSessionLocal()
        try:
            skus = _multi_brand_skus(db)
            if len(skus) < 2:
                pytest.skip("seed lacks 2 brands")
            headers = _login(client, "shopper@confit.io", "ledger_lineage")
            order = _checkout(client, headers, skus, qty={0: 1, 1: 2})
            items = db.execute(text("select id, subtotal, brand_id, product_id, product_sku_id from order_items "
                                    "where order_id=:o order by id"), {"o": order["id"]}).mappings().all()
            events = db.query(BrandAnalyticsEvent).filter(
                BrandAnalyticsEvent.order_id == order["id"], BrandAnalyticsEvent.event_type == "purchase").all()
            assert len(events) == len(items) >= 2
            by_item = {e.order_item_id: e for e in events}
            for it in items:
                ev = by_item[it["id"]]  # KeyError == lineage broken
                assert to_decimal(ev.revenue_amount) == to_decimal(it["subtotal"])
                assert ev.brand_id == it["brand_id"]
                assert ev.product_id == it["product_id"]
                assert ev.sku_id == it["product_sku_id"]
                assert ev.user_id is not None and ev.order_id == order["id"]
                assert ev.attribution_source in ("visual_search", "outfit_builder", "virtual_stylist", "organic")
                assert ev.event_id == f"purchase_item_{it['id']}"
                assert ev.created_at is not None
            _assert_conserved(db)
        finally:
            db.close()

    def test_purchase_event_requires_order_item_id(self):
        db = TestingSessionLocal()
        try:
            repo = BrandRepository(db)
            pid, bid = db.execute(text("select id, brand_id from products limit 1")).one()
            with pytest.raises(ValueError):
                repo.create_analytics_event(brand_id=bid, event_type="purchase", attribution_source="organic",
                                            product_id=pid, revenue_amount=Decimal("10.00"),
                                            idempotency_key="no_item_purchase")
            with pytest.raises(ValueError):
                repo.create_analytics_event(brand_id=bid, event_type="return", product_id=pid,
                                            revenue_amount=Decimal("10.00"), idempotency_key="no_item_return")
            assert db.query(BrandAnalyticsEvent).filter(
                BrandAnalyticsEvent.event_id.in_(["no_item_purchase", "no_item_return"])).count() == 0
        finally:
            db.close()

    def test_non_finite_revenue_rejected_before_persistence(self):
        db = TestingSessionLocal()
        try:
            repo = BrandRepository(db)
            pid, bid = db.execute(text("select id, brand_id from products limit 1")).one()
            item_id = db.execute(text("select id from order_items limit 1")).scalar()
            if item_id is None:
                pytest.skip("no order items")
            for bad in ("NaN", "Infinity", float("nan"), "-1", "10000000000.00"):
                with pytest.raises(ValueError):
                    repo.create_analytics_event(brand_id=bid, event_type="purchase", attribution_source="organic",
                                                product_id=pid, order_item_id=item_id, revenue_amount=bad,
                                                idempotency_key=f"bad_rev_{bad}")
            assert db.query(BrandAnalyticsEvent).filter(BrandAnalyticsEvent.event_id.like("bad_rev_%")).count() == 0
        finally:
            db.close()

    def test_duplicate_instrumentation_does_not_double_count(self, client: TestClient):
        """Re-running the ledger writer for an order is a no-op (unique per item)."""
        db = TestingSessionLocal()
        try:
            skus = _multi_brand_skus(db)
            if len(skus) < 2:
                pytest.skip("seed lacks 2 brands")
            headers = _login(client, "shopper@confit.io", "ledger_dup")
            order = _checkout(client, headers, skus)
            from backend.app.services.commerce_service import CommerceService
            from backend.app.models.commerce import Order
            svc = CommerceService(db)
            o = db.query(Order).filter(Order.id == order["id"]).one()
            before = _assert_conserved(db)
            svc._record_purchase_ledger(o, user_id=o.user_id, session_token="ledger_dup",
                                        payment_method="cod", stylist_assisted=True)  # different attribution!
            n = db.query(BrandAnalyticsEvent).filter(BrandAnalyticsEvent.order_id == o.id,
                                                     BrandAnalyticsEvent.event_type == "purchase").count()
            assert n == len(o.items)
            after = _assert_conserved(db)
            assert after["channels"] == before["channels"], "re-instrumentation changed attribution"
        finally:
            db.close()


class TestItemLevelRefundNetting:
    def test_partial_return_nets_only_returned_item(self, client: TestClient):
        """Brand A item returned -> A's revenue leaves the ledger, B keeps its 700."""
        db = TestingSessionLocal()
        try:
            skus = _multi_brand_skus(db)
            if len(skus) < 2:
                pytest.skip("seed lacks 2 brands")
            headers = _login(client, "shopper@confit.io", "ledger_partial_return")
            order = _checkout(client, headers, skus, qty={0: 1, 1: 2})
            item_a, item_b = order["items"][0], order["items"][1]
            before = _assert_conserved(db)
            _set_order_status(db, order["id"], "delivered")

            r = client.post("/api/v1/commerce/returns", headers=headers,
                            json={"order_id": order["id"], "reason": "Changed Mind", "item_ids": [item_a["id"]]})
            assert r.status_code == 201, r.text
            ret_ev = db.query(BrandAnalyticsEvent).filter(BrandAnalyticsEvent.order_item_id == item_a["id"],
                                                          BrandAnalyticsEvent.event_type == "return").one()
            assert to_decimal(ret_ev.revenue_amount) == to_decimal(item_a["subtotal"])
            assert db.query(BrandAnalyticsEvent).filter(BrandAnalyticsEvent.order_item_id == item_b["id"],
                                                        BrandAnalyticsEvent.event_type == "return").count() == 0

            after = _assert_conserved(db)
            delta = before["net_item_revenue"] - after["net_item_revenue"]
            assert delta == to_decimal(item_a["subtotal"]), (before, after)
            # per-brand: A lost exactly its item, B unchanged
            repo = BrandRepository(db)
            a_led = repo.compute_item_grain_attribution(brand_id=skus[0]["brand_id"])
            b_led = repo.compute_item_grain_attribution(brand_id=skus[1]["brand_id"])
            assert a_led["returned_item_revenue"] >= to_decimal(item_a["subtotal"])
            assert b_led["conserved"] and a_led["conserved"]
            return_id = r.json()["id"]
            self._reject_and_recover(client, db, order, item_a, return_id, after, before)
        finally:
            db.close()

    def _reject_and_recover(self, client, db, order, item_a, return_id, after, before):
        """Operator rejects the return: is_returned reverts, return event voided,
        ledger recovers to the pre-return figure."""
        admin = _login(client, "admin@confit.io", "ledger_admin")
        r = client.post(f"/api/v1/commerce/returns/{return_id}/reject", headers=admin,
                        json={"reason": "Goods never received"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "rejected"
        db.expire_all()
        flag = db.execute(text("select is_returned from order_items where id=:i"), {"i": item_a["id"]}).scalar()
        assert flag in (0, False)
        assert db.query(BrandAnalyticsEvent).filter(BrandAnalyticsEvent.order_item_id == item_a["id"],
                                                    BrandAnalyticsEvent.event_type == "return").count() == 0
        recovered = _assert_conserved(db)
        assert recovered["net_item_revenue"] == before["net_item_revenue"]
        assert recovered["channels"] == before["channels"]
        # audit row persisted for the operator action
        n = db.execute(text("select count(*) from audit_logs where action='RETURN_REJECTED' and resource_id=:r"),
                       {"r": str(return_id)}).scalar()
        assert n == 1
        # cannot reject twice
        r2 = client.post(f"/api/v1/commerce/returns/{return_id}/reject", headers=admin, json={"reason": "again"})
        assert r2.status_code in (400, 409, 422), r2.text

    def test_brand_user_cannot_reject_another_brands_return(self, client: TestClient):
        db = TestingSessionLocal()
        try:
            skus = _multi_brand_skus(db)
            if len(skus) < 2:
                pytest.skip("seed lacks 2 brands")
            headers = _login(client, "shopper@confit.io", "ledger_reject_scope")
            order = _checkout(client, headers, skus)
            _set_order_status(db, order["id"], "delivered")
            r = client.post("/api/v1/commerce/returns", headers=headers,
                            json={"order_id": order["id"], "reason": "Changed Mind",
                                  "item_ids": [order["items"][0]["id"]]})
            assert r.status_code == 201, r.text
            return_id = r.json()["id"]
            # find a brand user whose brand is NOT the returned item's brand
            other = db.execute(text("""
                select u.email from users u join brand_profiles bp on bp.user_id = u.id
                where bp.id <> :b limit 1"""), {"b": skus[0]["brand_id"]}).scalar()
            if not other:
                pytest.skip("no second brand user")
            bh = _login(client, other, "ledger_reject_scope_brand")
            r = client.post(f"/api/v1/commerce/returns/{return_id}/reject", headers=bh, json={"reason": "x"})
            assert r.status_code == 403, r.text
            # consumer cannot reject at all
            r = client.post(f"/api/v1/commerce/returns/{return_id}/reject", headers=headers, json={"reason": "x"})
            assert r.status_code == 403, r.text
        finally:
            db.close()

    def test_cancelled_order_leaves_ledger_entirely(self, client: TestClient):
        db = TestingSessionLocal()
        try:
            skus = _multi_brand_skus(db)
            if len(skus) < 2:
                pytest.skip("seed lacks 2 brands")
            headers = _login(client, "shopper@confit.io", "ledger_cancel")
            order = _checkout(client, headers, skus)
            before = _assert_conserved(db)
            item_total = money_sum([to_decimal(i["subtotal"]) for i in order["items"]])
            _set_order_status(db, order["id"], "cancelled")
            after = _assert_conserved(db)
            assert before["net_item_revenue"] - after["net_item_revenue"] == item_total
            _set_order_status(db, order["id"], "refunded")
            assert _assert_conserved(db)["net_item_revenue"] == after["net_item_revenue"]
        finally:
            db.close()


class TestVisualSearchLineageThroughOrderItem:
    def test_visual_view_then_purchase_is_attributed_via_order_item(self, client: TestClient):
        db = TestingSessionLocal()
        try:
            skus = _multi_brand_skus(db)
            if len(skus) < 2:
                pytest.skip("seed lacks 2 brands")
            headers = _login(client, "shopper@confit.io", "ledger_vs")
            uid = db.execute(text("select id from users where email='shopper@confit.io'")).scalar()
            repo = BrandRepository(db)
            # real view event as written by VisualSearchService (same product, same user)
            repo.create_analytics_event(brand_id=skus[0]["brand_id"], event_type="view",
                                        attribution_source="visual_search", product_id=skus[0]["product_id"],
                                        user_id=uid, idempotency_key=f"vs_view_test_{skus[0]['product_id']}_{uid}")
            order = _checkout(client, headers, skus)
            ev = {e.order_item_id: e for e in db.query(BrandAnalyticsEvent).filter(
                BrandAnalyticsEvent.order_id == order["id"], BrandAnalyticsEvent.event_type == "purchase")}
            a, b = order["items"][0], order["items"][1]
            assert ev[a["id"]].attribution_source == "visual_search"
            assert ev[b["id"]].attribution_source == "organic", "search A must not attribute B"
            led = _assert_conserved(db)
            assert led["channels"]["visual_search"] >= to_decimal(a["subtotal"])
            # lineage chain: VisualSearch view -> Product -> purchase event -> OrderItem -> brand revenue
            chain = db.execute(text("""
                select oi.brand_id, oi.subtotal from brand_analytics_events e
                join order_items oi on oi.id = e.order_item_id
                where e.event_type='purchase' and e.attribution_source='visual_search' and e.order_id=:o
            """), {"o": order["id"]}).all()
            assert chain and chain[0][0] == skus[0]["brand_id"]
        finally:
            db.close()

    def test_guest_visual_search_then_authenticated_purchase_is_stitched(self, client: TestClient):
        """Anonymous view (user_id NULL, session_token = browser token) + later
        authenticated checkout with the SAME X-Session-Token -> visual_search."""
        db = TestingSessionLocal()
        try:
            skus = _multi_brand_skus(db)
            if len(skus) < 2:
                pytest.skip("seed lacks 2 brands")
            token = "guest_browser_token_stitch"
            repo = BrandRepository(db)
            repo.create_analytics_event(brand_id=skus[1]["brand_id"], event_type="view",
                                        attribution_source="visual_search", product_id=skus[1]["product_id"],
                                        user_id=None, session_token=token,
                                        idempotency_key=f"vs_view_guest_{skus[1]['product_id']}")
            # fresh user: no prior visual-search history of their own
            email = f"stitch_{token}@confit.io"
            r = client.post("/api/v1/auth/register", json={
                "email": email, "password": "Password123!", "full_name": "Guest Turned Member"})
            assert r.status_code in (200, 201), r.text
            headers = _login(client, email, token)
            order = _checkout(client, headers, skus)
            ev = {e.order_item_id: e for e in db.query(BrandAnalyticsEvent).filter(
                BrandAnalyticsEvent.order_id == order["id"], BrandAnalyticsEvent.event_type == "purchase")}
            a, b = order["items"][0], order["items"][1]
            assert ev[b["id"]].attribution_source == "visual_search", "guest lineage not stitched"
            assert ev[a["id"]].attribution_source == "organic"
            assert ev[b["id"]].user_id is not None and ev[b["id"]].session_token == token
            _assert_conserved(db)
            # A DIFFERENT user in a DIFFERENT browser session does not inherit
            # the guest lineage (stitching is by browser token or user only).
            other_email = f"stitch_other_{token}@confit.io"
            r = client.post("/api/v1/auth/register", json={
                "email": other_email, "password": "Password123!", "full_name": "Other Shopper"})
            assert r.status_code in (200, 201), r.text
            headers2 = _login(client, other_email, "unrelated_browser")
            order2 = _checkout(client, headers2, [skus[1]])
            ev2 = db.query(BrandAnalyticsEvent).filter(BrandAnalyticsEvent.order_id == order2["id"],
                                                       BrandAnalyticsEvent.event_type == "purchase").one()
            assert ev2.attribution_source == "organic"
            _assert_conserved(db)
        finally:
            db.close()

    def test_visual_search_endpoint_persists_session_token_on_view_events(self, client: TestClient, monkeypatch):
        import base64
        import io
        from PIL import Image
        from backend.app.core.config import settings
        monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
        buf = io.BytesIO()
        Image.new("RGB", (64, 96), (30, 40, 120)).save(buf, format="PNG")
        data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        token = "vs_endpoint_session_token"
        r = client.post("/api/v1/tryon/visual-search", headers={"X-Session-Token": token},
                        json={"image_base64": data_url, "top_k": 3, "in_stock_only": False})
        assert r.status_code == 200, r.text
        db = TestingSessionLocal()
        try:
            n = db.query(BrandAnalyticsEvent).filter(BrandAnalyticsEvent.event_type == "view",
                                                     BrandAnalyticsEvent.attribution_source == "visual_search",
                                                     BrandAnalyticsEvent.session_token == token).count()
            assert n == min(3, r.json()["results_count"]) > 0
        finally:
            db.close()


class TestLegacyRowsAreReportedNotHidden:
    def test_item_without_purchase_event_counts_as_organic_and_is_flagged(self):
        db = TestingSessionLocal()
        try:
            repo = BrandRepository(db)
            before = repo.compute_item_grain_attribution()
            # simulate a pre-instrumentation order: delete its purchase events
            oid = db.execute(text("select order_id from brand_analytics_events where event_type='purchase' "
                                  "and order_item_id is not null limit 1")).scalar()
            if oid is None:
                pytest.skip("no instrumented orders")
            subtotal = to_decimal(db.execute(text("select sum(subtotal) from order_items where order_id=:o"),
                                             {"o": oid}).scalar())
            status = db.execute(text("select status from orders where id=:o"), {"o": oid}).scalar()
            if status in ("cancelled", "refunded", "failed"):
                pytest.skip("picked an ineligible order")
            db.execute(text("delete from brand_analytics_events where order_id=:o and event_type='purchase'"),
                       {"o": oid})
            db.commit()
            after = repo.compute_item_grain_attribution()
            assert after["conserved"] is True
            assert after["uninstrumented_items"] > before["uninstrumented_items"]
            assert after["net_item_revenue"] == before["net_item_revenue"], "legacy items are still revenue"
            assert subtotal > 0
        finally:
            db.close()

    def test_no_order_level_fallback_in_source(self):
        """Mutation guard: the ledger must join through order_item_id only."""
        import inspect
        src = inspect.getsource(BrandRepository.compute_item_grain_attribution)
        assert "order_item_id" in src
        assert "Order.total_amount" not in src
        assert "Order.stylist_assisted" not in src, "order-level flag fallback re-introduced"
        assert "OrderItem.outfit_id" not in src, "order-item flag fallback re-introduced"
