# Brand Partner Portal remediation — 2026-09-21

This is a non-punitive product-improvement review: evidence helps us repair the
system and learn, not punish individuals. Scope excludes other concurrent work.

## Change set 1: ingestion and mutation correctness

Baseline: `b9e1d0e` (main advanced beyond the supplied `cd17a22`). Existing focused
suite: 21 passed. New isolated regression suite BEFORE fixes: **17 failed, 3
passed**. After fixes: **41 passed** including existing focused tests.

Full-suite first rehearsal: 1259 passed, 2 skipped, 2 failures: the historic
admin-first-brand assertion and CSV header error classification. Classification
was preserved; the authorization test was updated to the explicit tenant policy
below. This is not a claim that all production workflows were tested.

### BRD / acceptance contracts
- Consumers cannot enter partner APIs. An account must be linked to a tenant.
- Unassigned administrators must not silently select the first brand. Platform
  oversight remains `/admin/*`; no tenant selection UI is implied.
- CSV and JSON share normalization, validation, idempotent SKU upsert identity,
  error shape, bounded workload (1,000 rows / CSV 10 MiB) and job accounting.
- `accepted_rows + rejected_rows == total_rows` for parsed data rows; multiple
  field errors do not inflate row counts. File-level errors use row 0, not an
  invented data row. Original input row numbers survive validation.
- Each accepted row is a transaction. A rejected SKU cannot leave behind a
  product. Repeat uploads update the same identity; duplicate SKUs in one batch
  are rejected. Moving a SKU to a different product is deliberately forbidden.
- Missing stock means **0**, not fabricated sellable stock. Blank optional CSV
  cells get documented defaults. No seeded reviews/ratings on imported products.
- An inventory PATCH must match path ID, store, SKU and tenant. Reserved stock
  cannot exceed quantity. A real store parent lock serializes first-time upserts
  on PostgreSQL; locking an absent inventory row alone does not.
- Placement PATCH validates final combined state before assignment, rejects
  unknown fields/types, honors spend floor and UTC-normalized date order. Dates
  roundtrip. This does not establish ad delivery or billing correctness.

### Architecture / design decisions
Keep existing controller → service → repository boundaries. One catalog pipeline
(DRY), one placement policy module (shared invariant validation). DB unique and
check constraints remain the last line of defence. No schema migration in this
change set. Product identity is currently brand + title; renames require an
explicit product-edit workflow and are not inferred from SKU reassignment.
Serializing imports per brand trades throughput for deterministic identity under
concurrent uploads. CSV is bounded synchronous processing despite the legacy 202
status; returned job status is final, not a promise of a queue worker.

### Evidence and limits
- Tests use fresh isolated SQLite tenants; no demo account dependence or skips in
  the new suite. SQLite does not prove PostgreSQL locking behavior.
- Production `/api/v1/health` returned 200 with schema revision 0017 during initial
  read-only inspection. This proves availability/schema only, not partner UAT.
- No production account creation, imports, campaigns, database writes or emails
  were used for these tests. Secrets are outside Git; rotate the shared keys.
- Audit calls were added for import jobs, store edits and store inventory edits.
  Existing post-commit best-effort audit handling is NOT an atomic audit guarantee.

## Research references (reviewed, not copied wholesale)
- OWASP API1 object-level authorization:
  https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/
- SQLAlchemy transaction scope and rollback:
  https://docs.sqlalchemy.org/en/20/orm/session_transaction.html
- PostgreSQL row locking and absent-row limitations:
  https://www.postgresql.org/docs/current/explicit-locking.html
- Upstream SQLAlchemy maintainer discussion of savepoint lifecycle:
  https://github.com/sqlalchemy/sqlalchemy/discussions/8110

The implementation uses explicit per-row outer transactions rather than mixing
savepoints with Session.commit(), which would commit the outer transaction in
SQLAlchemy 2.x. No third-party implementation was vendored.

## Change set 2: usable UI contracts and truthful tenant analytics

- Partner product responses now explicitly include SKUs (`BrandProductOut`). A
  real browser run found that `ProductSummaryOut` discarded the service's SKU
  payload: successful imports appeared with empty stock tables. Added a direct
  API contract regression and exercised the editor in Chromium.
- Authenticated consumers see partnership onboarding, not a dead-end 403 page.
  Consumer registration is no longer advertised as partner provisioning.
- A partial analytics failure terminates loading and offers retry. Failed refresh
  clears stale data. Brand pages no longer call admin analytics; admin view uses
  its own request scope. Out-of-order fetch responses are discarded.
- Failed stock/placement mutations retain the edit form. Awaited success is
  required before dismissing it. Actual product ID is used instead of hardcoded
  ID 1. Fixed CPC input step alignment (the previous default failed native form
  validation). Modal focus/Escape behavior uses the existing shared hook.
- Store inventory has a working explicit upsert form and API; PATCH still binds
  the path identity. Full inventory is displayed rather than silently hiding
  everything after the fifth product. Store DTOs reject blank/oversized fields,
  invalid coordinates and nulls in required columns.
- Removed illustrative showcase components from partner operational screens;
  unverified claims of cross-system stock sync, causal return improvement and
  verified ad delivery were removed. Product currency is displayed as supplied.
- Missing return/BOPIS denominators are null, rendered as “Not enough data”.
  No default benchmark is reported as observed data. Return metrics count brand
  order lines marked `is_returned`, grouped by **order-level** try-on flag. This
  flag is not item-level exposure; `is_returned` includes opened return requests,
  not necessarily completed refunds. No causal or seasonality-adjusted claim.
- BOPIS completion uses picked_up/completed pickup fulfillment groups over
  eligible pickup groups, not orders divided by order lines.
- Brand returns no longer include global platform metrics. Preference heatmaps
  are brand-product scoped and require ten distinct users per cell, not ten
  outfits from one user. Missing geography is disclosed: Global, all-time,
  `region_filter_applied=false`; no catalog-tag fallback impersonates user data.
- Product-level conversion breakdown uses grouped queries instead of per-product
  queries. The legacy `per_sku` key is retained with `grain=product`. Headline
  and breakdown exclude cancelled/refunded/failed order lines consistently.
  These are heterogeneous snapshots, NOT a linked-session funnel.
- Implicit generated SKU imports recognize an existing unambiguous natural
  variant, preserving older generated codes rather than duplicating variants.

### Executed evidence (local, 2026-09-21)

| Check | Result |
|---|---|
| Full backend, sequential fresh fixture run | 1291 passed, 5 skipped |
| Partner contracts + analytics + concurrency on PostgreSQL 17.11 UTF-8 | 37 passed |
| Frontend Vitest | 120 passed / 22 files |
| TypeScript + Vite production build | passed |
| Runtime dependency manifest gate | Vercel + Docker passed |
| Real migration chain on local PostgreSQL | empty → head → base → head, parity + schema gate + numeric roundtrip passed |
| Chromium + live local FastAPI/PostgreSQL/Vite | login → CSV Arabic product → SKU edit → store create → store stock → placement create/pause → analytics, 7 checks passed |

The full backend's five skips include three PostgreSQL-only concurrency tests
(run separately above) and two pre-existing environment-dependent tests.
One attempted parallel run was invalidated by the repository's shared SQLite
seed fixture colliding across pytest processes; it was stopped and replaced by
the sequential full run above. Do NOT run these pytest invocations concurrently
against the same checkout/data directory. CI's PostgreSQL job is separate.

The browser test discovered a response-schema defect rather than only checking
mocked component behavior. Reusable local-only harness:
`backend/scripts/check_brand_portal_browser.py` (Playwright optional tooling).
It refuses non-loopback targets. It requires an already provisioned **fresh local
brand tenant**, JSON login credentials outside Git, and a writable evidence dir.
No actual credentials, cookies, authorization headers or production row data
are committed with test evidence.

### Reproduce

```sh
pip install -r backend/requirements.txt
PYTHONPATH=. pytest -q backend/tests
# Run SEQUENTIALLY, against a local disposable PostgreSQL service:
CONFIT_PORTAL_TEST_PG_URL="$LOCAL_TEST_DATABASE_URL" PYTHONPATH=. pytest -q \
  backend/tests/test_brand_portal_regressions.py \
  backend/tests/test_brand_portal_analytics.py \
  backend/tests/test_brand_portal_postgres.py
npm ci --prefix frontend
npm run build --prefix frontend
npm test --prefix frontend
# Optional real browser, with a fresh local-only tenant and running API/Vite:
pip install playwright
python -m playwright install --with-deps chromium
python backend/scripts/check_brand_portal_browser.py \
  --credentials-file /path/outside/repo/local-login.json \
  --evidence-dir /path/to/local-evidence
```

### Release and rollback

Use ONE feature branch: `fix/brand-partner-portal`. PR #127 merged as
`037d01e0bf85c0113b61e258511754896037dedd`. Subsequent PR uses the same branch,
merging current main normally as required. Required checks are not bypassed.
No migration/production-data change was needed. Revert the relevant merge commit
for application rollback; do not revert unrelated parallel work. Imported rows
are business data and are not automatically deleted by a code rollback.

### OPEN / not claimed complete

1. **Production partner UAT:** no real limited brand account was supplied. No
   production login was invented and no customer accounts were promoted. Local
   success and health 200 are not production feature acceptance.
2. **Shared staff membership:** the existing schema links one `BrandProfile` to
   one user. A real multi-user owner/manager/staff tenant invitation workflow and
   role-specific write policy require a reviewed membership migration/backfill,
   staging rehearsal and production-schema release order. Not implemented here.
3. **Ad delivery/billing:** placement configuration and local counter budget
   enforcement are tested. No proof of global serving/ranking, daily spend reset,
   fraud protection or idempotent billable event ingestion. Do not sell this as
   a production ad-billing system; do not click-track synthetic production data.
4. **Atomic audit:** existing post-commit best-effort audit handling is not a
   transactional outbox. Added audit call sites do not close that architecture gap.
5. **Scale/operations:** synchronous bounded CSV imports have no durable worker
   retry/recovery protocol; no throughput/SLO/load acceptance, catalog pagination,
   complete product editing/deactivation, team provisioning or full localization
   acceptance was performed. Unicode product/store input was tested.
6. **Telemetry:** no session-linked funnel, completed-render-only denominator,
   matched cohorts, regional/time filters or independent billing reconciliation
   is implied. All-time snapshots and their limitations are stated in API/UI.
7. **Storage:** initial production health explicitly reported local storage as
   non-production-grade. This change imports image URLs, not a durable image
   asset-upload system. Production object storage setup is a separate dependency.
8. **Cloudflare Workers:** branch build checks failed with no accessible log
   explanation; GitHub code/security/schema gates and Vercel deployment status
   were separate. Cloudflare readiness is NOT established.
9. **Secrets:** rotate the supplied tokens/passwords. A temporary restrictive
   local file is not a secret manager and is not a durable private memory vault.

This report is for repair and learning, not punitive evaluation of individuals.

### Additional real-browser mobile finding
At a 390px viewport the existing navbar overflowed to 454px and hid *all* partner
navigation below md. The shared shell also used light text on white cards and
navy headings on a near-black body. The follow-up makes the content shell light,
keeps a dark navigation area, uses one scrollable route list on every breakpoint,
wraps header controls and removes the fabricated “Massimo Dutti” identity fallback.
This was a browser-observed defect, not a visual redesign claim.
