from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Sequence
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, desc, asc
from backend.app.models.catalog import (
    Category,
    Product,
    ProductImage,
    ProductSKU,
    StoreLocation,
    StoreInventory,
    RecentlyViewed,
)
from backend.app.services.product_media_service import order_media, primary_url
from backend.app.models.user import BrandProfile


def purchasable_criterion():
    """SQL predicate for "a shopper can actually buy this product right now".

    ONE definition, imported by every storefront read path (catalogue list,
    dashboard, search, autocomplete) so the answer to "is it buyable?" cannot
    drift between the page that lists a product and the page that sells it.

    A product is purchasable when at least one of its SKUs is both flagged
    in-stock AND carries a positive stock level. Both conditions are required
    because they are maintained by different code paths: `is_in_stock` is a
    merchandising flag a brand can toggle, `stock_level` is decremented by
    checkout (commerce_service, line ~1403). Trusting either alone lets a
    sold-out product stay listed, or a deliberately hidden one reappear.

    Kept as a criterion rather than a Python filter so the database does the
    work: filtering in Python would break LIMIT/OFFSET pagination (you would
    page over rows you then discard) and force a full table read.
    """
    return Product.skus.any((ProductSKU.is_in_stock == True) & (ProductSKU.stock_level > 0))  # noqa: E712


class CatalogRepository:
    def __init__(self, db: Session):
        self.db = db

    def images_for_product(self, product_id: int) -> List[ProductImage]:
        """The registered media set for one product (empty when none exists).

        Rows are returned in the gallery order defined by
        ``services.product_media_service`` — primary first, then the ratio
        ladder — so every caller (product page, media route, verification
        script) sees the same first image and the same set.
        """
        rows = (
            self.db.query(ProductImage)
            .filter(ProductImage.product_id == product_id)
            .all()
        )
        return order_media(rows)

    def primary_media_urls(self, product_ids: Sequence[int]) -> Dict[int, str]:
        """Hero URL per product in ONE query (list pages must not fan out).

        The list endpoint serves up to 100 products; resolving each one's hero
        with a separate query would turn one page render into 100 round trips.
        The ratio/format preference is applied in Python so the same rule that
        orders a gallery also picks the card image — the card and the first
        gallery frame can therefore never disagree.
        """
        ids = [pid for pid in dict.fromkeys(product_ids) if pid is not None]
        if not ids:
            return {}
        rows = (
            self.db.query(ProductImage)
            .filter(ProductImage.product_id.in_(ids))
            .all()
        )
        grouped: Dict[int, List[ProductImage]] = {}
        for row in rows:
            grouped.setdefault(row.product_id, []).append(row)
        return {
            pid: url
            for pid, group in grouped.items()
            if (url := primary_url(order_media(group))) is not None
        }

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
        sort_by: Optional[str] = "recommended",
        brand_ids: Optional[List[int]] = None,
        in_stock_only: bool = False,
    ) -> List[Product]:
        query = self.db.query(Product).options(
            joinedload(Product.brand),
            joinedload(Product.category),
            joinedload(Product.skus),
        ).filter(Product.is_active == True)

        if category_slug:
            query = query.join(Category).filter(Category.slug == category_slug)
        if brand_id:
            query = query.filter(Product.brand_id == brand_id)
        if brand_ids:
            # Visual search passes a brand allow-list (schema: brand_ids). The
            # service called this with a keyword the repository did not accept,
            # which was a second, latent TypeError behind the visual-search 500.
            query = query.filter(Product.brand_id.in_(list(brand_ids)))
        if in_stock_only:
            query = query.filter(purchasable_criterion())
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

    def record_product_view(self, user_id: int, product_id: int) -> None:
        """Upsert a recently-viewed row (re-viewing refreshes recency)."""
        row = (
            self.db.query(RecentlyViewed)
            .filter(RecentlyViewed.user_id == user_id, RecentlyViewed.product_id == product_id)
            .first()
        )
        if row:
            row.viewed_at = datetime.now(timezone.utc)
        else:
            self.db.add(RecentlyViewed(user_id=user_id, product_id=product_id))
        self.db.commit()

    def get_recently_viewed(self, user_id: int, limit: int = 10) -> List[Product]:
        """Most-recently viewed products for a user, newest first."""
        rows = (
            self.db.query(RecentlyViewed)
            .filter(RecentlyViewed.user_id == user_id)
            .order_by(desc(RecentlyViewed.viewed_at))
            .limit(limit)
            .all()
        )
        pids = [r.product_id for r in rows]
        if not pids:
            return []
        products = (
            self.db.query(Product)
            .options(joinedload(Product.brand), joinedload(Product.category), joinedload(Product.skus))
            .filter(Product.id.in_(pids), Product.is_active == True)
            .all()
        )
        by_id = {p.id: p for p in products}
        return [by_id[i] for i in pids if i in by_id]

    def get_new_from_brands(self, brand_names: List[str], limit: int = 8) -> List[Product]:
        """Latest active products from the given brand names, newest first."""
        if not brand_names:
            return []
        return (
            self.db.query(Product)
            .options(joinedload(Product.brand), joinedload(Product.category))
            .join(BrandProfile, Product.brand_id == BrandProfile.id)
            .filter(BrandProfile.brand_name.in_(brand_names), Product.is_active == True)
            .order_by(desc(Product.created_at))
            .limit(limit)
            .all()
        )

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
