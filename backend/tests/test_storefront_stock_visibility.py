"""Storefront must not shelve a product it cannot sell.

THE GAP (found 2026-09-30)
--------------------------
``CatalogRepository.filter_products`` has had an ``in_stock_only`` parameter
for a long time, but the only caller passing it was visual search. The
storefront catalogue, the home dashboard and keyword search all queried with
the default ``False``, so a product whose last unit had been sold stayed on
the shelf. The shopper clicked through, chose a size, and only met
``InventoryUnavailableError`` at add-to-cart — the failure surfaced three
screens later than the truth was known.

It was not visible in production seed data (every seeded product had stock),
which is exactly why it needed a test rather than a manual check.
"""
from __future__ import annotations

import pytest

from backend.app.models.catalog import Product, ProductSKU
from backend.app.repositories.catalog_repository import CatalogRepository
from backend.tests.conftest import TestingSessionLocal


@pytest.fixture
def db_session(catalog_state_guard):
    """The same session factory the app uses under test, so a mutation made
    here is visible to the HTTP layer in the same test."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


def _sold_out(db, product: Product) -> None:
    """Drive the product to the state checkout leaves behind at zero stock."""
    for sku in product.skus:
        sku.stock_level = 0
        sku.is_in_stock = False
    db.commit()


def _first_product_with_stock(db) -> Product:
    product = (
        db.query(Product)
        .join(ProductSKU)
        .filter(ProductSKU.stock_level > 0, ProductSKU.is_in_stock.is_(True))
        .first()
    )
    assert product is not None, "seed data must contain at least one buyable product"
    return product


# ── repository level ─────────────────────────────────────────────────────────

def test_repository_hides_a_sold_out_product(db_session):
    repo = CatalogRepository(db_session)
    product = _first_product_with_stock(db_session)

    assert product.id in {p.id for p in repo.filter_products(limit=100, in_stock_only=True)}
    _sold_out(db_session, product)
    assert product.id not in {p.id for p in repo.filter_products(limit=100, in_stock_only=True)}


def test_merchandising_can_still_see_sold_out_rows(db_session):
    """Hiding must be a STOREFRONT policy, not data loss — brand and admin
    catalogue views still need the row."""
    repo = CatalogRepository(db_session)
    product = _first_product_with_stock(db_session)
    _sold_out(db_session, product)

    assert product.id in {p.id for p in repo.filter_products(limit=100, in_stock_only=False)}


def test_a_flagged_out_sku_hides_the_product_even_with_stock_on_hand(db_session):
    """`is_in_stock` is a merchandising flag a brand can toggle; `stock_level`
    is decremented by checkout. Both must hold, because they are maintained by
    different code paths and trusting either alone is a bug in one direction
    or the other."""
    repo = CatalogRepository(db_session)
    product = _first_product_with_stock(db_session)
    for sku in product.skus:
        sku.is_in_stock = False          # withdrawn by the brand
        sku.stock_level = 25             # warehouse still holds units
    db_session.commit()

    assert product.id not in {p.id for p in repo.filter_products(limit=100, in_stock_only=True)}


def test_one_remaining_sku_keeps_the_product_on_the_shelf(db_session):
    """Sold out in M does not mean sold out."""
    repo = CatalogRepository(db_session)
    product = _first_product_with_stock(db_session)
    if len(product.skus) < 2:
        pytest.skip("needs a multi-SKU product")
    for sku in product.skus[1:]:
        sku.stock_level = 0
        sku.is_in_stock = False
    product.skus[0].stock_level = 1
    product.skus[0].is_in_stock = True
    db_session.commit()

    assert product.id in {p.id for p in repo.filter_products(limit=100, in_stock_only=True)}


# ── HTTP contract ────────────────────────────────────────────────────────────

def test_catalogue_endpoint_hides_sold_out_by_default(client, db_session):
    product = _first_product_with_stock(db_session)
    before = client.get("/api/v1/catalog/products?limit=100")
    assert before.status_code == 200
    assert product.id in {p["id"] for p in before.json()}

    _sold_out(db_session, product)

    after = client.get("/api/v1/catalog/products?limit=100")
    assert after.status_code == 200
    assert product.id not in {p["id"] for p in after.json()}


def test_include_sold_out_is_an_explicit_opt_in(client, db_session):
    product = _first_product_with_stock(db_session)
    _sold_out(db_session, product)

    res = client.get("/api/v1/catalog/products?limit=100&include_sold_out=true")
    assert res.status_code == 200
    assert product.id in {p["id"] for p in res.json()}


def test_search_and_the_shelf_agree_about_what_is_buyable(client, db_session):
    """Two query builders, one purchasability definition. If search kept its
    own predicate the two surfaces would drift the first time either changed."""
    product = _first_product_with_stock(db_session)
    token = product.title.split()[0]

    found = client.get(f"/api/v1/catalog/search?q={token}&limit=100")
    assert found.status_code == 200
    assert product.id in {r["id"] for r in found.json()["results"]}

    _sold_out(db_session, product)

    gone = client.get(f"/api/v1/catalog/search?q={token}&limit=100")
    assert gone.status_code == 200
    assert product.id not in {r["id"] for r in gone.json()["results"]}


def test_home_dashboard_never_recommends_an_unbuyable_product(client, db_session):
    product = _first_product_with_stock(db_session)
    _sold_out(db_session, product)

    res = client.get("/api/v1/catalog/dashboard")
    assert res.status_code == 200
    body = res.json()
    ids = {
        item.get("id")
        for key in ("todays_picks", "trending", "new_from_your_brands", "recently_viewed")
        for item in (body.get(key) or [])
        if isinstance(item, dict)
    }
    assert product.id not in ids
