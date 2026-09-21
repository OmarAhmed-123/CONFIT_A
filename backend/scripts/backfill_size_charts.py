"""Backfill `products.size_chart_json` for the seeded demo catalogue.

`seed_database()` refuses to touch a database that already has users, which is
correct — it must never wipe real data. The consequence is that the size charts
added in PR #126 reach a fresh database only, so the existing production
catalogue kept `size_chart_json = "{}"` and the engine kept falling back to the
EN 13402-3 standard there.

This script closes that gap without reseeding anything:

* it matches products by **slug** and touches exactly one column;
* it is **idempotent** — a product that already carries the intended chart is
  skipped, so re-running changes nothing;
* it **never overwrites a non-empty chart** it did not author. If a product has
  some other chart (e.g. a real brand later uploads one), it is left alone and
  reported, because a brand's own measurements always outrank ours;
* `--dry-run` prints the plan and writes nothing.

Usage::

    python -m backend.scripts.backfill_size_charts --dry-run
    python -m backend.scripts.backfill_size_charts
"""

from __future__ import annotations

import argparse
import json
import sys

from backend.app.core.database import SessionLocal
from backend.app.models.catalog import Product
from backend.app.seed_size_charts import SIZE_CHARTS_BY_SLUG, size_chart_json_for_slug

EMPTY = {"", "{}", "null", "[]"}


def _is_empty(raw: str | None) -> bool:
    return (raw or "").strip() in EMPTY


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
    args = parser.parse_args()

    db = SessionLocal()
    updated, skipped, foreign, missing = [], [], [], []
    try:
        for slug in sorted(SIZE_CHARTS_BY_SLUG):
            product = db.query(Product).filter(Product.slug == slug).one_or_none()
            if product is None:
                missing.append(slug)
                continue

            intended = size_chart_json_for_slug(slug)
            current = product.size_chart_json

            if not _is_empty(current):
                try:
                    same = json.loads(current) == json.loads(intended)
                except (ValueError, TypeError):
                    same = False
                (skipped if same else foreign).append(slug)
                continue

            if not args.dry_run:
                product.size_chart_json = intended
            updated.append(slug)

        if not args.dry_run:
            db.commit()
    finally:
        db.close()

    verb = "would update" if args.dry_run else "updated"
    print(f"{verb}: {len(updated)}")
    for s in updated:
        print(f"  + {s}")
    if skipped:
        print(f"already correct (no-op): {len(skipped)}")
    if foreign:
        print(f"LEFT ALONE — carries a different chart we did not author: {len(foreign)}")
        for s in foreign:
            print(f"  ! {s}")
    if missing:
        print(f"not present in this catalogue: {len(missing)}")
        for s in missing:
            print(f"  ? {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
