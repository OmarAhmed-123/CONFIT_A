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
Existing-data ownership/backfill and rolling-deployment behavior still need
explicit release evidence beyond the empty-database gate.

## Actual verification before preview deployment

* Full backend suite: **1439 passed, 7 skipped**, 283.63 seconds.
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

## Mandatory verification matrix

| Gap | Status | Evidence | Files/PR/Commit | Test | Local | Staging | Production |
|---|---|---|---|---|---|---|---|
| Authenticated end-to-end workflow and cleanup | NOT VERIFIED | No deployed UAT yet | Portal routes / pending PR | API regression only | PARTIALLY VERIFIED | NOT VERIFIED | NOT VERIFIED |
| Membership, invitations and ownership | PARTIALLY VERIFIED | Tenant and concurrent last-owner tests | brand_access, brand_team, 0019 | Local/PG passes | VERIFIED | NOT VERIFIED | NOT VERIFIED |
| CPC serving, billing and fraud controls | PARTIALLY VERIFIED | Counter journal only; billable=false | placement_counters, 0021 | Replay/day/concurrency passes | PARTIALLY VERIFIED | NOT VERIFIED | NOT VERIFIED |
| Atomic critical audit | PARTIALLY VERIFIED | Shared transactions and rollback tests | partner_audit, 0019 | Suite passes | VERIFIED | NOT VERIFIED | NOT VERIFIED |
| Durable import, pagination and scale | PARTIALLY VERIFIED | SQL checkpoint queue; bounded reads | partner_import_queue, worker, 0020 | Unit/contract passes; no production load claim | PARTIALLY VERIFIED | NOT VERIFIED | NOT VERIFIED |
| Product/SKU lifecycle and complete EN/AR | PARTIALLY VERIFIED | Lifecycle APIs, editor, paired locale gate | partner_product_service, frontend b2b | 247 frontend tests; backend suite | PARTIALLY VERIFIED | NOT VERIFIED | NOT VERIFIED |
| Analytics semantic contracts | PARTIALLY VERIFIED | Null denominator and unpaged aggregate tests | brand_repository, brand_service | Totals regression passes | PARTIALLY VERIFIED | NOT VERIFIED | NOT VERIFIED |
| Persistent image lifecycle / CSP | PARTIALLY VERIFIED | Local validation and durable intent tests | partner_assets, 0020 | Local tests; no S3 lifecycle claim yet | PARTIALLY VERIFIED | NOT VERIFIED | NOT VERIFIED |
| Cloudflare necessity / actual edge verification | NOT VERIFIED | Optional R2 adapter found | storage_service; existing integrations | No request verification yet | PARTIALLY VERIFIED | NOT VERIFIED | NOT VERIFIED |
| Credentials / rotation | PARTIALLY VERIFIED | Deployment/GitHub encrypted configuration installed | No values committed | No rotation evidence | PARTIALLY VERIFIED | PARTIALLY VERIFIED | NOT VERIFIED |

## Remaining release blockers

Actual staging Login→Portal→Catalog→Product→SKU→Inventory→Store→Placement→
Analytics→Audit; persistent S3 read/delete and cleanup proof; automated runner
execution; variant/store/inventory/analytics UI pagination and complete role
visibility/localized errors/formatting; production-compatible existing-data
migration proof; trusted CPC business decisions/serving/fraud/reconciliation;
protected PR/CI/release and production checks. Do not interpret this checklist
or a green build as evidence that those blockers are resolved.
