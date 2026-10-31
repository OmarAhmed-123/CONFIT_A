# Migration 0047 + 0048 — review and apply checklist (P3)

## Chain

`0046_user_wishlist_items` → `0047_wardrobe_analysis_source` → **`0048_wardrobe_outfits`** (new head)

| Rev | Change | Reversible | Data touched | Lock risk |
|---|---|---|---|---|
| 0047 | `wardrobe_items.analysis_source VARCHAR(120) NULL`, `analysis_description TEXT NULL` | yes (drop columns) | none (no backfill; NULL is the truthful historical state) | `ADD COLUMN … NULL` without default = metadata-only on PG ≥ 11 |
| 0048 | new tables `wardrobe_outfits`, `wardrobe_outfit_items` (+3 indexes), GRANTs to `confit_app_rw` | yes (drop tables) | none | new objects only |

Both are idempotent (inspector guards) and additive. Downgrade of 0048 drops
saved looks — acceptable because the feature ships with it; downgrade of 0047
loses provenance labels only.

## Verification performed

| Check | Where | Result |
|---|---|---|
| Chain parses, single head, `test_flow_e` pins head = 0048 | `backend/tests/test_flow_e_purchase_to_wardrobe.py` | PASS |
| Schema gate lists new tables; ORM ↔ required-objects parity | `backend/app/core/schema_gate.py`, `test_schema_drift_gate.py` | PASS |
| empty → head → `0046` → head on **sqlite** | `alembic -c backend/alembic.ini upgrade head / downgrade / upgrade` (local) | PASS (`alembic_version = 0048_wardrobe_outfits`, both tables present) |
| empty → head → base → head on **PostgreSQL 17** + gate verdict | CI job `postgres migration chain + schema gate` (`backend/scripts/check_migration_chain_postgres.py`) | **PASS — AUTOMATED on `f1a881d` (the push carrying 0048)**, GitHub check-run SUCCESS |
| empty → head → `0046` → head on **PostgreSQL 16** (local, UTF8) + object inspection | re-validation pass 2026-10-26: `alembic upgrade head / downgrade 0046 / upgrade head`, then `pg_constraint` / `pg_indexes` / `information_schema.columns` | **PASS — VERIFIED**: single head `0048_wardrobe_outfits`; `wardrobe_items.analysis_source` + `analysis_description` present; `wardrobe_outfit_items` FKs `…_outfit_id_fkey` and `…_wardrobe_item_id_fkey` both `confdeltype = c` (ON DELETE CASCADE); indexes `ix_wardrobe_outfits_user_id`, `ix_wardrobe_outfit_items_outfit_id`, `ix_wardrobe_outfit_items_wardrobe_item_id` present |
| FK cascade observed through the API on PostgreSQL | `docs/qa/load/style_list_negative_tests_postgres.json` ("outfit readable after item delete") | PASS — deleting a garment leaves the look readable with `items=[]`, no 5xx |
| Grants to `confit_app_rw` | 0048 `GRANT` statements | **NOT RUN on Neon** (quota lock); the local rig has no such role, so the grants are exercised only by CI's chain job |
| Behaviour on top of the schema | `test_wardrobe_saved_outfits.py` (7), `test_watsonx_stylist.py` (37) | PASS |

## Database state actually observed (2026-10-26, re-probed in the re-validation pass the same day)

| Environment | Host | Observation |
|---|---|---|
| staging `confit_fixverify` (owner + `confit_app_rw`) | Neon project endpoint (eu-central-1; host kept in the local env file) | **Connection refused by Neon: "Your account or project has exceeded the quota. Upgrade your plan to increase limits."** Revision could **not** be read. **Re-probed (read-only, both roles): still refused.** → **BLOCKED** |
| production `neondb` (owner + `confit_app_rw`) | same Neon project | **Same quota refusal.** Revision could **not** be read. **Re-probed: still refused.** → **BLOCKED** |

Recovery owner: the Neon account holder (billing). Action: upgrade the plan or
delete/suspend unused branches/compute to drop under quota, then re-run step 0
below. This cannot be performed from the repository or with the credentials
available here (no Neon API key; the console is a billing action).

Consequence: `alembic_version` for both environments is **NOT VERIFIED** this
session; last known (session 1, before the quota lock) was that 0047 had **not**
been applied anywhere. Nothing was applied. Production also serves HTTP 402
`DEPLOYMENT_DISABLED` from Vercel, so no running app depends on the schema right now.

## Startup note for PostgreSQL in non-production environments (found 2026-10-26)

Before this pass, `backend/app/main.py` held the catalogue-probe session open
while calling `seed_database()` on an **empty** catalogue. On PostgreSQL that
self-deadlocks (idle-in-transaction AccessShareLock on `categories` vs. the
seeder's `DROP TABLE products`), so a fresh non-production Postgres database
never finished starting — invisible on SQLite. Fixed (probe closed before
seeding; regression test `backend/tests/test_startup_seed_no_open_session.py`).
Production is unaffected (the dev seed path is skipped when
`ENVIRONMENT=production`). Two residual, documented behaviours: (a) with
several workers on an *empty* dev catalogue, every worker attempts the seed and
all but one log a benign "Database initialization notice"; seed once with a
single worker or pre-seed; (b) the seeder writes Arabic names, so the database
must be `UTF8` (Neon is; a locally `initdb`'d cluster without a locale is
`SQL_ASCII` and rejects the seed).

### Update 2026-10-27 — residual behaviour (a) was not benign; fixed

Reproduced on PostgreSQL 17.11 with `uvicorn --workers 2` against a database
that was **fully migrated (0048) but empty**: in **3/3** starts, worker A's
seeder `drop_all()`ed while worker B was probing, so B logged
`relation "categories" does not exist` **and its schema gate recorded
`verdict=drift, blocking=True`** (in development that is a log line; the
same words in a staging log would send an operator chasing a migration
problem that does not exist). Fix: `backend/app/core/startup_lock.py` — a
PostgreSQL session advisory lock on a dedicated AUTOCOMMIT connection
serialises the decide-and-seed step (no table locks, so the 2026-10-26
deadlock class cannot return; no-op on SQLite). After the fix: 3/3 starts,
both workers `verdict=ok`, seeded exactly once, zero notices. Tests:
`backend/tests/test_startup_seed_lock_postgres.py` (runs in the CI
isolated-PostgreSQL step). Production is unaffected either way (it never
seeds); the per-environment 0047/0048 state in Neon staging/prod remains
**NOT VERIFIED** (quota lock, re-checked 2026-10-27 15:00 UTC).

Also re-run today on PostgreSQL 17.11: `alembic upgrade head` from empty,
`downgrade 0046` → `upgrade head` → `current` = `0048_wardrobe_outfits (head)`;
`wardrobe_outfits` columns present. PASS.

## Apply procedure (staging first; production only with explicit written authorisation)

```bash
set -a && source ~/.env.local && set +a        # never commit these
export PYTHONPATH=.
# 0) preflight — read-only
python - <<'PY'
import os, psycopg2
c = psycopg2.connect(os.environ["DATABASE_URL_OWNER_FIXVERIFY"]); c.set_session(readonly=True)
cur = c.cursor(); cur.execute("select version_num from alembic_version"); print(cur.fetchall())
cur.execute("select count(*) from wardrobe_items"); print("wardrobe_items", cur.fetchone())
PY
# 1) backup / branch — Neon: create a branch from the target DB in the console (instant PITR point)
# 2) dry run SQL
DATABASE_URL="$DATABASE_URL_OWNER_FIXVERIFY" alembic -c backend/alembic.ini upgrade 0046_user_wishlist_items:head --sql > /tmp/0047_0048.sql
less /tmp/0047_0048.sql
# 3) apply with the OWNER role (the app role cannot create objects)
DATABASE_URL="$DATABASE_URL_OWNER_FIXVERIFY" alembic -c backend/alembic.ini upgrade head
# 4) verify
DATABASE_URL="$DATABASE_URL_APP_RW_FIXVERIFY" python backend/scripts/check_release_schema_parity.py
#    expect verdict ok, head = 0048_wardrobe_outfits; then as confit_app_rw:
#    INSERT/SELECT/DELETE on wardrobe_outfits must succeed (grants).
# 5) smoke the API against staging: POST /wardrobe/outfits round trip (tests above as a script)
# 6) rollback plan: alembic downgrade 0046_user_wishlist_items  (or restore Neon branch)
```

Production: repeat 0–6 against `DATABASE_URL_OWNER_NEONDB` **only after**
(a) Neon quota is lifted, (b) the Vercel deployment is re-enabled, (c) the
operator authorises it in writing. Until then the release gate will keep
failing on `/health` and the schema gate will report drift (expected head 0048).
