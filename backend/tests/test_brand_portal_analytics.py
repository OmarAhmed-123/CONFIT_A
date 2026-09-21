"""Analytical acceptance uses controlled item counts, never seeded benchmark values."""
import pytest
from backend.tests.test_brand_portal_regressions import portal, row, upload, make_inventory
from backend.app.models.catalog import Product, ProductSKU
from backend.app.models.commerce import Order, OrderItem, FulfillmentGroup
from backend.app.models.stylist import Outfit, OutfitItem
from backend.app.models.user import User, UserRole
from backend.app.repositories.brand_repository import BrandRepository


def test_empty_brand_has_no_fabricated_benchmarks_or_rankings(portal):
    client, _, h, _ = portal
    r = client.get('/brand/analytics', headers=h[0])
    assert r.status_code == 200, r.text
    d = r.json()
    assert d['return_rate_before_vton'] is None
    assert d['return_rate_after_vton'] is None
    assert d['return_reduction_percentage'] is None
    assert d['bopis_store_fulfillment_rate'] is None
    assert d['outfit_appearance_rankings'] == []
    assert d['return_cohorts']['tryon_items'] == 0
    assert d['data_source'] == 'transactional_snapshot'


def test_mixed_brand_return_is_item_scoped_and_failed_purchase_excluded(portal):
    client, factory, h, ids = portal
    for i in range(2):
        upload(client, h[i], [row(title=f'Brand {i}', sku_code=f'BRAND-{i}')])
    with factory() as db:
        products = db.query(Product).order_by(Product.id).all()
        for n, (assisted, status) in enumerate([(False, 'refunded'), (True, 'delivered'), (True, 'failed')]):
            order = Order(order_number=f'isolated-{n}', total_amount=40, subtotal_amount=40,
                          try_on_assisted=assisted, status=status)
            db.add(order); db.flush()
            for i,p in enumerate(products):
                db.add(OrderItem(order_id=order.id, product_id=p.id, brand_id=p.brand_id,
                    product_title=p.title, brand_name=p.brand.brand_name, size='M', color='Navy',
                    unit_price=20, quantity=1, subtotal=20, is_returned=n==0 and i==1))
        db.commit()
    a = client.get('/partner/analytics/returns', headers=h[0]).json()
    b = client.get('/partner/analytics/returns', headers=h[1]).json()
    assert a['non_tryon_items'] == b['non_tryon_items'] == 1
    assert a['tryon_items'] == b['tryon_items'] == 1
    assert a['return_rate_before_vton'] == 0
    assert b['return_rate_before_vton'] == 100
    assert a['return_reduction_percentage'] is None
    assert b['return_reduction_percentage'] == 100
    assert 'platform_metrics' not in a
    conv = client.get('/partner/analytics/conversion', headers=h[0]).json()
    assert conv['purchases'] == 1 and conv['per_sku'][0]['purchases'] == 1
    assert conv['grain'] == 'product'


def test_bopis_fulfillment_uses_groups_not_order_lines(portal):
    client, factory, h, ids = portal
    with factory() as db:
        order = Order(order_number='pickup', total_amount=10, subtotal_amount=10)
        db.add(order); db.flush()
        for status in ['picked_up', 'processing', 'cancelled']:
            db.add(FulfillmentGroup(order_id=order.id, brand_id=ids[0], brand_name='A', fulfillment_type='bopis', status=status))
        db.commit()
    d = client.get('/brand/analytics', headers=h[0]).json()
    assert d['bopis_store_fulfillment_rate'] == 50


def test_heatmaps_suppress_repeated_outfits_from_one_user_and_foreign_brand(portal):
    client, factory, h, ids = portal
    upload(client, h[0], [row()])
    with factory() as db:
        product = db.query(Product).one()
        for _ in range(12):
            outfit = Outfit(user_id=1, title='Private', style_tags='["private-style"]')
            db.add(outfit); db.flush()
            db.add(OutfitItem(outfit_id=outfit.id, product_id=product.id, position='top'))
        db.commit()
    for headers in h[:2]:
        r = client.get('/partner/analytics/heatmaps?region=MENA', headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data['top_aesthetics'] == []
        assert data['sample_size'] == 0
        assert data['region'] == 'Global'
        assert data['region_filter_applied'] is False


def test_heatmap_cell_requires_ten_distinct_users(portal):
    client, factory, h, ids = portal
    upload(client, h[0], [row()])
    with factory() as db:
        product = db.query(Product).one()
        for i in range(10):
            user = User(email=f'viewer-{i}@example.test', full_name='Viewer', hashed_password='unused', role=UserRole.CONSUMER)
            db.add(user); db.flush()
            outfit = Outfit(user_id=user.id, title='Outfit', style_tags='["minimal"]')
            db.add(outfit); db.flush()
            db.add(OutfitItem(outfit_id=outfit.id, product_id=product.id, position='top'))
        db.commit()
    data = client.get('/partner/analytics/heatmaps', headers=h[0]).json()
    assert data['top_aesthetics'] == [{'name':'minimal','weight':100,'count':10}]
    assert client.get('/partner/analytics/heatmaps', headers=h[1]).json()['top_aesthetics'] == []


def test_explicit_inventory_upsert_is_repeatable_and_audited(portal):
    client, factory, h, ids = portal
    inventory_id, payload = make_inventory(portal)
    for _ in range(2):
        r = client.post('/partner/inventory', headers=h[0], json=payload)
        assert r.status_code == 200, r.text
        assert r.json()['inventory_id'] == inventory_id
    assert client.post('/partner/inventory', headers=h[1], json=payload).status_code == 400
    from backend.app.models.user import AuditLog
    with factory() as db:
        assert db.query(AuditLog).filter_by(action='BRAND_STORE_INVENTORY_UPDATED').count() == 2


@pytest.mark.parametrize('bad', [{'name':' '}, {'city':'x'*101}, {'latitude':91}, {'address':None}, {'brand_id':999}])
def test_store_create_rejects_invalid_values(portal, bad):
    client, _, h, _ = portal
    payload = dict(name='Giza', city='Giza', country='EG', address='Test') | bad
    assert client.post('/partner/stores', headers=h[0], json=payload).status_code == 422


def test_store_patch_cannot_null_required_fields(portal):
    client, _, h, _ = portal
    r = client.post('/partner/stores', headers=h[0], json=dict(name='Giza',city='Giza',country='EG',address='Test'))
    assert r.status_code == 201
    sid = r.json()['id']
    assert client.patch(f'/partner/stores/{sid}', headers=h[0], json={'name':None}).status_code == 422
    assert client.patch(f'/partner/stores/{sid}', headers=h[1], json={'name':'Other'}).status_code == 404
    assert client.get('/partner/stores', headers=h[0]).json()[0]['name'] == 'Giza'


def test_partner_product_response_keeps_skus_for_the_editor(portal):
    client, _, h, _ = portal
    assert upload(client, h[0], [row(title='معطف اختبار')]).json()['accepted_rows'] == 1
    for path in ['/brand/products', '/partner/products']:
        products = client.get(path, headers=h[0]).json()
        assert products[0]['title'] == 'معطف اختبار'
        assert products[0]['skus'][0]['sku_code'] == 'COAT-M-NAVY'
        assert products[0]['skus'][0]['stock_level'] == 10
        assert client.get(path, headers=h[1]).json() == []


def test_generated_sku_upgrade_does_not_duplicate_legacy_variant(portal):
    client, factory, h, _ = portal
    upload(client, h[0], [row(sku_code='LEGACY-GENERATED-M-NAVY')])
    assert upload(client, h[0], [row(sku_code='', stock_level='3')]).json()['accepted_rows'] == 1
    with factory() as db:
        assert db.query(ProductSKU).count() == 1
        sku = db.query(ProductSKU).one()
        assert sku.sku_code == 'LEGACY-GENERATED-M-NAVY' and sku.stock_level == 3
