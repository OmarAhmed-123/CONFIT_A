"""Stock and price changes must become visible to every other role.

THE DEFECT THIS ADDRESSES
-------------------------
The web client caches catalogue queries with `staleTime: 5 minutes`. When a
brand sold out a size or changed a price, every other role kept rendering the
OLD value for up to five minutes and had no way to know. A shopper could add a
sold-out size to their bag and only find out at checkout.

`/catalog/revision` is a cheap fingerprint the client can poll to know WHEN to
invalidate. These tests assert the fingerprint actually moves for the things
shoppers see, and stays put otherwise — a signature that always changes is as
useless as one that never does, because the client would refetch constantly.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

import pytest

from backend.app.models.catalog import Product, ProductSKU


@pytest.fixture(autouse=True)
def restore_catalog_state():
    """Snapshot and restore the seed rows these tests deliberately mutate.

    These tests must CHANGE stock and prices — that is the behaviour under
    test. Leaving those changes behind broke an unrelated account-deletion
    test in the full run while every test still passed in isolation, which is
    the most expensive kind of failure to diagnose. The mutation stays; the
    residue does not.
    """
    from backend.tests.conftest import TestingSessionLocal

    with TestingSessionLocal() as db:
        skus = [(s.id, s.stock_level, s.is_in_stock)
                for s in db.query(ProductSKU).all()]
        prods = [(p.id, p.base_price, p.compare_at_price)
                 for p in db.query(Product).all()]
    yield
    with TestingSessionLocal() as db:
        for sku_id, stock, in_stock in skus:
            row = db.get(ProductSKU, sku_id)
            if row is not None:
                row.stock_level, row.is_in_stock = stock, in_stock
        for pid, base, compare in prods:
            row = db.get(Product, pid)
            if row is not None:
                row.base_price, row.compare_at_price = base, compare
        db.commit()


def _revision(client: TestClient) -> str:
    r = client.get("/api/v1/catalog/revision")
    assert r.status_code == 200, r.text
    return r.json()["revision"]


def test_revision_is_stable_when_nothing_changes(client: TestClient) -> None:
    first = _revision(client)
    assert first == _revision(client), (
        "a fingerprint that drifts on its own would make every client refetch "
        "the catalogue forever"
    )


def test_selling_out_a_sku_changes_the_revision(client: TestClient) -> None:
    """The case that mattered: a brand drops stock to zero."""
    before = _revision(client)

    from backend.tests.conftest import TestingSessionLocal

    with TestingSessionLocal() as db:
        sku = db.query(ProductSKU).filter(ProductSKU.stock_level > 0).first()
        assert sku is not None, "seed must contain an in-stock SKU"
        sku.stock_level = 0
        sku.is_in_stock = False
        db.commit()

    assert _revision(client) != before, (
        "stock went to zero and the revision did not move — other roles would "
        "keep showing the item as available"
    )


def test_price_change_changes_the_revision(client: TestClient) -> None:
    before = _revision(client)
    from backend.tests.conftest import TestingSessionLocal

    with TestingSessionLocal() as db:
        p = db.query(Product).first()
        p.base_price = Decimal(str(p.base_price)) + Decimal("1.00")
        db.commit()
    assert _revision(client) != before


def test_starting_a_sale_changes_the_revision(client: TestClient) -> None:
    """A discount appearing must reach shoppers, not wait out the cache."""
    before = _revision(client)
    from backend.tests.conftest import TestingSessionLocal

    with TestingSessionLocal() as db:
        p = db.query(Product).first()
        p.compare_at_price = Decimal(str(p.base_price)) * 2
        db.commit()
    assert _revision(client) != before


def test_revision_reports_the_totals_behind_it(client: TestClient) -> None:
    """An operator must be able to see WHY it changed, not just that it did."""
    body = client.get("/api/v1/catalog/revision").json()
    for key in ("revision", "counts", "sellable_units", "store_units",
                "reserved_units"):
        assert key in body, f"{key} missing from the revision payload"
    assert body["counts"]["products"] >= 1
    assert isinstance(body["sellable_units"], int)


def test_revision_is_readable_without_authentication(client: TestClient) -> None:
    """Every role polls this, including signed-out shoppers."""
    assert client.get("/api/v1/catalog/revision").status_code == 200
