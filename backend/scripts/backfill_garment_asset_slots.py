"""One-off migration: backfill garment_assets.slot_type to the VTON slot vocabulary.

Historically the raw catalogue category slug (outerwear, tops, bottoms,
dresses, footwear, accessories) was persisted into garment_assets.slot_type.
The worker's AgnosticMaskGenerator only understands the VTON vocabulary
(upper_outer, upper_inner, lower, dress, footwear, accessory) and now raises
on anything else — so stale rows must be remapped, not merely fixed at the
write path.

Run once per environment:

    PYTHONPATH=. python3 backend/scripts/backfill_garment_asset_slots.py

Alternatively, if the cached assets hold nothing worth keeping, truncating
garment_assets is equally safe: the table is a cache keyed by product id and
repopulates on demand via get_or_create_garment_asset().
"""

from backend.app.core.database import SessionLocal
from backend.app.models.tryon import GarmentAsset
from backend.app.services.tryon_service import CATEGORY_TO_VTON_SLOT


def main() -> None:
    db = SessionLocal()
    try:
        updated = 0
        skipped = 0
        for asset in db.query(GarmentAsset).all():
            mapped = CATEGORY_TO_VTON_SLOT.get(asset.slot_type)
            if mapped:
                asset.slot_type = mapped
                updated += 1
            else:
                skipped += 1
        db.commit()
        print(f"Backfill complete: {updated} row(s) remapped, {skipped} already valid.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
