# Database audit — 2026-10-17 (read-only)

Scope: the Neon PostgreSQL database `neondb` (PostgreSQL 16.15, eu-central-1), inspected through the
least-privileged application role in a **read-only session** (`default_transaction_read_only=on`).
No writes, no DDL, no migrations were run against it. Connection strings and passwords are not recorded here.

## 1. Environment and migration state

| Check | Result | Status |
| --- | --- | --- |
| Connectivity | Connected as `confit_app_rw`; `transaction_read_only = on` | PASS |
| Applied Alembic revision | `0036_recently_viewed_unique` | PASS |
| Repo migration head (static, `alembic heads`) | `0036_recently_viewed_unique` (single head) | PASS |
| Pending migrations | none | PASS |
| Repo schema gate, `--env production` | `schema gate: OK  db=0036 expected=0036` | PASS |
| Tables in `public` | 58 (54 ORM-mapped + 4 migration-only) | recorded |
| Foreign keys / unique constraints / indexes | 88 / 16 / 217 | recorded |

## 2. ORM metadata vs. live schema (Alembic `compare_metadata`, read-only)

28 differences. Classified:

**Expected (no action):**
- Migration-only tables with no ORM model: `product_images` (0035), `migration_audit_log`, `store_inventories_tenant_quarantine`, and `alembic_version`. The schema gate already lists these as migration-created.
- Index naming differences. The live DB has equivalent indexes under other names (e.g. `ix_ad_ledger_entries_actor` vs ORM `ix_ad_ledger_entries_actor_user_id`). Column sets match.
- Composite tenant foreign keys and unique constraints present in the DB but not declared in the ORM (`fk_store_inv_*_tenant`, `uq_product_skus_id_brand`, `uq_store_locations_id_brand`). These are the database's tenant-isolation guarantees from migration 0019.

**Real drift — open, not fixed in this change:**
- `product_skus.brand_id` and `store_inventories.brand_id`: the database is **NOT NULL** (migration 0019, `op.alter_column(... nullable=False)`), but the ORM declares `nullable=True`. The live database has 0 NULL rows in both tables.
  - Attempted fix: set `nullable=False` in the ORM. Result: 59 test errors (`sqlite3.IntegrityError: NOT NULL constraint failed: product_skus.brand_id`). The SQLite test fixtures and the app's own seeder insert SKUs without `brand_id`, and only the production trigger `trg_sync_sku_brand` fills it in.
  - Change reverted. The baseline `schema_drift_gate` / `release_schema_parity_gate` / tenant tests pass on the unmodified tree (58 passed, 1 skipped).
  - **Planned fix:** populate `brand_id` in the ORM from the parent (SKU from `products.brand_id`, store inventory from `store_locations.brand_id`) with SQLAlchemy `before_insert` listeners that mirror the DB trigger. Then flip the flag and update the seeder. Verify on PostgreSQL (CI `postgres-migrations` job) and the full SQLite suite.
  - Risk if left as is: none observed on the live DB, because the DB enforces NOT NULL. The gap affects dev/test schemas only.
- `product_skus.stock_level` / other nullable differences: none found beyond the above.

## 3. Data snapshot (row counts, read-only)

Key tables: `users` 57, `orders` 19, `payment_transactions` 19, `products` 12, `product_skus` 28, `store_inventories` 46, `brand_profiles` 4, `audit_logs` 799, `store_inventories_tenant_quarantine` **11**.

**Open item:** `store_inventories_tenant_quarantine` holds 11 rows of cross-tenant inventory quarantined by migration 0019. These need a documented disposition (review and retain, or repair) with the brand owners. Do not delete them without that decision.

Empty tables (0 rows): `checkout_sessions`, `email_outbox`, `exchange_requests`, `migration_audit_log`, `person_scan_cache`, `return_requests`, `return_items`, `shipments`, `style_heatmap_aggregates`, `wardrobe_gap_analyses`, `webhook_events`. These need a live feature test before the feature is called verified.

## 4. Backups and recovery

- **NOT VERIFIED.** A SQL session cannot see Neon's backup or point-in-time-restore status. No Neon management API key is in the local secrets file, so the backup record could not be checked.
- Needed to verify: Neon console or API read access (project and branch restore points), plus a documented restore drill on a **branch** (not on `neondb`).

## 5. Credential hygiene findings

- The local secrets entry `NEON_DATABASE_URL` is **rejected by the server** (password authentication failed for `neondb_owner`). Other stored URLs authenticate. The entry is stale and should be replaced or removed.
- Connection strings and passwords were pasted into chat more than once. Treat them as exposed and rotate them in Neon, especially the `neondb_owner` and `confit_app_rw` passwords.

## 6. Verdict

- Schema and migration state of `neondb`: **consistent with the repo** at head `0036`. The schema gate passes.
- Model-to-database drift: **two known NOT NULL mismatches**. Neither is currently exploitable on the live DB, but both need the planned ORM fix before the drift is closed.
- No production write, migration, or repair was performed in this audit.
