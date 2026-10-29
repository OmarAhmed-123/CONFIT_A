# Local development — full stack without Neon, Vercel or Cloudflare

**Status: verified 2026-10-29** on a 2 vCPU / 2 GB Debian 13 sandbox with no Docker
(PostgreSQL 17.11 native, Python 3.13, Node 20). Every command below was executed
during that verification; nothing is assumed. Evidence:
`docs/qa/evidence/local_e2e_20261029/` (browser screenshots, EN + AR),
`docs/qa/load/stylist_mocked_20vu_postgres17_2workers_5s_20261029.json` (benchmark).

The app has **no dependency on any hosted provider** for local work. SQLite still
works for quick unit-test loops, but it is **not** a PostgreSQL substitute: the
migration chain, the audit-provenance triggers (migration 0024) and the load
benchmark are PostgreSQL-only behaviours and are only considered verified on
PostgreSQL.

## 0. Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | ≥ 3.11 (3.13 verified) | `python -m venv .venv && . .venv/bin/activate && pip install -r backend/requirements.txt` |
| Node + npm | ≥ 20 | `cd frontend && npm ci` |
| PostgreSQL | 16 or 17 | **either** Docker (`docker-compose.dev.yml`) **or** a native install |
| ruff | any | `pip install ruff` (CI lint) |

## 1. PostgreSQL

### Option A — Docker Compose (preferred where Docker exists)
```bash
docker compose -f docker-compose.dev.yml up -d      # postgres:17-alpine, 127.0.0.1:5432
```
Creates `confit_dev`, `confit_test`, `confit_bench` (role `confit`, password `POSTGRES_PASSWORD`, default `confit`,
UTF-8, C.UTF-8 — the seed contains Arabic). PostgreSQL **only**; the API and Vite run
natively. The full production-shaped stack (Redis, Meilisearch, Celery, built images)
remains in `docker-compose.yml`.

> Not executed in the verification sandbox (no Docker daemon). The file is a
> straightforward single-service compose; the init SQL it mounts is the same one the
> native script runs. Treat as *reviewed, not run* until someone with Docker confirms.

### Option B — native (verified)
```bash
sudo apt-get install -y postgresql          # Debian/Ubuntu; macOS: brew install postgresql@17
./scripts/dev/start_postgres_native.sh      # initdb (UTF8) + start on 127.0.0.1:5432 + create role/dbs
```
Data lives in `$HOME/.confit-pgdata`; stop with `pg_ctl -D ~/.confit-pgdata stop`.
If `pg_ctl` complains about `/var/run/postgresql`, the script already passes
`unix_socket_directories=/tmp` — that was the only snag hit during verification.

## 2. Configuration (`.env.example`, no real secrets)

`backend/.env.example` is the authoritative list. For local PostgreSQL you need only:

```bash
export POSTGRES_PASSWORD=confit                       # local default; the DSN is assembled by scripts/dev/_env.sh
export DATABASE_URL="postgresql://confit:${POSTGRES_PASSWORD}@127.0.0.1:5432/confit_dev"
export SECRET_KEY=local-dev-secret-not-for-prod
export JWT_REFRESH_SECRET=local-dev-refresh-not-for-prod
export WARDROBE_STYLIST_PROVIDER=deterministic      # see §6 AI modes
```
`scripts/dev/_env.sh` applies exactly these defaults when the variables are unset.
Driver selection follows `docs/POSTGRES_DRIVER_POLICY.md` (a bare `postgresql://`
URL is normalised to `postgresql+psycopg2://` by the app and by `reset_db.sh`).

## 3. Migrate, seed, run

```bash
./scripts/dev/migrate.sh         # alembic upgrade head → prints "0048_wardrobe_outfits (head)"
./scripts/dev/run_backend.sh     # uvicorn :8000 ; first start on an EMPTY db seeds the demo catalogue
./scripts/dev/run_frontend.sh    # vite :43123 ; /api → :8000 proxy (vite.config.ts)
./scripts/dev/healthcheck.sh     # liveness + schema gate + capability snapshot
```
Verified results: full chain `upgrade head` **1.5 s** on an empty PostgreSQL 17 db
(64 tables), `downgrade 0046` → `upgrade head` round-trip clean, startup
`schema_gate verdict=ok database_revision=0048_wardrobe_outfits`, seed ran once
("Database was empty — seeded the default catalogue"), **never** on a populated db.

Demo accounts after seeding: `shopper@confit.io`, `admin@confit.io`,
`brand@confit.io` — password `Password123!`.

Multi-worker note: `uvicorn --workers 2` on an **empty** db logs a harmless
`UniqueViolation … pg_type_typname_nsp_index` "Database initialization notice"
(both workers race `create_all`); the schema gate still reports `ok`. Seed once with
one worker first (also in README).

## 4. Reset procedure

```bash
./scripts/dev/reset_db.sh        # DROP SCHEMA public CASCADE → migrate; API reseeds on next start
```
Guards (both verified): refuses unless `DATABASE_URL` host is `127.0.0.1`/`localhost`
**and** `ENVIRONMENT=development`. Verified: users 20 → 0 after reset, head 0048.

## 5. Tests

| What | Command | Verified result 2026-10-29 |
|---|---|---|
| Stylist suites on SQLite (default) | `PYTHONPATH=. ENVIRONMENT=test pytest backend/tests/test_stylist_explanation_consistency.py backend/tests/test_watsonx_stylist.py backend/tests/test_stylist_colour_constraints_eval.py -q` | **76 passed** (incl. new D13) |
| Same on **PostgreSQL** (`confit_test`) | `./scripts/dev/test_backend_pg.sh` | **49 passed**, 61 tables created in `confit_test` |
| Wardrobe/colour/taxonomy sweep | `… pytest backend/tests -k "taxonomy or color or colour or wardrobe"` | **231 passed** (incl. new D14 ×6) |
| Frontend | `cd frontend && npx vitest run && npx tsc --noEmit` | 901 / clean at 3f2fe70 (not re-run today — no TS change) |

Full backend suite in one process OOMs in a 2 GB sandbox; run it in `-k` chunks
there. CI runs it whole.

## 6. AI modes (explicit, never silent)

| `WARDROBE_STYLIST_PROVIDER` | What answers | How it is labelled in the API / UI |
|---|---|---|
| `deterministic` | CONFIT rule matcher, **no model call** | `source="deterministic_fallback"`, `ai_generated=false`, `fallback_reason="provider_mode_deterministic"`, every item `selected_by="rule_matcher"`; UI badge **"Rule-based match — not AI" / "مطابقة قائمة على القواعد — ليست ذكاءً اصطناعيًا"** |
| `watsonx` | IBM watsonx.ai `ibm/granite-4-h-small` (needs `WATSONX_APIKEY`, `WATSONX_PROJECT_ID`, `WATSONX_URL`) | `source="watsonx"`, `model_id`, `prompt_version=wx-stylist-1.1`, `ai_generated=true`; rule-completed pieces (D12) carry `selected_by="rule_matcher"` + **"Added by rules"** badge |
| `auto` (default) | watsonx when configured, otherwise deterministic | as above, per actual path |

A fixture/double is **never** presented as Granite: the load-test double
(`scripts/load/watsonx_double.py`) exists only for the benchmark rig and is wired
by pointing `WATSONX_URL` at it explicitly (`scripts/dev/run_benchmark.sh`).

## 7. End-to-end verification performed (deterministic mode, PostgreSQL)

API (`/tmp` probe, httpx): register → 7 wardrobe items → `POST /wardrobe/outfit-recommendation`
EN + AR → 200, honest source labels, Arabic limitations
(`لا يوجد حذاء في خزانتك لإكمال هذه الإطلالة`), `missing_categories=["Footwear"]`;
error states: short occasion → **422**, bad season literal → **422**, unauthenticated → **403**,
saved-outfit body without `title` → **422**.

Browser (headless Chromium via playwright-core, real cookie login):
`/wardrobe?tab=stylist` → sign-in modal → Smart Casual → **Build my outfit** →
`data-source=deterministic_fallback`, badge "RULE-BASED MATCH — NOT AI", 3 items each
with "Added by rules", **Save this look** → "Saved to your wardrobe looks (#2)";
same in Arabic (`dir=rtl`, "حُفظت ضمن إطلالات خزانتك (رقم 3)"); signed-out state
shows "Sign in to use the stylist." Zero page errors. Screenshots in
`docs/qa/evidence/local_e2e_20261029/`.

Two defects were found *by this run* and fixed the same day (D13, D14 —
see `docs/known-limitations.md` and `docs/release-readiness.md`).

## 8. Benchmark

`./scripts/dev/run_benchmark.sh` (≈ 6 min for 20 VUs). Results and method:
`docs/performance-test-report.md`.
