#!/usr/bin/env python3
"""Materialise and register catalogue media so the storefront's image URLs work.

WHAT WAS WRONG (measured 2026-10-20, read-only, against production)
-------------------------------------------------------------------
* ``GET /api/v1/catalog/products`` served ``thumbnail_url`` values such as
  ``/api/v1/media/pexels:450212:4x5:hero``.
* Every one of them answered ``404 RESOURCE_NOT_FOUND``; the storefront showed
  "Image unavailable" on every card (14 placeholders measured on the home page).
* ``product_images`` held 54 rows; the bucket held 120 objects under
  ``products/{product_id}/{product_id}-{ratio}.{ext}``; the media route accepts
  only ``products/{id}/{file}``.

Three disjoint naming schemes. The registry rows carried
``{provider}:{photo_id}:{ratio}:{role}`` — labels written by the 2026-10-09
repair pass, which assumed the media route served ``public_url``. It serves
``storage_key``. And none of the 54 rows' byte counts matched any object in the
bucket, so those files had never been uploaded at all: the registry recorded
intent.

WHAT THIS SCRIPT DOES
---------------------
For each product with a known licensed source (``product_image_plan_*.json``):

  1. fetch the source rendition from the approved host (Unsplash/Pexels only);
  2. derive the design system's ratio ladder and re-encode jpeg + webp;
  3. store them under the canonical key ``products/{id}/{id}-{ratio}.{ext}``;
  4. register one ``product_images`` row per (ratio, format) whose
     ``storage_key`` IS that key, with bytes/width/height/checksum measured
     from the stored bytes, plus source_type/provider/attribution.

It goes through ``MediaMaterializationService`` — the same code the brand
catalogue import uses — so the repair and the import can never disagree.
No raw SQL: every read and write is an ORM statement.

Usage (DATABASE_URL must be a PostgreSQL DSN; it is never printed):

    python -m backend.scripts.materialize_catalog_media            # dry run
    python -m backend.scripts.materialize_catalog_media --apply --backup docs/data-repairs/media-<ts>.json
    python -m backend.scripts.materialize_catalog_media --verify
    python -m backend.scripts.materialize_catalog_media --rollback docs/data-repairs/media-<ts>.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLAN_PATH = REPO / "backend/scripts/data/product_image_plan_2026-10-09.json"

#: ratio -> the JPEG rendition URL recorded in the plan. The plan stores one
#: entry per (ratio, role); ``thumb`` is a second 4:5 crop used only by the
#: legacy column and is deliberately not registered as a row.
RATIOS = ("4x5", "1x1", "3x2", "16x9", "master")


def load_plan() -> dict:
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def rendition_urls(plan_product: dict) -> dict:
    """{ratio: url} for the ladder, preferring the non-thumb rendition."""
    urls = {}
    for r in plan_product.get("renditions", []):
        if r.get("role") == "thumb":
            continue
        urls.setdefault(r["ratio"], r["url"])
    return {k: v for k, v in urls.items() if k in RATIOS}


def provenance(plan_product: dict) -> dict:
    src = plan_product.get("source") or {}
    provider = src.get("provider")
    return {
        "source_type": "generated" if provider == "generated" else "stock",
        "provider": provider,
        "source_ref": src.get("source_ref"),
        "attribution": src.get("attribution"),
    }


def session():
    from backend.app.core.database import SessionLocal
    return SessionLocal()


def snapshot(db) -> dict:
    """Everything this script can change, in a form --rollback can restore."""
    from backend.app.models.catalog import Product, ProductImage

    cols = ["id", "product_id", "storage_key", "public_url", "ratio", "format", "width", "height",
            "bytes", "role", "is_primary", "source_type", "provider", "source_ref", "attribution", "checksum"]
    images = []
    for row in db.query(ProductImage).order_by(ProductImage.id).all():
        images.append({c: (getattr(row, c).isoformat() if c == "created_at" else getattr(row, c)) for c in cols})
    products = [
        {"id": p.id, "slug": p.slug, "thumbnail_url": p.thumbnail_url, "images": p.images}
        for p in db.query(Product).order_by(Product.id).all()
    ]
    return {
        "taken_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "products": products,
        "product_images": images,
    }


def report_state(db, label: str) -> dict:
    """Before/after summary. Counts only — no credentials, no connection string."""
    from sqlalchemy import func

    from backend.app.models.catalog import Product, ProductImage
    from backend.app.services.media_materialization_service import CANONICAL_KEY_RE

    rows = db.query(ProductImage).all()
    canonical = sum(1 for r in rows if CANONICAL_KEY_RE.match(r.storage_key or ""))
    state = {
        "label": label,
        "products": db.query(func.count(Product.id)).scalar(),
        "product_images_rows": len(rows),
        "rows_with_canonical_key": canonical,
        "rows_with_legacy_label_key": len(rows) - canonical,
        "distinct_products_with_media": db.query(func.count(func.distinct(ProductImage.product_id))).scalar(),
        "sample_keys": [r.storage_key for r in rows[:3]],
    }
    print(json.dumps(state, indent=2))
    return state


def apply_plan(db, *, dry_run: bool, only_slug: str | None = None) -> int:
    from backend.app.models.catalog import Product
    from backend.app.services.media_materialization_service import (
        MediaMaterializationError, MediaMaterializationService,
    )

    plan = load_plan()
    service = MediaMaterializationService(db)
    changed = 0
    for slug, plan_product in plan["products"].items():
        if only_slug and slug != only_slug:
            continue
        product = db.query(Product).filter(Product.slug == slug).first()
        if product is None:
            print(f"  SKIP {slug}: no product with that slug in this database")
            continue
        urls = rendition_urls(plan_product)
        if not urls:
            print(f"  SKIP {slug}: no usable renditions in the plan")
            continue
        if dry_run:
            print(f"  WOULD materialise {slug} (product {product.id}): {', '.join(sorted(urls))}")
            changed += 1
            continue
        try:
            rows = service.materialize(product, urls["4x5"], ratios=sorted(urls), **provenance(plan_product))
        except MediaMaterializationError as exc:
            print(f"  FAIL {slug}: {exc}")
            continue
        print(f"  OK   {slug} (product {product.id}): {len(rows)} rows registered")
        changed += 1
    return changed


def rollback(db, backup_path: str) -> None:
    from backend.app.models.catalog import Product, ProductImage

    data = json.loads(Path(backup_path).read_text(encoding="utf-8"))
    db.query(ProductImage).delete()
    for row in data["product_images"]:
        db.add(ProductImage(**{k: v for k, v in row.items() if k in ProductImage.__table__.columns.keys()}))
    for p in data["products"]:
        product = db.query(Product).filter(Product.id == p["id"]).first()
        if product:
            product.thumbnail_url = p["thumbnail_url"]
            product.images = p["images"]
    db.commit()
    print(f"restored {len(data['product_images'])} product_images rows and {len(data['products'])} products")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write to the database (default: dry run)")
    ap.add_argument("--backup", help="path to write a JSON snapshot before applying")
    ap.add_argument("--rollback", help="restore from a snapshot written by --backup")
    ap.add_argument("--verify", action="store_true", help="read-only: report registry state")
    ap.add_argument("--slug", help="restrict to one product slug")
    args = ap.parse_args()

    if not os.environ.get("DATABASE_URL"):
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2

    db = session()
    try:
        if args.rollback:
            rollback(db, args.rollback)
            return 0

        if args.verify:
            report_state(db, "verify")
            return 0

        if args.apply:
            if not args.backup:
                print("REFUSING to write without --backup <path>: a production media "
                      "repair must be reversible.", file=sys.stderr)
                return 2
            before = report_state(db, "before")
            Path(args.backup).write_text(json.dumps(snapshot(db), indent=2, default=str), encoding="utf-8")
            print(f"backup written: {args.backup}")
            changed = apply_plan(db, dry_run=False, only_slug=args.slug)
            after = report_state(db, "after")
            print(json.dumps({"products_changed": changed, "before": before, "after": after}, indent=2))
            return 0

        print("DRY RUN (no writes). Planned changes:")
        apply_plan(db, dry_run=True, only_slug=args.slug)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
