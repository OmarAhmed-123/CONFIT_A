"""A discount stored in the database must reach every product surface.

THE DEFECT THIS LOCKS DOWN
--------------------------
`products.compare_at_price` was added, serialized in `ProductSummaryOut` /
`ProductDetailOut`, and rendered by the product card and product page — and
still showed nothing, because the catalogue endpoints build their response
OBJECT FIELD BY FIELD:

    ProductSummaryOut(id=p.id, base_price=p.base_price, ...)

A column that is not named there is simply never passed, so Pydantic fills in
the schema default (None). Every layer looked correct in isolation; the value
was dropped in the wiring. Nothing raised, and the storefront advertised no
reduction while the database held one.

These tests assert the value SURVIVES the round trip on each surface, which is
the only thing a per-layer unit test cannot show.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from backend.app.models.catalog import Product


def _put_on_sale(product_id: int, multiplier: str = "1.5") -> tuple[float, float]:
    from backend.tests.conftest import TestingSessionLocal

    with TestingSessionLocal() as db:
        p = db.get(Product, product_id)
        assert p is not None
        was = (Decimal(str(p.base_price)) * Decimal(multiplier)).quantize(Decimal("0.01"))
        p.compare_at_price = was
        db.commit()
        return float(p.base_price), float(was)


def _first_product_id(client: TestClient) -> int:
    listing = client.get("/api/v1/catalog/products").json()
    assert listing, "seed catalogue must not be empty"
    return listing[0]["id"]


def test_list_endpoint_carries_the_prior_price(client: TestClient) -> None:
    pid = _first_product_id(client)
    now, was = _put_on_sale(pid)

    rows = client.get("/api/v1/catalog/products").json()
    row = next(r for r in rows if r["id"] == pid)

    assert row.get("compare_at_price") is not None, (
        "the catalogue list dropped compare_at_price — the response is built "
        "field-by-field, so a new column must be added to that constructor"
    )
    assert abs(row["compare_at_price"] - was) < 0.01
    assert row["compare_at_price"] > row["base_price"], (
        "a prior price at or below the selling price is not a discount"
    )


def test_detail_endpoint_carries_the_prior_price(client: TestClient) -> None:
    pid = _first_product_id(client)
    now, was = _put_on_sale(pid)

    detail = client.get(f"/api/v1/catalog/products/{pid}").json()
    assert detail.get("compare_at_price") is not None, (
        "the product detail endpoint dropped compare_at_price"
    )
    assert abs(detail["compare_at_price"] - was) < 0.01


def test_a_product_not_on_sale_reports_no_prior_price(client: TestClient) -> None:
    """Absence must be explicit: no invented strike-through."""
    from backend.tests.conftest import TestingSessionLocal

    pid = _first_product_id(client)
    with TestingSessionLocal() as db:
        p = db.get(Product, pid)
        p.compare_at_price = None
        db.commit()

    detail = client.get(f"/api/v1/catalog/products/{pid}").json()
    assert detail.get("compare_at_price") is None
    rows = client.get("/api/v1/catalog/products").json()
    assert next(r for r in rows if r["id"] == pid).get("compare_at_price") is None


def test_discount_percentage_is_derivable_by_any_client(client: TestClient) -> None:
    """The API ships the two numbers; the percentage is arithmetic, not a claim.

    Shipping a server-computed percentage as well would be a second source of
    truth that could disagree with the prices beside it.
    """
    pid = _first_product_id(client)
    now, was = _put_on_sale(pid, "2.0")  # exactly 50% off

    detail = client.get(f"/api/v1/catalog/products/{pid}").json()
    pct = round((detail["compare_at_price"] - detail["base_price"])
                / detail["compare_at_price"] * 100)
    assert pct == 50, f"expected 50% off, derived {pct}%"
