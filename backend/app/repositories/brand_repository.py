from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta
from backend.app.core.money import to_decimal, money_add, money_sub, money_sum, to_float, quantize_money, validate_money
from backend.app.core.revenue_policy import (
    NON_REVENUE_ORDER_STATUSES,
    REVENUE_BASIS,
    revenue_eligible,
    return_denominator_eligible,
)
from backend.app.core.timeutils import TimeRange, to_naive_utc
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_, or_, desc, case, select, literal
import json
import hashlib

from backend.app.models.user import BrandProfile, User
from backend.app.models.catalog import Product, ProductSKU, StoreLocation, StoreInventory, RecentlyViewed, Category
from backend.app.models.brand_analytics import SponsoredPlacement, StyleHeatmapAggregate
from backend.app.models.catalog_import import CatalogImportJob, BrandAnalyticsEvent
from backend.app.models.commerce import Order, OrderItem, CartItem, Cart, ReturnRequest, ReturnItem, InventoryReservation, FulfillmentGroup
from backend.app.models.stylist import Outfit, OutfitItem
from backend.app.models.tryon import TryOnSession
from backend.app.models.profile import UserStyleProfile


class BrandRepository:
    # Money limits for brand-side inputs (domain constants, single source).
    MAX_BID_PER_CLICK = Decimal("100.00")
    MAX_DAILY_BUDGET = Decimal("10000.00")
    MAX_SKU_PRICE = Decimal("100000.00")

    def __init__(self, db: Session):
        self.db = db

    # --- Basic CRUD ---
    def get_by_user_id(self, user_id: int) -> Optional[BrandProfile]:
        return self.db.query(BrandProfile).filter(BrandProfile.user_id == user_id).first()

    def get_by_id(self, brand_id: int) -> Optional[BrandProfile]:
        # Session.get() consults the identity map BEFORE emitting SQL, while
        # query(...).filter(...).first() always goes to the database. Within one
        # request the brand profile has usually already been loaded while
        # resolving the caller's tenant, so this is typically a free lookup
        # instead of a ~150ms round trip to the managed database.
        return self.db.get(BrandProfile, brand_id)

    def get_all_brands(self) -> List[BrandProfile]:
        return self.db.query(BrandProfile).all()

    def get_brand_products(self, brand_id: int) -> List[Product]:
        return (
            self.db.query(Product)
            .options(joinedload(Product.skus), joinedload(Product.category), joinedload(Product.brand))
            .filter(Product.brand_id == brand_id)
            .all()
        )

    def get_brand_placements(self, brand_id: int) -> List[SponsoredPlacement]:
        return (
            self.db.query(SponsoredPlacement)
            .options(joinedload(SponsoredPlacement.product))
            .filter(SponsoredPlacement.brand_id == brand_id)
            .order_by(desc(SponsoredPlacement.created_at))
            .all()
        )

    def create_placement(
        self,
        brand_id: int,
        product_id: int,
        placement_type: str,
        bid_amount: float,
        daily_budget: float,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> SponsoredPlacement:
        # Validate bid and budget through the canonical money validator:
        # NaN/Infinity/garbage/out-of-range/sub-cent -> MoneyValueError /
        # MoneyRangeError (both ValueError) BEFORE any ORM assignment.
        bid_dec = validate_money(bid_amount, "bid_amount_per_click", allow_zero=False,
                                 required=True, exact_scale=True)
        budget_dec = validate_money(daily_budget, "daily_budget", allow_zero=False,
                                    required=True, exact_scale=True)
        if bid_dec > budget_dec:
            raise ValueError("Bid amount cannot exceed daily budget")
        if budget_dec > self.MAX_DAILY_BUDGET:
            raise ValueError(f"Daily budget exceeds maximum allowed ({self.MAX_DAILY_BUDGET})")
        if bid_dec > self.MAX_BID_PER_CLICK:
            raise ValueError(f"Bid amount exceeds maximum allowed ({self.MAX_BID_PER_CLICK})")

        from backend.app.services.placement_policy import validate_placement
        normalized = validate_placement(dict(bid_amount_per_click=bid_dec, daily_budget=budget_dec,
            placement_type=placement_type, start_date=start_date, end_date=end_date))
        start_date, end_date = normalized["start_date"], normalized["end_date"]

        placement = SponsoredPlacement(
            brand_id=brand_id,
            product_id=product_id,
            placement_type=placement_type,
            bid_amount_per_click=bid_dec,
            daily_budget=budget_dec,
            spent_today=Decimal("0.00"),
            status="active",
            impressions=0,
            clicks=0,
            conversions=0,
            revenue_generated=Decimal("0.00"),
            start_date=start_date,
            end_date=end_date
        )
        self.db.add(placement)
        self.db.commit()
        self.db.refresh(placement)
        return placement

    def update_sku_stock(self, sku_id: int, new_stock: int, price_override: Optional[float] = None) -> Optional[ProductSKU]:
        # Use SELECT FOR UPDATE to prevent lost updates
        sku = self.db.query(ProductSKU).filter(ProductSKU.id == sku_id).populate_existing().with_for_update().first()
        if not sku:
            return None

        if new_stock < 0:
            raise ValueError("Stock level cannot be negative")
        if new_stock > 100000:
            raise ValueError("Stock level exceeds maximum allowed")

        if price_override is not None:
            # Canonical domain validation (finite, 2dp, > 0, within NUMERIC(12,2)).
            # A price override of 0 would silently make the SKU free -> reject.
            price_dec = validate_money(price_override, "price_override", allow_zero=False,
                                       required=True, exact_scale=True)
            if price_dec > self.MAX_SKU_PRICE:
                raise ValueError(f"Price exceeds maximum allowed ({self.MAX_SKU_PRICE})")
            sku.price_override = price_dec

        sku.stock_level = int(new_stock)
        sku.is_in_stock = new_stock > 0
        self.db.commit()
        self.db.refresh(sku)
        return sku

    def update_store_inventory(self, store_id: int, sku_id: int, quantity: int, brand_id: int) -> StoreInventory:
        # Verify store belongs to brand - tenant isolation
        store = self.db.query(StoreLocation).filter(
            StoreLocation.id == store_id,
            StoreLocation.brand_id == brand_id
        ).with_for_update().first()
        if not store:
            raise ValueError(f"Store {store_id} does not belong to brand {brand_id}")

        # Verify SKU belongs to brand via product - tenant isolation
        sku = self.db.query(ProductSKU).join(Product, Product.id == ProductSKU.product_id).filter(
            ProductSKU.id == sku_id,
            Product.brand_id == brand_id
        ).first()
        if not sku:
            raise ValueError(f"SKU {sku_id} does not belong to brand {brand_id}")

        if quantity < 0:
            raise ValueError("Quantity cannot be negative")
        if quantity > 100000:
            raise ValueError("Quantity exceeds maximum")

        # Upsert with locking - concurrency-safe with SELECT FOR UPDATE.
        # Scoped by brand_id as well as the natural key: an existing row that
        # somehow belongs to another tenant must NOT be silently adopted by
        # this write (that is how the leaked rows became invisible).
        inv = self.db.query(StoreInventory).filter(
            StoreInventory.store_id == store_id,
            StoreInventory.sku_id == sku_id
        ).populate_existing().with_for_update().first()

        if inv:
            if inv.brand_id is not None and inv.brand_id != brand_id:
                raise ValueError(
                    f"Inventory row {inv.id} belongs to brand {inv.brand_id}, not {brand_id}"
                )
            # Invariant: reserved <= quantity, quantity >=0, reserved >=0
            if inv.reserved_quantity > quantity:
                raise ValueError(f"Cannot set quantity {quantity} below reserved {inv.reserved_quantity}")
            inv.quantity = int(quantity)
            inv.brand_id = brand_id  # heal legacy NULLs on write
            # Ensure invariants hold
            assert inv.quantity >= 0, "Invariant violation: quantity >=0"
            assert inv.reserved_quantity >= 0, "Invariant violation: reserved >=0"
            assert inv.reserved_quantity <= inv.quantity, "Invariant violation: reserved <= quantity"
        else:
            inv = StoreInventory(
                store_id=store_id,
                sku_id=sku_id,
                brand_id=brand_id,
                quantity=int(quantity),
                reserved_quantity=0
            )
            self.db.add(inv)

        self.db.commit()
        self.db.refresh(inv)
        # Final invariant check
        assert inv.quantity >= 0 and inv.reserved_quantity >= 0 and inv.reserved_quantity <= inv.quantity
        return inv

    def get_brand_stores(self, brand_id: int) -> List[StoreLocation]:
        """Canonical store list for a tenant. The ONLY query allowed to answer
        "which stores does this brand have" — the inventory breakdown below is
        derived from the same predicate so the two can never disagree."""
        return (
            self.db.query(StoreLocation)
            .filter(StoreLocation.brand_id == brand_id)
            .order_by(StoreLocation.id)
            .all()
        )

    def get_brand_store_inventory_map(self, brand_id: int) -> Dict[int, List["StoreInventoryRow"]]:
        """{sku_id: [rows]} of store inventory for ONE tenant, fully scoped.

        P1 root cause (production-confirmed): callers previously filtered
        StoreInventory by `sku_id IN (brand's skus)` only. StoreInventory is a
        join table between two independently-owned entities (a store and a
        SKU), so that predicate constrains ONE side of the join. Legacy rows
        where store.brand_id != product.brand_id therefore surfaced another
        tenant's store id and quantities — while `get_brand_stores` (correctly
        scoped) returned 0. Hence "Store Locations (0)" next to "Store #1".

        Both sides are now pinned to the SAME brand_id in a single SQL join,
        which is also what the 0019 composite-FK migration enforces at the
        database level. Application scoping and schema constraint agree; this
        method is the single source of truth for the breakdown (DRY).
        """
        rows = (
            self.db.query(
                StoreInventory.id,
                StoreInventory.sku_id,
                StoreInventory.store_id,
                StoreInventory.quantity,
                StoreInventory.reserved_quantity,
                StoreLocation.name.label("store_name"),
            )
            .join(StoreLocation, StoreLocation.id == StoreInventory.store_id)
            .join(ProductSKU, ProductSKU.id == StoreInventory.sku_id)
            .join(Product, Product.id == ProductSKU.product_id)
            .filter(
                StoreLocation.brand_id == brand_id,   # store side owned by tenant
                Product.brand_id == brand_id,         # SKU side owned by tenant
            )
            .order_by(StoreInventory.sku_id, StoreInventory.store_id)
            .all()
        )
        inv_map: Dict[int, List[Any]] = {}
        for row in rows:
            inv_map.setdefault(row.sku_id, []).append(row)
        return inv_map

    def find_cross_tenant_inventory(self, brand_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Detective control: StoreInventory rows whose store and SKU belong to
        different brands. Must always return [] — used by the integrity test and
        by scripts/audit_brand_tenant_integrity.py so a regression is caught by
        evidence rather than by a customer."""
        q = (
            self.db.query(
                StoreInventory.id,
                StoreInventory.store_id,
                StoreInventory.sku_id,
                StoreLocation.brand_id.label("store_brand_id"),
                Product.brand_id.label("product_brand_id"),
                StoreInventory.quantity,
            )
            .join(StoreLocation, StoreLocation.id == StoreInventory.store_id)
            .join(ProductSKU, ProductSKU.id == StoreInventory.sku_id)
            .join(Product, Product.id == ProductSKU.product_id)
            .filter(StoreLocation.brand_id != Product.brand_id)
        )
        if brand_id is not None:
            q = q.filter(or_(StoreLocation.brand_id == brand_id, Product.brand_id == brand_id))
        return [
            {"inventory_id": r.id, "store_id": r.store_id, "sku_id": r.sku_id,
             "store_brand_id": r.store_brand_id, "product_brand_id": r.product_brand_id,
             "quantity": r.quantity}
            for r in q.order_by(StoreInventory.id).all()
        ]

    def create_store(self, brand_id: int, data: Dict[str, Any]) -> StoreLocation:
        # Validate required fields
        required = ["name", "city", "country", "address"]
        for field in required:
            if not data.get(field):
                raise ValueError(f"Missing required field: {field}")

        # Validate lat/lng ranges
        try:
            lat = float(data.get("latitude", 0.0) or 0.0)
            lng = float(data.get("longitude", 0.0) or 0.0)
        except (ValueError, TypeError):
            raise ValueError("Invalid latitude/longitude format")
        if not (-90 <= lat <= 90):
            raise ValueError("Latitude must be between -90 and 90")
        if not (-180 <= lng <= 180):
            raise ValueError("Longitude must be between -180 and 180")

        name_val = data.get("name") or ""
        name_ar_val = data.get("name_ar") or name_val
        store = StoreLocation(
            brand_id=brand_id,
            name=name_val[:255],
            name_ar=name_ar_val[:255],
            address=(data.get("address") or "")[:500],
            city=(data.get("city") or "")[:100],
            country=(data.get("country") or "UAE")[:100],
            latitude=lat,
            longitude=lng,
            phone=(data.get("phone") or "")[:50] if data.get("phone") else None,
            pickup_instructions=data.get("pickup_instructions"),
            is_bopis_enabled=bool(data.get("is_bopis_enabled", True))
        )
        self.db.add(store)
        self.db.commit()
        self.db.refresh(store)
        return store

    def update_store(self, store_id: int, brand_id: int, data: Dict[str, Any]) -> StoreLocation:
        store = self.db.query(StoreLocation).filter(
            StoreLocation.id == store_id,
            StoreLocation.brand_id == brand_id
        ).with_for_update().first()
        if not store:
            raise ValueError(f"Store {store_id} not found for brand {brand_id}")

        # Only allow updating specific fields with validation
        allowed = ["name", "name_ar", "address", "city", "country", "latitude", "longitude", "phone", "pickup_instructions", "is_bopis_enabled"]
        for key in allowed:
            if key in data:
                if key == "latitude":
                    try:
                        lat = float(data[key])
                    except (ValueError, TypeError):
                        raise ValueError("Invalid latitude format")
                    if not (-90 <= lat <= 90):
                        raise ValueError("Latitude must be between -90 and 90")
                    setattr(store, key, lat)
                elif key == "longitude":
                    try:
                        lng = float(data[key])
                    except (ValueError, TypeError):
                        raise ValueError("Invalid longitude format")
                    if not (-180 <= lng <= 180):
                        raise ValueError("Longitude must be between -180 and 180")
                    setattr(store, key, lng)
                elif key == "is_bopis_enabled":
                    setattr(store, key, bool(data[key]))
                else:
                    setattr(store, key, str(data[key])[:500] if isinstance(data[key], str) else data[key])

        self.db.commit()
        self.db.refresh(store)
        return store

    # --- Real Analytics ---

    ACTIVITY_METHODOLOGY = (
        "All-time retained RecentlyViewed product-view rows, TryOnSession records (not necessarily completed), current CartItem lines, and non-cancelled/non-refunded/non-failed OrderItem purchase lines. Not a session-linked conversion funnel: these are independent per-table counts, so ratios mix measurement units and may exceed 100%. A null rate means the denominator is zero (not measurable), never 0%. Ad spend is reconciled against the append-only ad_ledger_entries journal (see /partner/billing/statement), not read from mutable counters."
    )

    ATTRIBUTED_FUNNEL_METHODOLOGY = (
        "Session-linked funnel at SESSION grain, not event counts. A session enters "
        "the denominator only if it produced a view event for one of this brand's "
        "products carrying a session_token; each later stage counts how many of "
        "THOSE SAME sessions also reached that stage, so the sequence is monotonically "
        "non-increasing by construction and a rate can never exceed 100%. Try-on is "
        "joined via tryon_sessions.guest_session_token and constrained to products "
        "owned by this brand; cart via carts.session_token; purchase via a purchase "
        "event on the same token. Anonymous activity with no session_token is NOT "
        "attributable and is excluded from every stage -- attributable_view_coverage "
        "reports what fraction of view events could be used, so a low-coverage funnel "
        "is never mistaken for a complete one. Rates are None (N/A) when the "
        "denominator is zero. This is observational co-occurrence within a session, "
        "not a causal claim."
    )

    def get_attributed_funnel(self, brand_id: int) -> Dict[str, Any]:
        """A real session-linked funnel, or an explicit statement that there isn't one.

        WHY THIS IS SEPARATE FROM get_activity_snapshot()
        The activity snapshot counts four unrelated tables independently. Dividing
        one by another mixes measurement units, which is how a dashboard ends up
        printing 3500%: 35 try-on rows over 0 retained view rows is not a rate, it
        is two different things in a fraction. That snapshot is still useful as a
        volume indicator, so it stays -- but it is NOT a funnel and must not be
        presented as one.

        This method only ever counts SESSIONS, and every stage is a subset of the
        stage before it. Because each stage filters the same starting set of view
        sessions, the counts cannot increase down the funnel and a ratio cannot
        exceed 100%. That property is structural, not something we validate after
        the fact.

        HONESTY ABOUT COVERAGE
        Only events carrying a session_token can be attributed. In production that
        is 66% of view events for one brand and 19.5% for another, so a funnel
        presented without that number would look authoritative while silently
        describing a fifth of the traffic. attributable_view_coverage is returned
        alongside the funnel and is intended to be displayed with it.
        """
        # Stage 0: the attributable denominator -- sessions that viewed a product
        # belonging to THIS brand. brand_id is applied on the event itself, so a
        # session that only ever viewed another tenant's products never enters.
        view_sessions = select(BrandAnalyticsEvent.session_token).where(
            BrandAnalyticsEvent.brand_id == brand_id,
            BrandAnalyticsEvent.event_type == "view",
            BrandAnalyticsEvent.session_token.isnot(None),
        ).distinct().subquery()
        vs = select(view_sessions.c.session_token).scalar_subquery()

        # Try-on is tenant-scoped through the product, because tryon_sessions has
        # no brand column -- without that join a session that tried on another
        # brand's garment would be credited to this one.
        brand_tryon_tokens = select(TryOnSession.guest_session_token).join(
            Product, Product.id == TryOnSession.product_id
        ).where(
            Product.brand_id == brand_id,
            TryOnSession.guest_session_token.isnot(None),
        ).distinct().scalar_subquery()

        cart_tokens = select(Cart.session_token).where(
            Cart.session_token.isnot(None)
        ).distinct().scalar_subquery()

        purchase_tokens = select(BrandAnalyticsEvent.session_token).where(
            BrandAnalyticsEvent.brand_id == brand_id,
            BrandAnalyticsEvent.event_type == "purchase",
            BrandAnalyticsEvent.session_token.isnot(None),
        ).distinct().scalar_subquery()

        row = self.db.execute(
            select(
                select(func.count()).select_from(view_sessions)
                .scalar_subquery().label("viewed"),

                select(func.count()).select_from(view_sessions)
                .where(view_sessions.c.session_token.in_(brand_tryon_tokens))
                .scalar_subquery().label("tried_on"),

                select(func.count()).select_from(view_sessions)
                .where(view_sessions.c.session_token.in_(cart_tokens))
                .scalar_subquery().label("added_to_cart"),

                select(func.count()).select_from(view_sessions)
                .where(view_sessions.c.session_token.in_(purchase_tokens))
                .scalar_subquery().label("purchased"),

                select(func.count(BrandAnalyticsEvent.id)).where(
                    BrandAnalyticsEvent.brand_id == brand_id,
                    BrandAnalyticsEvent.event_type == "view",
                ).scalar_subquery().label("view_events_total"),

                select(func.count(BrandAnalyticsEvent.id)).where(
                    BrandAnalyticsEvent.brand_id == brand_id,
                    BrandAnalyticsEvent.event_type == "view",
                    BrandAnalyticsEvent.session_token.isnot(None),
                ).scalar_subquery().label("view_events_attributable"),
            )
        ).one()

        viewed = int(row.viewed or 0)

        def rate(numerator: int) -> Optional[float]:
            # Zero sessions means the rate is undefined, not zero. Returning 0.0
            # would assert "nobody converted", which is a different and unproven
            # claim from "there is nothing to divide by".
            if viewed <= 0:
                return None
            return round(numerator / viewed * 100, 2)

        tried_on = int(row.tried_on or 0)
        added = int(row.added_to_cart or 0)
        purchased = int(row.purchased or 0)
        total_views = int(row.view_events_total or 0)
        attributable = int(row.view_events_attributable or 0)

        return {
            "grain": "session",
            "available": viewed > 0,
            "stages": [
                {"stage": "viewed", "sessions": viewed, "rate_of_viewed": rate(viewed)},
                {"stage": "tried_on", "sessions": tried_on, "rate_of_viewed": rate(tried_on)},
                {"stage": "added_to_cart", "sessions": added, "rate_of_viewed": rate(added)},
                {"stage": "purchased", "sessions": purchased, "rate_of_viewed": rate(purchased)},
            ],
            "view_sessions": viewed,
            "tryon_sessions": tried_on,
            "cart_sessions": added,
            "purchase_sessions": purchased,
            "try_on_rate": rate(tried_on),
            "add_to_cart_rate": rate(added),
            "purchase_rate": rate(purchased),
            # Displayed WITH the funnel: a funnel built on 19.5% of traffic must
            # not look as authoritative as one built on 100%.
            "attributable_view_coverage": (
                round(attributable / total_views * 100, 2) if total_views else None
            ),
            "view_events_total": total_views,
            "view_events_attributable": attributable,
            "methodology": self.ATTRIBUTED_FUNNEL_METHODOLOGY,
        }

    def get_activity_snapshot(self, brand_id: int,
                              product_ids: Optional[List[int]] = None) -> Dict[str, Any]:
        """The four headline activity counters plus the funnel ratio, in ONE round trip.

        Extracted so /partner/analytics/conversion can stop building the entire
        dashboard just to read six of its fields. That endpoint needed views,
        try-ons, add-to-carts, purchases, the ratio and the methodology string,
        and was paying for outfit rankings, return cohorts, BOPIS fulfilment and
        ad totals to get them -- five extra round trips, ~750ms of pure network
        latency, all of it discarded.

        This is the ONLY place those four counters are defined, so the dashboard
        and the conversion endpoint cannot drift apart (DRY): they are now two
        callers of one query, not two queries that happen to agree today.

        Passing product_ids lets a caller that has already loaded the catalog
        avoid re-fetching it; omitting it makes the method self-contained.
        """
        if product_ids is None:
            product_ids = [pid for (pid,) in self.db.query(Product.id)
                           .filter(Product.brand_id == brand_id).all()]

        if product_ids:
            headline = self.db.execute(
                select(
                    select(func.count(RecentlyViewed.id))
                    .where(RecentlyViewed.product_id.in_(product_ids))
                    .scalar_subquery().label("views"),

                    select(func.count(TryOnSession.id))
                    .where(TryOnSession.product_id.in_(product_ids))
                    .scalar_subquery().label("tryons"),

                    select(func.count(CartItem.id))
                    .join(ProductSKU, CartItem.product_sku_id == ProductSKU.id)
                    .where(ProductSKU.product_id.in_(product_ids))
                    .scalar_subquery().label("add_to_carts"),

                    select(func.count(OrderItem.id))
                    .join(Order, OrderItem.order_id == Order.id)
                    .where(OrderItem.brand_id == brand_id,
                           revenue_eligible(Order.status))
                    .scalar_subquery().label("purchases"),
                )
            ).one()
            total_views = headline.views or 0
            total_tryons = headline.tryons or 0
            total_add_to_carts = headline.add_to_carts or 0
            total_purchases = headline.purchases or 0
        else:
            # No products: every count is definitionally zero. Skip the trip.
            total_views = total_tryons = total_add_to_carts = total_purchases = 0

        # A zero denominator yields None ("not measurable"), never 0.0 and never
        # a substituted denominator of 1. Reporting 0% when there are no views
        # asserts "nobody converted", which is a different and unproven claim
        # from "there is nothing to divide by".
        funnel_rate = round(total_purchases / total_views * 100, 2) if total_views > 0 else None

        return {
            "total_views": int(total_views),
            "total_tryons": int(total_tryons),
            "total_add_to_carts": int(total_add_to_carts),
            "total_purchases": int(total_purchases),
            "funnel_conversion_rate": float(funnel_rate) if funnel_rate is not None else None,
            "methodology": self.ACTIVITY_METHODOLOGY,
        }

    def get_brand_analytics(self, brand_id: int) -> Dict[str, Any]:
        """
        Real analytics from transactional data:
        - Views from RecentlyViewed
        - Try-ons from TryOnSession
        - Add-to-cart from CartItem via ProductSKU -> Product -> brand
        - Purchases from OrderItem where brand_id = brand_id
        - Outfit appearances from OutfitItem -> Product -> brand
        - Returns from ReturnRequest via OrderItem
        """
        brand = self.get_by_id(brand_id)
        if not brand:
            return {}

        products = self.get_brand_products(brand_id)
        product_ids = [p.id for p in products]
        total_skus = sum(len(p.skus) for p in products)

        # Headline counters: FOUR independent aggregates over four unrelated
        # tables, issued as ONE round trip instead of four.
        #
        # WHY THIS SHAPE (measured, not guessed): against production these
        # aggregates scan 3-114 rows and each still costs ~150ms, while a bare
        # `SELECT 1` on the same connection also costs ~150ms. The cost is
        # therefore network round-trip latency to the managed database, not
        # query execution -- so an index would buy nothing and only reducing
        # the NUMBER of round trips helps. Scalar subqueries in one SELECT are
        # the correct tool: each subquery is exactly the query that ran before
        # (same predicates, same semantics), so the numbers are unchanged; only
        # the number of network hops drops from 4 to 1.
        snapshot = self.get_activity_snapshot(brand_id, product_ids)
        total_views = snapshot["total_views"]
        total_tryons = snapshot["total_tryons"]
        total_add_to_carts = snapshot["total_add_to_carts"]
        total_purchases = snapshot["total_purchases"]
        funnel_rate = snapshot["funnel_conversion_rate"]

        # 5. Outfit Performance: real ranking from OutfitItem
        # Count appearances of each product in outfits
        outfit_appearances = self.db.query(
            OutfitItem.product_id,
            func.count(OutfitItem.id).label("appearances")
        ).filter(
            OutfitItem.product_id.in_(product_ids)
        ).group_by(OutfitItem.product_id).order_by(desc("appearances")).limit(10).all()

        # N+1 ELIMINATED. This loop previously issued TWO queries per ranked
        # product (add-to-cart count, purchase count), so a brand with 10
        # ranked products paid 20 extra round trips -- ~3s of pure latency on
        # top of everything else. Both are now computed for ALL ranked products
        # in two grouped queries before the loop, and the loop reads dicts.
        ranked_ids = [pid for pid, _ in outfit_appearances]
        atc_by_product: Dict[int, int] = {}
        purch_by_product: Dict[int, int] = {}
        if ranked_ids:
            atc_by_product = {
                pid: n for pid, n in self.db.query(
                    ProductSKU.product_id, func.count(CartItem.id)
                ).join(CartItem, CartItem.product_sku_id == ProductSKU.id)
                .filter(ProductSKU.product_id.in_(ranked_ids))
                .group_by(ProductSKU.product_id).all()
            }
            purch_by_product = {
                pid: n for pid, n in self.db.query(
                    OrderItem.product_id, func.count(OrderItem.id)
                ).join(Order, Order.id == OrderItem.order_id)
                .filter(OrderItem.product_id.in_(ranked_ids),
                        OrderItem.brand_id == brand_id,
                        revenue_eligible(Order.status))
                .group_by(OrderItem.product_id).all()
            }

        # Build rankings with real data
        outfit_rankings = []
        for prod_id, appearances in outfit_appearances:
            prod = next((p for p in products if p.id == prod_id), None)
            if not prod:
                continue

            prod_add_to_cart = atc_by_product.get(prod_id, 0)
            prod_purchases = purch_by_product.get(prod_id, 0)

            # Rates based on appearances
            add_to_cart_rate = round((prod_add_to_cart / appearances * 100) if appearances > 0 else 0.0, 1)
            purchase_rate = round((prod_purchases / appearances * 100) if appearances > 0 else 0.0, 1)

            outfit_rankings.append({
                "product_id": prod.id,
                "product_title": prod.title,
                "thumbnail_url": prod.thumbnail_url,
                "outfit_appearances": int(appearances),
                "add_to_cart_rate": add_to_cart_rate,
                "purchase_rate": purchase_rate
            })

        # Item-grain cohorts cannot attribute another brand's return in a
        # mixed-brand order to this tenant. No benchmark fallback.
        #
        # get_brand_return_metrics() is deliberately NOT inlined here: it is
        # also the sole implementation behind GET /brand/returns
        # (brand_controller.py:195). Duplicating its cohort logic to save one
        # round trip would put the same return-rate definition in two places,
        # which is exactly how two screens start disagreeing about the same
        # number. One extra hop is the right trade for one definition (DRY).
        returns = self.get_brand_return_metrics(brand_id)
        pre_rate = returns["return_rate_before_vton"]
        post_rate = returns["return_rate_after_vton"]
        reduction = returns["return_reduction_percentage"]
        bopis = self.db.query(FulfillmentGroup.status, func.count(FulfillmentGroup.id)).filter(
            FulfillmentGroup.brand_id == brand_id, FulfillmentGroup.fulfillment_type == "bopis",
            FulfillmentGroup.status.notin_(["cancelled", "failed"])
        ).group_by(FulfillmentGroup.status).all()
        bopis_total = sum(n for _, n in bopis)
        bopis_done = sum(n for status, n in bopis if status in ("picked_up", "completed"))
        bopis_rate = round(bopis_done / bopis_total * 100, 1) if bopis_total else None

        # 8. Ad spend and revenue. Previously this loaded every SponsoredPlacement
        # ORM object just to sum two columns; now the database sums them and
        # returns two scalars in one row. Same totals, far less transferred.
        ad_totals = self.db.execute(
            select(
                func.coalesce(func.sum(SponsoredPlacement.spent_today), 0),
                func.coalesce(func.sum(SponsoredPlacement.revenue_generated), 0),
            ).where(SponsoredPlacement.brand_id == brand_id)
        ).one()
        ad_spend = quantize_money(to_decimal(ad_totals[0] or 0))
        ad_revenue = quantize_money(to_decimal(ad_totals[1] or 0))

        return {
            "brand_name": brand.brand_name,
            "total_products_count": len(products),
            "total_skus_count": total_skus,
            "total_views": int(total_views),
            "total_tryons": int(total_tryons),
            "total_add_to_carts": int(total_add_to_carts),
            "total_purchases": int(total_purchases),
            "funnel_conversion_rate": float(funnel_rate) if funnel_rate is not None else None,
            "return_rate_before_vton": pre_rate,
            "return_rate_after_vton": post_rate,
            "return_reduction_percentage": reduction,
            "outfit_appearance_rankings": outfit_rankings,
            "bopis_store_fulfillment_rate": bopis_rate,
            "return_cohorts": returns,
            "data_source": "transactional_snapshot",
            "methodology": self.ACTIVITY_METHODOLOGY,
            "ad_spend_total": to_float(ad_spend),
            "ad_revenue_total": to_float(ad_revenue)
        }

    def get_brand_return_metrics(self, brand_id):
        """Returned order-line snapshot, grouped by order-level try-on flag.

        is_returned currently marks an opened return, not proof of a completed
        refund. The API names are kept for compatibility; methodology says so.
        Fully refunded orders stay in the denominator to avoid survivorship bias.
        """
        counts = self.db.query(Order.try_on_assisted, func.count(OrderItem.id),
            func.sum(case((OrderItem.is_returned == True, 1), else_=0))
        ).join(Order, Order.id == OrderItem.order_id).filter(
            OrderItem.brand_id == brand_id, return_denominator_eligible(Order.status)
        ).group_by(Order.try_on_assisted).all()
        cohorts = {bool(assisted): (int(total), int(returned or 0)) for assisted, total, returned in counts}
        non_total, non_returns = cohorts.get(False, (0, 0))
        yes_total, yes_returns = cohorts.get(True, (0, 0))
        before = round(non_returns / non_total * 100, 2) if non_total else None
        after = round(yes_returns / yes_total * 100, 2) if yes_total else None
        reduction = round((before-after)/before*100, 1) if before and after is not None else None
        return dict(non_tryon_items=non_total, tryon_items=yes_total,
            non_tryon_returned_items=non_returns, tryon_returned_items=yes_returns,
            return_rate_before_vton=before, return_rate_after_vton=after,
            return_reduction_percentage=reduction,
            methodology="All-time brand order lines marked is_returned (opened, non-rejected return requests), divided by non-cancelled/non-failed order lines; cohorts use Order.try_on_assisted, not item-specific exposure. Includes refunded orders. Unmatched observational comparison: no causal, seasonality-adjusted or completed-refund claim. Null means insufficient denominator.")

    def get_conversion_analytics_per_sku(self, brand_id: int) -> List[Dict[str, Any]]:
        """Legacy name; product-grain snapshots, grouped in four bounded queries."""
        products = self.get_brand_products(brand_id)
        ids = [p.id for p in products]
        if not ids:
            return []
        # Four per-product aggregates over four unrelated tables, fetched in ONE
        # round trip via UNION ALL instead of four sequential queries. Against
        # the production database each round trip costs ~150ms regardless of how
        # little data it touches, so the hop count -- not the row count -- is
        # the latency. Each branch below is the exact query that ran before
        # (same joins, same predicates, same grouping), tagged with a metric
        # name; the tags are split back out in Python. Identical numbers, a
        # quarter of the network cost.
        metric_rows = self.db.execute(
            select(literal("views").label("metric"),
                   RecentlyViewed.product_id.label("pid"),
                   func.count(RecentlyViewed.id).label("n"))
            .where(RecentlyViewed.product_id.in_(ids))
            .group_by(RecentlyViewed.product_id)
            .union_all(
                select(literal("tryons"), TryOnSession.product_id,
                       func.count(TryOnSession.id))
                .where(TryOnSession.product_id.in_(ids))
                .group_by(TryOnSession.product_id),

                select(literal("carts"), ProductSKU.product_id,
                       func.count(CartItem.id))
                .select_from(ProductSKU)
                .join(CartItem, CartItem.product_sku_id == ProductSKU.id)
                .where(ProductSKU.product_id.in_(ids))
                .group_by(ProductSKU.product_id),

                select(literal("purchases"), OrderItem.product_id,
                       func.count(OrderItem.id))
                .select_from(OrderItem)
                .join(Order, Order.id == OrderItem.order_id)
                .where(OrderItem.brand_id == brand_id,
                       revenue_eligible(Order.status))
                .group_by(OrderItem.product_id),
            )
        ).all()

        views: Dict[int, int] = {}
        tryons: Dict[int, int] = {}
        carts: Dict[int, int] = {}
        purchases: Dict[int, int] = {}
        _buckets = {"views": views, "tryons": tryons,
                    "carts": carts, "purchases": purchases}
        for metric, pid, n in metric_rows:
            _buckets[metric][pid] = n
        result = [dict(product_id=p.id, sku_count=len(p.skus), title=p.title,
            views=views.get(p.id, 0), tryons=tryons.get(p.id, 0), add_to_cart=carts.get(p.id, 0),
            purchases=purchases.get(p.id, 0),
            # None (not 0.0) when a product has no views: undefined, not zero.
            conversion_rate=round(purchases.get(p.id, 0) / views[p.id] * 100, 2) if views.get(p.id) else None
        ) for p in products]
        # Unmeasurable products sort last instead of masquerading as 0% converters.
        return sorted(result, key=lambda x: (x["conversion_rate"] is None,
                                             -(x["conversion_rate"] or 0.0), x["product_id"]))

    def get_brand_preference_heatmaps(self, brand_id, region: Optional[str] = None, min_users: int = 10):
        """Tenant-scoped style signals for one brand's products.

        Counts DISTINCT authenticated users per cell rather than outfit rows, so
        one prolific shopper cannot manufacture a trend for the brand.

        Emits the SAME cell shape as the platform-wide heatmap
        (``{name, raw_name, share, count}`` under ``top_aesthetics`` /
        ``trending_colors`` / ``top_occasions``). It previously emitted
        ``weight`` and a differently-named ``top_colors`` key — the last
        remaining fork of the style-signal contract (G-04).

        ``region`` is accepted, applied to nothing, and reported as not applied:
        the schema carries no region attribute, so echoing the caller's region
        back as the label would mislabel platform-wide numbers (G-03).
        """
        rows = self.db.query(Outfit.user_id, Outfit.style_tags, Outfit.color_palette, Outfit.occasion).filter(
            Outfit.user_id.isnot(None), Outfit.id.in_(self.db.query(OutfitItem.outfit_id).join(
                Product, Product.id == OutfitItem.product_id).filter(Product.brand_id == brand_id))
        ).all()
        buckets: List[Dict[str, set]] = [dict(), dict(), dict()]
        users = set()
        for uid, styles, colors, occasion in rows:
            users.add(uid)
            for bucket, raw in zip(buckets, (styles, colors, json.dumps([occasion] if occasion else []))):
                for value in self._count_json_list(raw):
                    bucket.setdefault(value, set()).add(uid)

        sample_size = len(users)
        publishable = sample_size >= min_users

        def dimension(bucket: Dict[str, set]):
            if not publishable:
                return []
            counts = {label: len(ids) for label, ids in bucket.items()}
            cells, _suppressed = self._publish_cells(counts, sample_size, 5, min_users)
            return cells

        limitations = [
            "Scoped to outfits containing this brand's products; a shopper's "
            "preferences expressed on other brands are not counted here.",
            "Region and period filters are not supported: these source rows carry "
            "no region attribute and the aggregate is all-time.",
        ]
        if not publishable:
            limitations.insert(
                0,
                f"Only {sample_size} distinct shopper(s) in scope; at least "
                f"{min_users} are required before any cell is published, so "
                "nothing is shown rather than a small-population aggregate.",
            )

        return dict(
            region="Platform-wide",
            requested_region=region,
            region_scope="platform_wide",
            region_filter_applied=False,
            period=None,
            sample_size=sample_size if publishable else 0,
            min_sample_required=int(min_users),
            k_anonymity_floor=int(min_users),
            data_available=bool(publishable),
            privacy_threshold=(
                f"At least {min_users} distinct users per cell across {sample_size} "
                "shoppers; cells below the floor are suppressed and no "
                "individual-level data is exposed."
            ),
            top_aesthetics=dimension(buckets[0]),
            trending_colors=dimension(buckets[1]),
            top_occasions=dimension(buckets[2]),
            anonymized=True,
            methodology=(
                "Brand-product outfit preferences; DISTINCT authenticated users per "
                "cell, no catalogue fallback. Shares are a percentage of the "
                "shoppers in scope. All-time only: region and monthly filters are "
                "not supported by these source rows."
            ),
            limitations=limitations,
        )

    def get_platform_admin_analytics(
        self, time_range: Optional["TimeRange"] = None
    ) -> Dict[str, Any]:
        """Platform analytics from transactional data, over a bounded window.

        G-14 — the brand comparison table used to issue five queries *per
        brand* and the most-styled list one query *per row*; a platform with
        60 brands and a 10-row ranking cost ~310 round trips. Both are now
        single grouped queries, so the cost no longer grows with the number of
        brands or ranked products.

        G-15 — ``time_range`` is pushed into the SQL predicate of every
        aggregate rather than filtered in Python afterwards, and the resolved
        window is echoed in the payload so a reader can tell which question
        each number answers. Bounds are inclusive on both ends, matching the
        boundary contract ``/admin/audit`` already publishes.

        Every figure below traces to a real table; there is no fallback that
        invents a value when the window is empty.
        """
        tr = time_range or TimeRange()
        in_order_window = tr.bound(Order.created_at)

        total_users = self.db.query(func.count(User.id)).filter(
            *tr.bound(User.created_at)
        ).scalar() or 0
        total_brands = self.db.query(func.count(BrandProfile.id)).filter(
            *tr.bound(BrandProfile.created_at)
        ).scalar() or 0
        total_orders = self.db.query(func.count(Order.id)).filter(*in_order_window).scalar() or 0

        # G-13: GMV and the attribution ledger below must filter the same
        # population, or the four channel figures cannot sum to this headline.
        total_gmv = self.db.query(func.sum(Order.total_amount)).filter(
            revenue_eligible(Order.status), *in_order_window
        ).scalar() or 0.0

        # Try-on adoption. This count doubles as the denominator of a return
        # rate below, so it keeps refunded orders: excluding them would lower
        # the return rate precisely when returns succeed.
        tryon_orders = self.db.query(func.count(Order.id)).filter(
            Order.try_on_assisted == True,
            return_denominator_eligible(Order.status),
            *in_order_window,
        ).scalar() or 0

        tryon_adoption_rate = round((tryon_orders / total_orders * 100) if total_orders > 0 else 0.0, 1)

        # Stylist conversion: saved outfits in the window, and those whose
        # items were actually purchased (OrderItem.outfit_id lineage).
        total_saved_outfits = self.db.query(func.count(Outfit.id)).filter(
            Outfit.is_saved == True, *tr.bound(Outfit.created_at)
        ).scalar() or 0

        outfits_with_purchase = self.db.query(func.count(func.distinct(OrderItem.outfit_id))).join(
            Order, Order.id == OrderItem.order_id
        ).filter(
            OrderItem.outfit_id.isnot(None), *in_order_window
        ).scalar() or 0

        stylist_conversion = round((outfits_with_purchase / total_saved_outfits * 100) if total_saved_outfits > 0 else 0.0, 1)

        # Return rates: try-on users vs non-try-on users.
        total_returns = self.db.query(func.count(ReturnRequest.id)).filter(
            *tr.bound(ReturnRequest.created_at)
        ).scalar() or 0
        platform_avg_return = round((total_returns / total_orders * 100) if total_orders > 0 else 0.0, 1)

        returns_tryon = self.db.query(func.count(ReturnRequest.id)).filter(
            ReturnRequest.try_on_used_for_item == True, *tr.bound(ReturnRequest.created_at)
        ).scalar() or 0

        returns_non_tryon = total_returns - returns_tryon
        tryon_return_rate = round((returns_tryon / tryon_orders * 100) if tryon_orders > 0 else 0.0, 1)
        non_tryon_orders = total_orders - tryon_orders
        non_tryon_return_rate = round((returns_non_tryon / non_tryon_orders * 100) if non_tryon_orders > 0 else 0.0, 1)

        # Revenue attribution: canonical item-grain ledger (order_item_id lineage).
        _ledger = self.compute_item_grain_attribution()
        stylist_rev_exclusive = _ledger["channels"]["virtual_stylist"]
        outfit_rev_exclusive = _ledger["channels"]["outfit_builder"]
        visual_rev_exclusive = _ledger["channels"]["visual_search"]
        organic_revenue = _ledger["channels"]["organic"]
        total_revenue = to_decimal(total_gmv)

        # --- G-14: most-styled ranking in ONE query -------------------------
        # Previously: one grouped query for the ids, then one `Product` SELECT
        # per ranked row (each of which lazily loaded `product.brand`).
        most_styled_rows = (
            self.db.query(
                Product.id,
                Product.title,
                Product.thumbnail_url,
                BrandProfile.brand_name,
                func.count(OutfitItem.id).label("appearances"),
            )
            .join(OutfitItem, OutfitItem.product_id == Product.id)
            .join(Outfit, Outfit.id == OutfitItem.outfit_id)
            .outerjoin(BrandProfile, BrandProfile.id == Product.brand_id)
            .filter(*tr.bound(Outfit.created_at))
            .group_by(Product.id, Product.title, Product.thumbnail_url, BrandProfile.brand_name)
            .order_by(desc("appearances"))
            .limit(10)
            .all()
        )
        most_styled_items = [
            {
                "product_id": prod_id,
                "title": title,
                "brand_name": brand_name or "Unknown",
                "thumbnail_url": thumbnail_url,
                "appearances": int(appearances),
            }
            for prod_id, title, thumbnail_url, brand_name, appearances in most_styled_rows
        ]

        # --- G-14: brand comparison table in FIVE grouped queries, not 5N ---
        brands = self.db.query(BrandProfile).all()
        brand_ids = [b.id for b in brands]
        orders_by_brand: Dict[int, int] = {}
        products_by_brand: Dict[int, int] = {}
        views_by_brand: Dict[int, int] = {}
        tryons_by_brand: Dict[int, int] = {}
        returns_by_brand: Dict[int, int] = {}
        if brand_ids:
            orders_by_brand = dict(
                self.db.query(OrderItem.brand_id, func.count(OrderItem.id))
                .join(Order, Order.id == OrderItem.order_id)
                .filter(
                    OrderItem.brand_id.in_(brand_ids),
                    revenue_eligible(Order.status),
                    *in_order_window,
                )
                .group_by(OrderItem.brand_id)
                .all()
            )
            products_by_brand = dict(
                self.db.query(Product.brand_id, func.count(Product.id))
                .filter(Product.brand_id.in_(brand_ids))
                .group_by(Product.brand_id)
                .all()
            )
            views_by_brand = dict(
                self.db.query(Product.brand_id, func.count(RecentlyViewed.id))
                .join(RecentlyViewed, RecentlyViewed.product_id == Product.id)
                .filter(Product.brand_id.in_(brand_ids), *tr.bound(RecentlyViewed.viewed_at))
                .group_by(Product.brand_id)
                .all()
            )
            tryons_by_brand = dict(
                self.db.query(Product.brand_id, func.count(TryOnSession.id))
                .join(TryOnSession, TryOnSession.product_id == Product.id)
                .filter(Product.brand_id.in_(brand_ids), *tr.bound(TryOnSession.created_at))
                .group_by(Product.brand_id)
                .all()
            )
            returns_by_brand = dict(
                self.db.query(OrderItem.brand_id, func.count(func.distinct(ReturnRequest.id)))
                .join(Order, ReturnRequest.order_id == Order.id)
                .join(OrderItem, OrderItem.order_id == Order.id)
                .filter(OrderItem.brand_id.in_(brand_ids), *tr.bound(ReturnRequest.created_at))
                .group_by(OrderItem.brand_id)
                .all()
            )

        brand_performance = []
        for brand in brands:
            brand_orders = int(orders_by_brand.get(brand.id, 0))
            brand_products = int(products_by_brand.get(brand.id, 0))
            brand_views = int(views_by_brand.get(brand.id, 0))
            brand_tryons = int(tryons_by_brand.get(brand.id, 0))
            brand_returns = int(returns_by_brand.get(brand.id, 0))

            conversion = round((brand_orders / brand_views * 100) if brand_views > 0 else 0.0, 2)
            tryon_rate = round((brand_tryons / brand_views * 100) if brand_views > 0 else 0.0, 1)
            brand_return_rate = round((brand_returns / brand_orders * 100) if brand_orders > 0 else 0.0, 1)

            brand_performance.append({
                "brand_id": brand.id,
                "brand": brand.brand_name,
                "products": brand_products,
                "views": brand_views,
                "tryons": brand_tryons,
                "orders": brand_orders,
                "conversion_rate": float(conversion),
                "tryon_rate": f"{tryon_rate}%",
                "return_rate": f"{brand_return_rate}%",
                "return_rate_value": float(brand_return_rate)
            })

        # Sort by orders descending
        brand_performance.sort(key=lambda x: x["orders"], reverse=True)

        # G-01/G-02/G-04: one honest heatmap builder, shared with
        # /admin/analytics/heatmaps and /partner/analytics/heatmaps.
        style_heatmap = self.get_style_heatmap(
            date_from=tr.date_from, date_to=tr.date_to
        )

        # Exclusive attribution to avoid double count - mathematically valid
        return {
            "total_users_count": int(total_users),
            "total_brands_count": int(total_brands),
            "total_gmv": to_float(total_gmv),
            "total_orders": int(total_orders),
            "tryon_adoption_rate": float(tryon_adoption_rate),
            "stylist_conversion_ratio": float(stylist_conversion),
            "platform_avg_return_rate": float(platform_avg_return),
            "return_rate_tryon_users": float(tryon_return_rate),
            "return_rate_non_tryon_users": float(non_tryon_return_rate),
            "revenue_attribution": {
                "ai_virtual_stylist": to_float(stylist_rev_exclusive),
                "outfit_builder": to_float(outfit_rev_exclusive),
                "visual_search": to_float(visual_rev_exclusive),
                "organic_discovery": to_float(organic_revenue)
            },
            "top_performing_brands": brand_performance[:10],
            "most_styled_items": most_styled_items,
            "outfit_to_purchase_ratio": float(stylist_conversion),
            "style_preference_heatmap": style_heatmap,
            "revenue_basis": REVENUE_BASIS,
            "revenue_excludes_statuses": sorted(NON_REVENUE_ORDER_STATUSES),
            "time_range": tr.describe(),
            "methodology": {
                "time_window": tr.describe(),
                "boundary_semantics": "inclusive on both ends, matching /admin/audit",
                "revenue": f"order-level, accrual basis; excludes {sorted(NON_REVENUE_ORDER_STATUSES)}",
                "return_rates": "denominator keeps refunded orders — a completed return is evidence, not noise",
                "attribution": "item-grain ledger keyed on BrandAnalyticsEvent.order_item_id",
                "brand_comparison": "single grouped aggregate per metric; no per-brand query loop",
            },
        }

    def get_most_styled_items(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Ranking of items by outfit appearances across all users.

        G-14: one query. This used to run the ranking query and then one
        ``Product`` SELECT per ranked row (each lazily loading ``product.brand``),
        so a 20-row ranking cost 21+ round trips and dropped rows whose product
        had since been deleted — the join makes that explicit instead.
        """
        rows = (
            self.db.query(
                Product.id,
                Product.title,
                Product.thumbnail_url,
                BrandProfile.brand_name,
                func.count(OutfitItem.id).label("appearances"),
                func.count(func.distinct(OutfitItem.outfit_id)).label("outfit_count"),
            )
            .join(OutfitItem, OutfitItem.product_id == Product.id)
            .outerjoin(BrandProfile, BrandProfile.id == Product.brand_id)
            .group_by(Product.id, Product.title, Product.thumbnail_url, BrandProfile.brand_name)
            .order_by(desc("appearances"))
            .limit(limit)
            .all()
        )
        return [
            {
                "product_id": prod_id,
                "title": title,
                "brand_name": brand_name or "Unknown",
                "thumbnail_url": thumbnail_url,
                "appearances": int(appearances),
                "outfit_count": int(outfit_count),
            }
            for prod_id, title, thumbnail_url, brand_name, appearances, outfit_count in rows
        ]

    def get_outfit_to_purchase_ratio(self) -> Dict[str, Any]:
        """% of saved outfits that result in purchase - measures stylist ROI"""
        total_saved = self.db.query(func.count(Outfit.id)).filter(Outfit.is_saved == True).scalar() or 0
        purchased = self.db.query(func.count(func.distinct(Outfit.id))).join(
            OutfitItem, Outfit.id == OutfitItem.outfit_id
        ).join(
            OrderItem, and_(OrderItem.product_id == OutfitItem.product_id, OrderItem.outfit_id == Outfit.id)
        ).filter(Outfit.is_saved == True).scalar() or 0

        # Alternative: outfits where at least one item purchased via outfit_id
        purchased_alt = self.db.query(func.count(func.distinct(OrderItem.outfit_id))).filter(
            OrderItem.outfit_id.isnot(None)
        ).scalar() or 0

        # Use max of both methods for accuracy
        purchased_count = max(purchased, purchased_alt)

        ratio = round((purchased_count / total_saved * 100) if total_saved > 0 else 0.0, 2)

        return {
            "total_saved_outfits": int(total_saved),
            "purchased_outfits": int(purchased_count),
            "outfit_to_purchase_ratio": float(ratio),
            "methodology": "Saved outfits where at least one item was purchased with outfit_id attribution"
        }

    def get_return_reduction_metrics(self) -> Dict[str, Any]:
        """Comparison of return rates: try-on users vs non-try-on users"""
        # Denominators of a return rate: refunded orders stay in, see
        # revenue_policy.RETURN_DENOMINATOR_EXCLUDED_STATUSES.
        total_orders = self.db.query(func.count(Order.id)).filter(
            return_denominator_eligible(Order.status)
        ).scalar() or 0

        tryon_orders = self.db.query(func.count(Order.id)).filter(
            Order.try_on_assisted == True,
            return_denominator_eligible(Order.status)
        ).scalar() or 0

        total_returns = self.db.query(func.count(ReturnRequest.id)).scalar() or 0
        tryon_returns = self.db.query(func.count(ReturnRequest.id)).filter(
            ReturnRequest.try_on_used_for_item == True
        ).scalar() or 0

        non_tryon_orders = total_orders - tryon_orders
        non_tryon_returns = total_returns - tryon_returns

        tryon_return_rate = round((tryon_returns / tryon_orders * 100) if tryon_orders > 0 else 0.0, 2)
        non_tryon_return_rate = round((non_tryon_returns / non_tryon_orders * 100) if non_tryon_orders > 0 else 0.0, 2)
        platform_avg = round((total_returns / total_orders * 100) if total_orders > 0 else 0.0, 2)

        reduction = round(((non_tryon_return_rate - tryon_return_rate) / non_tryon_return_rate * 100) if non_tryon_return_rate > 0 else 0.0, 1)

        return {
            "total_orders": int(total_orders),
            "tryon_orders": int(tryon_orders),
            "non_tryon_orders": int(non_tryon_orders),
            "total_returns": int(total_returns),
            "tryon_returns": int(tryon_returns),
            "non_tryon_returns": int(non_tryon_returns),
            "platform_avg_return_rate": float(platform_avg),
            "return_rate_tryon_users": float(tryon_return_rate),
            "return_rate_non_tryon_users": float(non_tryon_return_rate),
            "return_reduction_percentage": float(reduction),
            "methodology": "Cohort analysis: try-on assisted orders vs non-try-on orders, return rate comparison. Try-on adoption attributed via Order.try_on_assisted and ReturnRequest.try_on_used_for_item from real VTON events."
        }

    # Order states whose items are NOT eligible revenue (order-level).
    # NOTE: order status "rejected" is the terminal state of a REJECTED RETURN
    # (ORDER_TRANSITIONS: return_requested -> rejected): goods were delivered
    # and kept, so the revenue stands. "failed" = payment failed, inventory
    # released, never revenue.
    # Kept as the public name callers and the mutation gate already use; the
    # classification itself lives in core.revenue_policy so there is one place
    # to change it (G-13).
    INELIGIBLE_ORDER_STATUSES = tuple(sorted(NON_REVENUE_ORDER_STATUSES))
    ATTRIBUTION_CHANNELS = ("visual_search", "outfit_builder", "virtual_stylist", "organic")

    def compute_item_grain_attribution(self, brand_id: Optional[int] = None) -> Dict[str, Any]:
        """Canonical item-grain revenue attribution ledger.

        Source of truth: brand_analytics_events joined to order_items THROUGH
        order_item_id (migration 0014). There is deliberately NO order-level
        fallback and NO reconstruction via (order_id, product_id, sku_id).

        Per eligible OrderItem (order not cancelled/refunded/failed/rejected):
            channel[purchase.attribution_source] += purchase.revenue_amount
            channel[...]                         -= return.revenue_amount (if returned)
            items with no purchase event (pre-instrumentation) count as organic
            at OrderItem.subtotal and are reported in uninstrumented_items.
        Conservation base (computed independently from OrderItem, not events):
            net = Σ subtotal(eligible items) − Σ subtotal(items with a return event)
        Invariant (tested, and exposed as ``conserved``):
            Σvisual + Σoutfit + Σstylist + Σorganic == net
        A missing, duplicated or corrupt ledger row breaks the equality and is
        reported — never repaired silently. Exact Decimal throughout; floats
        appear only in the JSON view.
        """
        eligible_items = (
            self.db.query(OrderItem)
            .join(Order, OrderItem.order_id == Order.id)
            .filter(revenue_eligible(Order.status))
        )
        if brand_id is not None:
            eligible_items = eligible_items.filter(OrderItem.brand_id == brand_id)
        items = eligible_items.all()
        item_ids = [it.id for it in items]

        purchase_by_item: Dict[int, Tuple[str, Decimal]] = {}
        return_by_item: Dict[int, Decimal] = {}
        if item_ids:
            rows = self.db.query(
                BrandAnalyticsEvent.order_item_id, BrandAnalyticsEvent.event_type,
                BrandAnalyticsEvent.attribution_source, BrandAnalyticsEvent.revenue_amount,
            ).filter(
                BrandAnalyticsEvent.order_item_id.in_(item_ids),
                BrandAnalyticsEvent.event_type.in_(["purchase", "return"]),
            ).all()
            for oid, etype, source, amount in rows:
                if etype == "purchase":
                    channel = source if source in self.ATTRIBUTION_CHANNELS else "organic"
                    purchase_by_item[oid] = (channel, to_decimal(amount))
                else:
                    return_by_item[oid] = to_decimal(amount)

        # Channel figures come from the LEDGER (event.revenue_amount); the
        # conservation base comes from the ITEMS (OrderItem.subtotal). They are
        # computed independently so a corrupt / missing / duplicated ledger row
        # shows up as conserved=False instead of being papered over.
        channel_totals: Dict[str, Decimal] = {c: Decimal("0.00") for c in self.ATTRIBUTION_CHANNELS}
        gross = Decimal("0.00")
        returned = Decimal("0.00")
        uninstrumented_items = 0
        for it in items:
            sub = to_decimal(it.subtotal)
            gross += sub
            purchase = purchase_by_item.get(it.id)
            if purchase is None:
                uninstrumented_items += 1
                channel, amount = "organic", sub  # legacy row: item value, reported
            else:
                channel, amount = purchase
            channel_totals[channel] += amount
            if it.id in return_by_item:
                returned += sub
                channel_totals[channel] -= return_by_item[it.id]  # item-level refund netting

        net = quantize_money(gross - returned)
        attributed_sum = quantize_money(sum(channel_totals.values(), Decimal("0.00")))
        return {
            "eligible_items": len(items),
            "gross_item_revenue": quantize_money(gross),
            "returned_item_revenue": quantize_money(returned),
            "net_item_revenue": net,
            "channels": {c: quantize_money(v) for c, v in channel_totals.items()},
            "attributed_sum": attributed_sum,
            "conserved": attributed_sum == net,
            "uninstrumented_items": uninstrumented_items,
        }

    def get_revenue_attribution(self) -> Dict[str, Any]:
        """Revenue attributable to Virtual Stylist, Outfit Builder, Visual Search (JSON view)."""
        total_gmv = self.db.query(func.sum(Order.total_amount)).filter(
            revenue_eligible(Order.status)
        ).scalar() or Decimal("0.00")

        ledger = self.compute_item_grain_attribution()
        ch = ledger["channels"]
        return {
            "total_gmv": to_float(total_gmv),
            "attribution_base_item_subtotal": to_float(ledger["net_item_revenue"]),
            "gross_item_subtotal": to_float(ledger["gross_item_revenue"]),
            "returned_item_subtotal": to_float(ledger["returned_item_revenue"]),
            "revenue_attribution": {
                "ai_virtual_stylist": to_float(ch["virtual_stylist"]),
                "outfit_builder": to_float(ch["outfit_builder"]),
                "visual_search": to_float(ch["visual_search"]),
                "organic_discovery": to_float(ch["organic"]),
            },
            "conservation_holds": bool(ledger["conserved"]),
            "uninstrumented_items": int(ledger["uninstrumented_items"]),
            "attribution_methodology": (
                "ITEM-LEVEL ledger: each eligible OrderItem (order not cancelled/refunded/failed/rejected) "
                "is attributed to exactly one channel via its BrandAnalyticsEvent purchase event joined THROUGH "
                "order_item_id (no order-level fallback, no (order,product,sku) reconstruction). Channel priority is "
                "fixed at checkout: visual_search > outfit_builder > virtual_stylist > organic. Items with a 'return' "
                "ledger event are netted to zero at item grain (partial refunds subtract only the returned item). "
                "Items without a purchase event (pre-instrumentation) are reported as organic and counted in "
                "uninstrumented_items. Invariant: visual+outfit+stylist+organic == net eligible item subtotal. "
                "Order.total_amount (tax+shipping) is reported separately as total_gmv and is NEVER the attribution base."
            ),
            "attribution_window": "30 days from visual_search view event to purchase (same product, same user or browser session)",
            "dedup_policy": "One purchase event per OrderItem enforced by unique index uq_brand_analytics_item_event",
        }

    # --- Style signal heatmap (single implementation, G-01/G-02/G-04) ------

    #: Below this many aggregated outfits the aggregate is NOT published at all.
    HEATMAP_MIN_SAMPLE = 10
    #: A cell must occur at least this often to be published (k-anonymity floor).
    HEATMAP_K_FLOOR = 5
    #: Hard cap on the outfit scan so the aggregation cannot become unbounded.
    HEATMAP_SCAN_LIMIT = 5000

    @staticmethod
    def _count_json_list(raw: Optional[str]) -> List[str]:
        """Parse a JSON list column, tolerating the malformed rows that exist."""
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return []
        if not isinstance(parsed, list):
            return []
        return [str(item) for item in parsed if item not in (None, "")]

    @classmethod
    def _publish_cells(cls, counter: Dict[str, int], total: int, top_n: int, k_floor: int) -> Tuple[List[Dict[str, Any]], int]:
        """Rank cells, drop everything under the k-floor, report what was dropped.

        The k-floor is a hard floor: it is NOT bypassed when the sample is
        large (the previous ``count >= 3 or sample_size >= 50`` let a single
        occurrence through once the dataset was big — G-02).
        """
        ranked = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
        published: List[Dict[str, Any]] = []
        suppressed = 0
        for name, count in ranked:
            if count < k_floor:
                suppressed += 1
                continue
            if len(published) < top_n:
                published.append(
                    {
                        "name": name.replace("_", " ").title() if "_" in name else name,
                        "raw_name": name,
                        "share": round(count / total * 100, 1) if total else 0.0,
                        "count": int(count),
                    }
                )
        return published, suppressed

    def get_style_heatmap(
        self,
        *,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        top_n: int = 5,
        k_floor: int = HEATMAP_K_FLOOR,
        min_sample: int = HEATMAP_MIN_SAMPLE,
    ) -> Dict[str, Any]:
        """Aggregate anonymised style signals from real ``Outfit`` rows.

        Single source of truth for every style-signal endpoint. Honest by
        construction:

        * **No fabricated rows.** The previous implementation returned four
          hardcoded aesthetics and four hardcoded colour chips whenever the
          aggregation was empty, inside a dashboard labelled "Real Data"
          (G-01). An empty result now returns empty lists plus
          ``data_available: false`` and the reason.
        * **``sample_size`` is the number of outfits actually aggregated.** It
          was previously inflated to ``total_users`` whenever fewer than ten
          outfits existed, which made the published privacy statement false
          (G-02).
        * **The k-floor is a floor.** No large-sample bypass, and it is applied
          to occasions too (they had no threshold at all).
        * **Catalogue tags are not shopper signals.** The old code fell back to
          ``Product.style_tags`` when outfits were thin and presented the result
          as shopper preferences. Two different populations are not one metric,
          so the fallback is gone and the limitation is stated instead.
        * **Period is real.** ``date_from``/``date_to`` are pushed into the SQL
          predicate; the payload reports the window actually applied instead of
          a hardcoded ``"monthly"``.
        """
        query = self.db.query(Outfit)
        lower = to_naive_utc(date_from)
        upper = to_naive_utc(date_to)
        if lower:
            query = query.filter(Outfit.created_at >= lower)
        if upper:
            query = query.filter(Outfit.created_at <= upper)
        outfits = query.limit(self.HEATMAP_SCAN_LIMIT).all()

        style_counter: Dict[str, int] = {}
        color_counter: Dict[str, int] = {}
        occasion_counter: Dict[str, int] = {}
        for outfit in outfits:
            for tag in self._count_json_list(outfit.style_tags):
                style_counter[tag] = style_counter.get(tag, 0) + 1
            for color in self._count_json_list(outfit.color_palette):
                color_counter[color] = color_counter.get(color, 0) + 1
            if outfit.occasion:
                occasion_counter[outfit.occasion] = occasion_counter.get(outfit.occasion, 0) + 1

        sample_size = len(outfits)
        data_available = sample_size >= min_sample
        scan_truncated = sample_size >= self.HEATMAP_SCAN_LIMIT

        def dimension(counter: Dict[str, int]) -> Tuple[List[Dict[str, Any]], int]:
            if not data_available:
                return [], 0
            total = sum(counter.values())
            return self._publish_cells(counter, total, top_n, k_floor)

        top_aesthetics, sup_style = dimension(style_counter)
        trending_colors, sup_color = dimension(color_counter)
        top_occasions, sup_occasion = dimension(occasion_counter)

        limitations: List[str] = [
            "Derived from saved outfits only. Outfits a shopper built but never "
            "saved are not counted, so this measures expressed preference, not "
            "browsing intent.",
            "The platform stores no region attribute on users or outfits, so this "
            "aggregate is platform-wide; region breakdowns are not available.",
        ]
        if not data_available:
            limitations.insert(
                0,
                f"Only {sample_size} outfit(s) in scope; at least {min_sample} are "
                "required before any cell is published, so nothing is shown rather "
                "than a small-population aggregate.",
            )
        if scan_truncated:
            limitations.append(
                f"The scan is capped at {self.HEATMAP_SCAN_LIMIT} outfits; the "
                "aggregate covers the most recent rows within that cap."
            )

        return {
            "region": "Platform-wide",
            "region_scope": "platform_wide",
            "region_filter_applied": False,
            "period": {
                "from": lower.isoformat() if lower else None,
                "to": upper.isoformat() if upper else None,
            },
            "sample_size": int(sample_size),
            "min_sample_required": int(min_sample),
            "k_anonymity_floor": int(k_floor),
            "data_available": bool(data_available),
            "top_aesthetics": top_aesthetics,
            "trending_colors": trending_colors,
            "top_occasions": top_occasions,
            "suppressed_cells": int(sup_style + sup_color + sup_occasion),
            "anonymized": True,
            "privacy_threshold": (
                f"Every published cell occurs at least {k_floor} times and the "
                f"aggregate covers {sample_size} outfits; cells below the floor "
                "are suppressed ({sup_style + sup_color + sup_occasion} suppressed "
                "in this run). No individual-level data is exposed."
            ),
            "methodology": (
                "COUNT over Outfit.style_tags, Outfit.color_palette and "
                "Outfit.occasion within the requested window, ranked by frequency. "
                "Shares are a percentage of all occurrences in that dimension, so "
                "they sum to ~100% across the FULL distribution, not just the "
                "published top-N. No rows are synthesised and catalogue tags are "
                "never substituted for shopper signals."
            ),
            "limitations": limitations,
        }

    def get_user_preference_heatmaps(
        self,
        *,
        region: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        min_sample_size: int = HEATMAP_MIN_SAMPLE,
    ) -> Dict[str, Any]:
        """Thin wrapper kept for the existing admin endpoint.

        ``region`` is accepted but reported as NOT applied — the same contract
        ``get_brand_preference_heatmaps`` already publishes on the partner
        surface (``region`` / ``requested_region`` / ``region_filter_applied``).
        The platform stores no region attribute on users or outfits, so the
        previous behaviour of echoing the caller's region back as the label on
        platform-wide numbers is gone (G-03); one convention now covers both
        endpoints instead of two.
        """
        heatmap = self.get_style_heatmap(
            date_from=date_from, date_to=date_to, min_sample=min_sample_size
        )
        heatmap["requested_region"] = region
        if region:
            heatmap["limitations"] = [
                f"The requested region filter '{region}' was NOT applied: the "
                "platform stores no region attribute on users or outfits, so the "
                "figures below are platform-wide. See region_filter_applied."
            ] + list(heatmap["limitations"])
        return heatmap

    # --- Analytics Event Instrumentation (REAL attribution) ---
    def create_analytics_event(
        self,
        brand_id: int,
        event_type: str,
        attribution_source: str = None,
        product_id: int = None,
        sku_id: int = None,
        user_id: int = None,
        session_token: str = None,
        outfit_id: int = None,
        order_id: int = None,
        revenue_amount=None,
        event_metadata: dict = None,
        idempotency_key: str = None,
        order_item_id: int = None,
    ) -> Optional[BrandAnalyticsEvent]:
        """Idempotent analytics event creation - prevents double count.

        Financial events (purchase / return) MUST carry order_item_id — the
        attribution ledger is item-grain and joins through that column only.
        """
        import uuid as _uuid
        if event_type in ("purchase", "return") and order_item_id is None:
            raise ValueError(f"{event_type} analytics events require order_item_id (item-grain ledger)")
        if revenue_amount is not None:
            # Domain validation BEFORE persistence: finite, NUMERIC(12,2) range,
            # never negative (a return is a positive amount with event_type='return').
            revenue_amount = validate_money(revenue_amount, "revenue_amount", allow_negative=False)
        eid = idempotency_key or f"{event_type}_{attribution_source or 'na'}_{order_id or ''}_{product_id or ''}_{_uuid.uuid4().hex[:8]}"
        existing = self.db.query(BrandAnalyticsEvent).filter(BrandAnalyticsEvent.event_id == eid).first()
        if existing:
            return existing
        try:
            ev = BrandAnalyticsEvent(
                event_id=eid,
                brand_id=brand_id,
                product_id=product_id,
                sku_id=sku_id,
                user_id=user_id,
                session_token=session_token,
                event_type=event_type,
                attribution_source=attribution_source,
                outfit_id=outfit_id,
                order_id=order_id,
                order_item_id=order_item_id,
                revenue_amount=revenue_amount,
                event_metadata_json=json.dumps(event_metadata or {}),
            )
            self.db.add(ev)
            self.db.commit()
            self.db.refresh(ev)
            return ev
        except Exception:
            # Only a concurrent insert of the SAME event (unique event_id or
            # unique (order_item_id, event_type)) is tolerated: return that row.
            # Anything else is re-raised — swallowing it would silently drop a
            # financial event from the ledger.
            self.db.rollback()
            existing = self.db.query(BrandAnalyticsEvent).filter(BrandAnalyticsEvent.event_id == eid).first()
            if existing is None and order_item_id is not None:
                existing = self.db.query(BrandAnalyticsEvent).filter(
                    BrandAnalyticsEvent.order_item_id == order_item_id,
                    BrandAnalyticsEvent.event_type == event_type,
                ).first()
            if existing is None:
                raise
            return existing

    def get_recent_visual_search_for_user(self, user_id: int, within_days: int = 30, product_id: int = None,
                                          session_token: Optional[str] = None) -> bool:
        """Product-level visual-search lineage check: a visual_search VIEW event
        for the given product within the window, owned by the user or by the
        browser session (guest -> authenticated stitching).

        No fallback: a database error propagates. The previous version fell
        back to "any prior search query by this user" on ANY exception, which
        could attribute unrelated purchases on a transient DB error.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=within_days)
        owners = []
        if user_id:
            owners.append(BrandAnalyticsEvent.user_id == user_id)
        if session_token:
            owners.append(BrandAnalyticsEvent.session_token == session_token)
        if not owners:
            return False
        q = self.db.query(BrandAnalyticsEvent.id).filter(
            BrandAnalyticsEvent.event_type == "view",
            BrandAnalyticsEvent.attribution_source == "visual_search",
            BrandAnalyticsEvent.created_at >= cutoff,
            or_(*owners),
        )
        if product_id:
            q = q.filter(BrandAnalyticsEvent.product_id == product_id)
        return q.first() is not None

    def create_import_job(self, brand_id: int, file_name: str = None, file_size: int = None) -> CatalogImportJob:
        job = CatalogImportJob(
            brand_id=brand_id,
            file_name=file_name,
            file_size=file_size,
            status="queued",
            total_rows=0,
            accepted_rows=0,
            rejected_rows=0,
            duplicate_rows=0,
            errors_json="[]"
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_import_job(self, job_id: int, brand_id: int) -> Optional[CatalogImportJob]:
        return self.db.query(CatalogImportJob).filter(
            CatalogImportJob.id == job_id,
            CatalogImportJob.brand_id == brand_id
        ).first()

    def get_brand_import_jobs(self, brand_id: int, limit: int = 20) -> List[CatalogImportJob]:
        return self.db.query(CatalogImportJob).filter(
            CatalogImportJob.brand_id == brand_id
        ).order_by(desc(CatalogImportJob.created_at)).limit(limit).all()

    def update_import_job(self, job_id: int, brand_id: int, data: Dict[str, Any]) -> Optional[CatalogImportJob]:
        job = self.get_import_job(job_id, brand_id)
        if not job:
            return None

        for key, value in data.items():
            if hasattr(job, key):
                setattr(job, key, value)

        self.db.commit()
        self.db.refresh(job)
        return job
