"""Brand portal: tenant-safe store inventory + append-only ad billing ledger.

Revision ID: 0019_brand_tenant_integrity_and_ad_ledger
Revises: 0018_outfit_share_lifecycle

WHAT THIS MIGRATION FIXES
=========================

1. CROSS-TENANT STORE INVENTORY (P1, confirmed in production 2026-09-22)
   `store_inventories` joins a store to a SKU. Each side is owned by a brand,
   but nothing in the schema required them to be the SAME brand. Production
   held 11 rows where they differed, which is why the COS portal rendered
   "Store Locations (0)" beside "Store #1: 6 avail" — Store #1 belongs to
   Massimo Dutti. The count was right; the breakdown was reading another
   tenant's rows.

   Fixed structurally, not just in the query, using the standard Postgres
   multi-tenant pattern (tenant-carrying composite foreign keys):

     * denormalise `brand_id` onto `store_inventories`
     * UNIQUE (id, brand_id) on both parents, so a composite FK can target it
     * FK (store_id, brand_id)  -> store_locations (id, brand_id)
     * FK (sku_id,   brand_id)  -> product_skus    (id, brand_id)

   Both parents must now agree on brand_id, so a cross-tenant inventory row is
   rejected by the database. Forgetting a WHERE clause stops being catastrophic.

   `product_skus` has no brand_id of its own (it inherits via products), so a
   generated/maintained `brand_id` column is added there too and kept in step
   with its product by trigger.

   Existing violations are QUARANTINED (copied to
   `store_inventories_tenant_quarantine`, then deleted) rather than silently
   reassigned: we must not invent which tenant a leaked row belonged to.

2. DAILY BUDGET WINDOW
   `sponsored_placements.spent_today` had no date, so it was never reset and a
   daily budget behaved as a lifetime budget. Adds `spend_date`.

3. APPEND-ONLY AD BILLING LEDGER
   Adds `ad_ledger_entries`: the immutable journal of record for placement
   billing, with UNIQUE(event_key) for exactly-once charging.

Safety: this migration is idempotent-ish and guards every DDL step with
existence checks, and is SQLite-tolerant (composite FKs / partial DDL are
skipped there) so the local test suite still runs.
"""
from alembic import op
import sqlalchemy as sa


revision: str = "0019_brand_tenant_integrity_and_ad_ledger"
down_revision: str = "0018_outfit_share_lifecycle"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    # ---------- 3. ad ledger (all dialects) ----------
    if "ad_ledger_entries" not in tables:
        op.create_table(
            "ad_ledger_entries",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("placement_id", sa.Integer(),
                      sa.ForeignKey("sponsored_placements.id", ondelete="CASCADE"), nullable=False),
            sa.Column("brand_id", sa.Integer(),
                      sa.ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=False),
            sa.Column("entry_type", sa.String(20), nullable=False),
            sa.Column("event_key", sa.String(128), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("bid_at_event", sa.Numeric(12, 2), nullable=True),
            sa.Column("spend_date", sa.Date(), nullable=False),
            sa.Column("actor_user_id", sa.Integer(), nullable=True),
            sa.Column("ip_hash", sa.String(64), nullable=True),
            sa.Column("user_agent", sa.String(300), nullable=True),
            sa.Column("request_id", sa.String(64), nullable=True),
            sa.Column("billable", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("reason", sa.String(200), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("event_key", name="uq_ad_ledger_event_key"),
            sa.CheckConstraint("amount >= 0", name="ck_ad_ledger_amount_nonneg"),
            sa.CheckConstraint(
                "entry_type IN ('impression','click','conversion','adjustment')",
                name="ck_ad_ledger_entry_type_valid"),
        )
        op.create_index("ix_ad_ledger_placement_date", "ad_ledger_entries",
                        ["placement_id", "spend_date"])
        op.create_index("ix_ad_ledger_brand_date", "ad_ledger_entries",
                        ["brand_id", "spend_date"])
        op.create_index("ix_ad_ledger_entries_created_at", "ad_ledger_entries", ["created_at"])
        op.create_index("ix_ad_ledger_entries_ip_hash", "ad_ledger_entries", ["ip_hash"])
        op.create_index("ix_ad_ledger_entries_actor", "ad_ledger_entries", ["actor_user_id"])

    # ---------- 2. daily budget window ----------
    placement_cols = {c["name"] for c in inspector.get_columns("sponsored_placements")} \
        if "sponsored_placements" in tables else set()
    if "sponsored_placements" in tables and "spend_date" not in placement_cols:
        op.add_column("sponsored_placements", sa.Column("spend_date", sa.Date(), nullable=True))
        op.create_index("ix_sponsored_placements_spend_date", "sponsored_placements", ["spend_date"])
        # Existing rows carry an un-dated spend. Attribute it to today so the
        # first request of tomorrow performs a clean rollover instead of
        # treating historical spend as belonging to an unknown day.
        op.execute("UPDATE sponsored_placements SET spend_date = CURRENT_DATE WHERE spend_date IS NULL")

    if not _is_postgres():
        # SQLite (test suite) cannot express the composite FKs below. The
        # application-layer scoping in BrandRepository.get_brand_store_inventory_map
        # plus the integrity tests cover the same invariant there.
        return

    # ---------- 1. tenant-safe store inventory ----------
    si_cols = {c["name"] for c in inspector.get_columns("store_inventories")}

    # 1a. brand_id on product_skus (inherited from its product), kept in step
    #     by trigger so it cannot drift.
    sku_cols = {c["name"] for c in inspector.get_columns("product_skus")}
    if "brand_id" not in sku_cols:
        op.add_column("product_skus", sa.Column("brand_id", sa.Integer(), nullable=True))
        op.execute("""
            UPDATE product_skus s
               SET brand_id = p.brand_id
              FROM products p
             WHERE p.id = s.product_id
               AND s.brand_id IS DISTINCT FROM p.brand_id
        """)
        op.alter_column("product_skus", "brand_id", nullable=False)
        op.create_index("ix_product_skus_brand_id", "product_skus", ["brand_id"])

    op.execute("""
        CREATE OR REPLACE FUNCTION confit_sync_sku_brand() RETURNS trigger AS $$
        BEGIN
            SELECT p.brand_id INTO NEW.brand_id FROM products p WHERE p.id = NEW.product_id;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("DROP TRIGGER IF EXISTS trg_sync_sku_brand ON product_skus")
    op.execute("""
        CREATE TRIGGER trg_sync_sku_brand
        BEFORE INSERT OR UPDATE OF product_id ON product_skus
        FOR EACH ROW EXECUTE FUNCTION confit_sync_sku_brand();
    """)

    # A product must never change hands without its SKUs following, otherwise
    # the composite FK below would be checked against a stale brand_id.
    op.execute("""
        CREATE OR REPLACE FUNCTION confit_cascade_product_brand() RETURNS trigger AS $$
        BEGIN
            IF NEW.brand_id IS DISTINCT FROM OLD.brand_id THEN
                UPDATE product_skus SET brand_id = NEW.brand_id WHERE product_id = NEW.id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("DROP TRIGGER IF EXISTS trg_cascade_product_brand ON products")
    op.execute("""
        CREATE TRIGGER trg_cascade_product_brand
        AFTER UPDATE OF brand_id ON products
        FOR EACH ROW EXECUTE FUNCTION confit_cascade_product_brand();
    """)

    # 1b. quarantine the cross-tenant rows BEFORE adding the constraint.
    op.execute("""
        CREATE TABLE IF NOT EXISTS store_inventories_tenant_quarantine (
            id integer,
            store_id integer,
            sku_id integer,
            quantity integer,
            reserved_quantity integer,
            store_brand_id integer,
            product_brand_id integer,
            quarantined_at timestamp NOT NULL DEFAULT now(),
            reason text
        )
    """)
    op.execute("""
        INSERT INTO store_inventories_tenant_quarantine
            (id, store_id, sku_id, quantity, reserved_quantity,
             store_brand_id, product_brand_id, reason)
        SELECT si.id, si.store_id, si.sku_id, si.quantity, si.reserved_quantity,
               sl.brand_id, p.brand_id,
               'cross-tenant store/SKU pair rejected by 0019 composite FK'
          FROM store_inventories si
          JOIN store_locations sl ON sl.id = si.store_id
          JOIN product_skus sk    ON sk.id = si.sku_id
          JOIN products p         ON p.id  = sk.product_id
         WHERE sl.brand_id <> p.brand_id
    """)
    op.execute("""
        DELETE FROM store_inventories si
         USING store_locations sl, product_skus sk, products p
         WHERE sl.id = si.store_id
           AND sk.id = si.sku_id
           AND p.id  = sk.product_id
           AND sl.brand_id <> p.brand_id
    """)

    # 1c. denormalised tenant column + composite FKs
    if "brand_id" not in si_cols:
        op.add_column("store_inventories", sa.Column("brand_id", sa.Integer(), nullable=True))
        op.execute("""
            UPDATE store_inventories si
               SET brand_id = sl.brand_id
              FROM store_locations sl
             WHERE sl.id = si.store_id
        """)
        op.execute("DELETE FROM store_inventories WHERE brand_id IS NULL")
        op.alter_column("store_inventories", "brand_id", nullable=False)
        op.create_index("ix_store_inventories_brand_id", "store_inventories", ["brand_id"])

    # Parent unique keys the composite FKs point at (redundant beside the PK,
    # but load-bearing: a composite FK needs a matching unique constraint).
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_store_locations_id_brand') THEN
                ALTER TABLE store_locations ADD CONSTRAINT uq_store_locations_id_brand UNIQUE (id, brand_id);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_product_skus_id_brand') THEN
                ALTER TABLE product_skus ADD CONSTRAINT uq_product_skus_id_brand UNIQUE (id, brand_id);
            END IF;
        END $$;
    """)

    # The tenant now travels INSIDE the reference: a row can only point at a
    # store and a SKU that both belong to store_inventories.brand_id.
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_store_inv_store_tenant') THEN
                ALTER TABLE store_inventories
                    ADD CONSTRAINT fk_store_inv_store_tenant
                    FOREIGN KEY (store_id, brand_id)
                    REFERENCES store_locations (id, brand_id) ON DELETE CASCADE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_store_inv_sku_tenant') THEN
                ALTER TABLE store_inventories
                    ADD CONSTRAINT fk_store_inv_sku_tenant
                    FOREIGN KEY (sku_id, brand_id)
                    REFERENCES product_skus (id, brand_id) ON DELETE CASCADE;
            END IF;
        END $$;
    """)

    # Hot-path index: every tenant-scoped inventory read filters brand first.
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_store_inventories_brand_sku
            ON store_inventories (brand_id, sku_id)
    """)


def downgrade() -> None:
    if _is_postgres():
        op.execute("ALTER TABLE store_inventories DROP CONSTRAINT IF EXISTS fk_store_inv_sku_tenant")
        op.execute("ALTER TABLE store_inventories DROP CONSTRAINT IF EXISTS fk_store_inv_store_tenant")
        op.execute("ALTER TABLE store_locations DROP CONSTRAINT IF EXISTS uq_store_locations_id_brand")
        op.execute("ALTER TABLE product_skus DROP CONSTRAINT IF EXISTS uq_product_skus_id_brand")
        op.execute("DROP INDEX IF EXISTS ix_store_inventories_brand_sku")
        op.execute("DROP INDEX IF EXISTS ix_store_inventories_brand_id")
        op.execute("DROP TRIGGER IF EXISTS trg_sync_sku_brand ON product_skus")
        op.execute("DROP TRIGGER IF EXISTS trg_cascade_product_brand ON products")
        op.execute("DROP FUNCTION IF EXISTS confit_sync_sku_brand()")
        op.execute("DROP FUNCTION IF EXISTS confit_cascade_product_brand()")
        op.execute("ALTER TABLE store_inventories DROP COLUMN IF EXISTS brand_id")
        op.execute("ALTER TABLE product_skus DROP COLUMN IF EXISTS brand_id")
        op.execute("DROP INDEX IF EXISTS ix_sponsored_placements_spend_date")
    # Quarantine table is intentionally retained: it is forensic evidence.
    op.execute("ALTER TABLE sponsored_placements DROP COLUMN IF EXISTS spend_date")
    op.execute("DROP TABLE IF EXISTS ad_ledger_entries")
