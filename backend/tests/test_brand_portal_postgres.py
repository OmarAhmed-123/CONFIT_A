"""Run with CONFIT_PORTAL_TEST_PG_URL pointing at local ephemeral PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from backend.tests.test_brand_portal_regressions import portal, row, upload, make_inventory, make_placement
from backend.app.models.catalog import StoreInventory, Product, ProductSKU
from backend.app.repositories.brand_repository import BrandRepository
from backend.app.services.brand_catalog_service import BrandCatalogService


def postgres_only(factory):
    with factory() as db:
        if db.bind.dialect.name != 'postgresql':
            pytest.skip('requires real PostgreSQL row locking; exercised by postgres CI job')


def test_concurrent_first_inventory_upsert_has_one_row(portal):
    _, factory, _, ids = portal
    postgres_only(factory)
    inv_id, payload = make_inventory(portal)
    with factory() as db:
        db.delete(db.get(StoreInventory, inv_id)); db.commit()
    barrier = Barrier(2)
    def update(quantity):
        with factory() as db:
            barrier.wait(timeout=10)
            inv = BrandRepository(db).update_store_inventory(payload['store_id'], payload['sku_id'], quantity, ids[0])
            return inv.id
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(update, [7, 8]))
    assert results[0] == results[1]
    with factory() as db:
        assert db.query(StoreInventory).count() == 1
        assert db.query(StoreInventory).one().quantity in (7,8)


def test_concurrent_import_same_brand_preserves_product_identity(portal):
    _, factory, _, ids = portal
    postgres_only(factory)
    barrier = Barrier(2)
    def load(_):
        with factory() as db:
            barrier.wait(timeout=10)
            return BrandCatalogService(db).process_json_import([row()], ids[0])
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(load, [0,1]))
    assert [r['accepted_rows'] for r in results] == [1,1]
    with factory() as db:
        assert db.query(Product).count() == db.query(ProductSKU).count() == 1


def test_click_budget_is_not_overspent_concurrently(portal):
    client, factory, h, _ = portal
    postgres_only(factory)
    pid = make_placement(portal)
    assert client.patch(f'/partner/placements/{pid}', headers=h[0], json={'daily_budget':1}).status_code == 200
    barrier = Barrier(2)
    def click(index):
        barrier.wait(timeout=10)
        return client.post(f'/partner/placements/{pid}/click', headers=h[0] | {'Idempotency-Key': f'concurrent-budget-event-{index}'}).status_code
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(click, [0,1]))
    assert sorted(results) == [200,400]
    data = client.get('/partner/placements', headers=h[0]).json()[0]
    assert data['spent_today'] == 1 and data['clicks'] == 1
