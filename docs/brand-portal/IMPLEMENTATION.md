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
