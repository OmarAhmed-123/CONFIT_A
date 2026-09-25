# Admin Governance — Audit Operations Runbook

Companion to `ADMIN_GOVERNANCE_THREAT_MODEL.md`. Everything here was executed
at least once for real (locally against PostgreSQL 17, and on production
Neon) — no step is aspirational.

## 1. HMAC key lifecycle

Deployment key material lives in the Vercel secret store; an authorized
operator may use an access-controlled private credential file for deliberate
offline verification. It is never logged, returned by an endpoint or committed.

| Variable | Meaning |
|---|---|
| `AUDIT_HMAC_KEY` | Active signing key (required in production; startup fails without it). |
| `AUDIT_CHAIN_KEY_VERSION` | Integer version stamped on every new row (`chain_key_version`). |
| `AUDIT_HMAC_KEY_V{n}` | Retired key for version *n*. Needed only after a rotation, only for verification. |

### Rotation procedure (K1 → K2)

1. Generate a new high-entropy key K2 (≥ 32 chars, distinct from `SECRET_KEY`).
2. In the secret store, **in one change set**:
   - `AUDIT_HMAC_KEY_V1` ← current K1 value,
   - `AUDIT_HMAC_KEY` ← K2,
   - `AUDIT_CHAIN_KEY_VERSION` ← `2`.
3. Redeploy. New rows are signed with K2 (`chain_key_version=2`); old rows
   verify with `AUDIT_HMAC_KEY_V1`.
4. Run the full-history verifier (§3) and confirm `intact: true` with mixed
   key versions.

Fail-closed property (tested): if a retired key is missing or wrong,
verification reports `key_unavailable` / `entry_hash_mismatch` for those rows
— it never silently passes. Rotate IMMEDIATELY if key compromise is suspected
(actor I in the threat model): rotation limits the forgery window to rows
signed before rotation.

## 2. Database privilege and INSERT-provenance model (0022 + 0024)

- Runtime credential: `confit_app_rw` — INSERT + SELECT only on
  `audit_logs` and `audit_verification_runs` (REVOKE applied by 0022).
- Migration credential: `neondb_owner` — owns the tables, runs DDL. The
  Alembic URL (`ALEMBIC_DATABASE_URL`) is the only place it appears.
- Six 0022 triggers reject UPDATE/DELETE/TRUNCATE for *every* role, including
  the owner, until the owner deliberately drops them (DDL — that act is the
  boundary and is visible in DB logs).
- Two 0024 BEFORE INSERT triggers require all chain-provenance fields on every
  new row. This closes the explicit-low-id/negative-id legacy-classification
  bypass for PostgreSQL and the official SQLite mode. It deliberately checks
  field presence, not HMAC truth: PostgreSQL does not hold the application
  HMAC secret, so non-NULL garbage is admitted and then reported by verification.
- If a NEW runtime role is ever introduced, grant it INSERT/SELECT only on
  the audit tables; migration 0022's conditional REVOKE covers only
  `confit_app_rw` by name.

Verification of the model (run as owner):

```sql
SELECT has_table_privilege('confit_app_rw','audit_logs','UPDATE');  -- must be f
SELECT tgname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
 WHERE c.relname LIKE 'audit%' AND NOT tgisinternal;                -- 8 triggers
```

A rolled-back runtime probe must receive SQLSTATE `23514` for a low-id INSERT
whose chain fields are NULL. Legitimate ORM inserts must continue to pass.

## 3. Full-history chain verification (deliberate, offline)

The dashboard endpoint verifies a **window sample** and says so in its
`coverage` block. The whole chain from genesis is verified only by:

```bash
DATABASE_URL=postgresql://... AUDIT_HMAC_KEY=... \
  python -m backend.scripts.verify_audit_chain
```

Read-only. It verifies BOTH chains from genesis: `audit_logs` and, since 0023,
`audit_verification_runs` (including invalid signatures and unsigned rows that
sort after the first signed id), validates the highest referenced run cross-link
in the audit chain, then checks the last run's recorded audit head. Migration
0024 prevents a runtime caller from adding a new NULL-provenance row at any id.
The CLI still cannot infer whether an unsigned low-id row was maliciously added
*before* 0024, or after an owner deliberately disabled the guard; insertion time
is not authenticated row data. Exit 0 = intact, 1 = violations, 2 = could not
run. Run it after every key rotation, during incident response and periodically.
Never wire it into a request path.

## 4. Production proof (2026-09-25)

The exact sequence was deliberate: PR #206 commit
`7019f4befe91884b2524874d11dfb394c5b0ce5a` first reached Vercel production
state `READY`; only then was 0024 applied with the owner migration credential.
Production subsequently proved:

- Alembic revision `0024_audit_insert_provenance_guard`;
- runtime identity `confit_app_rw` with SELECT/INSERT true and
  UPDATE/DELETE/TRUNCATE/TRIGGER false on both audit tables;
- all eight non-internal guards enabled (six mutation + two INSERT provenance);
- rolled-back unsigned explicit-low-id probes rejected on both tables with
  SQLSTATE `23514` and no persisted probe row;
- one real integrity HTTP-handler execution against production storage added
  exactly one signed verification run and one `ADMIN_AUDIT_INTEGRITY_CHECK`
  cross-link in one transaction; the response model returned status 200,
  `verdict: ok`, `tamper_evident: true`, `coverage.mode: window_sample`, no
  chain breaks/bypass suspects, and the signed run metadata;
- the persisted run had all provenance fields, its response id and request id
  matched storage, and its primary-chain cross-link verified as `anchored`;
- a deliberate full-history follow-up verified 440 audit rows and one signed
  run from their respective genesis values: zero breaks, zero suspected bypass,
  verification-run chain intact, tail anchor `anchored`.

Transport qualification: the authenticated request exercised the real FastAPI
route, dependency chain, transaction and response model using production
runtime-role storage, but through local ASGI transport. It did **not** transit
the Vercel production origin because no production admin login credential was
available and sensitive Vercel signing material is intentionally non-readable.
Therefore storage behavior and HTTP serialization are **CONFIRMED**; a directly
authenticated Vercel-origin integrity response remains **UNVERIFIED**. This
qualification must not be shortened to “production E2E.”

## 5. Incident response — audit integrity

Trigger: `tamper_evident: false` on the integrity endpoint, a non-empty
`breaks` array, `chain_bypass_suspected`, `tail_truncation_detected`, or a
failed CLI run.

1. **Freeze evidence**: capture the integrity endpoint response and run the
   CLI verifier; store both outputs outside the database.
2. **Classify** using the `issue` field:
   - `entry_hash_mismatch` → a stored row was modified after write (actor E/F/H).
   - `chain_link_mismatch` → deletion/reordering at or before that row.
   - `tail_truncation_detected` → newest rows deleted after the last
     verification run.
   - `chain_bypass_suspected` → something wrote unchained rows after chaining
     began (writing path bypass, or hash columns nulled).
   - `key_unavailable` / `verification_run_key_unavailable` → operational
     (missing retired key), not necessarily an attack — fix the secret store
     first, re-run.
   - `verification_run_hash_mismatch` → persisted verification result changed.
   - `verification_run_link_mismatch` → a signed verification result was
     deleted/reordered within the checked chain.
   - `verification_run_tail_deletion_detected` → the newest run referenced by
     the independent audit chain no longer exists.
   - `verification_run_crosslink_mismatch` / `verification_run_malformed_crosslink`
     → the persisted run no longer matches its audit-chain reference, or that
     reference is structurally invalid.
   - `verification_run_forgery_suspected` → unsigned result inserted after
     signed-run enforcement began (raw/Core/direct SQL bypass).
3. **Contain**: rotate `AUDIT_HMAC_KEY` (§1) — assume actor I until excluded.
   Rotate the `confit_app_rw` password if process compromise is plausible.
   Check Neon logs for DDL (`DROP TRIGGER`) and direct connections.
4. **Scope**: the last intact verification run in `audit_verification_runs`
   bounds the tamper window (`run_at`, `head_row_id`).
5. **Record**: the investigation itself must appear in the audit trail
   (admin integrity checks are audited as `ADMIN_AUDIT_INTEGRITY_CHECK`).
6. Known internal limit (threat model, actor I): DB-write + HMAC-key
   compromise can re-forge forward undetectably; treat external evidence
   (DB logs, backups, verification-run history) as authoritative in that case.

## 6. Verification cost model

- Dashboard endpoint: bounded audit sample (`sample_limit` ≤ 500) + bounded
  verification-run tail (≤100) + highest referenced 0023 run among at most 100
  integrity-read events (safe under out-of-order concurrent responses) + indexed anchor/global bypass counts — no full-history
  request scan.
- CLI verifier: O(n) over audit rows plus O(r) over verification runs —
  deliberate runs only.
- Never add a full scan to a request path; that is what the CLI is for.

## 7. 0024 deployment and rollback

Deployment order is a compatibility rule, not a preference:

1. Deploy 0023-aware code from PR #206. Confirm the exact commit is `READY`.
2. Apply `alembic upgrade 0024_audit_insert_provenance_guard` with the owner URL.
3. As runtime role, prove grants and rolled-back low-id rejection; then execute
   one supported-path insert and run the full-history verifier.

Rollback has no data rewrite: `alembic downgrade 0023_verification_run_hmac_chain`
only removes the two INSERT triggers/functions. It reopens the low-id bypass and
must trigger an incident/risk record. If application code must roll back to a
pre-#206 writer, remove 0024 **before** switching traffic because that writer
may emit unsigned verification-run rows which 0024 correctly rejects. Never
downgrade 0023 merely to hide a verification failure; preserve evidence first.
