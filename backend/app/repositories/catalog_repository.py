from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, desc, asc
from backend.app.models.catalog import Category, Product, ProductSKU, StoreLocation, StoreInventory


class CatalogRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_categories(self) -> List[Category]:
        return self.db.query(Category).all()

    def get_category_by_slug(self, slug: str) -> Optional[Category]:
        return self.db.query(Category).filter(Category.slug == slug).first()

    def get_product_by_id(self, product_id: int) -> Optional[Product]:
        return (
            self.db.query(Product)
            .options(
                joinedload(Product.brand),
                joinedload(Product.category),
                joinedload(Product.skus)
            )
            .filter(Product.id == product_id)
            .first()
        )

    def get_product_by_slug(self, slug: str) -> Optional[Product]:
        return (
            self.db.query(Product)
            .options(
                joinedload(Product.brand),
                joinedload(Product.category),
                joinedload(Product.skus)
            )
            .filter(Product.slug == slug)
            .first()
        )

    def get_sku_by_id(self, sku_id: int) -> Optional[ProductSKU]:
        return (
            self.db.query(ProductSKU)
            .options(joinedload(ProductSKU.product))
            .filter(ProductSKU.id == sku_id)
            .first()
        )

    def get_featured_products(self, limit: int = 10) -> List[Product]:
        return self.filter_products(is_featured=True, limit=limit)

    def filter_products(
        self,
        category_slug: Optional[str] = None,
        brand_id: Optional[int] = None,
        color: Optional[str] = None,
        occasion: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        search_query: Optional[str] = None,
        is_featured: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: Optional[str] = "recommended"
    ) -> List[Product]:
        query = self.db.query(Product).options(
            joinedload(Product.brand),
            joinedload(Product.category)
        ).filter(Product.is_active == True)

        if category_slug:
            query = query.join(Category).filter(Category.slug == category_slug)
        if brand_id:
            query = query.filter(Product.brand_id == brand_id)
        if color:
            query = query.filter(Product.color_family.ilike(f"%{color}%"))
        if occasion:
            query = query.filter(Product.occasion_tags.like(f"%{occasion}%"))
        if min_price is not None:
            query = query.filter(Product.base_price >= min_price)
        if max_price is not None:
            query = query.filter(Product.base_price <= max_price)
        if search_query:
            search_pattern = f"%{search_query}%"
            query = query.filter(
                or_(
                    Product.title.ilike(search_pattern),
                    Product.title_ar.ilike(search_pattern),
                    Product.description.ilike(search_pattern),
                    Product.color_family.ilike(search_pattern),
                    Product.style_tags.ilike(search_pattern)
                )
            )
        if is_featured is not None:
            query = query.filter(Product.is_featured == is_featured)

        if sort_by == "price_asc":
            query = query.order_by(asc(Product.base_price))
        elif sort_by == "price_desc":
            query = query.order_by(desc(Product.base_price))
        elif sort_by == "rating":
            query = query.order_by(desc(Product.rating))
        elif sort_by == "newest":
            query = query.order_by(desc(Product.created_at))
        else:
            query = query.order_by(desc(Product.rating), desc(Product.id))

        return query.offset(offset).limit(limit).all()

    def get_stores_for_product_sku(self, sku_id: int) -> List[Dict[str, Any]]:
        results = (
            self.db.query(StoreInventory, StoreLocation)
            .join(StoreLocation, StoreInventory.store_id == StoreLocation.id)
            .filter(StoreInventory.sku_id == sku_id)
            .filter(StoreLocation.is_bopis_enabled == True)
            .all()
        )
        output = []
        for inv, store in results:
            output.append({
                "store_id": store.id,
                "store_name": store.name,
                "store_name_ar": store.name_ar,
                "address": store.address,
                "city": store.city,
                "country": store.country,
                "quantity_available": inv.quantity - inv.reserved_quantity,
                "is_available_for_pickup": (inv.quantity - inv.reserved_quantity) > 0,
                "latitude": store.latitude,
                "longitude": store.longitude
            })
        return output
