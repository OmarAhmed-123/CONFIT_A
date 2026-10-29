# Production Readiness Report — 2026-10-29 (ninth pass)

Supersedes the decision section of `docs/release-readiness.md` (kept for history). Code head for this report: see the commit that adds this file (all numbers below were produced on that tree, fresh, on 2026-10-29 unless marked *historical*).

## A. Executive summary

* **Production deployment: NO-GO.** Vercel (HTTP 402), Neon (quota-locked) and the Cloudflare Workers Builds integration are owner/account blockers; no repository change can clear them (`docs/deployment/`).
* **Code readiness: CONDITIONAL GO** — all code gates green locally; CI to be confirmed on this commit. Conditions listed in §D.
* This pass fixed three defects (Unknown colour family, concurrent empty-DB initialisation race, missing browser E2E gate), proved the p99 benchmark miss to be a harness-rule artefact rather than a bottleneck, and produced the review packages (fashion, Arabic, UI/UX, accessibility, security/ops, vision decision).

## B. Verified this pass (fresh evidence)

| Item | Result | Evidence |
|---|---|---|
| Backend pytest, all 267 files (4 chunks) | **4 657 passed / 29 skipped / 0 failed**, exit 0 ×4 | terminal, 2026-10-29 |
| PostgreSQL-backed stylist suites (`scripts/dev/test_backend_pg.sh`) | 76 passed | |
| PostgreSQL concurrency suites (startup init ×3 trials ×4 workers, seed lock, MFA) | 7 passed | `confit_race` DB |
| Frontend vitest | **2 365 passed / 0 failed** (157 files) | |
| `tsc --noEmit` | clean | |
| i18n parity gate | pass (0 missing AR keys) | |
| Deterministic stylist eval | 16 scenarios, exit 0 | `/tmp/eval_det.json` (same shape as `docs/qa/eval/...deterministic_20261029.json`) |
| Browser E2E (new gate), EN + AR | **24/24 checks PASS** | `docs/qa/evidence/browser_e2e_20261029/` |
| Load benchmark runs 2 & 3 | p95/p99 **PASS** absolute thresholds; retries bounded (413 calls / 400 req) | `docs/performance/LOAD_TEST_RESULTS.md` |
| `pip-audit` | 0 known vulnerabilities | |
| `npm audit --omit=dev` | 0 | (7 dev-only findings, SEC-1) |
| Keyboard-only a11y (9 checks × 2 languages) | PASS | `docs/accessibility/MANUAL_ACCESSIBILITY_AUDIT.md` |
| Race reproduction before fix | 9/12 unlocked `create_all` workers failed (`pg_type_typname_nsp_index`) | test docstring |

## C. Release checklist — 14 categories

| # | Category | Status | Basis |
|---|---|---|---|
| 1 | Functional correctness (auth, wardrobe, stylist, save) | **PASS** | backend suite + browser E2E |
| 2 | Data integrity / migrations | **PASS** | chain to 0048 on PG17; schema gate; concurrency test |
| 3 | AI provider correctness & honesty (labelled source, no substitution, bounded retries) | **PASS** (reasoning) / **BLOCKED** (Granite Vision) | live eval 2026-10-28 *(historical)*; `docs/ai/VISION_PROVIDER_DECISION.md` |
| 4 | Performance | **PASS** against p95 ≤ 6.5 / p99 ≤ 8 on evidence-based latency; baseline run 1 p99 FAIL explained (harness rule) | `docs/performance/` |
| 5 | Security controls | **PASS** (code) with open SEC-1..3 | `docs/security/OPERATIONAL_READINESS.md` |
| 6 | Secrets hygiene | **PASS** | gitleaks ✓, no DSN literals |
| 7 | Accessibility — automated | **PASS** | CI drawer gate *(historical, green on ffd6118)* |
| 8 | Accessibility — manual keyboard | **PASS** | this pass |
| 9 | Accessibility — screen reader | **BLOCKED** | no AT runtime |
| 10 | Localization (AR) | **PASS** parity / **NOT TESTED** native review; LOC-1..4 open | `docs/quality/ARABIC_LOCALIZATION_REVIEW.md` |
| 11 | Fashion-domain quality | **NOT TESTED** (package prepared, no reviewer) | `docs/quality/FASHION_EXPERT_REVIEW.md` |
| 12 | UI/UX | **PASS** with UX-1 (mobile reach) High | `docs/quality/UI_UX_REVIEW.md` |
| 13 | Deployment platforms (Vercel / Neon / Cloudflare) | **FAIL / BLOCKED** | `docs/deployment/*` |
| 14 | Operations (monitoring, alerting, backups, on-call) | **FAIL** (not configured) | OPS-1..3 |

**Decision: NO-GO for production; CONDITIONAL GO for the code line.**

## D. Conditions to convert CONDITIONAL GO → GO (code) and NO-GO → GO (production)

1. Owner recovers Vercel billing (402), Neon quota, and decides Cloudflare A/B — then re-run `release-gate`.
2. Production env: `RATE_LIMIT_STORAGE_URL` (Redis), `GLITCHTIP_DSN`, `ENVIRONMENT=production`, APP_RW `DATABASE_URL` on backend only.
3. Screen-reader pass executed (category 9).
4. Native Arabic review of the sheet + fix LOC-1 (two dialect strings).
5. Fashion reviewer scores ≥ "Accept with edits" on the 16 cases, or documented exceptions.
6. Dev-toolchain audit findings (SEC-1) bumped in a dedicated PR.
7. CI on this commit green for: backend, postgres-migrations, production-parity, frontend, stylist-browser-gate, **browser-e2e** (new), gitleaks.

## E. Changes in this pass (code)

| Area | Change | Tests |
|---|---|---|
| Colour taxonomy | `normalize_color` → `"Unknown"` for unrecognised/empty; `UNKNOWN_COLOR`, `is_known_color`; Unknown never neutral / preferred / banned / gap-match / palette anchor; swatch `#A3A3A3`; UI label localised (`wardrobe.color_unknown`, `frontend/src/lib/colorLabel.ts`) | `backend/tests/test_color_unknown_family.py` (21) |
| Startup | `backend/app/core/startup_init.py`: `create_all()` + decide-and-seed inside one advisory-lock critical section; `main.lifespan` calls it | `backend/tests/test_startup_init_concurrent_postgres.py` (CI job updated) |
| CI | new job `browser-e2e` (PG17 service, deterministic backend, vite preview, Chromium; not allowed to fail; artifacts always uploaded) | `scripts/qa/e2e_stylist_browser.{sh,mjs}` |
| Load harness | `DOUBLE_FAULT_TIMING`, `double_stats`/`double_knobs` in reports, benchmark exits with load status, knobs overridable | runs 2–3 |
| Dev scripts | `test_backend_pg.sh` default-args bug fixed | 76 passed |

## F. Not done / honest gaps

* No live watsonx load soak; no real 503 timing from IBM; Granite Vision remains unavailable.
* `docker-compose.dev.yml` still reviewed-not-run (no Docker in sandbox).
* Fashion and Arabic reviews are **prepared**, not performed.
* CI result for this exact commit is recorded in `docs/release-readiness.md §B` after the push (see final report section I).

## G. Reproducibility (repo root)

```bash
# backend (chunked to fit 2 GB; run whole on CI)
PYTHONPATH=. ENVIRONMENT=test pytest -q backend/tests
# PostgreSQL-backed
scripts/dev/start_postgres_native.sh && scripts/dev/migrate.sh && scripts/dev/test_backend_pg.sh
CONFIT_CONCURRENCY_PG_URL=postgresql://confit:${POSTGRES_PASSWORD}@127.0.0.1:5432/confit_race \
  PYTHONPATH=. ENVIRONMENT=test pytest -q backend/tests/test_startup_init_concurrent_postgres.py
# frontend
cd frontend && npm ci && npm run i18n:check && npx tsc --noEmit && npx vitest run && npm run build && cd ..
# browser e2e
E2E_DATABASE_URL=postgresql://confit:${POSTGRES_PASSWORD}@127.0.0.1:5432/confit_e2e PY=.venv/bin/python bash scripts/qa/e2e_stylist_browser.sh
# benchmark (run 1 defaults; run 2; run 3)
scripts/dev/run_benchmark.sh
DOUBLE_FAULT_TIMING=before scripts/dev/run_benchmark.sh
DOUBLE_LATENCY_MS=2900 DOUBLE_JITTER_MS=1100 MODEL_LATENCY_S=2.9 scripts/dev/run_benchmark.sh
# eval, audits
PYTHONPATH=. python scripts/eval/wardrobe_stylist_quality_eval.py --mode deterministic
pip-audit -r backend/requirements.txt ; (cd frontend && npm audit --omit=dev)
```
