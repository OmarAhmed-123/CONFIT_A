from fastapi import APIRouter, Depends, Query, UploadFile, File, Header, HTTPException, Response
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user_optional
from backend.app.services.brand_access import require_partner, resolve
from backend.app.services.partner_product_service import PartnerProductService, product_out, sku_out
from backend.app.services.partner_assets import PartnerAssetService, MAX_UPLOAD, read
from backend.app.services.partner_import_queue import PartnerImportQueue
from backend.app.repositories.partner_catalog_repository import PartnerCatalogRepository
from backend.app.schemas.partner_operations import ProductEdit, VariantEdit, VariantCreate
from backend.app.schemas.brand import CatalogBulkImportRequest

router=APIRouter(tags=['Partner catalog operations'])


@router.get('/partner/catalog/products')
def products(after:int=Query(0,ge=0),limit:int=Query(25,ge=1,le=100),user=Depends(require_partner()),db:Session=Depends(get_db)):
    rows,cursor=PartnerCatalogRepository(db,resolve(db,user).brand_id).products(after,limit)
    return {'items':[product_out(p) for p in rows],'next_cursor':cursor}


@router.get('/partner/catalog/products/{product_id}')
def product(product_id:int,user=Depends(require_partner()),db:Session=Depends(get_db)):
    return product_out(PartnerCatalogRepository(db,resolve(db,user).brand_id).product(product_id))


@router.patch('/partner/catalog/products/{product_id}')
def edit_product(product_id:int,payload:ProductEdit,user=Depends(require_partner('catalog.write')),db:Session=Depends(get_db)):
    return PartnerProductService(db,user).edit(product_id,payload.model_dump(exclude_unset=True))


@router.get('/partner/catalog/products/{product_id}/skus')
def variants(product_id:int,after:int=Query(0,ge=0),limit:int=Query(25,ge=1,le=100),user=Depends(require_partner()),db:Session=Depends(get_db)):
    rows,cursor=PartnerCatalogRepository(db,resolve(db,user).brand_id).skus(product_id,after,limit)
    return {'items':[sku_out(s) for s in rows],'next_cursor':cursor}


@router.post('/partner/catalog/products/{product_id}/skus',status_code=201)
def create_variant(product_id:int,payload:VariantCreate,user=Depends(require_partner('catalog.write')),db:Session=Depends(get_db)):
    return PartnerProductService(db,user).variant(product_id,payload.model_dump())


@router.patch('/partner/catalog/products/{product_id}/skus/{sku_id}')
def edit_variant(product_id:int,sku_id:int,payload:VariantEdit,user=Depends(require_partner('catalog.write')),db:Session=Depends(get_db)):
    return PartnerProductService(db,user).variant(product_id,payload.model_dump(exclude_unset=True),sku_id)


@router.get('/partner/stock')
def stock(after:int=Query(0,ge=0),limit:int=Query(25,ge=1,le=100),user=Depends(require_partner()),db:Session=Depends(get_db)):
    rows,cursor=PartnerCatalogRepository(db,resolve(db,user).brand_id).store_stock(after,limit)
    return {'items':[{'id':r.id,'store_id':r.store_id,'store_name':r.store.name,'sku_id':r.sku_id,
        'sku_code':r.sku.sku_code,'quantity':r.quantity,'reserved_quantity':r.reserved_quantity} for r in rows],'next_cursor':cursor}


@router.post('/partner/catalog/products/{product_id}/image',status_code=201)
async def image(product_id:int,file:UploadFile=File(...),user=Depends(require_partner('catalog.write')),db:Session=Depends(get_db)):
    data=await file.read(MAX_UPLOAD+1)
    return PartnerAssetService(db,user).upload(product_id,data,file.filename,file.content_type)


@router.delete('/partner/catalog/assets/{asset_id}')
def delete_image(asset_id:str,user=Depends(require_partner('catalog.write')),db:Session=Depends(get_db)):
    return PartnerAssetService(db,user).delete(asset_id)


@router.get('/catalog/assets/{asset_id}')
def get_image(asset_id:str,user=Depends(get_current_user_optional),db:Session=Depends(get_db)):
    # Same origin works under existing CSP without widening the image allowlist.
    data=read(db,asset_id,user)
    return Response(data,media_type='image/webp',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})


def import_key(value):
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,100}',value):raise HTTPException(422,'A 16–100 character Idempotency-Key is required')
    return value


@router.post('/partner/catalog/jobs',status_code=202)
def enqueue(payload:CatalogBulkImportRequest,idempotency_key:str=Header(...),user=Depends(require_partner('catalog.import')),db:Session=Depends(get_db)):
    return PartnerImportQueue(db).enqueue(user,payload.products,import_key(idempotency_key))


@router.post('/partner/catalog/jobs/csv',status_code=202)
async def enqueue_csv(file:UploadFile=File(...),idempotency_key:str=Header(...),user=Depends(require_partner('catalog.import')),db:Session=Depends(get_db)):
    content=await file.read(10*1024*1024+1)
    if len(content)>10*1024*1024:raise HTTPException(413,'CSV exceeds 10 MiB')
    if not (file.filename or '').lower().endswith('.csv'):raise HTTPException(422,'CSV filename required')
    try:raw=content.decode('utf-8-sig')
    except UnicodeError:raise HTTPException(422,'UTF-8 CSV required')
    return PartnerImportQueue(db).enqueue(user,raw,import_key(idempotency_key),csv=True,filename=file.filename)


@router.post('/partner/catalog/jobs/{job_id}/run')
def run_batch(job_id:int,user=Depends(require_partner('catalog.import')),db:Session=Depends(get_db)):
    brand_id=resolve(db,user).brand_id
    from backend.app.models.catalog_import import CatalogImportJob
    if not db.query(CatalogImportJob.id).filter_by(id=job_id,brand_id=brand_id).first():raise HTTPException(404,'Import unavailable')
    return PartnerImportQueue(db).run_batch(job_id,brand_id)


@router.post('/partner/catalog/jobs/{job_id}/retry')
def retry_job(job_id:int,user=Depends(require_partner('catalog.import')),db:Session=Depends(get_db)):
    return PartnerImportQueue(db).retry(user,job_id)
