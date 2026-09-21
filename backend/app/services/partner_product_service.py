import json
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from backend.app.models.catalog import Product, ProductSKU, Category
from backend.app.models.brand_analytics import SponsoredPlacement
from backend.app.repositories.partner_catalog_repository import PartnerCatalogRepository
from backend.app.services.brand_access import resolve
from backend.app.services.partner_audit import append_event, snapshot

FIELDS = ['id','brand_id','category_id','title','title_ar','description','description_ar',
          'base_price','currency','material','care_instructions','color_family','dominant_hex','thumbnail_url']


def product_out(p):
    return snapshot(p, FIELDS) | {'status': p.publication_status,
        'style_tags': json.loads(p.style_tags or '[]'), 'occasion_tags': json.loads(p.occasion_tags or '[]')}


def sku_out(s):
    return snapshot(s, ['id','product_id','sku_code','size','color','color_hex','price_override','stock_level','is_in_stock'])


class PartnerProductService:
    def __init__(self, db, user):
        self.db, self.user = db, user
        self.member = resolve(db, user)
        self.repo = PartnerCatalogRepository(db, self.member.brand_id)

    def edit(self, product_id, changes):
        resolve(self.db, self.user, 'catalog.write', lock=True)
        if 'base_price' in changes:
            resolve(self.db, self.user, 'pricing.write')
        if 'status' in changes:
            resolve(self.db, self.user, 'catalog.publish')
        p = self.repo.product(product_id, lock=True)
        before = product_out(p)
        if 'category_id' in changes and not self.db.get(Category, changes['category_id']):
            raise HTTPException(422, 'Category unavailable')
        if 'base_price' in changes and changes['base_price'] > 100000:
            raise HTTPException(422, 'Price exceeds catalog maximum')
        if 'title' in changes and self.db.query(Product.id).filter(Product.brand_id == self.member.brand_id,
            Product.title == changes['title'], Product.id != product_id).first():
            raise HTTPException(409, 'Another product already has this import identity')
        status = changes.pop('status', None)
        for key, value in changes.items():
            setattr(p, key, json.dumps(value, ensure_ascii=False) if key in ('style_tags','occasion_tags') else value)
        if status == 'active':
            from backend.app.models.user import BrandProfile
            if self.db.get(BrandProfile, self.member.brand_id).is_test:
                raise HTTPException(409, 'Production test tenants cannot publish products')
            if not p.thumbnail_url or not self.db.query(ProductSKU.id).filter_by(product_id=p.id).first():
                raise HTTPException(422, 'Publishing requires an image and at least one SKU')
            p.is_active, p.archived_at = True, None
        elif status in ('draft','archived'):
            p.is_active = False
            p.archived_at = datetime.now(timezone.utc) if status == 'archived' else None
            # Unpublishing must stop active promotion, not delete financial history.
            self.db.query(SponsoredPlacement).filter_by(product_id=p.id, status='active').update({'status':'paused'})
        append_event(self.db, self.member.brand_id, 'BRAND_PRODUCT_UPDATED', 'Product', p.id,
                     before=before, after=product_out(p))
        self.db.commit()
        return product_out(p)

    def variant(self, product_id, changes, sku_id=None):
        resolve(self.db, self.user, 'catalog.write', lock=True)
        p = self.repo.product(product_id, lock=True)
        if p.archived_at:
            raise HTTPException(409, 'Restore the product to draft before editing variants')
        if sku_id is not None:
            sku = self.repo.variant(product_id, sku_id)
            before = sku_out(sku)
        else:
            sku = ProductSKU(product_id=p.id, stock_level=0, is_in_stock=False)
            before = None
        if 'price_override' in changes and changes['price_override'] != (before.get('price_override') if before else None):
            resolve(self.db, self.user, 'pricing.write')
        # Natural-variant ambiguity is rejected, not silently reparented.
        q = self.db.query(ProductSKU).filter_by(product_id=p.id, size=changes['size'], color=changes['color'])
        if sku_id is not None:q = q.filter(ProductSKU.id != sku_id)
        if q.first():raise HTTPException(409, 'Variant already exists')
        for key, value in changes.items():setattr(sku, key, value)
        if sku_id is None:self.db.add(sku)
        try:
            self.db.flush()
            append_event(self.db, self.member.brand_id, 'BRAND_VARIANT_UPDATED' if before else 'BRAND_VARIANT_CREATED',
                         'ProductSKU', sku.id, before=before, after=sku_out(sku))
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(409, 'SKU identity already exists')
        return sku_out(sku)
