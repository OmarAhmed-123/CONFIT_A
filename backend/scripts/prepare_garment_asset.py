"""Prepare a REAL flat-lay garment asset so the segfee engine can render it.

WHY THIS SCRIPT EXISTS
  `get_or_create_garment_asset()` deliberately refuses to pretend: it records the
  product's source photo, classifies it, and leaves `tryon_ready = False` until a
  validated clean asset is stored. That is correct — but it means a catalogue
  product can never become renderable on its own. This is the missing write path.

WHAT IT REFUSES TO DO
  * It never forces `tryon_ready = True`. The gate `classify_garment_photo()` is
    run on the actual bytes FIRST, and an image it calls `model` is rejected and
    nothing is written. There is no `--force`.
  * It never overwrites a product's catalogue photo, price, stock or SKUs. It
    writes one `garment_assets` row (or updates that row) and nothing else.
  * It never claims a generated image is a photograph of a real garment. Every
    row it writes records its provenance in `classification_json`, and an asset
    produced from a generated image is stamped `provenance = "generated-demo"`
    so a later operator can find and replace it.

USAGE
    PYTHONPATH=. python3 backend/scripts/prepare_garment_asset.py \
        --product-id 1 \
        --image /path/to/flatlay.png \
        --provenance generated-demo \
        --note "demo asset: no real product photography exists in this catalogue"

    # inspect without writing anything
    ... --product-id 1 --image x.png --dry-run

EXIT CODES
    0 asset written (or --dry-run verified only)
    2 the guard rejected the image (photo_type == "model") - nothing written
    3 product not found / has no VTON slot
    4 storage upload failed
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from datetime import datetime, timezone

from PIL import Image

from backend.app.core.database import SessionLocal
from backend.app.models.tryon import GarmentAsset
from backend.app.services.garment_asset_guard import classify_garment_photo
from backend.app.services.storage_service import get_storage_backend
from backend.app.services.tryon_service import CATEGORY_TO_VTON_SLOT, DEFAULT_VTON_SLOT

#: photo_types the VTON pipeline accepts as engine-ready input.
ACCEPTED_PHOTO_TYPES = {"flat-lay", "ghost-mannequin"}


def _load_image(path: str) -> Image.Image:
    with open(path, "rb") as fh:
        return Image.open(io.BytesIO(fh.read())).convert("RGB")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--product-id", type=int, required=True)
    ap.add_argument("--image", required=True, help="path to the flat-lay / ghost-mannequin image")
    ap.add_argument(
        "--provenance",
        default="generated-demo",
        choices=["generated-demo", "studio-photo", "supplier-flatlay"],
        help="where the image came from; recorded verbatim, never guessed",
    )
    ap.add_argument("--note", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    db = SessionLocal()
    try:
        from backend.app.models.catalog import Product  # local import: keeps CLI startup light

        product = db.query(Product).filter(Product.id == args.product_id).first()
        if not product:
            print(f"ERROR: product {args.product_id} not found", file=sys.stderr)
            return 3

        slug = product.category.slug if getattr(product, "category", None) else None
        slot = CATEGORY_TO_VTON_SLOT.get(slug, DEFAULT_VTON_SLOT)
        if slot in ("footwear", "accessory"):
            # The registry returns an empty engine chain for these on purpose.
            print(
                f"ERROR: product {product.id} maps to slot '{slot}', which the VTON "
                f"registry refuses by design (Fit Check only). Not preparing.",
                file=sys.stderr,
            )
            return 3

        image = _load_image(args.image)
        photo_type, evidence = classify_garment_photo(image)
        print(f"guard verdict      : {photo_type}")
        print(f"guard evidence     : {json.dumps(evidence, default=str)}")

        if photo_type not in ACCEPTED_PHOTO_TYPES:
            print(
                "\nREJECTED: the guard classifies this image as a worn/model photo.\n"
                "The segmentation-free engine would copy hands and background into the\n"
                "render (the 'ghost hands' incident). Supply a clean flat-lay instead.\n"
                "Nothing was written.",
                file=sys.stderr,
            )
            return 2

        with open(args.image, "rb") as fh:
            payload = fh.read()

        key = f"garment-assets/{product.id}/clean-{datetime.now(timezone.utc):%Y%m%d%H%M%S}.png"
        print(f"storage key        : {key}")

        if args.dry_run:
            print("\nDRY RUN: guard passed, nothing uploaded or written.")
            return 0

        try:
            backend = get_storage_backend()
            clean_url = backend.store(key, payload)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: storage upload failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 4
        print(f"clean_image_url    : {clean_url}")

        record = {
            "photo_type": photo_type,
            "evidence": evidence,
            "provenance": args.provenance,
            "note": args.note,
            "source_image": os.path.basename(args.image),
            "prepared_at": datetime.now(timezone.utc).isoformat(),
            "prepared_by": "backend/scripts/prepare_garment_asset.py",
        }

        asset = (
            db.query(GarmentAsset).filter(GarmentAsset.product_id == product.id).first()
        )
        created = asset is None
        if created:
            asset = GarmentAsset(
                product_id=product.id,
                slot_type=slot,
                flat_image_url=product.thumbnail_url,
            )
            db.add(asset)

        asset.slot_type = slot
        asset.photo_type = photo_type
        asset.clean_image_url = clean_url
        # segmented_garment_url / garment_mask_url stay NULL: this script prepares
        # a CLEAN SOURCE, it does not run segmentation. Claiming otherwise would
        # be the exact lie the guard was written to prevent.
        asset.tryon_ready = True
        asset.classification_json = json.dumps(record, ensure_ascii=False)
        if created:
            asset.flat_image_url = product.thumbnail_url

        db.commit()
        print(f"\n{'CREATED' if created else 'UPDATED'} garment_assets row id={asset.id}")
        print(f"  tryon_ready      : {bool(asset.tryon_ready)}")
        print(f"  slot_type        : {asset.slot_type}")
        print(f"  provenance       : {args.provenance}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
