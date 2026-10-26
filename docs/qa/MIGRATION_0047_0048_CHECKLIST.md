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
| empty → head → base → head on **PostgreSQL 17** + gate verdict | CI job `postgres migration chain + schema gate` (`backend/scripts/check_migration_chain_postgres.py`) | PASS on PR #387 for 0047; **re-runs on push of 0048** — check the run before applying anywhere |
| Behaviour on top of the schema | `test_wardrobe_saved_outfits.py` (7), `test_watsonx_stylist.py` (37) | PASS |

## Database state actually observed (2026-10-26)

| Environment | Host | Observation |
|---|---|---|
| staging `confit_fixverify` (owner + `confit_app_rw`) | Neon project endpoint (eu-central-1; host kept in the local env file) | **Connection refused by Neon: "Your account or project has exceeded the quota. Upgrade your plan to increase limits."** Revision could **not** be read. |
| production `neondb` (owner + `confit_app_rw`) | same Neon project | **Same quota refusal.** Revision could **not** be read. |

Consequence: `alembic_version` for both environments is **NOT VERIFIED** this
session; last known (session 1, before the quota lock) was that 0047 had **not**
been applied anywhere. Nothing was applied. Production also serves HTTP 402
`DEPLOYMENT_DISABLED` from Vercel, so no running app depends on the schema right now.

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
