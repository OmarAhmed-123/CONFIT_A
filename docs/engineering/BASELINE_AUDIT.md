# Baseline Audit — 2026-10-29 (start of the deployment-recovery / production-readiness pass)

Snapshot taken **before** any change in this pass, at commit `90c8371` on `main`.
Everything below was observed by running the command shown; nothing is inferred.

## 1. Repository state

| Check | Command | Result |
|---|---|---|
| Working tree | `git status --porcelain` | clean |
| Head | `git log --oneline -1` | `90c8371 release-readiness: record final CI state for this pass` |
| Remote | `git remote -v` | `https://github.com/OmarAhmed-123/CONFIT_A` (pushed, in sync) |
| CI on previous head (ffd6118/90c8371) | GitHub Actions `ci` | backend ✓ · postgres migration chain + schema gate ✓ · production-parity ✓ · frontend ✓ · stylist drawer browser gate ✓ · gitleaks ✓ ; `release-gate` ✗ (fails closed on Vercel HTTP 402, by design) ; Cloudflare Workers Builds ✗ (external, account-side) |

## 2. Toolchain present in the sandbox

| Tool | Version |
|---|---|
| Python (`/home/user/.venv`) | 3.13.16 |
| Node | v20.20.2 (CI uses 22) |
| PostgreSQL | 17.11, native cluster at `/home/user/.pgdata`, databases `confit_dev`, `confit_test`, `confit_bench` |
| Alembic head | `0048_wardrobe_outfits` |

## 3. Architecture (as found)

* **Backend** — FastAPI (`backend/app`), SQLAlchemy models, Alembic migrations, SlowAPI rate limiting, httpOnly-cookie JWT auth (`confit_token`) + CSRF cookie. Startup: `create_all()` + seed in non-production only; schema-drift gate (`core/schema_gate.py`) enforces migration head.
* **AI providers** — `backend/app/providers/watsonx/` (IAM token, chat, retry policy), reasoning model `ibm/granite-4-h-small` configured centrally (`WATSONX_REASONING_MODEL_ID`), vision model configurable (`WATSONX_VISION_MODEL_ID`). Stylist provider modes `auto | watsonx | deterministic`.
* **Frontend** — React + Vite + TypeScript, i18next (`frontend/src/i18n/{en,ar}.json`, 3215 keys), RTL via `document.documentElement.dir`.
* **Hosting** — Vercel (frontend) · Neon (PostgreSQL) · Cloudflare Workers Builds (separate pipeline) — see `docs/deployment/`.
* **Local stack** — `scripts/dev/*` (`start_postgres_native.sh`, `migrate.sh`, `run_backend.sh`, `run_frontend.sh`, `test_backend_pg.sh`, `run_benchmark.sh`) and `docker-compose.dev.yml`.

## 4. Test and quality gates at baseline (historical, from the 2026-10-29 eighth pass — see `docs/release-readiness.md`)

| Gate | Baseline result |
|---|---|
| Backend pytest (broad sweep, chunked) | 842 passed / 5 skipped |
| Stylist suites | 76 (SQLite) / 49 (PostgreSQL) passed |
| Frontend vitest | 2363 passed |
| `tsc --noEmit` | clean |
| i18n parity gate | pass |
| Deterministic stylist eval | 16/16 clean |
| Live Granite eval (2026-10-28) | 22 calls, 0 violations, p50 2.9 s |
| Load benchmark (PG17, 2 workers, double 5 s ±1.5 s, 2 % 503 + 1 % 429, 20 VU × 20) | p50 5.044 · **p95 6.475 PASS** · **p99 10.932 FAIL** · 660 req · 0 errors |

## 5. Known defects / open items at baseline

| ID | Item | Status at baseline |
|---|---|---|
| KL-4 | Unknown colour words normalise to **Black** (silent) | open → fixed in this pass (Phase 11-A) |
| KL-B | Multi-worker boot on an empty PostgreSQL: `create_all()` runs **outside** the seed advisory lock | open (undetected) → reproduced and fixed in this pass (Phase 11-B) |
| KL-C | No permanent browser E2E in CI (only the drawer a11y/keyboard gate, no backend) | open → added (Phase 11-C) |
| PERF-1 | p99 miss under injected faults — cause not yet proven | open → analysed in `docs/performance/` |
| DEP-1 | Vercel project returns HTTP 402 (billing) | blocked, owner action |
| DEP-2 | Neon project quota-locked | blocked, owner action |
| DEP-3 | Cloudflare Workers Builds failing (account-side) | blocked, owner action |
| AI-1 | Granite Vision models withdrawn from multitenant watsonx (404) | blocked, decision recorded in `docs/ai/VISION_PROVIDER_DECISION.md` |

## 6. Retry policy as found (`backend/app/providers/watsonx/client.py` L227–246)

* Retries only `WatsonxError.retryable` (429, 5xx, timeout); one forced token refresh on the first 401.
* Bound: `WATSONX_MAX_RETRIES` (settings, default **2**) → at most **3** attempts per call.
* Backoff: `min(4.0, 0.5 · 2^(attempt−1))` s → 0.5 s, 1.0 s.
* Request timeout `WATSONX_TIMEOUT_SECONDS = 45`.

## 7. Baseline verdict

Code gates green; production path **NO-GO** (platform blockers DEP-1..3 unchanged); code readiness **CONDITIONAL GO** (`docs/release-readiness.md §H`). This pass does not change the platform blockers — it fixes KL-4, KL-B, KL-C, explains PERF-1, and produces the review/decision packages listed in `docs/release/PRODUCTION_READINESS_REPORT.md`.
