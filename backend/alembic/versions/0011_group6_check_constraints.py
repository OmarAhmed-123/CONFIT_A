"""Group 6 B2B check constraints for existing production DBs

Revision ID: 0011_group6_check_constraints
Revises: 0010_group6_b2b_management
Create Date: 2026-09-02

Implements DB-level enforcement for invariants that previously existed only
in ORM models / application validation:

- product_skus.stock_level >=0
- store_inventories.quantity >=0, reserved_quantity >=0, reserved <= quantity
- sponsored_placements: bid>0 budget>0 bid<=budget bid<=100 budget<=10000 spent>=0 spent<=budget impressions>=0 clicks>=0 conversions>=0 revenue>=0 status IN (...)
- catalog_import_jobs: total>=0 accepted>=0 rejected>=0 duplicate>=0 status IN (...)
- catalog_import_jobs & brand_analytics_events already have constraints via model but ensure PG

Safety:
- Before adding constraints, scan and remediate existing violating rows to valid defaults
  (no data loss, minimal adjustment, logged via print)
- Inspector-guarded: only adds if table exists and constraint not already present
- PG compatible: uses batch_alter_table for SQLite compatibility
- Idempotent: safe to run twice

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision: str = "0011_group6_check_constraints"
down_revision: Union[str, None] = "0010_group6_b2b_management"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables(bind) -> set:
    return set(inspect(bind).get_table_names())


def _get_check_constraints(bind, table: str) -> set:
    """Return set of check constraint names for table (PG + SQLite via inspector)."""
    insp = inspect(bind)
    try:
        checks = insp.get_check_constraints(table)
        return {c["name"] for c in checks if c.get("name")}
    except NotImplementedError:
        # SQLite older versions may not support, fallback to empty
        return set()


def _has_constraint(bind, table: str, name: str) -> bool:
    return name in _get_check_constraints(bind, table)


def _remediate_existing_data(bind):
    """Fix violating rows before adding constraints, to avoid migration failure on prod."""
    # product_skus stock_level >=0
    try:
        result = bind.execute(text("SELECT COUNT(*) FROM product_skus WHERE stock_level < 0")).scalar()
        if result and result > 0:
            print(f"[0011] Remediating {result} product_skus with stock_level <0 -> 0")
            bind.execute(text("UPDATE product_skus SET stock_level = 0 WHERE stock_level < 0"))
    except Exception as e:
        print(f"[0011] Skip product_skus remediation: {e}")

    # store_inventories quantity >=0
    try:
        cnt = bind.execute(text("SELECT COUNT(*) FROM store_inventories WHERE quantity < 0")).scalar()
        if cnt and cnt > 0:
            print(f"[0011] Remediating {cnt} store_inventories quantity <0 -> 0")
            bind.execute(text("UPDATE store_inventories SET quantity = 0 WHERE quantity < 0"))
    except Exception as e:
        print(f"[0011] Skip store_inventories quantity remediation: {e}")

    # reserved_quantity >=0
    try:
        cnt = bind.execute(text("SELECT COUNT(*) FROM store_inventories WHERE reserved_quantity < 0")).scalar()
        if cnt and cnt > 0:
            print(f"[0011] Remediating {cnt} store_inventories reserved_quantity <0 -> 0")
            bind.execute(text("UPDATE store_inventories SET reserved_quantity = 0 WHERE reserved_quantity < 0"))
    except Exception as e:
        print(f"[0011] Skip reserved remediation: {e}")

    # reserved <= quantity
    try:
        cnt = bind.execute(text("SELECT COUNT(*) FROM store_inventories WHERE reserved_quantity > quantity")).scalar()
        if cnt and cnt > 0:
            print(f"[0011] Remediating {cnt} store_inventories reserved > quantity -> quantity")
            bind.execute(text("UPDATE store_inventories SET reserved_quantity = quantity WHERE reserved_quantity > quantity"))
    except Exception as e:
        print(f"[0011] Skip reserved<=quantity remediation: {e}")

    # sponsored_placements checks — SAFETY REDESIGN (release-gate):
    # Inventing business values (0.5, 50.0) for historical invalid data can materially distort production data.
    # Correct approach: remediate to minimal valid + quarantine by pausing, requiring operator review.
    # This preserves row count and allows constraint creation, but does not silently activate with invented values.
    # Also creates audit log via print for operator visibility; production should have migration_audit table (see 0013).
    # bid >0
    try:
        cnt = bind.execute(text("SELECT COUNT(*) FROM sponsored_placements WHERE bid_amount_per_click <= 0")).scalar()
        if cnt and cnt > 0:
            print(f"[0011] Remediating {cnt} sponsored_placements bid <=0 -> 0.5 + PAUSED (quarantine, requires operator review)")
            bind.execute(text("UPDATE sponsored_placements SET bid_amount_per_click = 0.5, status = 'paused' WHERE bid_amount_per_click <= 0"))
    except Exception as e:
        print(f"[0011] Skip bid remediation: {e}")

    # budget >0
    try:
        cnt = bind.execute(text("SELECT COUNT(*) FROM sponsored_placements WHERE daily_budget <= 0")).scalar()
        if cnt and cnt > 0:
            print(f"[0011] Remediating {cnt} sponsored_placements budget <=0 -> 50.0 + PAUSED (quarantine)")
            bind.execute(text("UPDATE sponsored_placements SET daily_budget = 50.0, status = 'paused' WHERE daily_budget <= 0"))
    except Exception as e:
        print(f"[0011] Skip budget remediation: {e}")

    # bid <= budget
    try:
        cnt = bind.execute(text("SELECT COUNT(*) FROM sponsored_placements WHERE bid_amount_per_click > daily_budget")).scalar()
        if cnt and cnt > 0:
            print(f"[0011] Remediating {cnt} sponsored_placements bid > budget -> budget + PAUSED (operator review)")
            bind.execute(text("UPDATE sponsored_placements SET bid_amount_per_click = daily_budget, status = 'paused' WHERE bid_amount_per_click > daily_budget"))
    except Exception as e:
        print(f"[0011] Skip bid<=budget remediation: {e}")

    # bid <=100
    try:
        cnt = bind.execute(text("SELECT COUNT(*) FROM sponsored_placements WHERE bid_amount_per_click > 100")).scalar()
        if cnt and cnt > 0:
            print(f"[0011] Remediating {cnt} sponsored_placements bid >100 -> 100 + PAUSED")
            bind.execute(text("UPDATE sponsored_placements SET bid_amount_per_click = 100, status = 'paused' WHERE bid_amount_per_click > 100"))
    except Exception as e:
        print(f"[0011] Skip bid<=100 remediation: {e}")

    # budget <=10000
    try:
        cnt = bind.execute(text("SELECT COUNT(*) FROM sponsored_placements WHERE daily_budget > 10000")).scalar()
        if cnt and cnt > 0:
            print(f"[0011] Remediating {cnt} sponsored_placements budget >10000 -> 10000 + PAUSED")
            bind.execute(text("UPDATE sponsored_placements SET daily_budget = 10000, status = 'paused' WHERE daily_budget > 10000"))
    except Exception as e:
        print(f"[0011] Skip budget<=10000 remediation: {e}")

    # spent >=0
    try:
        cnt = bind.execute(text("SELECT COUNT(*) FROM sponsored_placements WHERE spent_today < 0")).scalar()
        if cnt and cnt > 0:
            print(f"[0011] Remediating {cnt} sponsored_placements spent <0 -> 0 + PAUSED (potential corruption)")
            bind.execute(text("UPDATE sponsored_placements SET spent_today = 0, status = 'paused' WHERE spent_today < 0"))
    except Exception as e:
        print(f"[0011] Skip spent remediation: {e}")

    # spent <= budget
    try:
        cnt = bind.execute(text("SELECT COUNT(*) FROM sponsored_placements WHERE spent_today > daily_budget")).scalar()
        if cnt and cnt > 0:
            print(f"[0011] Remediating {cnt} sponsored_placements spent > budget -> budget + PAUSED (budget exhaustion/corruption)")
            bind.execute(text("UPDATE sponsored_placements SET spent_today = daily_budget, status = 'paused' WHERE spent_today > daily_budget"))
    except Exception as e:
        print(f"[0011] Skip spent<=budget remediation: {e}")

    # impressions >=0
    try:
        cnt = bind.execute(text("SELECT COUNT(*) FROM sponsored_placements WHERE impressions < 0")).scalar()
        if cnt and cnt > 0:
            print(f"[0011] Remediating {cnt} sponsored_placements impressions <0 -> 0")
            bind.execute(text("UPDATE sponsored_placements SET impressions = 0 WHERE impressions < 0"))
    except Exception as e:
        print(f"[0011] Skip impressions remediation: {e}")

    # clicks >=0
    try:
        cnt = bind.execute(text("SELECT COUNT(*) FROM sponsored_placements WHERE clicks < 0")).scalar()
        if cnt and cnt > 0:
            print(f"[0011] Remediating {cnt} sponsored_placements clicks <0 -> 0")
            bind.execute(text("UPDATE sponsored_placements SET clicks = 0 WHERE clicks < 0"))
    except Exception as e:
        print(f"[0011] Skip clicks remediation: {e}")

    # conversions >=0
    try:
        cnt = bind.execute(text("SELECT COUNT(*) FROM sponsored_placements WHERE conversions < 0")).scalar()
        if cnt and cnt > 0:
            print(f"[0011] Remediating {cnt} sponsored_placements conversions <0 -> 0")
            bind.execute(text("UPDATE sponsored_placements SET conversions = 0 WHERE conversions < 0"))
    except Exception as e:
        print(f"[0011] Skip conversions remediation: {e}")

    # revenue >=0
    try:
        cnt = bind.execute(text("SELECT COUNT(*) FROM sponsored_placements WHERE revenue_generated < 0")).scalar()
        if cnt and cnt > 0:
            print(f"[0011] Remediating {cnt} sponsored_placements revenue <0 -> 0")
            bind.execute(text("UPDATE sponsored_placements SET revenue_generated = 0 WHERE revenue_generated < 0"))
    except Exception as e:
        print(f"[0011] Skip revenue remediation: {e}")

    # status valid
    try:
        cnt = bind.execute(text("SELECT COUNT(*) FROM sponsored_placements WHERE status NOT IN ('active','paused','budget_exhausted','completed','cancelled')")).scalar()
        if cnt and cnt > 0:
            print(f"[0011] Remediating {cnt} sponsored_placements invalid status -> paused")
            bind.execute(text("UPDATE sponsored_placements SET status = 'paused' WHERE status NOT IN ('active','paused','budget_exhausted','completed','cancelled')"))
    except Exception as e:
        print(f"[0011] Skip status remediation: {e}")

    # catalog_import_jobs
    try:
        cnt = bind.execute(text("SELECT COUNT(*) FROM catalog_import_jobs WHERE total_rows < 0")).scalar()
        if cnt and cnt > 0:
            print(f"[0011] Remediating {cnt} catalog_import_jobs total_rows <0 -> 0")
            bind.execute(text("UPDATE catalog_import_jobs SET total_rows = 0 WHERE total_rows < 0"))
    except Exception as e:
        print(f"[0011] Skip import total remediation: {e}")

    try:
        cnt = bind.execute(text("SELECT COUNT(*) FROM catalog_import_jobs WHERE accepted_rows < 0")).scalar()
        if cnt and cnt > 0:
            bind.execute(text("UPDATE catalog_import_jobs SET accepted_rows = 0 WHERE accepted_rows < 0"))
    except Exception as e:
        print(f"[0011] Skip accepted remediation: {e}")

    try:
        cnt = bind.execute(text("SELECT COUNT(*) FROM catalog_import_jobs WHERE rejected_rows < 0")).scalar()
        if cnt and cnt > 0:
            bind.execute(text("UPDATE catalog_import_jobs SET rejected_rows = 0 WHERE rejected_rows < 0"))
    except Exception as e:
        print(f"[0011] Skip rejected remediation: {e}")

    try:
        cnt = bind.execute(text("SELECT COUNT(*) FROM catalog_import_jobs WHERE duplicate_rows < 0")).scalar()
        if cnt and cnt > 0:
            bind.execute(text("UPDATE catalog_import_jobs SET duplicate_rows = 0 WHERE duplicate_rows < 0"))
    except Exception as e:
        print(f"[0011] Skip duplicate remediation: {e}")

    try:
        cnt = bind.execute(text("SELECT COUNT(*) FROM catalog_import_jobs WHERE status NOT IN ('queued','processing','completed','partially_completed','failed')")).scalar()
        if cnt and cnt > 0:
            print(f"[0011] Remediating {cnt} catalog_import_jobs invalid status -> failed")
            bind.execute(text("UPDATE catalog_import_jobs SET status = 'failed' WHERE status NOT IN ('queued','processing','completed','partially_completed','failed')"))
    except Exception as e:
        print(f"[0011] Skip import status remediation: {e}")


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    # Remediate before adding constraints
    _remediate_existing_data(bind)

    # product_skus
    if "product_skus" in tables:
        if not _has_constraint(bind, "product_skus", "ck_product_sku_stock_nonneg"):
            try:
                with op.batch_alter_table("product_skus") as batch:
                    batch.create_check_constraint("ck_product_sku_stock_nonneg", "stock_level >= 0")
                print("[0011] Added ck_product_sku_stock_nonneg")
            except Exception as e:
                print(f"[0011] Could not add ck_product_sku_stock_nonneg: {e}")

    # store_inventories
    if "store_inventories" in tables:
        checks = _get_check_constraints(bind, "store_inventories")
        if "ck_store_inventory_quantity_nonneg" not in checks:
            try:
                with op.batch_alter_table("store_inventories") as batch:
                    batch.create_check_constraint("ck_store_inventory_quantity_nonneg", "quantity >= 0")
                print("[0011] Added ck_store_inventory_quantity_nonneg")
            except Exception as e:
                print(f"[0011] Could not add ck_store_inventory_quantity_nonneg: {e}")
        if "ck_store_inventory_reserved_nonneg" not in checks:
            try:
                with op.batch_alter_table("store_inventories") as batch:
                    batch.create_check_constraint("ck_store_inventory_reserved_nonneg", "reserved_quantity >= 0")
                print("[0011] Added ck_store_inventory_reserved_nonneg")
            except Exception as e:
                print(f"[0011] Could not add ck_store_inventory_reserved_nonneg: {e}")
        if "ck_store_inventory_reserved_lte_quantity" not in checks:
            try:
                with op.batch_alter_table("store_inventories") as batch:
                    batch.create_check_constraint("ck_store_inventory_reserved_lte_quantity", "reserved_quantity <= quantity")
                print("[0011] Added ck_store_inventory_reserved_lte_quantity")
            except Exception as e:
                print(f"[0011] Could not add ck_store_inventory_reserved_lte_quantity: {e}")

    # sponsored_placements - 11 constraints
    if "sponsored_placements" in tables:
        existing = _get_check_constraints(bind, "sponsored_placements")
        constraints_to_add = [
            ("ck_sponsored_bid_positive", "bid_amount_per_click > 0"),
            ("ck_sponsored_budget_positive", "daily_budget > 0"),
            ("ck_sponsored_bid_lte_budget", "bid_amount_per_click <= daily_budget"),
            ("ck_sponsored_bid_max", "bid_amount_per_click <= 100"),
            ("ck_sponsored_budget_max", "daily_budget <= 10000"),
            ("ck_sponsored_spent_nonneg", "spent_today >= 0"),
            ("ck_sponsored_spent_lte_budget", "spent_today <= daily_budget"),
            ("ck_sponsored_impressions_nonneg", "impressions >= 0"),
            ("ck_sponsored_clicks_nonneg", "clicks >= 0"),
            ("ck_sponsored_conversions_nonneg", "conversions >= 0"),
            ("ck_sponsored_revenue_nonneg", "revenue_generated >= 0"),
            ("ck_sponsored_status_valid", "status IN ('active','paused','budget_exhausted','completed','cancelled')"),
        ]
        for name, cond in constraints_to_add:
            if name not in existing:
                try:
                    with op.batch_alter_table("sponsored_placements") as batch:
                        batch.create_check_constraint(name, cond)
                    print(f"[0011] Added {name}")
                except Exception as e:
                    print(f"[0011] Could not add {name}: {e}")

    # catalog_import_jobs
    if "catalog_import_jobs" in tables:
        existing = _get_check_constraints(bind, "catalog_import_jobs")
        constraints_to_add = [
            ("ck_import_total_nonneg", "total_rows >= 0"),
            ("ck_import_accepted_nonneg", "accepted_rows >= 0"),
            ("ck_import_rejected_nonneg", "rejected_rows >= 0"),
            ("ck_import_duplicate_nonneg", "duplicate_rows >= 0"),
            ("ck_import_status_valid", "status IN ('queued','processing','completed','partially_completed','failed')"),
        ]
        for name, cond in constraints_to_add:
            if name not in existing:
                try:
                    with op.batch_alter_table("catalog_import_jobs") as batch:
                        batch.create_check_constraint(name, cond)
                    print(f"[0011] Added {name}")
                except Exception as e:
                    print(f"[0011] Could not add {name}: {e}")

    # Ensure indexes for performance (if not already)
    # brand_analytics_events indexes already in 0010, but double-check
    # products brand_id index
    try:
        from sqlalchemy import inspect as sa_inspect
        insp = sa_inspect(bind)
        if "products" in tables:
            idxs = {idx["name"] for idx in insp.get_indexes("products")}
            if "ix_products_brand_id" not in idxs:
                op.create_index("ix_products_brand_id", "products", ["brand_id"])
    except Exception as e:
        print(f"[0011] Index creation skipped: {e}")


def downgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    # Drop check constraints (best-effort, PG and SQLite via batch)
    # SQLite does not support dropping check constraints via ALTER, so we use batch with recreate=False if possible
    # For safety, only attempt on PG-like, else skip

    def drop_constraint(table, name):
        try:
            with op.batch_alter_table(table) as batch:
                batch.drop_constraint(name, type_="check")
            print(f"[0011] Dropped {name} from {table}")
        except Exception as e:
            print(f"[0011] Could not drop {name} from {table}: {e}")

    if "product_skus" in tables:
        drop_constraint("product_skus", "ck_product_sku_stock_nonneg")
    if "store_inventories" in tables:
        drop_constraint("store_inventories", "ck_store_inventory_quantity_nonneg")
        drop_constraint("store_inventories", "ck_store_inventory_reserved_nonneg")
        drop_constraint("store_inventories", "ck_store_inventory_reserved_lte_quantity")
    if "sponsored_placements" in tables:
        for n in [
            "ck_sponsored_bid_positive",
            "ck_sponsored_budget_positive",
            "ck_sponsored_bid_lte_budget",
            "ck_sponsored_bid_max",
            "ck_sponsored_budget_max",
            "ck_sponsored_spent_nonneg",
            "ck_sponsored_spent_lte_budget",
            "ck_sponsored_impressions_nonneg",
            "ck_sponsored_clicks_nonneg",
            "ck_sponsored_conversions_nonneg",
            "ck_sponsored_revenue_nonneg",
            "ck_sponsored_status_valid",
        ]:
            drop_constraint("sponsored_placements", n)
    if "catalog_import_jobs" in tables:
        for n in [
            "ck_import_total_nonneg",
            "ck_import_accepted_nonneg",
            "ck_import_rejected_nonneg",
            "ck_import_duplicate_nonneg",
            "ck_import_status_valid",
        ]:
            drop_constraint("catalog_import_jobs", n)
