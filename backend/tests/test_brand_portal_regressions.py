"""Isolated partner contract tests. No production credentials, demo login or skips."""
import io
import csv
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend.app.main import app
from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token
from backend.app.models.user import User, UserRole, BrandProfile
from backend.app.models.catalog import Category, Product, ProductSKU, StoreLocation, StoreInventory
from backend.app.models.brand_analytics import SponsoredPlacement
from backend.app.services.brand_catalog_service import BrandCatalogService


@pytest.fixture
def portal():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        users = [User(email=f'{r}@example.test', full_name=r, hashed_password='not-a-login', role=r)
                 for r in [UserRole.BRAND_OWNER, UserRole.BRAND_MANAGER, UserRole.CONSUMER, UserRole.ADMIN]]
        db.add_all(users)
        db.flush()
        brands = [BrandProfile(user_id=u.id, brand_name=f'Isolated {i}', slug=f'isolated-{i}') for i,u in enumerate(users[:2])]
        db.add_all(brands)
        db.add(Category(name='Coats', name_ar='معاطف', slug='coats'))
        db.commit()
        headers = [{'Authorization': f'Bearer {create_access_token({"sub": str(u.id)})}'} for u in users]
        ids = [b.id for b in brands]
    old = app.dependency_overrides.get(get_db)
    def session():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = session
    try:
        yield TestClient(app), factory, headers, ids
    finally:
        if old is None: app.dependency_overrides.pop(get_db, None)
        else: app.dependency_overrides[get_db] = old
        engine.dispose()


def row(**changes):
    return dict(title='Coat', category_slug='coats', base_price='19.99', color_family='Navy',
                thumbnail_url='https://example.com/coat.jpg', sku_code='COAT-M-NAVY', size='M',
                color='Navy', stock_level='10', **{}) | changes


def upload(client, headers, rows):
    return client.post('/partner/catalog/import', headers=headers, json={'products': rows})


def test_json_invalid_shape_is_422(portal):
    client, _, h, _ = portal
    for products in ['bad', [None], [3], {'title': 'bad'}]:
        response = client.post('/partner/catalog/import', headers=h[0], json={'products': products})
        assert response.status_code == 422, response.text


def test_rejected_rows_are_not_field_errors(portal):
    client, _, h, _ = portal
    r = upload(client, h[0], [row(title='', base_price='NaN', color_family=''), row()])
    assert r.status_code == 202, r.text
    data = r.json()
    assert (data['total_rows'], data['accepted_rows'], data['rejected_rows']) == (2, 1, 1)
    assert len(data['errors']) >= 3


def test_rejected_foreign_sku_leaves_no_product(portal):
    client, factory, h, _ = portal
    assert upload(client, h[1], [row()]).json()['accepted_rows'] == 1
    data = upload(client, h[0], [row(title='Must not exist'), row(title='Accepted', sku_code='ACCEPTED')]).json()
    assert data['accepted_rows'] == 1
    with factory() as db:
        assert db.query(Product).filter_by(title='Must not exist').count() == 0
    assert data['errors'][0]['row'] == 2
    assert 'error' not in data['errors'][0]  # one UI-compatible error shape


def test_import_cannot_reparent_existing_sku(portal):
    client, factory, h, _ = portal
    upload(client, h[0], [row()])
    data = upload(client, h[0], [row(title='Different product')]).json()
    assert data['rejected_rows'] == 1
    with factory() as db:
        assert db.query(ProductSKU).one().product.title == 'Coat'


def test_bom_csv_optional_blanks_and_zero_stock(portal):
    client, factory, h, _ = portal
    text = '\ufefftitle,category_slug,base_price,color_family,thumbnail_url,size,color,stock_level,price_override\nCoat,coats,19.99,Navy,https://example.com/x.jpg,,,,\n'
    r = client.post('/partner/catalog/upload/csv', headers=h[0], files={'file': ('catalog.CSV', text.encode(), 'text/csv')})
    assert r.status_code == 202, r.text
    assert r.json()['accepted_rows'] == 1
    with factory() as db:
        sku = db.query(ProductSKU).one()
        assert sku.stock_level == 0  # never invent 20 sellable units
        assert sku.size == 'M'


@pytest.mark.parametrize('changes', [dict(stock_level='100001'), dict(stock_level='2.5'), dict(title='x'*256), dict(style_tags={'bad':'type'}), dict(thumbnail_url='javascript:alert(1)')])
def test_import_rejects_invalid_values(portal, changes):
    client, _, h, _ = portal
    r = upload(client, h[0], [row(**changes)])
    assert r.status_code == 202, r.text
    assert r.json()['accepted_rows'] == 0


def test_import_idempotency_and_duplicate_rows(portal):
    client, factory, h, _ = portal
    data = upload(client, h[0], [row(), row()]).json()
    assert data['accepted_rows'] == 1 and data['rejected_rows'] == 1
    assert data['duplicate_rows'] == 1
    assert upload(client, h[0], [row(stock_level='0')]).json()['accepted_rows'] == 1
    with factory() as db:
        assert db.query(Product).count() == db.query(ProductSKU).count() == 1
        assert db.query(ProductSKU).one().stock_level == 0


def make_inventory(portal):
    client, factory, h, ids = portal
    upload(client, h[0], [row()])
    with factory() as db:
        sku = db.query(ProductSKU).one()
        store = StoreLocation(brand_id=ids[0], name='Cairo', name_ar='القاهرة', city='Giza', country='EG', address='Test', latitude=30, longitude=31)
        db.add(store); db.flush()
        inv = StoreInventory(store_id=store.id, sku_id=sku.id, quantity=10, reserved_quantity=3)
        db.add(inv); db.commit()
        return inv.id, {'store_id': store.id, 'sku_id': sku.id, 'quantity': 7}


def test_inventory_path_identity_and_tenant(portal):
    client, factory, h, _ = portal
    inv_id, payload = make_inventory(portal)
    r = client.patch(f'/partner/inventory/{inv_id+100}', headers=h[0], json=payload)
    assert r.status_code == 404
    r = client.patch(f'/partner/inventory/{inv_id}', headers=h[1], json=payload)
    assert r.status_code in (403,404)
    with factory() as db:
        assert db.get(StoreInventory, inv_id).quantity == 10
    assert client.patch(f'/partner/inventory/{inv_id}', headers=h[0], json=payload).status_code == 200


def test_inventory_reserved_and_integer_validation(portal):
    client, _, h, _ = portal
    inv_id, payload = make_inventory(portal)
    for quantity in [-1, 100001, 1.5, True]:
        assert client.patch(f'/partner/inventory/{inv_id}', headers=h[0], json=payload | {'quantity': quantity}).status_code == 422
    assert client.patch(f'/partner/inventory/{inv_id}', headers=h[0], json=payload | {'quantity': 2}).status_code == 400


def make_placement(portal):
    client, factory, h, _ = portal
    upload(client, h[0], [row()])
    with factory() as db:
        product_id = db.query(Product).one().id
    r = client.post('/partner/placements', headers=h[0], json={'product_id': product_id, 'bid_amount_per_click': 1, 'daily_budget': 5})
    assert r.status_code == 201, r.text
    return r.json()['id']


def test_placement_validates_final_budget_not_old_budget(portal):
    client, _, h, _ = portal
    pid = make_placement(portal)
    r = client.patch(f'/partner/placements/{pid}', headers=h[0], json={'bid_amount_per_click': 8, 'daily_budget': 10})
    assert r.status_code == 200, r.text


@pytest.mark.parametrize('payload', [dict(placement_type='invented'), dict(start_date='2026-10-03',end_date='2026-10-01'), dict(daily_budget=None), dict(impressions=999)])
def test_placement_invalid_patch_is_client_error(portal, payload):
    client, _, h, _ = portal
    pid = make_placement(portal)
    r = client.patch(f'/partner/placements/{pid}', headers=h[0], json=payload)
    assert r.status_code in (400,422), r.text


def test_placement_dates_roundtrip_and_tracking_timezone(portal):
    client, _, h, _ = portal
    pid = make_placement(portal)
    r = client.patch(f'/partner/placements/{pid}', headers=h[0], json={'start_date': '2099-01-01T00:00:00+02:00', 'end_date': '2099-02-01T00:00:00Z'})
    assert r.status_code == 200
    assert client.get('/partner/placements', headers=h[0]).json()[0]['start_date'] is not None
    assert client.post(f'/partner/placements/{pid}/click', headers=h[0]).status_code == 400


def test_consumer_and_unassigned_admin_fail_closed(portal):
    client, _, h, _ = portal
    for headers in [h[2], h[3]]:
        assert client.get('/brand/profile', headers=headers).status_code == 403
