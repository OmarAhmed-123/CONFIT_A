> **Superseded 2026-10-29 (ninth pass)** by `docs/release/PRODUCTION_READINESS_REPORT.md`. Kept for history; the decision below (NO-GO production / CONDITIONAL GO code) is unchanged.

# Release readiness — wardrobe stylist (IBM watsonx.ai / Granite)

Branch `feat/watsonx-granite-stylist` · prepared 2026-10-29 · supersedes the
A–I report delivered with commit `3f2fe70`. Every number here was produced on this
date on the current checkout unless a date says otherwise; "not run" means not run.

## A. Executive summary

* The feature is **functionally complete and verified end-to-end on a local
  PostgreSQL stack with no hosted provider** (API + browser, EN + AR, deterministic
  mode; live Granite verified 2026-10-28 with 22 real calls). The IBM tutorial is
  implemented with documented, hardening departures (`ibm-tutorial-alignment.md`).
* Today's local run found and fixed **two new defects** (D13: fallback items
  attributed to "model"; D14: indigo/teal/denim colours persisted as *Black*) — a
  direct payoff of actually running the app rather than trusting prior reports.
* The PostgreSQL benchmark is now **reproducible by script** and matches the
  2026-10-27 run: p95 **6.475 s PASS**, p99 **10.93 s FAIL** (retry arithmetic; target
  not relaxed).
* **Decision: NO-GO for production** — not for code reasons: production and staging
  are unverifiable (Vercel 402, Neon quota), and the human fashion / Arabic reviews
  are still pending. Code-wise the branch is in a **CONDITIONAL GO** state.

## B. Work completed this pass (2026-10-29)

| Area | Done | Evidence |
|---|---|---|
| Local PostgreSQL (mandatory) | PG 17.11 native cluster; `docker-compose.dev.yml` (PG-only); `scripts/dev/*` (start/migrate/reset/run/health/test/benchmark); `.env.example` already secret-free (re-checked) | `local-development.md` |
| Clean migrations | 0001→0048 in 1.5 s on empty PG; 0048→0046→0048 round-trip; startup schema gate `ok` | alembic logs, `/health` |
| Safe seed / reset | seed only on empty db (observed once, never on populated); `reset_db.sh` with local-only + development-only guards (both exercised) | §4 of local-development |
| Test DB | `confit_test`; stylist suites green on PostgreSQL (49) — first time the suites ran on PG in this project | `scripts/dev/test_backend_pg.sh` |
| End-to-end | API probe (7 items → EN/AR recommendation → error states 422/422/403/422) and **real browser** run (cookie login → stylist → recommendation → save → signed-out state) EN + AR, 0 page errors | `docs/qa/evidence/local_e2e_20261029/*.png` |
| Explicit AI modes | documented and verified: deterministic (labelled), watsonx (live), auto; double only via explicit `WATSONX_URL` override | local-development §6 |
| Defects fixed | **D13** `selected_by="rule_matcher"` on every fallback item (+ test) · **D14** colour aliases indigo/denim/teal/turquoise/aqua/petrol/bordeaux/cherry/lime/moss/pistachio (+ 6 tests) · eval completion metric excludes fallback answers · stale `wx-stylist-1.0` references corrected in two docs | diff |
| Benchmark | 20 VU × 20 on PG17/2 workers/5 s double, scripted | `performance-test-report.md`, JSON |
| CI hygiene | gitleaks flagged the first commit of this pass (local-only `confit:confit@127.0.0.1` DSN literals in dev scripts — policy breach, not a credential leak); fixed by assembling DSNs from `${POSTGRES_PASSWORD}` and suppressing the historical fingerprints in `.gitleaksignore` (repo precedent; no history rewrite) | follow-up commit |
| Documentation | `ibm-tutorial-alignment`, `functional-requirements`, `non-functional-requirements`, `local-development`, `deployment-recovery`, `vision-integration-decision`, `fashion-expert-review`, `performance-test-report`, `accessibility-audit`, `known-limitations`, `architecture`, this file; README updated | `docs/` |

Earlier passes (D1–D12, EN/AR disclosure, colour exclusions, saved looks, a11y
gate, live eval) are recorded in `IBM_WATSONX_STYLIST_ACCEPTANCE.md` and
`docs/qa/WARDROBE_STYLIST_QUALITY_REPORT.md`; re-verified today by the suites below.

## C. Outstanding work by category

**Code (minor, non-blocking)**
1. `normalize_color` unknown → "Black" fallback: introduce an "Unknown" family ignored
   by the exclusion filter (known-limitations #4).
2. Two-worker `create_all` race notice on an empty db (cosmetic).
3. Promote the playwright-core browser E2E script to a CI job.

**Human validation (blocking for GO)**
4. Fashion-expert rubric — PENDING (`fashion-expert-review.md`).
5. Native-Arabic review — PENDING (`docs/qa/ARABIC_REVIEW_SHEET_STYLIST.md`).
6. Manual assistive-technology sessions incl. Arabic — NOT PERFORMED.

**Account / platform (blocking for production)**
7. Vercel 402 → resume; 8. Neon quota → restore, then apply 0047/0048 to staging →
prod; 9. Redis for shared rate limits; 10. Cloudflare Workers Builds configure or
disconnect; 11. Granite Vision DoD (optional, billable) — all in `deployment-recovery.md`.

**Process**
12. Redefine p99 SLO relative to retries (or exclude retried requests) — decision, not code.
13. Live staging load probe once 7–8 are resolved.

## D. Test results (2026-10-29, current checkout)

| Suite | Result | Status |
|---|---|---|
| Stylist suites (consistency 18 + watsonx 17 + colour eval), SQLite | **76 passed** | PASS |
| Stylist suites on **PostgreSQL 17** (`confit_test`) | **49 passed** | PASS |
| Wardrobe / colour / taxonomy `-k` sweep | **231 passed** | PASS |
| Broad backend `-k` sweep (stylist, watsonx, wardrobe, taxonomy, outfit, migration, schema_gate, startup, health, auth) | **842 passed, 5 skipped** | PASS |
| Full backend suite in one process | not run locally (2 GB OOM); **CI backend job green on `ceb8616` and `ffd6118`** | PASS (CI) |
| Frontend vitest | **2363 passed / 157 files** | PASS |
| TypeScript `tsc --noEmit` | clean | PASS |
| Ruff on touched files | 86 findings before = 86 after (pre-existing, CI does not gate) | PASS (no regression) |
| Deterministic 16-scenario eval | 16/16 scenarios, 22 runs, **0 hard failures**, 0 model calls, completion metric 0 (by definition in fallback) | PASS |
| Live 16-scenario eval (Granite, 22 calls) | 2026-10-28 on 3f2fe70 service code: violations 0/16, invented ids 0, completeness 16/16 (3 rule-completed, all disclosed), language 16/16, H10 3 (manually reviewed: negated-text false positives) | PASS (not re-run today — stylist model path unchanged; D13/D14 affect fallback labelling and taxonomy only) |
| Alembic chain on PostgreSQL | up / down / up clean | PASS |
| API end-to-end (deterministic, PG) | all expected codes | PASS |
| Browser end-to-end EN/AR | pass, screenshots | PASS |
| Load 20 VU (PG17, 2 workers) | p95 6.475 PASS · p99 10.93 FAIL · 0 × 5xx · provenance 400/400 | PARTIAL (p99 as written) |
| axe (8 states × EN/AR), keyboard, focus, live regions | 0 violations (2026-10-27, CI gate green) | PASS |
| Manual AT (NVDA/VoiceOver/…) | — | NOT RUN |
| Staging / production smoke | — | BLOCKED (402 / quota) |
| Docker compose dev file | reviewed, not executed (no Docker) | NOT RUN |

## E. Local execution commands

```bash
# one-time
python -m venv .venv && . .venv/bin/activate && pip install -r backend/requirements.txt
(cd frontend && npm ci)
./scripts/dev/start_postgres_native.sh            # or docker compose -f docker-compose.dev.yml up -d
# every time
./scripts/dev/migrate.sh
./scripts/dev/run_backend.sh                      # deterministic AI mode by default (labelled)
./scripts/dev/run_frontend.sh                     # http://localhost:43123/wardrobe?tab=stylist
./scripts/dev/healthcheck.sh
# live Granite instead
WARDROBE_STYLIST_PROVIDER=watsonx WATSONX_APIKEY=… WATSONX_PROJECT_ID=… WATSONX_URL=https://eu-de.ml.cloud.ibm.com ./scripts/dev/run_backend.sh
# tests / eval / benchmark / reset
./scripts/dev/test_backend_pg.sh
PYTHONPATH=. ENVIRONMENT=test python scripts/eval/wardrobe_stylist_quality_eval.py --mode deterministic
./scripts/dev/run_benchmark.sh
./scripts/dev/reset_db.sh
```

## F. Deployment status per provider

| Provider | Status 2026-10-29 | Class |
|---|---|---|
| Vercel production | HTTP 402 `DEPLOYMENT_DISABLED` | account |
| Neon prod + staging | quota exceeded, unreachable | account |
| Cloudflare Workers Builds | failing check, no in-repo config | account/integration |
| GitHub Actions on `3f2fe70` | backend ✓ frontend ✓ migration+schema gate ✓ a11y browser gate ✓ parity ✓ gitleaks ✓ · release gate ✗ (fails closed on 402, by design) | — |
| GitHub Actions on this pass (`ceb8616` code → `ffd6118` head) | backend ✓ frontend ✓ migration chain + schema gate ✓ stylist a11y browser gate ✓ production parity ✓ **gitleaks ✓** (after the DSN-literal fix) · release gate ✗ (fails closed on 402) · Workers Builds ✗ (external) | — |
| IBM watsonx.ai eu-de | live, verified | — |
| Granite Vision | not served (DoD only) | account |

Details and recovery order: `deployment-recovery.md`.

## G. Human validation status

| Review | Status |
|---|---|
| Fashion expert (16 scenarios, rubric) | **PENDING** — no reviewer engaged; nothing invented |
| Native Arabic (output quality) | **PENDING** |
| Screen-reader users (EN, AR) | **NOT PERFORMED** (Orca EN automated transcript only) |
| Product owner acceptance of D12/D13 labelling approach | **PENDING** |

## H. Decision

**NO-GO for production release.** Reasons, in order: (1) production/staging cannot be
verified or even reached (account-side); (2) human fashion and Arabic validation
pending; (3) p99 latency target unmet as written. **Code readiness: CONDITIONAL GO** —
all automated gates pass, the feature runs end-to-end locally on PostgreSQL in both
AI modes with honest labelling, and no open code defect is release-blocking.

## I. Next actions

1. Account owner: resume Vercel, restore Neon quota (then staging migration + smoke per
   `MIGRATION_0047_0048_CHECKLIST.md`), decide on Cloudflare integration, provision Redis.
2. Engage a qualified fashion reviewer and a native Arabic reviewer with the prepared
   sheets; paste results verbatim into the quality report.
3. Re-run the live staging probe and the live 16-scenario eval after deployment.
4. Agree the p99 SLO definition; implement the "Unknown" colour family; add the browser
   E2E to CI.
5. Re-issue this document; expected outcome CONDITIONAL GO → GO once 1–3 close.
