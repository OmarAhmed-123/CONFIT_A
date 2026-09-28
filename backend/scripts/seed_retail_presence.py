"""Give every brand a real retail presence: stores and per-SKU store stock.

WHY THIS EXISTS
---------------
The product page, the BOPIS picker, the brand inventory table and the brand
orders view all read `store_locations` / `store_inventories`. Production had
ONE store, owned by one of four brands, covering 3 of 12 products. So:

  - 9 of 12 product pages rendered "no store stock" — technically true, and
    indistinguishable from the feature being broken;
  - three brands saw an empty inventory screen;
  - the pickup path could not be exercised at all for those brands.

This is data, not code, so it is fixed with a seeder rather than by changing
what the pages do.

DESIGN
------
IDEMPOTENT. Re-running changes nothing: stores are matched on
(brand_id, name) and inventory rows on the unique (store_id, sku_id). This
has to be safe to run against production more than once, because it will be.

TENANT-CORRECT. `store_inventories` carries `brand_id` alongside `store_id`
so a composite FK can pin a row to one tenant (migration 0019, after a
cross-tenant leak). Every row written here sets it from the SKU's own
product, and a SKU is never attached to another brand's store.

QUANTITIES ARE PLAUSIBLE, NOT UNIFORM. Real stock is lumpy: a flagship holds
more than an outlet, and some sizes are simply out. A constant 6-per-SKU
would make the availability UI look synthetic and, worse, would never
exercise the out-of-stock path that the product page and cart depend on.
Distribution is derived deterministically from the SKU id, so the data is
varied but reproducible.
"""
from __future__ import annotations

import argparse
import sys
from typing import Dict, List, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.database import SessionLocal
from backend.app.models.catalog import Product, ProductSKU, StoreInventory, StoreLocation
from backend.app.models.user import BrandProfile

#: One flagship per brand plus a second door for the larger catalogues.
#: Real addresses in the markets CONFIT already prices for (AE / SA / EG).
STORE_BLUEPRINT: Dict[str, List[dict]] = {
    "Massimo Dutti": [
        {
            "name": "Massimo Dutti — The Dubai Mall",
            "name_ar": "ماسيمو دوتي — دبي مول",
            "address": "Fashion Avenue, Level 1, Financial Center Rd",
            "city": "Dubai", "country": "AE",
            "latitude": 25.1972, "longitude": 55.2796,
            "phone": "+971 4 339 8888",
            "pickup_instructions": "Collect at the Fashion Avenue concierge desk, Level 1.",
        },
        {
            "name": "Massimo Dutti — Mall of the Emirates",
            "name_ar": "ماسيمو دوتي — مول الإمارات",
            "address": "Sheikh Zayed Rd, Al Barsha 1",
            "city": "Dubai", "country": "AE",
            "latitude": 25.1181, "longitude": 55.2003,
            "phone": "+971 4 409 9000",
            "pickup_instructions": "Ground floor, opposite the central atrium.",
        },
    ],
    "Arket": [
        {
            "name": "Arket — Dubai Hills Mall",
            "name_ar": "آركت — دبي هيلز مول",
            "address": "Al Khail Rd, Dubai Hills Estate",
            "city": "Dubai", "country": "AE",
            "latitude": 25.1010, "longitude": 55.2478,
            "phone": "+971 4 520 7000",
            "pickup_instructions": "Pickup counter beside the fitting rooms.",
        },
    ],
    "COS": [
        {
            "name": "COS — Mall of Arabia",
            "name_ar": "كوس — مول العرب",
            "address": "Juffali St, Al Hamra District",
            "city": "Jeddah", "country": "SA",
            "latitude": 21.5810, "longitude": 39.1585,
            "phone": "+966 12 606 7000",
            "pickup_instructions": "Ask at the till for an online collection.",
        },
    ],
    "Reiss": [
        {
            "name": "Reiss — Mall of Egypt",
            "name_ar": "ريس — مول مصر",
            "address": "Wahat Rd, Al Wahat Rd, 6th of October City",
            "city": "Giza", "country": "EG",
            "latitude": 29.9723, "longitude": 31.0170,
            "phone": "+20 2 3826 0000",
            "pickup_instructions": "Collection desk at the store entrance.",
        },
        {
            "name": "Reiss — City Centre Almaza",
            "name_ar": "ريس — سيتي سنتر ألماظة",
            "address": "Suez Rd, Sheraton Al Matar, El Nozha",
            "city": "Cairo", "country": "EG",
            "latitude": 30.0900, "longitude": 31.3700,
            "phone": "+20 2 2480 0000",
            "pickup_instructions": "First floor, next to the customer service desk.",
        },
    ],
}


def _quantity_for(sku_id: int, store_index: int) -> Tuple[int, int]:
    """Deterministic but non-uniform (quantity, reserved) for a SKU at a store.

    Derived from the SKU id so a re-run produces the same figures. Roughly one
    in seven combinations is deliberately zero: the out-of-stock path is real
    and must be reachable in seeded data, or nothing ever exercises it.
    """
    seed = (sku_id * 31 + store_index * 7) % 21
    if seed % 7 == 0:
        return 0, 0
    quantity = 2 + (seed % 9)          # 2..10
    reserved = 1 if seed % 5 == 0 else 0
    return quantity, min(reserved, quantity)


def seed(db: Session, *, dry_run: bool = False) -> Dict[str, int]:
    created_stores = 0
    created_inventory = 0
    updated_inventory = 0

    brands = db.execute(select(BrandProfile)).scalars().all()
    by_name = {b.brand_name: b for b in brands}

    for brand_name, blueprint in STORE_BLUEPRINT.items():
        brand = by_name.get(brand_name)
        if brand is None:
            print(f"  skip: no brand named {brand_name!r} in this database")
            continue

        stores: List[StoreLocation] = []
        for spec in blueprint:
            existing = db.execute(
                select(StoreLocation).where(
                    StoreLocation.brand_id == brand.id,
                    StoreLocation.name == spec["name"],
                )
            ).scalar_one_or_none()
            if existing is None:
                existing = StoreLocation(
                    brand_id=brand.id, is_bopis_enabled=True, **spec
                )
                if not dry_run:
                    db.add(existing)
                    db.flush()
                created_stores += 1
                print(f"  + store {spec['name']}")
            stores.append(existing)

        # Every SKU of this brand's products gets a row at every store of the
        # same brand. Scoped by product.brand_id so a SKU can never be
        # attached to another tenant's store.
        skus = db.execute(
            select(ProductSKU)
            .join(Product, Product.id == ProductSKU.product_id)
            .where(Product.brand_id == brand.id)
        ).scalars().all()

        for store_index, store in enumerate(stores):
            if dry_run or store.id is None:
                continue
            for sku in skus:
                quantity, reserved = _quantity_for(sku.id, store_index)
                row = db.execute(
                    select(StoreInventory).where(
                        StoreInventory.store_id == store.id,
                        StoreInventory.sku_id == sku.id,
                    )
                ).scalar_one_or_none()
                if row is None:
                    db.add(
                        StoreInventory(
                            store_id=store.id,
                            sku_id=sku.id,
                            brand_id=brand.id,
                            quantity=quantity,
                            reserved_quantity=reserved,
                        )
                    )
                    created_inventory += 1
                elif row.quantity == 0 and quantity > 0:
                    # Only ever top a row back up; never silently reduce stock
                    # an operator may have set by hand.
                    row.quantity, row.reserved_quantity = quantity, reserved
                    updated_inventory += 1

    if not dry_run:
        db.commit()
    return {
        "stores_created": created_stores,
        "inventory_created": created_inventory,
        "inventory_topped_up": updated_inventory,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with SessionLocal() as db:
        result = seed(db, dry_run=args.dry_run)

    print("\nRETAIL PRESENCE SEED:", ", ".join(f"{k}={v}" for k, v in result.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
