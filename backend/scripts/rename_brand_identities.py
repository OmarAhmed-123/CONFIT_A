"""Retire real-brand names from the catalogue — service layer only.

WHY
---
The catalogue shipped four real retail trademarks (Massimo Dutti, COS, Reiss,
Arket) as if CONFIT were those brands: their names on cards, their names in
store labels, their names in slugs customers can link to. The seed code was
renamed to fictional house brands; existing rows were not, because renaming
identities that customers already see needs an explicit decision and a backup.

This script is that decision, made deliberate:

  * dry-run by default — it prints exactly what would change and writes nothing;
  * ``--apply`` REQUIRES ``--backup`` — no backup, no write;
  * the backup is the rollback: it captures every affected row (brands, their
    products, their SKUs, their store locations) with a sha256 over the payload;
  * every change goes through BrandService.rename_brand / rename_store, the
    same validated, audited path a brand edit uses. There is no SQL here;
  * ``--rollback <file>`` restores whatever the file recorded, through the same
    service.

It does NOT touch money, stock or orders. Names and slugs only. SKU codes
(MD-…, REISS-…, COS-…, ARK-…) are deliberately left alone: they are
transactional identifiers that appear on existing order lines, so renaming them
is a data-migration decision, not a cosmetic one.

USAGE
-----
    # see what would change
    python -m backend.scripts.rename_brand_identities

    # do it (backup path is mandatory)
    python -m backend.scripts.rename_brand_identities --apply \
        --backup /path/to/brand_identities_<ts>.json

    # undo
    python -m backend.scripts.rename_brand_identities --rollback /path/to/that.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

from backend.app.core.database import SessionLocal
from backend.app.models.catalog import Product, ProductSKU, StoreLocation
from backend.app.models.user import BrandProfile
from backend.app.services.brand_service import BrandService

# Real trademark -> fictional house brand. These are the same names the seed
# code now uses, so a fresh environment and a repaired one agree.
BRAND_RENAMES = {
    "Massimo Dutti": ("Atelier Sable", "atelier-sable"),
    "COS": ("Casa Lumen", "casa-lumen"),
    "Reiss": ("Riven Studio", "riven-studio"),
    "Arket": ("Nordhaus", "nordhaus"),
}

# Store labels are "Brand — Location"; only the brand prefix changes, so the
# mall names customers know stay intact.
def renamed_store(store_name: str) -> str:
    name = store_name or ""
    for old, (new, _slug) in BRAND_RENAMES.items():
        if name.lower().startswith(old.lower()):
            return new + name[len(old):]
    return name


def _sha256(payload) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def collect(db) -> dict:
    """Snapshot every row this script could touch, plus a checksum."""
    brands, products, skus, stores = [], [], [], []
    for brand in db.query(BrandProfile).order_by(BrandProfile.id).all():
        products_of_brand = db.query(Product).filter(Product.brand_id == brand.id).order_by(Product.id).all()
        skus_of_brand = db.query(ProductSKU).filter(ProductSKU.brand_id == brand.id).order_by(ProductSKU.id).all()
        stores_of_brand = db.query(StoreLocation).filter(StoreLocation.brand_id == brand.id).order_by(StoreLocation.id).all()
        brands.append({
            "id": brand.id, "brand_name": brand.brand_name, "slug": brand.slug,
            "products": len(products_of_brand), "skus": len(skus_of_brand), "stores": len(stores_of_brand),
        })
        products += [{"id": p.id, "brand_id": p.brand_id, "slug": p.slug} for p in products_of_brand]
        skus += [{"id": s.id, "brand_id": s.brand_id, "sku_code": s.sku_code} for s in skus_of_brand]
        stores += [{"id": s.id, "brand_id": s.brand_id, "name": s.name} for s in stores_of_brand]

    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "counts": {"brands": len(brands), "products": len(products), "skus": len(skus), "stores": len(stores)},
        "brands": brands, "products": products, "skus": skus, "stores": stores,
    }
    payload["checksum_sha256"] = _sha256({k: v for k, v in payload.items() if k != "checksum_sha256"})
    return payload


def plan(db) -> list[dict]:
    """What would change, computed from live rows (not from the mapping alone)."""
    changes = []
    for brand in db.query(BrandProfile).order_by(BrandProfile.id).all():
        target = BRAND_RENAMES.get(brand.brand_name)
        if target:
            changes.append({"kind": "brand", "id": brand.id, "from": brand.brand_name,
                            "to": target[0], "slug_to": target[1], "current_slug": brand.slug})
    for store in db.query(StoreLocation).order_by(StoreLocation.id).all():
        new_name = renamed_store(store.name)
        if new_name != store.name:
            changes.append({"kind": "store", "id": store.id, "brand_id": store.brand_id,
                            "from": store.name, "to": new_name})
    return changes


def apply(db, changes, backup_path: str) -> dict:
    service = BrandService(db)
    applied, failed = [], []
    for change in changes:
        try:
            if change["kind"] == "brand":
                result = service.rename_brand(change["id"], change["to"], slug=change["slug_to"])
            else:
                result = service.rename_store(change["id"], change["brand_id"], change["to"])
            applied.append({"kind": change["kind"], "id": change["id"],
                            "before": result["before"], "after": result["after"]})
        except Exception as exc:  # report, never half-apply silently
            db.rollback()
            failed.append({"kind": change["kind"], "id": change["id"], "error": f"{type(exc).__name__}: {exc}"})
    return {"backup": backup_path, "applied": applied, "failed": failed}


def rollback(db, backup: dict) -> dict:
    """Restore the exact previous names recorded in the backup, via the service."""
    service = BrandService(db)
    restored = []
    for brand in backup.get("brands", []):
        current = db.query(BrandProfile).filter(BrandProfile.id == brand["id"]).first()
        if current and (current.brand_name != brand["brand_name"] or current.slug != brand["slug"]):
            service.rename_brand(brand["id"], brand["brand_name"], slug=brand["slug"])
            restored.append({"kind": "brand", "id": brand["id"], "to": brand["brand_name"]})
    for store in backup.get("stores", []):
        current = db.query(StoreLocation).filter(StoreLocation.id == store["id"]).first()
        if current and current.name != store["name"]:
            service.rename_store(store["id"], store["brand_id"], store["name"])
            restored.append({"kind": "store", "id": store["id"], "to": store["name"]})
    return {"restored": restored}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Rename imitating brand identities to house brands (service layer only).")
    ap.add_argument("--apply", action="store_true", help="write the changes (requires --backup)")
    ap.add_argument("--backup", help="path to write the pre-change snapshot")
    ap.add_argument("--rollback", help="restore from a snapshot written by --backup")
    args = ap.parse_args(argv)

    db = SessionLocal()
    try:
        if args.rollback:
            with open(args.rollback) as fh:
                backup = json.load(fh)
            recorded = backup.get("checksum_sha256")
            recomputed = _sha256({k: v for k, v in backup.items() if k != "checksum_sha256"})
            if recorded and recorded != recomputed:
                print("REFUSING: backup checksum does not match its contents")
                return 2
            print(json.dumps(rollback(db, backup), indent=2))
            return 0

        snapshot = collect(db)
        changes = plan(db)

        if not args.apply:
            print(f"DRY RUN (no writes). Snapshot: {snapshot['counts']}")
            for c in changes:
                print(f"  WOULD rename {c['kind']} {c['id']}: {c['from']!r} -> {c['to']!r}"
                      + (f" (slug {c['current_slug']!r} -> {c['slug_to']!r})" if c["kind"] == "brand" else ""))
            if not changes:
                print("  nothing to rename")
            return 0

        if not args.backup:
            print("REFUSING: --apply requires --backup <file>. The backup is the rollback.")
            return 2
        if os.path.exists(args.backup):
            print(f"REFUSING: {args.backup} already exists; use a new timestamped path")
            return 2
        with open(args.backup, "w") as fh:
            json.dump(snapshot, fh, indent=2)
        print(f"backup written: {args.backup} ({os.path.getsize(args.backup)} B, sha256 {snapshot['checksum_sha256'][:16]}…)")

        result = apply(db, changes, args.backup)
        print(json.dumps(result, indent=2))

        after = collect(db)
        print(json.dumps({"label": "after", "counts": after["counts"],
                          "brands": [{"id": b["id"], "brand_name": b["brand_name"], "slug": b["slug"]} for b in after["brands"]],
                          "stores": [{"id": s["id"], "name": s["name"]} for s in after["stores"]]}, indent=2))
        return 0 if not result["failed"] else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
