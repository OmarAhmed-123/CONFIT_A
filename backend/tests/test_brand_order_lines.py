"""Per-line sales visibility for a brand — correctness and tenant isolation.

Two things are being protected here.

1. THE ARITHMETIC IS AUDITABLE. gross, discount and net are returned as three
   separate figures and must satisfy net == gross - discount on every line and
   in the totals. A brand that cannot reconcile its own statement will not
   trust any number on the page.

2. A BRAND SEES ONLY ITS OWN LINES. Carts here are deliberately multi-brand and
   partitioned into per-brand fulfillment groups, so a missing tenant predicate
   would disclose another brand's customers and revenue. This repository has
   already had one production cross-tenant inventory leak of exactly that
   shape (see get_partner_inventory), so it is asserted rather than assumed.
"""
from __future__ import annotations

import itertools
import uuid

from decimal import Decimal

from fastapi.testclient import TestClient

from backend.app.models.commerce import OrderItem

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




def _login(client: TestClient, email: str, password: str = "Password123!") -> str | None:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"] if r.status_code == 200 else None




def _place_discounted_multi_brand_order(client: TestClient, session: str, idem: str):
    headers = _fresh_shopper(client, session)

    listing = client.get("/api/v1/catalog/products").json()
    chosen, seen = [], set()
    for item in listing:
        if item["brand_name"] not in seen:
            chosen.append(item)
            seen.add(item["brand_name"])
        if len(chosen) == 2:
            break

    for product in chosen:
        detail = client.get(f"/api/v1/catalog/products/{product['id']}").json()
        sku = next((s for s in detail["skus"] if s["is_in_stock"]), detail["skus"][0])
        client.post(
            "/api/v1/commerce/cart/items",
            json={"product_sku_id": sku["id"], "quantity": 2},
            headers=headers,
        )

    client.post(
        "/api/v1/commerce/cart/promo",
        json={"promo_code": "CONFIT10"},
        headers=headers,
    )
    order = client.post(
        "/api/v1/commerce/checkout",
        json={
            "payment_method": "card",
            "fulfillment_type": "delivery",
            "idempotency_key": idem,
            "promo_code": "CONFIT10",
            "recipient_name": "Nadia Farouk",
            "phone": "+971501234567",
            "address_line": "8 Jumeirah Beach Road",
            "city": "Dubai",
            "country": "AE",
        },
        headers=headers,
    )
    assert order.status_code == 200, order.text
    return order.json()


def _brand_headers(client: TestClient, email: str) -> dict | None:
    token = _login(client, email)
    return {"Authorization": f"Bearer {token}"} if token else None


def test_order_lines_arithmetic_is_internally_consistent(client: TestClient) -> None:
    _place_discounted_multi_brand_order(client, "bol_math", "bol-math-1")

    headers = _brand_headers(client, "brand@massimodutti.com")
    if not headers:
        import pytest

        pytest.skip("brand fixture account not present in this seed")

    r = client.get("/api/v1/partner/orders", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["lines"], "brand should have at least one sold line"

    for line in body["lines"]:
        gross = Decimal(line["gross_amount"])
        disc = Decimal(line["discount_amount"])
        net = Decimal(line["net_amount"])
        assert net == gross - disc, (
            f"line {line['line_id']}: net {net} != gross {gross} - discount {disc}"
        )
        assert disc >= 0
        assert net >= 0, "a line can never net a negative amount"

    totals = body["totals"]
    assert Decimal(totals["net_amount"]) == Decimal(
        totals["gross_amount"]
    ) - Decimal(totals["discount_amount"])


def test_totals_cover_the_whole_filtered_set_not_just_the_page(
    client: TestClient,
) -> None:
    """A headline total that only sums the visible page is a lie."""
    _place_discounted_multi_brand_order(client, "bol_page", "bol-page-1")

    headers = _brand_headers(client, "brand@massimodutti.com")
    if not headers:
        import pytest

        pytest.skip("brand fixture account not present in this seed")

    full = client.get("/api/v1/partner/orders?limit=200", headers=headers).json()
    if full["pagination"]["total_lines"] < 2:
        import pytest

        pytest.skip("need at least two lines to test pagination independence")

    paged = client.get("/api/v1/partner/orders?limit=1", headers=headers).json()
    assert len(paged["lines"]) == 1
    assert paged["pagination"]["total_lines"] == full["pagination"]["total_lines"]
    # The totals must be identical regardless of page size.
    assert paged["totals"]["net_amount"] == full["totals"]["net_amount"]
    assert paged["totals"]["gross_amount"] == full["totals"]["gross_amount"]


def test_a_brand_never_sees_another_brands_lines(client: TestClient) -> None:
    """Tenant isolation, asserted against the database rather than inferred."""
    body = _place_discounted_multi_brand_order(client, "bol_tenant", "bol-tenant-1")

    headers = _brand_headers(client, "brand@massimodutti.com")
    if not headers:
        import pytest

        pytest.skip("brand fixture account not present in this seed")

    from backend.tests.conftest import TestingSessionLocal
    from backend.app.models.user import BrandProfile, User

    with TestingSessionLocal() as db:
        owner = db.query(User).filter(User.email == "brand@massimodutti.com").first()
        profile = (
            db.query(BrandProfile).filter(BrandProfile.user_id == owner.id).first()
        )
        my_brand_id = profile.id
        order_brand_ids = {
            i.brand_id
            for i in db.query(OrderItem).filter(
                OrderItem.order_id == body["id"]
            ).all()
        }

    if len(order_brand_ids) < 2:
        import pytest

        pytest.skip("seed produced a single-brand order; nothing to isolate")

    r = client.get("/api/v1/partner/orders?limit=200", headers=headers)
    assert r.status_code == 200

    returned_line_ids = {ln["line_id"] for ln in r.json()["lines"]}
    with TestingSessionLocal() as db:
        for line_id in returned_line_ids:
            item = db.get(OrderItem, line_id)
            assert item.brand_id == my_brand_id, (
                f"line {line_id} belongs to brand {item.brand_id} but was "
                f"returned to brand {my_brand_id} — cross-tenant disclosure"
            )


def test_line_states_what_left_inventory(client: TestClient) -> None:
    """Size, colour, quantity and remaining stock are the operational payload."""
    _place_discounted_multi_brand_order(client, "bol_inv", "bol-inv-1")

    headers = _brand_headers(client, "brand@massimodutti.com")
    if not headers:
        import pytest

        pytest.skip("brand fixture account not present in this seed")

    body = client.get("/api/v1/partner/orders", headers=headers).json()
    assert body["lines"]
    line = body["lines"][0]

    for field in ("size", "color", "quantity", "product_title", "customer_name"):
        assert line.get(field) not in (None, ""), f"{field} must be stated"

    assert line["quantity"] >= 1
    # Stock may legitimately be unknown (SKU deleted), but must be explicit
    # about it rather than defaulting to 0, which would read as "sold out".
    assert "sku_stock_remaining" in line


def test_endpoint_requires_a_brand_role(client: TestClient) -> None:
    anon = client.get("/api/v1/partner/orders")
    assert anon.status_code in {401, 403}

    shopper = _login(client, "shopper@confit.io")
    assert shopper
    as_shopper = client.get(
        "/api/v1/partner/orders",
        headers={"Authorization": f"Bearer {shopper}"},
    )
    assert as_shopper.status_code in {401, 403}, (
        "a shopper must not be able to read brand sales data"
    )
