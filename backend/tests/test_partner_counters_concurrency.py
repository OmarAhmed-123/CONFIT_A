import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date,timedelta
import pytest
from backend.tests.test_brand_portal_regressions import portal,row,upload
from backend.tests.test_brand_team_atomic import invitee,invitation
from backend.app.models.user import User,BrandProfile
from backend.app.models.brand_team import BrandMembership
from backend.app.models.brand_analytics import SponsoredPlacement,PlacementCounterEvent
from backend.app.services.partner_import_queue import PartnerImportQueue
from backend.app.models.catalog import Product,ProductSKU
from backend.app.repositories.brand_repository import BrandRepository


def placement(portal):
    c,f,h,b=portal;upload(c,h[0],[row()])
    with f() as db:pid=db.query(Product.id).scalar()
    r=c.post('/partner/placements',headers=h[0],json={'product_id':pid,'bid_amount_per_click':'0.10','daily_budget':'0.30'})
    assert r.status_code==201,r.text
    return r.json()['id']


def test_counter_idempotency_rollover_and_provenance(portal):
    c,f,h,b=portal;p=placement(portal);url=f'/partner/placements/{p}/click'
    assert c.post(url,headers=h[0]).status_code==422
    headers=h[0]|{'Idempotency-Key':'counter-original-event'}
    first=c.post(url,headers=headers);second=c.post(url,headers=headers)
    assert first.status_code==200 and second.json()==first.json()
    assert first.json()['billable'] is False
    with f() as db:
        obj=db.get(SponsoredPlacement,p);assert obj.clicks==1 and float(obj.spent_today)==0.10
        assert db.query(PlacementCounterEvent).count()==1
        obj.spend_day=date.today()-timedelta(days=1);obj.status='budget_exhausted';db.commit()
    nextday=c.post(url,headers=h[0]|{'Idempotency-Key':'counter-next-day-event'})
    assert nextday.json()['spent_today']==0.10
    assert c.post(url,headers=headers).json()==first.json()  # retries across dates do not bill again
    assert c.delete(f'/partner/placements/{p}',headers=h[0]).json()['status']=='cancelled'
    with f() as db:assert db.get(SponsoredPlacement,p) and db.query(PlacementCounterEvent).count()==2


def test_analytics_counts_are_not_a_catalog_page(portal):
    c,f,h,b=portal;upload(c,h[0],[row(title=f'P{i}',sku_code=f'SKU-{i}') for i in range(28)])
    assert len(c.get('/brand/products',headers=h[0]).json())==25
    data=c.get('/brand/analytics',headers=h[0]).json()
    assert data['total_products_count']==28 and data['total_skus_count']==28
    assert data['funnel_conversion_rate'] is None


@pytest.mark.skipif(not os.environ.get('CONFIT_PORTAL_TEST_PG_URL'),reason='PostgreSQL lock semantics')
def test_simultaneous_counter_retries_charge_once(portal):
    c,f,h,b=portal;p=placement(portal)
    def click(_):return c.post(f'/partner/placements/{p}/click',headers=h[0]|{'Idempotency-Key':'concurrent-counter-key'}).status_code
    with ThreadPoolExecutor(max_workers=6) as pool:assert list(pool.map(click,range(12)))==[200]*12
    with f() as db:
        assert db.get(SponsoredPlacement,p).clicks==1
        assert db.query(PlacementCounterEvent).count()==1


@pytest.mark.skipif(not os.environ.get('CONFIT_PORTAL_TEST_PG_URL'),reason='PostgreSQL lock semantics')
def test_two_owners_cannot_concurrently_remove_last_owner(portal):
    c,f,h,b=portal;uid,ih=invitee(f);inv=invitation(c,h[0],role='owner')
    assert c.post('/partner/team/accept',headers=ih,json={'token':inv['token']}).status_code==200
    members=c.get('/partner/team/members',headers=h[0]).json()['items']
    def remove(args):
        member,headers=args
        return c.delete(f"/partner/team/members/{member['id']}",headers=headers).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses=list(pool.map(remove,[(members[0],h[0]),(members[1],ih)]))
    assert sorted(statuses)==[200,409]
    with f() as db:assert db.query(BrandMembership).filter_by(brand_id=b[0],role='owner').count()==1


def test_inventory_total_is_not_first_variant_page(portal):
    c, f, h, brands = portal
    upload(c, h[0], [row(sku_code=f'VARIANT-{i}', size=str(i), stock_level='1') for i in range(28)])
    result = c.get('/partner/inventory', headers=h[0]).json()[0]
    assert len(result['skus']) == 25
    assert result['total_stock'] == 28
    assert result['skus_next_cursor'] is not None
