"""Order-level discount must reach the line items, and the brand report.

THE DEFECT THIS LOCKS DOWN
--------------------------
`orders.discount_amount` was stored once, order-wide, and never apportioned.
`order_items` had no discount column at all, so the brand sales report computed

    net_sales = gross_sales - returned_value

with no discount term. On every order placed with a promo code the brand was
shown MORE revenue than the order produced. Nothing raised; the statement was
simply wrong, and a brand reconciling against its payout would not be able to
find the difference.

These tests run the real checkout path against real seeded promotions, then
read the persisted rows — not the service's own return value — because the
question is what was actually written.
"""
from __future__ import annotations

import itertools
import uuid

from decimal import Decimal

from fastapi.testclient import TestClient

from backend.app.models.commerce import Order, OrderItem

# Each test registers its OWN shopper.
#
# Sharing the seeded `shopper@confit.io` made these tests both fragile and
# hostile: CONFIT10 allows 5 redemptions PER USER, so four tests here plus the
# existing group-5 promo test exhausted the allowance and failed each other.
# Checkout also syncs purchased items into the buyer's wardrobe, which shifted
# the wardrobe gap-analysis fixtures. A dedicated account per test removes both
# couplings — the tests then measure their own order and nothing else.
_UNIQUE = itertools.count(1)


def _fresh_shopper(client: TestClient, tag: str) -> dict:
    email = f"{tag}.{next(_UNIQUE)}.{uuid.uuid4().hex[:8]}@confit-test.example.com"
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": f"Test {tag.title()}",
        },
    )
    assert reg.status_code in {200, 201}, reg.text
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Password123!"}
    )
    assert login.status_code == 200, login.text
    return {
        "Authorization": f"Bearer {login.json()['access_token']}",
        "X-Session-Token": f"sess-{uuid.uuid4().hex[:10]}",
    }






def _checkout_with_promo(client: TestClient, session: str, idem: str, n_brands: int = 2):
    """Build a multi-brand cart, apply CONFIT10, and check out."""
    headers = _fresh_shopper(client, session)

    listing = client.get("/api/v1/catalog/products").json()
    chosen, seen_brands = [], set()
    for item in listing:
        if item["brand_name"] not in seen_brands:
            chosen.append(item)
            seen_brands.add(item["brand_name"])
        if len(chosen) == n_brands:
            break
    assert len(chosen) == n_brands, "seed data must span multiple brands"

    for product in chosen:
        detail = client.get(f"/api/v1/catalog/products/{product['id']}").json()
        sku = next((s for s in detail["skus"] if s["is_in_stock"]), detail["skus"][0])
        r = client.post(
            "/api/v1/commerce/cart/items",
            json={"product_sku_id": sku["id"], "quantity": 2},
            headers=headers,
        )
        assert r.status_code in {200, 201}, r.text

    promo = client.post(
        "/api/v1/commerce/cart/promo",
        json={"promo_code": "CONFIT10"},
        headers=headers,
    )
    assert promo.status_code == 200, promo.text
    assert promo.json()["discount_amount"] > 0, "fixture promo must actually discount"

    order = client.post(
        "/api/v1/commerce/checkout",
        json={
            "payment_method": "card",
            "fulfillment_type": "delivery",
            "idempotency_key": idem,
            "promo_code": "CONFIT10",
            "recipient_name": "Amira Hassan",
            "phone": "+971501234567",
            "address_line": "12 Al Wasl Road",
            "city": "Dubai",
            "country": "AE",
        },
        headers=headers,
    )
    assert order.status_code == 200, order.text
    return order.json(), headers


# ── The conservation invariant, on real persisted rows ─────────────────────

def test_line_discounts_sum_exactly_to_the_order_discount(client: TestClient) -> None:
    body, _ = _checkout_with_promo(client, "disc_sum", "disc-alloc-sum")

    from backend.tests.conftest import TestingSessionLocal

    with TestingSessionLocal() as db:
        order = db.get(Order, body["id"])
        assert order is not None
        items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
        assert len(items) >= 2, "need a multi-line order to test apportionment"

        order_discount = Decimal(str(order.discount_amount))
        assert order_discount > 0, "this test is meaningless without a discount"

        allocated = sum(
            (Decimal(str(i.discount_amount)) for i in items), Decimal("0.00")
        )
        assert allocated == order_discount, (
            f"apportioned {allocated} but the order discount is {order_discount}. "
            f"A mismatch here is money appearing or vanishing between the "
            f"customer's total and the brand statements."
        )


def test_no_line_is_discounted_below_zero(client: TestClient) -> None:
    body, _ = _checkout_with_promo(client, "disc_nonneg", "disc-alloc-nonneg")

    from backend.tests.conftest import TestingSessionLocal

    with TestingSessionLocal() as db:
        items = db.query(OrderItem).filter(OrderItem.order_id == body["id"]).all()
        for item in items:
            share = Decimal(str(item.discount_amount))
            assert share >= 0, "a line cannot receive a negative discount"
            assert share <= Decimal(str(item.subtotal)), (
                f"line {item.id} discounted by {share} but its subtotal is only "
                f"{item.subtotal} — that would imply negative revenue"
            )


def test_discount_is_apportioned_proportionally_not_evenly(client: TestClient) -> None:
    """A bigger line must bear a bigger share."""
    body, _ = _checkout_with_promo(client, "disc_prop", "disc-alloc-prop")

    from backend.tests.conftest import TestingSessionLocal

    with TestingSessionLocal() as db:
        items = db.query(OrderItem).filter(OrderItem.order_id == body["id"]).all()
        by_subtotal = sorted(items, key=lambda i: Decimal(str(i.subtotal)))
        smallest, largest = by_subtotal[0], by_subtotal[-1]
        if Decimal(str(smallest.subtotal)) == Decimal(str(largest.subtotal)):
            import pytest

            pytest.skip("seeded lines are equal-valued; proportionality is untestable")
        assert Decimal(str(largest.discount_amount)) >= Decimal(
            str(smallest.discount_amount)
        ), "the larger line must absorb at least as much of the discount"


def test_order_without_promo_allocates_zero(client: TestClient) -> None:
    """The column must be 0, never NULL, on undiscounted orders."""
    headers = _fresh_shopper(client, "disc_none")
    products = client.get("/api/v1/catalog/products").json()
    detail = client.get(f"/api/v1/catalog/products/{products[0]['id']}").json()
    sku = detail["skus"][0]
    client.post(
        "/api/v1/commerce/cart/items",
        json={"product_sku_id": sku["id"], "quantity": 1},
        headers=headers,
    )
    order = client.post(
        "/api/v1/commerce/checkout",
        json={
            "payment_method": "card",
            "fulfillment_type": "delivery",
            "idempotency_key": "disc-alloc-none",
            "recipient_name": "No Promo",
            "phone": "+971501234567",
            "address_line": "1 Test St",
            "city": "Dubai",
            "country": "AE",
        },
        headers=headers,
    )
    assert order.status_code == 200, order.text

    from backend.tests.conftest import TestingSessionLocal

    with TestingSessionLocal() as db:
        items = db.query(OrderItem).filter(
            OrderItem.order_id == order.json()["id"]
        ).all()
        assert items
        for item in items:
            assert item.discount_amount is not None, "must be 0, never NULL"
            assert Decimal(str(item.discount_amount)) == Decimal("0.00")


# ── The report that was wrong ──────────────────────────────────────────────

def test_brand_report_subtracts_the_discount_from_net_sales(client: TestClient) -> None:
    """net_sales must equal gross - discount - returns.

    This is the assertion that failed before the fix: net_sales was
    gross - returns, overstating what the brand earned on every discounted
    order.

    The report SERVICE is exercised directly against the brand that actually
    sold a line, rather than through an authenticated HTTP call, so the test
    asserts the arithmetic instead of depending on which fixture accounts a
    given seed happens to create.
    """
    body, _ = _checkout_with_promo(client, "disc_report", "disc-alloc-report")

    from backend.app.services.brand_report_service import BrandReportService
    from backend.tests.conftest import TestingSessionLocal

    with TestingSessionLocal() as db:
        items = db.query(OrderItem).filter(OrderItem.order_id == body["id"]).all()
        assert items
        # Pick the brand that bore the most discount — the one whose figures
        # would have been most overstated.
        target = max(items, key=lambda i: Decimal(str(i.discount_amount)))
        brand_id = target.brand_id
        assert Decimal(str(target.discount_amount)) > 0

        report = BrandReportService(db).build_product_sales_report(brand_id)

        assert "discount_total" in report["totals"], (
            "the report must STATE the discount it subtracted, not apply it "
            "silently — a brand has to be able to reconcile the number"
        )
        assert report["totals"]["discount_total"] > 0, (
            "this brand demonstrably bore a discount; the report reports none"
        )

        for row in report["rows"]:
            gross = Decimal(str(row["gross_sales"]))
            disc = Decimal(str(row["discount_total"]))
            net = Decimal(str(row["net_sales"]))
            assert net <= gross, (
                f"net_sales {net} exceeds gross_sales {gross} for "
                f"{row.get('title')!r} — net can never be the larger figure"
            )
            # net is gross - discount - returns; with no returns opened the
            # identity is exact and is the thing that used to be wrong.
            if row["returned_units"] == 0:
                assert net == gross - disc, (
                    f"net_sales for {row.get('title')!r} is {net}, expected "
                    f"{gross - disc} (gross {gross} - discount {disc})"
                )

        totals = report["totals"]
        assert Decimal(str(totals["net_sales"])) <= Decimal(str(totals["gross_sales"]))
