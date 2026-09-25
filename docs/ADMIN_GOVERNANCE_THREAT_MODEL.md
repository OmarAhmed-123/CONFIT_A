# Admin Governance — Audit Trail Threat Model & Exact Guarantees

Date: 2026-09-24 (re-audit of PRs #187/#188/#189; hardened by migration 0022).
Scope: `audit_logs`, `audit_verification_runs`, the hash chain
(`backend/app/core/audit_chain.py`), the DB guard
(`backend/app/core/audit_db_guard.py`), verification
(`AuditTrailService.integrity`, `backend/scripts/verify_audit_chain.py`).

## Terminology (used precisely, everywhere)

| Term | Meaning here |
|---|---|
| **Tamper-evident** | Mutation/deletion/reordering of chained rows is *detectable* by recomputing the HMAC chain. It is not prevented. |
| **Append-only (database-restricted)** | UPDATE/DELETE/TRUNCATE are rejected by the database itself (REVOKE + triggers) for the stated credential. Not a physical guarantee against the table owner. |
| **Externally anchored** | Chain heads notarised outside this database's trust boundary (WORM store, transparency log). **NOT implemented** — see status below. |
| Never used | "immutable", "tamper-proof", "non-repudiable" — no mechanism in this system supports those words. |

## Attacker ladder and what each one can/cannot do

| Actor | Capability | Outcome against the audit trail |
|---|---|---|
| A. Anonymous user | HTTP only | No access. Admin endpoints require admin JWT (RBAC tests). Failed logins are themselves audited. |
| B. Authenticated non-admin | HTTP only | 403 on all `/admin/*` (RBAC/IDOR tests). Cannot read or write audit rows. |
| C. Admin (legitimate) | Admin API | Can read the trail; every read/mutation is itself audited. No API mutates or deletes audit rows (no such endpoint exists). |
| D. Compromised app process / runtime DB credential (`confit_app_rw`) | SQL as runtime role | Can INSERT rows going forward, **cannot** rewrite history: UPDATE/DELETE/TRUNCATE are revoked *and* trigger-blocked (0022, verified on production). Invalid signed rows fail HMAC/link checks and ordinary unsigned rows that sort after enforcement are classified as bypass/forgery. **Remaining 0023 limit:** because the legacy classifier is id-ordered and INSERT permits an explicit id, an unsigned row deliberately inserted below the first signed id can masquerade as legacy until a database insert guard is deployed. A compromised web process that also reads the HMAC secret has actor-I capability. |
| E. DB owner credential (`neondb_owner`, migrations) | SQL + DDL | Can DROP the 0022 triggers, then mutate. Mutation of chained rows still breaks the HMAC chains (**tamper-evident**). Audit-log tail deletion is caught by persisted run heads; verification-run tail deletion is caught by the independent audit-chain cross-link from the next check. DDL access is the trust boundary — this is why the runtime does not use this credential. |
| F. Infrastructure operator (Neon/Vercel) | Storage/snapshot access | Same as E plus snapshot rewrites. Tamper-evident only; prevention requires external anchoring (**REQUIRES INFRASTRUCTURE**). |
| G. Holder of app secrets (not DB) | `AUDIT_HMAC_KEY` etc. | Can compute valid HMACs but has no DB write path; alone, harmless to stored history. |
| H. DB write access without HMAC key | SQL | Any edit/deletion of chained rows is detected (HMAC recompute fails / links break / predecessor anchor fails). |
| I. DB write access **plus** HMAC key | SQL + secret | Can re-forge the chain forward from any point. Detection limits: (a) cross-run head anchoring catches truncation after a recorded run; (b) key rotation invalidates the stolen key for future rows; (c) full re-forgery is **undetectable internally** — only external anchoring closes this. Stated honestly in the API's `limitations`. |

## Current status per control

| Control | Status |
|---|---|
| HMAC-SHA256 hash chain, canonical v1, genesis-anchored | **CONFIRMED** (local + production row evidence) |
| Separator-injection hardening at the single write path | **CONFIRMED** (tests: `test_audit_trust_boundary.py::TestCanonicalisation`) |
| DB-restricted append-only for runtime role (REVOKE + triggers, both audit tables) | **CONFIRMED** on PostgreSQL (0022; behavioural tests + production probe). SQLite dev: no-op, **documented parity limitation** |
| Verification-run provenance / forged INSERT detection | **PARTIALLY CONFIRMED** (0023): independent domain-separated HMAC chain plus an atomically committed audit-chain tail cross-link detect modification, middle/tail deletion, reordering, invalid/ordinary unsigned forgery, missing/wrong/versioned keys and chain forks. Production schema is at 0023 but has no signed run yet. Explicit low-id unsigned INSERT can still be misclassified as legacy; database INSERT enforcement remains open. |
| Key rotation K1→K2, fail-closed on missing retired key | **CONFIRMED** (tests: `TestKeyRotation` + verification-run rotation) |
| Window verification anchored to actual DB predecessor / genesis | **CONFIRMED** (tests: `TestVerificationCoverage`) |
| Bypass-vs-legacy classification of unchained rows | **PARTIALLY CONFIRMED** (tests + global count on the wire): correct for monotonic application ids, but an explicit low id can sort a new unsigned row into the legacy prefix until the database insert guard is deployed. |
| Cross-run tail-truncation detection | **CONFIRMED** (0021, existing tests) |
| Full-history verification | **CONFIRMED** as a deliberate offline CLI (`verify_audit_chain.py`), never per-request |
| External anchoring (WORM / transparency log) | **REQUIRES INFRASTRUCTURE** — the only credential-isolated sink available today (S3-compatible bucket) lives in the *same* secret store as the app; anchoring there would not move the trust boundary, so claiming it would be theatre. |

## Canonicalisation decision (RFC 8785 evaluated)

Canonical v1 is a fixed-order, `\x1f`-separated join of the stored columns with
a version prefix. RFC 8785 (JCS) was evaluated for v2: it solves key-ordering
and number-normalisation ambiguity for *nested JSON*, but our canonical input
is a flat, fixed-order column list where JSON payloads are embedded as the
exact stored strings — byte-stability is already guaranteed by construction,
and hashing the stored bytes (not a re-parse) is what lets verification work
on rows as they exist. Switching to JCS would re-hash re-parsed JSON and make
verification depend on parser behaviour. Decision: keep v1, enforce the
separator invariant at the write path, keep `CANONICAL_VERSION` so a future
v2 remains possible without breaking old rows.

## Retention

No retention/deletion policy is implemented. That is deliberate: a retention
period is a **business/legal decision that has not been made** (no invented
"90 days"). When made, it must arrive as a documented policy with its own
audited, owner-credential procedure — never a runtime capability.
