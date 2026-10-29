# Neon Recovery — owner checklist

**Observed (2026-10-28/29)**: both Neon projects reachable in the credentials file (`fixverify`, `neondb`) refuse connections with a **quota / compute-suspended** error. Local PostgreSQL 17 was used for all verification in this pass; **Neon has not been fixed** by anything in this repository.

## Verified facts

* Migration chain applies cleanly to an empty PostgreSQL 17 (`alembic upgrade head` → `0048_wardrobe_outfits`), CI job `postgres migration chain + schema gate` green.
* Driver policy: `backend/app/core/postgres_url.py` normalises `postgres://` / `postgresql://` to psycopg2 with `sslmode=require` for non-local hosts (`docs/POSTGRES_DRIVER_POLICY.md`).
* Schema gate (`core/schema_gate.py`) **refuses to serve** in production when the DB is not at head — no silent drift.
* Startup on an empty DB is now safe for N workers (`docs/engineering/BASELINE_AUDIT.md` KL-B; `backend/tests/test_startup_init_concurrent_postgres.py`), but production **never** auto-creates or seeds (ENVIRONMENT=production skips it by design).

## Owner steps

1. **Quota** — Neon console → Project → *Billing/Usage*: check compute hours / storage / data-transfer against the plan. Upgrade or wait for the monthly reset. Record which limit was hit.
2. **Compute** — *Branches → main → Compute*: ensure the endpoint is not suspended / is allowed to autoscale ≥ 0.25 CU; wake it (`psql` once).
3. **Roles** — keep two roles as already provisioned: `*_OWNER` (migrations only) and `*_APP_RW` (runtime). Rotate both passwords in the Neon console **after** recovery if there is any doubt they leaked (they never appear in this repo; `.gitleaks.toml` blocks DSNs with literal passwords).
4. **Migrate** — from a trusted machine with the OWNER DSN in the environment only:
   `PYTHONPATH=. alembic -c backend/alembic.ini upgrade head` → expect `0048_wardrobe_outfits`. Then `python backend/scripts/check_migration_chain_postgres.py "$DATABASE_URL"`.
5. **Runtime env** — set `DATABASE_URL` (APP_RW DSN) on the **backend** host only (never Vercel frontend). `ENVIRONMENT=production`.
6. **Verify** — backend `/health` → 200 and `schema_gate verdict=ok` in logs; `GET /api/v1/wardrobe/items` with a real session → 200.
7. **Backups** — confirm Neon point-in-time restore window (plan-dependent) and write the value into `docs/security/OPERATIONAL_READINESS.md §Backups`.

## Not allowed

* Running `Base.metadata.create_all()` or the seeder against Neon (dev-only path, disabled in production).
* `alembic stamp head` to make the gate pass.
* Committing any DSN.

## Status: **BLOCKED — owner action required**.
