import json
import math
import urllib.parse
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
from backend.app.models.commerce import Promotion


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great circle distance between two points in kilometers."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(r * c, 1)


def build_google_maps_url(address: str, latitude: Optional[float], longitude: Optional[float]) -> str:
    """Generate high-reliability Google Maps universal navigation link with fallback."""
    if latitude is not None and longitude is not None and not (latitude == 0.0 and longitude == 0.0):
        return f"https://www.google.com/maps/dir/?api=1&destination={latitude:.6f},{longitude:.6f}"
    return f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote_plus(address)}"



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

    def get_occasion_vocabulary(self) -> List[dict]:
        """Distinct occasion tags across ACTIVE products with counts,
        most-stocked first. This is the single source of truth for the
        storefront's occasion filter pills — a hardcoded pill list drifted
        from the real tags and permanently showed empty results."""
        import json as _json
        rows = (
            self.db.query(Product.occasion_tags)
            .filter(Product.is_active == True)
            .all()
        )
        counts: dict = {}
        for (raw,) in rows:
            if not raw:
                continue
            try:
                tags = _json.loads(raw)
            except (ValueError, TypeError):
                continue
            if not isinstance(tags, list):
                continue
            for tag in tags:
                if isinstance(tag, str) and tag.strip():
                    key = tag.strip().lower()
                    counts[key] = counts.get(key, 0) + 1
        return [
            {"value": v, "count": c}
            for v, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ]

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
            # ilike, not like: tags are stored lowercase ("work") while UI
            # tokens historically arrived capitalized ("Work") — the
            # case-sensitive LIKE silently returned an EMPTY catalogue for
            # every occasion filter in production.
            query = query.filter(Product.occasion_tags.ilike(f"%{occasion}%"))
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
        """Upsert a recently-viewed row (re-viewing refreshes recency).

        DB-01 fix: relies on unique (user_id, product_id) constraint
        (0035_recently_viewed_unique). Handles race-induced duplicate inserts
        by catching IntegrityError and converting to an update, so concurrent
        views never create duplicate rows.
        """
        from sqlalchemy.exc import IntegrityError

        row = (
            self.db.query(RecentlyViewed)
            .filter(RecentlyViewed.user_id == user_id, RecentlyViewed.product_id == product_id)
            .first()
        )
        if row:
            row.viewed_at = datetime.now(timezone.utc)
            try:
                self.db.commit()
            except IntegrityError:
                # Rare race where another transaction inserted same key between
                # our SELECT and COMMIT. Rollback and update the now-existing row.
                self.db.rollback()
                existing = (
                    self.db.query(RecentlyViewed)
                    .filter(RecentlyViewed.user_id == user_id, RecentlyViewed.product_id == product_id)
                    .first()
                )
                if existing:
                    existing.viewed_at = datetime.now(timezone.utc)
                    self.db.commit()
            return

        # No existing row - try insert
        try:
            self.db.add(RecentlyViewed(user_id=user_id, product_id=product_id))
            self.db.commit()
        except IntegrityError:
            # Another concurrent request inserted same (user, product) between
            # our SELECT and INSERT. Convert to update of recency.
            self.db.rollback()
            existing = (
                self.db.query(RecentlyViewed)
                .filter(RecentlyViewed.user_id == user_id, RecentlyViewed.product_id == product_id)
                .first()
            )
            if existing:
                existing.viewed_at = datetime.now(timezone.utc)
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

    # =========================================================================
    # Customer Brand Discovery, Store Locator & Branch-Level Product Inventory
    # =========================================================================

    def _get_active_promotions_for_brand(self, brand_id: int) -> List[Promotion]:
        now = datetime.now(timezone.utc)
        return (
            self.db.query(Promotion)
            .filter(
                Promotion.brand_id == brand_id,
                Promotion.is_active == True,
                or_(Promotion.starts_at.is_(None), Promotion.starts_at <= now),
                or_(Promotion.expires_at.is_(None), Promotion.expires_at >= now),
            )
            .all()
        )

    def get_customer_brands(
        self,
        q: Optional[str] = None,
        category: Optional[str] = None,
        city: Optional[str] = None,
        has_offers: Optional[bool] = None,
        sort: str = "alphabetical",
    ) -> List[Dict[str, Any]]:
        """Fetch all public verified brands decorated with store counts, active promotions, and categories."""
        query = self.db.query(BrandProfile).filter(BrandProfile.is_verified.is_(True))

        if q and q.strip():
            token = f"%{q.strip()}%"
            query = query.filter(
                or_(
                    BrandProfile.brand_name.ilike(token),
                    BrandProfile.description.ilike(token),
                    BrandProfile.description_ar.ilike(token),
                )
            )

        brands = query.all()
        now = datetime.now(timezone.utc)
        results = []

        for b in brands:
            # Gather brand's active products
            brand_products = (
                self.db.query(Product)
                .options(joinedload(Product.category), joinedload(Product.brand))
                .filter(Product.brand_id == b.id, Product.is_active == True)
                .all()
            )
            categories = sorted(list({p.category.name for p in brand_products if p.category}))

            # Filter by category if requested
            if category and category.strip():
                req_cat = category.strip().lower()
                matches_category = any(
                    req_cat in c.lower() or (p.category and req_cat == p.category.slug.lower())
                    for c in categories for p in brand_products
                )
                if not matches_category:
                    continue

            # Gather stores
            stores = self.db.query(StoreLocation).filter(StoreLocation.brand_id == b.id).all()
            cities = sorted(list({s.city for s in stores if s.city}))

            # Filter by city if requested
            if city and city.strip():
                req_city = city.strip().lower()
                if not any(req_city in c.lower() for c in cities):
                    continue

            # Gather active promotions
            promotions = (
                self.db.query(Promotion)
                .filter(
                    Promotion.brand_id == b.id,
                    Promotion.is_active == True,
                    or_(Promotion.starts_at.is_(None), Promotion.starts_at <= now),
                    or_(Promotion.expires_at.is_(None), Promotion.expires_at >= now),
                )
                .all()
            )

            if has_offers is True and not promotions:
                continue

            # Sample products (up to 4)
            sample_prods = brand_products[:4]

            results.append({
                "brand": b,
                "total_products": len(brand_products),
                "stores_count": len(stores),
                "cities": cities,
                "categories": categories,
                "active_promotions_count": len(promotions),
                "promotions": promotions,
                "sample_products": sample_prods,
            })

        # Apply sorting
        if sort == "stores":
            results.sort(key=lambda x: x["stores_count"], reverse=True)
        elif sort == "products":
            results.sort(key=lambda x: x["total_products"], reverse=True)
        elif sort == "offers":
            results.sort(key=lambda x: x["active_promotions_count"], reverse=True)
        else:  # alphabetical
            results.sort(key=lambda x: x["brand"].brand_name.lower())

        return results

    def get_customer_brand_detail(
        self,
        slug_or_id: str,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fetch complete brand profile, branches with coordinates/distance, promotions, and sample items."""
        brand = None
        if slug_or_id.isdigit():
            brand = self.db.query(BrandProfile).filter(BrandProfile.id == int(slug_or_id)).first()
        if not brand:
            brand = self.db.query(BrandProfile).filter(BrandProfile.slug == slug_or_id).first()
        if not brand:
            return None
        if not brand.is_verified:
            return None

        # Fetch all stores for this brand
        stores = (
            self.db.query(StoreLocation)
            .filter(StoreLocation.brand_id == brand.id)
            .all()
        )

        stores_summary = []
        for s in stores:
            # Count in-stock SKUs at this branch
            in_stock_count = (
                self.db.query(StoreInventory)
                .filter(
                    StoreInventory.store_id == s.id,
                    (StoreInventory.quantity - StoreInventory.reserved_quantity) > 0,
                )
                .count()
            )

            # Distance calculation if coordinates provided
            dist = None
            if lat is not None and lng is not None:
                dist = haversine_distance_km(lat, lng, s.latitude, s.longitude)

            gmaps_url = build_google_maps_url(s.address, s.latitude, s.longitude)

            stores_summary.append({
                "store": s,
                "distance_km": dist,
                "google_maps_url": gmaps_url,
                "in_stock_skus_count": in_stock_count,
            })

        if lat is not None and lng is not None:
            stores_summary.sort(key=lambda x: (x["distance_km"] if x["distance_km"] is not None else 99999))

        # Brand products
        brand_products = (
            self.db.query(Product)
            .options(joinedload(Product.category), joinedload(Product.brand))
            .filter(Product.brand_id == brand.id, Product.is_active == True)
            .all()
        )
        categories = sorted(list({p.category.name for p in brand_products if p.category}))
        cities = sorted(list({s.city for s in stores if s.city}))

        # Active promotions
        promos = self._get_active_promotions_for_brand(brand.id)

        return {
            "brand": brand,
            "total_products": len(brand_products),
            "stores_count": len(stores),
            "cities": cities,
            "categories": categories,
            "active_promotions_count": len(promos),
            "promotions": promos,
            "sample_products": brand_products[:6],
            "stores": stores_summary,
        }

    def get_customer_stores(
        self,
        brand_id: Optional[int] = None,
        city: Optional[str] = None,
        q: Optional[str] = None,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve physical stores with brand details, promotions, and proximity sorting."""
        query = (
            self.db.query(StoreLocation)
            .options(joinedload(StoreLocation.brand))
        )

        if brand_id:
            query = query.filter(StoreLocation.brand_id == brand_id)
        if city and city.strip():
            query = query.filter(StoreLocation.city.ilike(f"%{city.strip()}%"))
        if q and q.strip():
            token = f"%{q.strip()}%"
            query = query.filter(
                or_(
                    StoreLocation.name.ilike(token),
                    StoreLocation.address.ilike(token),
                    StoreLocation.city.ilike(token),
                )
            )

        stores = query.all()
        results = []

        for s in stores:
            in_stock_count = (
                self.db.query(StoreInventory)
                .filter(
                    StoreInventory.store_id == s.id,
                    (StoreInventory.quantity - StoreInventory.reserved_quantity) > 0,
                )
                .count()
            )
            dist = None
            if lat is not None and lng is not None:
                dist = haversine_distance_km(lat, lng, s.latitude, s.longitude)

            gmaps_url = build_google_maps_url(s.address, s.latitude, s.longitude)
            promos = self._get_active_promotions_for_brand(s.brand_id)

            results.append({
                "store": s,
                "distance_km": dist,
                "google_maps_url": gmaps_url,
                "in_stock_skus_count": in_stock_count,
                "active_promotions": promos,
            })

        if lat is not None and lng is not None:
            results.sort(key=lambda x: (x["distance_km"] if x["distance_km"] is not None else 99999))
        else:
            results.sort(key=lambda x: (x["store"].city, x["store"].name))

        return results

    def get_customer_store_detail(
        self,
        store_id: int,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve specific store branch profile."""
        store = (
            self.db.query(StoreLocation)
            .options(joinedload(StoreLocation.brand))
            .filter(StoreLocation.id == store_id)
            .first()
        )
        if not store:
            return None

        in_stock_count = (
            self.db.query(StoreInventory)
            .filter(
                StoreInventory.store_id == store.id,
                (StoreInventory.quantity - StoreInventory.reserved_quantity) > 0,
            )
            .count()
        )
        dist = None
        if lat is not None and lng is not None:
            dist = haversine_distance_km(lat, lng, store.latitude, store.longitude)

        gmaps_url = build_google_maps_url(store.address, store.latitude, store.longitude)
        promos = self._get_active_promotions_for_brand(store.brand_id)

        return {
            "store": store,
            "distance_km": dist,
            "google_maps_url": gmaps_url,
            "in_stock_skus_count": in_stock_count,
            "active_promotions": promos,
        }

    def get_branch_inventory_catalog(
        self,
        store_id: int,
        category: Optional[str] = None,
        in_stock_only: bool = False,
        search: Optional[str] = None,
        sort_by: str = "newest",
    ) -> Optional[Dict[str, Any]]:
        """Fetch clothing items and available stock at this branch."""
        store = (
            self.db.query(StoreLocation)
            .options(joinedload(StoreLocation.brand))
            .filter(StoreLocation.id == store_id)
            .first()
        )
        if not store:
            return None

        # Fetch StoreInventory records joined with ProductSKU and Product
        inv_query = (
            self.db.query(StoreInventory, ProductSKU, Product)
            .join(ProductSKU, StoreInventory.sku_id == ProductSKU.id)
            .join(Product, ProductSKU.product_id == Product.id)
            .options(joinedload(Product.category), joinedload(Product.brand))
            .filter(StoreInventory.store_id == store_id, Product.is_active == True)
        )

        rows = inv_query.all()

        # Group SKUs by Product
        products_map: Dict[int, Dict[str, Any]] = {}
        all_categories = set()
        all_sizes = set()

        for inv, sku, prod in rows:
            if prod.category:
                all_categories.add(prod.category.name)
            all_sizes.add(sku.size)

            avail_qty = max(0, inv.quantity - inv.reserved_quantity)
            if avail_qty == 0:
                avail_status = "out_of_stock"
            elif avail_qty <= 3:
                avail_status = "low_stock"
            else:
                avail_status = "in_stock"

            sku_info = {
                "sku_id": sku.id,
                "sku_code": sku.sku_code,
                "size": sku.size,
                "color": sku.color,
                "color_hex": sku.color_hex or "#212529",
                "quantity_available": avail_qty,
                "reserved_quantity": inv.reserved_quantity,
                "is_in_stock": avail_qty > 0,
                "availability_status": avail_status,
            }

            if prod.id not in products_map:
                products_map[prod.id] = {
                    "product": prod,
                    "skus": [],
                    "total_available": 0,
                }
            products_map[prod.id]["skus"].append(sku_info)
            products_map[prod.id]["total_available"] += avail_qty

        # Build list of BranchProductItemOut
        product_items = []
        for prod_id, data in products_map.items():
            prod = data["product"]
            total_avail = data["total_available"]

            # Filter in_stock_only
            if in_stock_only and total_avail <= 0:
                continue

            # Filter by category
            if category and category.strip():
                req_cat = category.strip().lower()
                cat_match = (
                    (prod.category and req_cat in prod.category.name.lower())
                    or (prod.category and req_cat == prod.category.slug.lower())
                )
                if not cat_match:
                    continue

            # Filter by search term
            if search and search.strip():
                req_search = search.strip().lower()
                text_match = (
                    req_search in prod.title.lower()
                    or req_search in prod.description.lower()
                    or (prod.category and req_search in prod.category.name.lower())
                )
                if not text_match:
                    continue

            if total_avail == 0:
                p_status = "out_of_stock"
            elif total_avail <= 3:
                p_status = "low_stock"
            else:
                p_status = "in_stock"

            discount_pct = None
            if prod.compare_at_price and prod.compare_at_price > prod.base_price:
                discount_pct = int(round(((float(prod.compare_at_price) - float(prod.base_price)) / float(prod.compare_at_price)) * 100))

            product_items.append({
                "product": prod,
                "branch_id": store.id,
                "branch_name": store.name,
                "branch_total_units": total_avail,
                "branch_in_stock": total_avail > 0,
                "branch_availability_status": p_status,
                "branch_skus": sorted(data["skus"], key=lambda s: s["size"]),
                "discount_percent": discount_pct,
            })

        # Sort product items
        if sort_by == "price_asc":
            product_items.sort(key=lambda x: x["product"].base_price)
        elif sort_by == "price_desc":
            product_items.sort(key=lambda x: x["product"].base_price, reverse=True)
        elif sort_by == "stock":
            product_items.sort(key=lambda x: x["branch_total_units"], reverse=True)
        else:  # newest
            product_items.sort(key=lambda x: x["product"].created_at, reverse=True)

        promos = self._get_active_promotions_for_brand(store.brand_id)
        gmaps_url = build_google_maps_url(store.address, store.latitude, store.longitude)

        return {
            "store": {
                "store": store,
                "distance_km": None,
                "google_maps_url": gmaps_url,
                "in_stock_skus_count": sum(1 for p in product_items if p["branch_in_stock"]),
                "active_promotions": promos,
            },
            "brand": store.brand,
            "total_items": len(product_items),
            "products": product_items,
            "categories": sorted(list(all_categories)),
            "available_sizes": sorted(list(all_sizes)),
            "active_promotions": promos,
        }

