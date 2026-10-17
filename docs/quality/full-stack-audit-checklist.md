# CONFIT_A — Full-Stack Audit Checklist

Branch: `review/all-features` (based on `origin/main` @ `c52bb50`).
Status vocabulary: `NOT_STARTED` · `IN_PROGRESS` · `PASS` · `FAIL` · `BLOCKED` · `NOT_APPLICABLE`.
A row is `PASS` only when the verification was actually run and is recorded here.

## 1. Baseline (pre-change, on `main` @ c52bb50)

| Check | Command | Result | Status |
| --- | --- | --- | --- |
| Frontend i18n gate | `npm run i18n:check` | gate passed (keys exist, locale parity) | PASS |
| Frontend type check | `npx tsc --noEmit` | exit 0 | PASS |
| Frontend unit/component tests | `npx vitest run` | 134 files, 1594 tests passed | PASS |
| Frontend production build | `npx vite build` | built, exit 0 (chunk-size warning only) | PASS |
| Backend test suite (SQLite default) | `PYTHONPATH=. pytest backend/tests -q` | 3921 passed, 21 skipped, exit 0 | PASS |
| Backend Postgres-only tests | CI `postgres-migrations` job | not run locally (no Postgres/Docker in sandbox) | BLOCKED |
| Migration chain on real PostgreSQL | `backend/scripts/check_migration_chain_postgres.py` | not run locally | BLOCKED |
| Mutation gates | `backend/scripts/run_mutation_gates.py` | not run yet | NOT_STARTED |
| Runtime import gate | `backend/scripts/check_runtime_imports.py` | not run yet | NOT_STARTED |

## 2. Repository and release gates

| Item | Evidence | Status |
| --- | --- | --- |
| `main` required checks | `backend`, `frontend`, `release gate (production schema parity)` (branch protection, strict) | PASS (read via API) |
| Admin enforcement | `enforce_admins: true` | PASS (read via API) |
| Required reviews | none configured | NOT_APPLICABLE |
| Open PRs at baseline | 10 (incl. #352 `feat/brand-logo-individual-grid` → main) | PASS (inventory) |

## 2b. Database (read-only, 2026-10-17) — see `docs/quality/database-audit-2026-10-17.md`

| Item | Status |
| --- | --- |
| Live DB reachable through app role, read-only | PASS |
| Applied head == repo head (0036), no pending migrations | PASS |
| Repo schema gate (production) on live DB | PASS |
| ORM vs live schema comparison | PASS with open findings (see doc §2) |
| `product_skus` / `store_inventories` `brand_id` ORM nullability mismatch | FAIL (open; fix plan documented; naive fix reverted, 59 test errors) |
| `store_inventories_tenant_quarantine` (11 rows) disposition | BLOCKED (needs business decision) |
| Backup and PITR verification | BLOCKED (no Neon API access) |
| Restore drill | NOT_STARTED |
| Migration chain on real PostgreSQL (CI job) | BLOCKED (no local Postgres) |

## 3. Inventory, roles, traceability, UI, database, deployment

All remaining sections are `NOT_STARTED`: role/permission matrix, feature traceability matrix, frontend↔backend contract checks, database integrity and migration verification (production head read-only check pending), authorization boundary tests, E2E journeys, accessibility/responsive review, Logo #3 visual audit, deployment verification.
