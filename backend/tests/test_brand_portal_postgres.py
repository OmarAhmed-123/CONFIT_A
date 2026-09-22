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
    """Concurrent clicks must never overspend the daily budget, and the
    append-only ledger must reconcile with the cached counter afterwards.

    CONTRACT UPDATE (ad ledger, migration 0019): billable events now go through
    AdBillingService, which additionally de-duplicates repeated clicks from the
    SAME actor inside a short window. The previous version of this test raced
    two clicks from one authenticated user, so under the new fraud rule the
    second is legitimately "recorded, not billed" (HTTP 200) rather than
    "budget exceeded" (HTTP 400) — the budget is still never overspent, which
    is what this test exists to prove.

    Racing distinct actors keeps the test aimed at the lost-update/double-spend
    race it was written for, instead of accidentally testing the dedup window.
    """
    client, factory, h, ids = portal
    postgres_only(factory)
    pid = make_placement(portal)
    assert client.patch(f'/partner/placements/{pid}', headers=h[0],
                        json={'daily_budget': 1}).status_code == 200

    from backend.app.services.ad_billing_service import AdBillingService, AdBillingError

    # make_placement uses bid_amount_per_click = 1.00, and the PATCH above sets
    # daily_budget = 1.00 => EXACTLY ONE click may bill; the rest must be refused.
    workers = 8
    barrier = Barrier(workers)

    def click(i):
        barrier.wait(timeout=20)
        with factory() as db:
            try:
                return AdBillingService(db).record_event(
                    pid, ids[0], 'click',
                    event_key=f'conc-{pid}-{i}', actor_user_id=90000 + i)['status']
            except AdBillingError as exc:
                return exc.code

    with ThreadPoolExecutor(workers) as pool:
        results = list(pool.map(click, range(workers)))

    billed = [r for r in results if r == 'recorded']
    assert len(billed) == 1, f"budget allows exactly 1 click, billed {len(billed)}: {results}"
    assert all(r in ('recorded', 'BUDGET_EXHAUSTED') for r in results), results

    data = client.get('/partner/placements', headers=h[0]).json()[0]
    assert float(data['spent_today']) == 1.0
    assert float(data['spent_today']) <= float(data['daily_budget']), "overspent the daily budget"
    assert data['clicks'] == 1

    # The counter is only a projection: it must equal the immutable journal.
    with factory() as db:
        rec = AdBillingService(db).reconcile(pid)
    assert rec['balanced'] is True, f"ledger and counter diverged under concurrency: {rec}"
    assert rec['ledger_total'] == '1.00'
