#!/usr/bin/env python3
"""Detective control for the brand portal's tenant + billing invariants.

Run against ANY environment (local, staging, production) to get evidence
rather than assurances:

    DATABASE_URL='postgresql://...' python scripts/audit_brand_tenant_integrity.py
    # add --json for machine-readable output, --fail-on-violation for CI

Checks
------
1. CROSS-TENANT STORE INVENTORY  (the P1 leak)
   store_inventories rows whose store and SKU belong to different brands.
   Must be 0. Non-zero means one tenant can read another's store and stock.

2. COUNT / BREAKDOWN CONSISTENCY  (the visible symptom)
   For every brand: if it has 0 stores it must have 0 store-inventory rows.
   This is precisely the "Store Locations (0) ... Store #1: 6 avail" defect.

3. ORPHANED / UNSCOPED INVENTORY
   Rows with a NULL brand_id (pre-0019 legacy) that the composite FK cannot
   protect yet.

4. AD BILLING RECONCILIATION
   For every placement: SUM(billable ad_ledger_entries.amount) for its current
   spend_date must equal spent_today, and spent_today must never exceed
   daily_budget.

5. STALE DAILY BUDGET WINDOWS
   Placements whose spend_date is in the past but still carry spend — they
   will roll over lazily on next touch; reported for visibility.

Exit code is 1 when --fail-on-violation is set and any check fails, so this
can gate a deploy.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone

try:
    from sqlalchemy import create_engine, text
except ImportError:  # pragma: no cover
    print("SQLAlchemy is required: pip install sqlalchemy psycopg2-binary", file=sys.stderr)
    raise SystemExit(2)


CHECKS: list[dict] = []


def check(name: str, description: str):
    def wrap(fn):
        CHECKS.append({"name": name, "description": description, "fn": fn})
        return fn
    return wrap


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{table}"}).scalar())


def _column_exists(conn, table: str, column: str) -> bool:
    return bool(conn.execute(text("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = :t AND column_name = :c
    """), {"t": table, "c": column}).first())


@check("cross_tenant_inventory",
       "store_inventories rows whose store and SKU belong to different brands")
def check_cross_tenant(conn):
    rows = conn.execute(text("""
        SELECT si.id, si.store_id, si.sku_id,
               sl.brand_id AS store_brand_id, p.brand_id AS product_brand_id, si.quantity
          FROM store_inventories si
          JOIN store_locations sl ON sl.id = si.store_id
          JOIN product_skus sk    ON sk.id = si.sku_id
          JOIN products p         ON p.id  = sk.product_id
         WHERE sl.brand_id <> p.brand_id
         ORDER BY si.id
    """)).mappings().all()
    return [dict(r) for r in rows]


@check("store_count_breakdown_mismatch",
       "brands with zero stores that still have store-level inventory rows")
def check_mismatch(conn):
    rows = conn.execute(text("""
        SELECT bp.id AS brand_id, bp.brand_name,
               (SELECT count(*) FROM store_locations sl WHERE sl.brand_id = bp.id) AS store_count,
               (SELECT count(*)
                  FROM store_inventories si
                  JOIN product_skus sk ON sk.id = si.sku_id
                  JOIN products p      ON p.id  = sk.product_id
                 WHERE p.brand_id = bp.id) AS inventory_rows
          FROM brand_profiles bp
         ORDER BY bp.id
    """)).mappings().all()
    return [dict(r) for r in rows
            if r["store_count"] == 0 and r["inventory_rows"] > 0]


@check("unscoped_inventory_rows",
       "store_inventories rows with NULL brand_id (not protected by the composite FK)")
def check_unscoped(conn):
    if not _column_exists(conn, "store_inventories", "brand_id"):
        return [{"note": "brand_id column absent — migration 0019 has not been applied"}]
    rows = conn.execute(text("""
        SELECT id, store_id, sku_id FROM store_inventories
         WHERE brand_id IS NULL ORDER BY id LIMIT 200
    """)).mappings().all()
    return [dict(r) for r in rows]


@check("ad_billing_reconciliation",
       "placement spent_today must equal the billable ledger sum for its spend_date")
def check_reconciliation(conn):
    if not _table_exists(conn, "ad_ledger_entries"):
        return [{"note": "ad_ledger_entries absent — migration 0019 has not been applied"}]
    rows = conn.execute(text("""
        SELECT sp.id AS placement_id, sp.brand_id, sp.spend_date,
               sp.spent_today,
               COALESCE((SELECT SUM(l.amount) FROM ad_ledger_entries l
                          WHERE l.placement_id = sp.id
                            AND l.spend_date = sp.spend_date
                            AND l.billable), 0) AS ledger_total,
               sp.daily_budget
          FROM sponsored_placements sp
         ORDER BY sp.id
    """)).mappings().all()
    bad = []
    for r in rows:
        d = dict(r)
        if r["spend_date"] is not None and round(float(r["spent_today"]), 2) != round(float(r["ledger_total"]), 2):
            d["problem"] = "counter does not match ledger"
            bad.append(d)
        elif float(r["spent_today"]) > float(r["daily_budget"]):
            d["problem"] = "spend exceeds daily budget"
            bad.append(d)
    return bad


@check("stale_budget_windows",
       "placements carrying spend attributed to a past day (roll over on next touch)")
def check_stale(conn):
    if not _column_exists(conn, "sponsored_placements", "spend_date"):
        return [{"note": "spend_date absent — migration 0019 has not been applied"}]
    rows = conn.execute(text("""
        SELECT id AS placement_id, brand_id, spend_date, spent_today, status
          FROM sponsored_placements
         WHERE spend_date IS NOT NULL
           AND spend_date < CURRENT_DATE
           AND spent_today > 0
         ORDER BY id
    """)).mappings().all()
    return [dict(r) for r in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--fail-on-violation", action="store_true",
                        help="exit 1 if any check reports rows (use in CI)")
    args = parser.parse_args()

    if not args.database_url:
        print("DATABASE_URL is required (env or --database-url)", file=sys.stderr)
        return 2

    engine = create_engine(args.database_url)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": [],
        "violations_total": 0,
    }

    with engine.connect() as conn:
        for spec in CHECKS:
            try:
                findings = spec["fn"](conn)
                informational = all("note" in f for f in findings) if findings else False
                entry = {
                    "name": spec["name"],
                    "description": spec["description"],
                    "violations": 0 if informational else len(findings),
                    "informational": informational,
                    "findings": findings[:50],
                    "status": "PASS" if (not findings or informational) else "FAIL",
                }
            except Exception as exc:  # a check that cannot run must not look like a pass
                entry = {"name": spec["name"], "description": spec["description"],
                         "violations": 0, "status": "ERROR", "error": str(exc)[:500],
                         "findings": []}
            report["checks"].append(entry)
            report["violations_total"] += entry["violations"]

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(f"\nCONFIT brand-portal integrity audit — {report['generated_at']}")
        print("=" * 78)
        for c in report["checks"]:
            icon = {"PASS": "PASS ", "FAIL": "FAIL ", "ERROR": "ERROR"}[c["status"]]
            print(f"[{icon}] {c['name']}: {c['violations']} violation(s)")
            print(f"         {c['description']}")
            if c["status"] == "ERROR":
                print(f"         error: {c['error']}")
            for f in c["findings"][:10]:
                print(f"         -> {f}")
        print("=" * 78)
        print(f"TOTAL VIOLATIONS: {report['violations_total']}")

    if args.fail_on_violation and (report["violations_total"] > 0
                                   or any(c["status"] == "ERROR" for c in report["checks"])):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
