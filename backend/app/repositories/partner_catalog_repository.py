"""Bounded partner read model: keyset pagination, no SELECT-all slicing."""
from fastapi import HTTPException
from backend.app.models.catalog import Product, ProductSKU, StoreInventory, StoreLocation
from backend.app.models.user import AuditLog


def page(query, column, after, limit):
    rows = query.filter(column > after).order_by(column).limit(limit + 1).all()
    return rows[:limit], getattr(rows[limit - 1], column.key) if len(rows) > limit else None


class PartnerCatalogRepository:
    def __init__(self, db, brand_id):
        self.db, self.brand_id = db, brand_id

    def product(self, product_id, lock=False):
        q = self.db.query(Product).filter_by(id=product_id, brand_id=self.brand_id)
        result = q.with_for_update().first() if lock else q.first()
        if result is None:
            raise HTTPException(404, 'Product unavailable')
        return result

    def products(self, after, limit):
        return page(self.db.query(Product).filter_by(brand_id=self.brand_id), Product.id, after, limit)

    def skus(self, product_id, after, limit):
        self.product(product_id)
        return page(self.db.query(ProductSKU).filter_by(product_id=product_id), ProductSKU.id, after, limit)

    def variant(self, product_id, sku_id):
        self.product(product_id, lock=True)
        sku = self.db.query(ProductSKU).filter_by(product_id=product_id, id=sku_id).with_for_update().first()
        if not sku:
            raise HTTPException(404, 'SKU unavailable')
        return sku

    def store_stock(self, after, limit):
        from sqlalchemy.orm import joinedload
        q = self.db.query(StoreInventory).join(StoreLocation).filter(StoreLocation.brand_id == self.brand_id).options(
            joinedload(StoreInventory.store), joinedload(StoreInventory.sku))
        return page(q, StoreInventory.id, after, limit)
