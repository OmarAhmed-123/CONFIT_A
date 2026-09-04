"""End-to-end item-grain attribution through the REAL checkout endpoint.

test_attribution_behavioral_e2e.py exercises BrandRepository directly. That
proves the repository, not the instrumentation in CommerceService.checkout().
These tests drive the actual HTTP checkout with a MULTI-BRAND, MULTI-ITEM cart
and then assert, against the database it wrote:

  * exactly one purchase event per OrderItem (grain),
  * each event's revenue_amount equals that item's subtotal (not the order
    total, not the brand total),
  * sum(event revenue) == sum(item subtotals)  (revenue conservation at item
    grain, exact Decimal),
  * each event's brand_id matches its own item's brand.

Section 24 of the audit brief: BrandAnalyticsEvent has no order_item_id, so the
purchase -> OrderItem link is reconstructed via (order_id, product_id, sku_id).
These tests pin the conditions under which that reconstruction is unambiguous;
if a cart ever admits two lines with the same sku, they fail loudly.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app.core.money import to_decimal, money_sum
from backend.tests.conftest import TestingSessionLocal


def _login(client, session_token):
    """Each test needs its OWN session token: carts.session_token is UNIQUE."""
    r = client.post("/api/v1/auth/login", json={
        "email": "shopper@confit.io", "password": "Password123!"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}",
            "X-Session-Token": session_token}


def _empty_cart(client, headers):
    """Remove every line from the shopper's cart (no bulk-clear endpoint)."""
    r = client.get("/api/v1/commerce/cart", headers=headers)
    if r.status_code != 200:
        return
    for it in r.json().get("items", []):
        cid = it.get("id") or it.get("cart_item_id")
        if cid:
            client.delete(f"/api/v1/commerce/cart/items/{cid}", headers=headers)


def _multi_brand_skus(db, want=3):
    """Pick in-stock SKUs belonging to DISTINCT brands."""
    rows = db.execute(text("""
        select s.id as sku_id, p.id as product_id, p.brand_id
        from product_skus s join products p on p.id = s.product_id
        where s.size is not null
        order by p.brand_id, s.id
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


class TestItemGrainAttributionThroughRealCheckout:
    def test_multi_brand_checkout_emits_one_event_per_item_and_conserves_revenue(
        self, client: TestClient
    ):
        db = TestingSessionLocal()
        try:
            skus = _multi_brand_skus(db)
            if len(skus) < 2:
                pytest.skip("seed data lacks 2 distinct in-stock brands")

            headers = _login(client, "item_grain_multi")
            _empty_cart(client, headers)

            qty = {0: 1, 1: 2, 2: 3}
            for i, s in enumerate(skus):
                r = client.post("/api/v1/commerce/cart/items", headers=headers,
                                json={"product_sku_id": s["sku_id"],
                                      "quantity": qty.get(i, 1)})
                assert r.status_code in (200, 201), r.text

            r = client.post("/api/v1/commerce/checkout", headers=headers, json={
                "payment_method": "cod",
                "fulfillment_type": "delivery",
                "shipping_method": "standard",
                "recipient_name": "Item Grain",
                "phone": "+971500000000",
                "address_line": "1 Test St",
                "city": "Dubai",
                "country": "UAE",
            })
            assert r.status_code in (200, 201), r.text
            order_number = r.json().get("order_number") or r.json()["order"]["order_number"]

            oid = db.execute(
                text("select id from orders where order_number=:n"),
                {"n": order_number}).scalar_one()

            items = db.execute(text("""
                select oi.id, oi.product_id, oi.product_sku_id, oi.subtotal, p.brand_id
                from order_items oi join products p on p.id = oi.product_id
                where oi.order_id = :o order by oi.id
            """), {"o": oid}).mappings().all()
            assert len(items) >= 2, items

            events = db.execute(text("""
                select product_id, sku_id, brand_id, revenue_amount
                from brand_analytics_events
                where order_id = :o and event_type = 'purchase'
            """), {"o": oid}).mappings().all()

            # 1. grain: one event per order item
            assert len(events) == len(items), (
                f"expected 1 purchase event per OrderItem: "
                f"{len(items)} items vs {len(events)} events")

            # the (order_id, product_id, sku_id) reconstruction must be unique
            keys = [(i["product_id"], i["product_sku_id"]) for i in items]
            assert len(set(keys)) == len(keys), (
                "two OrderItems share (product_id, sku_id); the purchase event "
                "cannot be linked back to a single item — order_item_id needed")

            by_key = {(e["product_id"], e["sku_id"]): e for e in events}
            assert set(by_key) == set(keys)

            # 2. per-item: revenue is THIS item's subtotal, and brand matches
            for it in items:
                ev = by_key[(it["product_id"], it["product_sku_id"])]
                assert to_decimal(ev["revenue_amount"]) == to_decimal(it["subtotal"]), (
                    f"item {it['id']}: event {ev['revenue_amount']} != subtotal {it['subtotal']}")
                assert ev["brand_id"] == it["brand_id"]

            # 3. conservation at item grain, exact Decimal
            item_total = money_sum([to_decimal(i["subtotal"]) for i in items])
            event_total = money_sum([to_decimal(e["revenue_amount"]) for e in events])
            assert event_total == item_total, (event_total, item_total)

            # 4. and no event inflated to the ORDER total
            order_total = to_decimal(db.execute(
                text("select total_amount from orders where id=:o"), {"o": oid}).scalar_one())
            if item_total != order_total:
                for e in events:
                    assert to_decimal(e["revenue_amount"]) != order_total, (
                        "an event carries the order total — order-grain leak")
        finally:
            db.close()

    def test_repeat_checkout_does_not_double_count_revenue(self, client: TestClient):
        """Idempotency key is per (order, product, sku, attribution)."""
        db = TestingSessionLocal()
        try:
            skus = _multi_brand_skus(db, want=2)
            if len(skus) < 2:
                pytest.skip("seed data lacks 2 distinct in-stock brands")
            headers = _login(client, "item_grain_idem")
            _empty_cart(client, headers)
            for s in skus:
                client.post("/api/v1/commerce/cart/items", headers=headers,
                            json={"product_sku_id": s["sku_id"], "quantity": 1})
            payload = {
                "payment_method": "cod", "fulfillment_type": "delivery",
                "shipping_method": "standard", "recipient_name": "Idem",
                "phone": "+971500000001", "address_line": "2 Test St",
                "city": "Dubai", "country": "UAE",
                "idempotency_key": "item-grain-idem-001",
            }
            r1 = client.post("/api/v1/commerce/checkout", headers=headers, json=payload)
            assert r1.status_code in (200, 201), r1.text
            r2 = client.post("/api/v1/commerce/checkout", headers=headers, json=payload)
            assert r2.status_code in (200, 201), r2.text

            n1 = r1.json().get("order_number") or r1.json()["order"]["order_number"]
            n2 = r2.json().get("order_number") or r2.json()["order"]["order_number"]
            assert n1 == n2, "idempotent checkout created a second order"

            oid = db.execute(text("select id from orders where order_number=:n"),
                             {"n": n1}).scalar_one()
            items = db.execute(
                text("select count(*) from order_items where order_id=:o"),
                {"o": oid}).scalar_one()
            events = db.execute(text(
                "select count(*) from brand_analytics_events "
                "where order_id=:o and event_type='purchase'"), {"o": oid}).scalar_one()
            assert events == items, (items, events)
        finally:
            db.close()
