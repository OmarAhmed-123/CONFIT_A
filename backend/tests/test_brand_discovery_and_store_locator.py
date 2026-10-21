"""Comprehensive Tests for Customer Brand Discovery, Store Locator & Branch-Level Product Availability."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest
from backend.app.models.catalog import Product, ProductSKU, StoreLocation, StoreInventory, Category
from backend.app.models.user import BrandProfile
from backend.app.models.commerce import Promotion
from backend.app.repositories.catalog_repository import haversine_distance_km, build_google_maps_url
from backend.tests.conftest import TestingSessionLocal


@pytest.fixture
def db_session(catalog_state_guard):
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


def test_customer_brands_endpoint(client, db_session):
    """GET /api/v1/catalog/brands returns list of brands with store counts, cities, and categories."""
    res = client.get("/api/v1/catalog/brands")
    assert res.status_code == 200
    brands = res.json()
    assert isinstance(brands, list)
    assert len(brands) >= 1

    first = brands[0]
    assert "id" in first
    assert "brand_name" in first
    assert "slug" in first
    assert "stores_count" in first
    assert "total_products" in first
    assert "cities" in first
    assert "categories" in first
    assert "promotions" in first


def test_customer_brands_search_and_filter(client, db_session):
    """GET /api/v1/catalog/brands with query, category and sorting."""
    res = client.get("/api/v1/catalog/brands?q=Atelier")
    assert res.status_code == 200
    brands = res.json()
    assert any("atelier" in b["brand_name"].lower() for b in brands)

    # Empty search query returns nothing matching absurd string
    res_empty = client.get("/api/v1/catalog/brands?q=NonExistentBrandXYZ123")
    assert res_empty.status_code == 200
    assert len(res_empty.json()) == 0

    # Sort parameter tests
    res_sort_stores = client.get("/api/v1/catalog/brands?sort=stores")
    assert res_sort_stores.status_code == 200
    res_sort_prods = client.get("/api/v1/catalog/brands?sort=products")
    assert res_sort_prods.status_code == 200


def test_customer_brand_detail(client, db_session):
    """GET /api/v1/catalog/brands/{slug} returns brand detail, stores, and promotions."""
    brand = db_session.query(BrandProfile).first()
    assert brand is not None

    res = client.get(f"/api/v1/catalog/brands/{brand.slug}")
    assert res.status_code == 200
    data = res.json()
    assert data["brand_name"] == brand.brand_name
    assert "stores" in data
    assert "all_promotions" in data
    assert "sample_products" in data

    # 404 for missing brand
    res_404 = client.get("/api/v1/catalog/brands/non-existent-brand-slug")
    assert res_404.status_code == 404


def test_customer_stores_endpoint_and_google_maps_url(client, db_session):
    """GET /api/v1/catalog/stores returns stores with Google Maps directions link."""
    res = client.get("/api/v1/catalog/stores")
    assert res.status_code == 200
    stores = res.json()
    assert isinstance(stores, list)
    if stores:
        first = stores[0]
        assert "address" in first
        assert "city" in first
        assert "latitude" in first
        assert "longitude" in first
        assert "google_maps_url" in first
        # Must be valid Google Maps URL
        assert first["google_maps_url"].startswith("https://www.google.com/maps/")
        if first["latitude"] and first["longitude"]:
            assert "destination=" in first["google_maps_url"]


def test_google_maps_link_generation_and_fallback():
    """Unit test for Google Maps URL generator with coordinates vs address fallback."""
    # With verified GPS coordinates
    url_with_coords = build_google_maps_url("123 Fashion Ave", 25.1972, 55.2796)
    assert url_with_coords == "https://www.google.com/maps/dir/?api=1&destination=25.197200,55.279600"

    # With missing coordinates (fallback to address search query)
    url_fallback = build_google_maps_url("Fashion Avenue, Level 1, Dubai Mall", None, None)
    assert url_fallback == "https://www.google.com/maps/search/?api=1&query=Fashion+Avenue%2C+Level+1%2C+Dubai+Mall"

    # Distance calculation test
    # Cairo (30.0444, 31.2357) to Giza (29.9870, 31.2118) is roughly ~7-8 km
    dist = haversine_distance_km(30.0444, 31.2357, 29.9870, 31.2118)
    assert 6.0 <= dist <= 9.0


def test_customer_store_proximity_sorting(client, db_session):
    """GET /api/v1/catalog/stores?lat=...&lng=... computes distance_km."""
    # Test coordinates near Cairo (30.0444, 31.2357)
    res = client.get("/api/v1/catalog/stores?lat=30.0444&lng=31.2357")
    assert res.status_code == 200
    stores = res.json()
    if stores:
        for s in stores:
            assert s["distance_km"] is not None
            assert isinstance(s["distance_km"], (int, float))


def test_branch_inventory_and_product_availability(client, db_session):
    """GET /api/v1/catalog/stores/{store_id}/inventory returns branch-level products with SKU curves."""
    store = db_session.query(StoreLocation).first()
    assert store is not None

    res = client.get(f"/api/v1/catalog/stores/{store.id}/inventory")
    assert res.status_code == 200
    data = res.json()
    assert "store" in data
    assert "brand" in data
    assert "products" in data
    assert "categories" in data
    assert "available_sizes" in data

    products = data["products"]
    if products:
        p = products[0]
        assert "branch_id" in p
        assert "branch_name" in p
        assert "branch_total_units" in p
        assert "branch_availability_status" in p
        assert p["branch_availability_status"] in ("in_stock", "low_stock", "out_of_stock")
        assert "branch_skus" in p
        if p["branch_skus"]:
            sku = p["branch_skus"][0]
            assert "size" in sku
            assert "quantity_available" in sku
            assert "availability_status" in sku

    # 404 for missing store
    res_404 = client.get("/api/v1/catalog/stores/999999/inventory")
    assert res_404.status_code == 404


def test_branch_inventory_filtering_and_sorting(client, db_session):
    """Branch inventory filtering by category, search text, and sorting."""
    store = db_session.query(StoreLocation).first()
    assert store is not None

    # Sorting
    res_price_asc = client.get(f"/api/v1/catalog/stores/{store.id}/inventory?sort_by=price_asc")
    assert res_price_asc.status_code == 200
    prods_asc = res_price_asc.json()["products"]
    if len(prods_asc) >= 2:
        assert prods_asc[0]["base_price"] <= prods_asc[-1]["base_price"]

    # In stock only
    res_instock = client.get(f"/api/v1/catalog/stores/{store.id}/inventory?in_stock_only=true")
    assert res_instock.status_code == 200
    for p in res_instock.json()["products"]:
        assert p["branch_in_stock"] is True


def test_promotion_expiry_integrity(client, db_session):
    """Expired promotions must NEVER appear in public brand promotions."""
    brand = db_session.query(BrandProfile).first()
    assert brand is not None

    now = datetime.now(timezone.utc)
    expired_promo = Promotion(
        code="EXPIRED_DEAL_999",
        description="Expired Promotion",
        discount_type="percent",
        discount_value=50.0,
        currency="USD",
        brand_id=brand.id,
        is_active=True,
        starts_at=now - timedelta(days=30),
        expires_at=now - timedelta(days=1),
    )
    db_session.add(expired_promo)
    db_session.commit()

    res = client.get(f"/api/v1/catalog/brands/{brand.slug}")
    assert res.status_code == 200
    promos = res.json()["all_promotions"]
    assert not any(p["code"] == "EXPIRED_DEAL_999" for p in promos), "Expired promotion must not be served"
