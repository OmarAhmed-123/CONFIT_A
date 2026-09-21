# Brand Partner Portal — evidence-first gap closure

Date: 2026-09-21. Branch: `fix/brand-partner-portal`.

**Not a production-readiness certificate.** This extends PR127/132, preserves
PR145's directional schema compatibility policy, and does not rebuild it.
Audit is for fixing defects and learning, not punishment.

## Confirmed gaps and changes

* Global brand role / founder pointer was not a team-membership model. Added
  user-backed memberships, hashed 72-hour invitations, email verification on
  acceptance, owner-only administration, last-active-owner protection, and
  deterministic founder backfill. Invited consumers are not globally promoted.
* Critical portal changes and audit now share the database transaction.
  PostgreSQL protects audit rows against ordinary UPDATE/DELETE; a database
  owner is not prevented from changing the schema. Actor/request attribution
  is captured without invitation tokens or credentials in audit payloads.
* Product lifecycle, paginated variants, price-specific permissions, image
  upload intents and durable SQL import checkpoints were missing. Added these
  alongside existing APIs rather than deleting existing consumer behavior.
* Placement counters lacked an idempotent journal. New journal/lock/replay
  preserves one outcome per key and UTC-day budgets, but these remain
  **partner-reported, nonbillable counters**, not trusted serving receipts.
* Catalog pagination no longer truncates headline analytics totals. A missing
  exposure denominator is null, not a fabricated zero conversion rate.
* New queued imports accept approved public image origins or blank images;
  blank images create drafts for subsequent persistent image upload. Legacy
  synchronous import accepts external URLs; availability/CSP compatibility
  of those URLs is not guaranteed.

## Migration and release

Chain: upstream `0018_outfit_share_lifecycle` →
`0019_brand_membership_atomic_audit` → `0020_partner_catalog_operations` →
`0021_partner_counter_journal`.

Local PostgreSQL empty-database upgrade, ORM parity, required-object schema
checks, full downgrade/re-upgrade and numeric roundtrip passed (56 tables).
Isolated staging was migrated to 0021; production was not migrated by this
mission at this point. No gate/protection is disabled to make release pass.
Existing-data backfill now has an explicit PostgreSQL migration rehearsal: two
existing founders (including an inactive account) preserve ownership/timestamps
and global consumer roles. A legacy direct INSERT after upgrade also provisions
its founder membership through the PostgreSQL trigger. This is a scratch-data
rehearsal, not a copy of production data.

## Actual verification before preview deployment

* Full backend suite: **1441 passed, 7 skipped**, 294.26 seconds (final rerun).
* Frontend verify: i18n check, TypeScript, **30 files / 247 tests**, build passed.
* PostgreSQL counter/owner concurrency file: **4 passed** (same-key concurrent
  events, UTC rollover/replay, last-owner race, totals beyond a catalog page).
* Targeted catalog/import/counter suite: **27 passed, 2 skipped** on SQLite.
* Staging migration command exited 0. Deployment and browser UAT are separate
  checks; migration success does not prove the user workflow.

## Operation and security contracts

* Roles: owner manages team; owner/manager have operational writes;
  catalog_editor has catalog edits but not pricing/publishing/import;
  analyst/staff are read-only. All resource IDs are tenant-authorized server-side.
* Images: ≤4 MiB input, JPEG/PNG/WebP MIME/extension agreement, one frame,
  ≤20 megapixels, decode/re-encode with metadata removal, maximum 1600px and
  ≤2 MiB output. SVG is rejected. This is content normalization, **not a malware
  antivirus certification**. Same-origin reads respect draft visibility and
  hash/length integrity. Durable intents support retryable garbage collection.
* Storage requires `BRAND_ASSET_PROVIDER=s3`, bucket/prefix and authorized S3
  credentials in the deployment secret manager. No bucket credential is
  supplied to the client. Staging has a separate object prefix.
* `backend/scripts/run_partner_jobs.py` resumes ≤20-row transactional batches;
  `--purge-assets` retries stale intents/deletions. The GitHub workflow polls
  every 10 minutes after it reaches the default branch; GitHub scheduling is
  best-effort, not a low-latency worker SLA. SQL checkpoints survive process
  loss. The CLI is not an HTTP server and uses ephemeral bootstrap keys, not
  the application's production JWT/body-data keys.
* Worker configuration was installed into GitHub encrypted secrets. A scheduled
  successful execution is **not yet evidenced**. Private local mode-600 files
  are not a substitute for a secret manager. Exposed credential rotation has
  not been completed or claimed.
* Cloudflare R2 is an optional storage adapter, not a requirement of this
  implementation. Current Cloudflare deployment/check ownership and actual
  edge-request behavior are not verified; no Cloudflare infrastructure added.

## Analytics interpretation

Headline counts use all owned rows, independently of catalog paging. Existing
analytics combine retained product-view history, current cart rows and order
line snapshots; they are not a session-linked acquisition funnel. Return
requests are not settled refunds. Order try-on evidence is not SKU exposure.
No seasonality, geography, causal improvement or verified CPC billing is
inferred from these snapshots. Complete per-metric filter/grain documentation,
localized formatting and all list pagers remain open.

## Actual runtime UAT and release outcome

PR: https://github.com/OmarAhmed-123/CONFIT_A/pull/150 (**draft**).
Implementation commit: `82fc979`; review follow-up commits on the same branch.
No merge, no production migration, and **no Vercel deployment of this work**.

Vercel rejected preview creation with HTTP402:
`api-deployments-free-per-day` (more than100; retry after24hours). The Vercel
GitHub check reports the same build-rate-limit. Rather than use production
accounts, a production-mode workspace API/frontend was connected to the
already-isolated Neon staging database and real S3 staging namespace.

That alternate verification runtime passed:

* Actual password login for three isolated accounts, official invitation and
  acceptance, owner role change, revoked-member denial, cross-tenant404.
  Verified-email test accounts were bootstrapped in the empty isolated database;
  this does **not** certify email delivery/verification transport.
* Queued import/replay and a **separate CLI process** consuming one durable row;
  progress/history, product edit, SKU identity + inventory endpoints, store
  inventory, placement creation/replay, analytics and tenant-scoped audit.
* Real S3 upload/read, draft anonymous404, published anonymous image200,
  unpublish404, archive/write409, image deletion and provider HEAD404.
* Catalog editor denied when trying to clear an existing price override.
* Application-role UPDATE rejected by both append-only PostgreSQL triggers.
* Chromium UI sign-in/session cookie, real stored image render, product editor
  save via CSRF-protected cookie, inventory/placements/analytics/team/audit
  views, English/LTR and Arabic/RTL. No recorded post-login API failures or
  page errors. Browser evidence is from `82fc979`, before the final disclosure
  banner and inventory-total correction; those follow-ups have fresh full tests.

An initial UAT harness incorrectly supplied stock to the variant-identity
endpoint and correctly received422; the record is preserved. The corrected
harness uses the separate inventory endpoint. A first screenshot assertion
also ran before the image finished loading; waiting for actual image decode
passed. Neither failed attempt is represented as a product fix.

**Cleanup:** stopped the runtime; checked that only the three UAT accounts
existed; cleared54 test-data tables in the dedicated staging database with the
migration role, retaining Alembic0021 and migration history. S3 prefix listing
returned zero objects. Test passwords/accounts were removed from private
working configuration. Production was not used for cleanup.

**Scale sample:** real migrated local PostgreSQL,1000 products/30000 variants,
2 catalog SELECTs,25 products ×25 returned variants, correct totals across all
30 variants/product. Query plans and one measured duration are recorded. This
is a bounded-query sample, **not** a throughput/SLA or all-endpoints load test;
legacy nested store inventories and some UI list navigation remain incomplete.

**CI:** the initial backend/frontend/deployment-contract jobs passed. The
PostgreSQL job exposed a scratch test trying to DROP a table referenced by the
new immutable journal. It now renames the required table, preserving the same
missing-object/fail-closed assertion;45 PostgreSQL checks passed locally.
Gitleaks flagged a test-only HTTP idempotency identifier, not a credential. The
parameter was renamed and exactly that historical fingerprint is documented
in `.gitleaksignore`; no scanning rule/path was disabled. Follow-up CI must be
checked separately. New membership/queue/counter PostgreSQL tests are now
included in the existing CI PostgreSQL job.

**Production read-only check:** `/api/v1/health` returned200/healthy/schema-ok,
code/database revision0018. Last observed production deployment commit was
`3558d14`. The release gate **correctly blocks** this branch: it requires0021,
three unapplied migrations. No migration is applied simply to turn a gate green
while preview deployment and readiness gaps remain. Main protections are intact.

**Cloudflare:** current production health request reported Vercel headers;
repository API routing uses Vercel/same-origin, no Wrangler configuration was
found, and Cloudflare is not a required branch-protection check. R2 is optional.
The installed `Workers Builds: confit-a` integration nevertheless failed; its
private dashboard/edge deployment was not verified. It was not disabled or
presented as repaired. No claim that the entire project's Cloudflare use is legacy.

## Mandatory verification matrix

Staging cells below include the real isolated Neon/S3 checks, but remain
PARTIALLY VERIFIED where the Vercel-hosted runtime was blocked. Evidence links
are under [`evidence/2026-09-21`](evidence/2026-09-21/README.md).

| Gap | Status | Evidence | Files/PR/Commit | Test | Local | Staging | Production |
|---|---|---|---|---|---|---|---|
| Authenticated workflow and cleanup | PARTIALLY VERIFIED | API UAT, Chromium, cleanup-proof | PR150 /82fc979 | Login→audit;54 empty tables;zero S3 objects | VERIFIED | PARTIALLY VERIFIED | NOT VERIFIED |
| Membership, invitations and ownership | PARTIALLY VERIFIED | PG concurrency/backfill + staging role/IDOR | brand_access, brand_team,0019 /PR150 | Last-owner race;existing-owner preservation;revocation | VERIFIED | PARTIALLY VERIFIED | NOT VERIFIED |
| CPC serving, billing and fraud controls | PARTIALLY VERIFIED | Counter journal only;billable=false | placement_counters,0021 /PR150 | Replay/day/concurrency;no trusted billing proof | PARTIALLY VERIFIED | PARTIALLY VERIFIED | NOT VERIFIED |
| Atomic critical audit | PARTIALLY VERIFIED | Rollback tests;live migrated trigger rejection | partner_audit,0019 /PR150 | Same-transaction tests;app-role UPDATE blocked | VERIFIED | PARTIALLY VERIFIED | NOT VERIFIED |
| Durable import, pagination and scale | PARTIALLY VERIFIED | Separate worker process;scale query plans | queue/worker/repositories,0020 /PR150 | Checkpoints;1000 products/30000 SKUs;no scheduled-run proof | PARTIALLY VERIFIED | PARTIALLY VERIFIED | NOT VERIFIED |
| Product/SKU lifecycle and complete EN/AR | PARTIALLY VERIFIED | API lifecycle, browser editor,RTL screenshot | product service/frontend /PR150 | Final suites;UI session save;locale gate | PARTIALLY VERIFIED | PARTIALLY VERIFIED | NOT VERIFIED |
| Analytics semantic contracts | PARTIALLY VERIFIED | Null denominator/unpaged totals;staging reads | brand_repository/service /PR150 | Totals regressions;not causal/session attribution | PARTIALLY VERIFIED | PARTIALLY VERIFIED | NOT VERIFIED |
| Persistent image lifecycle / CSP | PARTIALLY VERIFIED | Actual S3 upload/read/delete/provider404 | partner_assets,0020 /PR150 | Image validation;browser render;draft/public visibility | VERIFIED | PARTIALLY VERIFIED | NOT VERIFIED |
| Cloudflare necessity / edge verification | PARTIALLY VERIFIED | Vercel production request;optional R2;failed external check | storage_service/existing integration | Cloudflare edge/dashboard not verified | PARTIALLY VERIFIED | NOT VERIFIED | PARTIALLY VERIFIED |
| Credentials / rotation | PARTIALLY VERIFIED | Secret-manager configuration;no values in deliverables | Provider settings;no credential values in Git | Test credentials removed;exposed keys not rotated | PARTIALLY VERIFIED | PARTIALLY VERIFIED | NOT VERIFIED |

## Remaining blockers and work — explicitly not closed

1. Vercel staging deployment and repeat UAT on that exact deployed commit;
   final CI/release, approved production migration and smoke checks.
2. **BRD §2.1/3.4 requires placement billing and CPC surfaces.** Trusted serving
   receipts, spend authorization/funding, fraud controls, financial ledger,
   refund/reconciliation and actual ad delivery are not delivered by a counter
   journal. No charges should be inferred or enabled from these counters.
3. Automatic scheduled-run evidence (the workflow is not on the default branch
   yet), crash/concurrent-worker rehearsal, full queue monitoring, query/index
   coverage and load evidence for every list. GitHub cron is best-effort.
4. Complete variant/store/inventory/analytics UI pagination, role-aware control
   visibility, dynamic errors and number/date/currency localization. RTL and
   paired dictionaries do not prove complete localization/accessibility.
5. Full source/grain/filter/display contracts for every snapshot; no causal
   return-reduction, geography, seasonality or SKU-exposure claims.
6. Image replacement/orphan lifecycle, legacy external-URL compatibility,
   deployed CSP and serverless request-limit behavior need further verification.
   Normalization is not an antivirus certification.
7. BRD extras such as search-index sync, barcode/compare-at/size-chart editing,
   store operating hours and automatic low-stock notifications are not certified
   by this delivery's narrower operational tests.
8. Exposed credential rotation remains unperformed. Coordinated production
   credential replacement/redeployment is unsafe while Vercel deployment is
   quota-blocked and dependency impact is unknown. Do not treat a private local
   file as a secret manager or assume existing historical secret exceptions
   mean the old credentials have been rotated.

## Design references consulted

* [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): explicit tenant/resource authorization, deny by default, least privilege.
* [OWASP API1 BOLA](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/): authorize every supplied resource ID.
* [SQLAlchemy transaction documentation](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html): savepoint versus outer transaction ownership.
* [PostgreSQL locking](https://www.postgresql.org/docs/current/explicit-locking.html) and [SELECT](https://www.postgresql.org/docs/current/sql-select.html): parent locks for first inserts and skip-locked queue claims.
* Project BRD and previous `IMPLEMENTATION.md` are scope references, not evidence
  that their example metrics or untested features are real.
