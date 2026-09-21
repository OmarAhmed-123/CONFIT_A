import io
from datetime import datetime, timezone, timedelta
import pytest
from PIL import Image
from backend.tests.test_brand_portal_regressions import portal, row, upload
from backend.app.models.catalog import Product, ProductSKU
from backend.app.models.brand_operations import CatalogImportWork, ProductAsset
from backend.app.models.catalog_import import CatalogImportJob
from backend.app.models.user import AuditLog, User
from backend.app.services.partner_import_queue import PartnerImportQueue
from backend.app.services.brand_catalog_service import BrandCatalogService
from backend.app.services import partner_assets
from backend.app.services.storage_service import LocalStorageBackend


def pid(factory):
    with factory() as db:return db.query(Product).order_by(Product.id).first().id


def test_product_lifecycle_and_idor(portal):
    c,f,h,b=portal;upload(c,h[0],[row()]);p=pid(f)
    assert c.patch(f'/partner/catalog/products/{p}',headers=h[1],json={'title':'hacked'}).status_code==404
    r=c.patch(f'/partner/catalog/products/{p}',headers=h[0],json={'title':'Edited','title_ar':'معدّل','status':'draft'})
    assert r.status_code==200,r.text
    assert r.json()['status']=='draft'
    assert c.get(f'/catalog/products/{p}').status_code==404
    assert c.patch(f'/partner/catalog/products/{p}',headers=h[0],json={'status':'active'}).status_code==200
    assert c.patch(f'/partner/catalog/products/{p}',headers=h[0],json={'status':'archived'}).json()['status']=='archived'
    with f() as db:
        assert db.get(Product,p).is_active is False
        assert db.query(ProductSKU).count()==1  # retained, not destructive delete
        assert db.query(AuditLog).filter_by(action='BRAND_PRODUCT_UPDATED',brand_id=b[0]).count()==3
    for payload in [{'title':None},{'brand_id':b[1]},{'base_price':'NaN'},{'status':'deleted'},{'category_id':999999}]:
        assert c.patch(f'/partner/catalog/products/{p}',headers=h[0],json=payload).status_code==422


def test_product_and_sku_pagination(portal):
    c,f,h,b=portal
    upload(c,h[0],[row(title=f'P{i}',sku_code=f'SKU-{i}') for i in range(5)])
    one=c.get('/partner/catalog/products?limit=2',headers=h[0]).json()
    two=c.get('/partner/catalog/products',headers=h[0],params={'after':one['next_cursor'],'limit':2}).json()
    assert len(one['items'])==len(two['items'])==2
    assert not {p['id'] for p in one['items']} & {p['id'] for p in two['items']}
    p=one['items'][0]['id'];url=f'/partner/catalog/products/{p}/skus'
    assert c.post(url,headers=h[0],json={'sku_code':'NEW-SKU','size':'L','color':'Navy'}).status_code==201
    assert c.post(url,headers=h[0],json={'sku_code':'NEW-OTHER','size':'L','color':'Navy'}).status_code==409
    assert c.post(url,headers=h[1],json={'sku_code':'NEW-OTHER','size':'XL','color':'Navy'}).status_code==404
    one=c.get(url+'?limit=1',headers=h[0]).json()
    two=c.get(url,headers=h[0],params={'after':one['next_cursor'],'limit':1}).json()
    assert len(one['items'])==len(two['items'])==1 and one['items'][0]['id']!=two['items'][0]['id']


def enqueue(c,h,rows,request_identity='test-idempotency-0001'):
    return c.post('/partner/catalog/jobs',headers=h|{'Idempotency-Key':request_identity},json={'products':rows})


def test_queue_checkpoint_retry_and_partial_rows(portal,monkeypatch):
    c,f,h,b=portal;rows=[row(title=f'P{i}',sku_code=f'SKU-{i}') for i in range(24)]+[row(title='',sku_code='INVALID')]
    result=enqueue(c,h[0],rows);assert result.status_code==202,result.text
    jobid=result.json()['job_id']
    assert enqueue(c,h[0],rows).json()['duplicate'] is True
    assert enqueue(c,h[0],[row()]).status_code==409
    with f() as db:assert db.query(Product).count()==0
    with f() as db:
        result=PartnerImportQueue(db).run_batch();assert result['processed']==20
    with f() as db:
        assert db.get(CatalogImportWork,jobid).cursor==20
        assert db.get(CatalogImportJob,jobid).accepted_rows==20
    original=BrandCatalogService.import_products
    def fail(*args,**kwargs):raise RuntimeError('injected transient worker failure')
    monkeypatch.setattr(BrandCatalogService,'import_products',fail)
    with f() as db:assert PartnerImportQueue(db).run_batch()['processed']==0
    with f() as db:
        work=db.get(CatalogImportWork,jobid);assert work.cursor==20 and work.attempts==1
        work.next_attempt_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
    monkeypatch.setattr(BrandCatalogService,'import_products',original)
    with f() as db:assert PartnerImportQueue(db).run_batch()['processed']==4
    with f() as db:
        job=db.get(CatalogImportJob,jobid);assert (job.accepted_rows,job.rejected_rows,job.total_rows)==(24,1,25)
        assert job.status=='partially_completed'
        assert db.get(CatalogImportWork,jobid).payload_json=='[]'
        assert db.query(Product).count()==24
    assert c.post(f'/partner/catalog/jobs/{jobid}/run',headers=h[1]).status_code==404
    with f() as db:assert PartnerImportQueue(db).run_batch()['processed']==0


def test_queue_rolls_back_whole_uncheckpointed_batch(portal,monkeypatch):
    c,f,h,b=portal;jobid=enqueue(c,h[0],[row(title=f'P{i}',sku_code=f'SKU-{i}') for i in range(3)]).json()['job_id']
    original=BrandCatalogService.import_products;calls=0
    def fail_after_one(*args,**kwargs):
        nonlocal calls
        calls+=1
        if calls==2:raise RuntimeError('crash before checkpoint')
        return original(*args,**kwargs)
    monkeypatch.setattr(BrandCatalogService,'import_products',fail_after_one)
    with f() as db:PartnerImportQueue(db).run_batch()
    with f() as db:
        assert db.get(CatalogImportWork,jobid).cursor==0
        assert db.query(Product).count()==0


def png():
    b=io.BytesIO();Image.new('RGB',(64,64),(50,100,150)).save(b,format='PNG');return b.getvalue()


def test_asset_validation_visibility_and_cleanup(portal,monkeypatch,tmp_path):
    from backend.app.core.config import settings
    monkeypatch.setattr(settings,'STORAGE_LOCAL_DIR',str(tmp_path))
    monkeypatch.setattr(partner_assets,'storage',lambda:LocalStorageBackend())
    c,f,h,b=portal;upload(c,h[0],[row()]);p=pid(f)
    endpoint=f'/partner/catalog/products/{p}/image'
    for filename,data,mime in [('a.svg',b'<svg/>','image/svg+xml'),('a.png',b'not an image','image/png'),('a.jpg',png(),'image/jpeg')]:
        assert c.post(endpoint,headers=h[0],files={'file':(filename,data,mime)}).status_code==422
    assert c.post(endpoint,headers=h[1],files={'file':('a.png',png(),'image/png')}).status_code==404
    c.patch(f'/partner/catalog/products/{p}',headers=h[0],json={'status':'draft'})
    r=c.post(endpoint,headers=h[0],files={'file':('a.png',png(),'image/png')});assert r.status_code==201,r.text
    asset=r.json();url=asset['url']
    assert c.get(url).status_code==404
    assert c.get(url,headers=h[1]).status_code==404
    image=c.get(url,headers=h[0]);assert image.status_code==200 and image.headers['content-type']=='image/webp'
    assert image.headers['cache-control']=='private, no-store'
    c.patch(f'/partner/catalog/products/{p}',headers=h[0],json={'status':'active'})
    assert c.get(url).status_code==200
    assert c.delete('/partner/catalog/assets/'+asset['id'],headers=h[0]).status_code==409
    c.patch(f'/partner/catalog/products/{p}',headers=h[0],json={'status':'draft'})
    assert c.delete('/partner/catalog/assets/'+asset['id'],headers=h[0]).json()['state']=='deleted'
    assert c.get(url,headers=h[0]).status_code==404
    with f() as db:
        record=db.get(ProductAsset,asset['id']);assert not LocalStorageBackend().exists(record.object_key)
