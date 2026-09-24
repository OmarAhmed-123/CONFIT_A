# CONFIT Admin Governance Re-audit — Evidence, Decisions and Remaining Limits

**Date:** 2026-09-24  
**Scope:** Admin Governance, Audit, Integrity, Readiness, Admin Analytics,
Attribution/Cohort semantics, Admin RBAC, Admin UX/accessibility and directly
related operations. No VTON redesign, consumer-page redesign or general payment
rewrite.

This document complements:

- `ADMIN_GOVERNANCE_THREAT_MODEL.md` — actors A–I and exact audit guarantees.
- `ADMIN_GOVERNANCE_AUDIT_OPERATIONS.md` — key rotation, DB roles, full scan,
  incident response and recovery.

## 1. BRD (actual requirements, not marketing)

### Goal

An admin must be able to decide whether the platform, its audit evidence and
its operational metrics can be trusted **within explicitly stated limits**.
No missing data may appear as zero, unknown as ready, an observational
correlation as causal, or an operational amount as a settled ledger amount.

### Users

- Platform admin/operator: investigates privileged activity and readiness.
- Security responder/auditor: independently verifies trail integrity.
- Product/finance reviewer: reads operational attribution without mistaking it
  for accounting or cross-currency money.
- Brand partner: has no platform-admin access and remains tenant-scoped.

### Requirements

1. Chained audit rows must be deterministically verifiable and runtime DB
   credentials must be unable to rewrite/delete/truncate history.
2. Verification coverage (window vs full history) must travel on the API.
3. Core readiness: unknown/not-probed is not ready. Optional/supporting unknown
   remains non-blocking but visible.
4. Metrics carry denominator/sample semantics; no invented threshold.
5. Money remains partitioned by currency; no implicit FX or `$` label.
6. Return numerator/denominator use one unit and one cohort assignment.
7. Authenticated authorization denials and sensitive audit reads are audited.
8. Admin governance remains usable at 390/414/768/1024 widths and by keyboard;
   automated semantics do not substitute for a manual AT/contrast evaluation.

### Non-goals

- Build a general ledger or payment settlement system without a product
  requirement/provider integration.
- Claim causality from self-selected cohorts.
- Claim immutability/non-repudiation without an independent trust boundary.
- Invent a legal retention period or statistical significance threshold.
- Add a Transactional Outbox without an external delivery requirement.

## 2. Baseline PR verification

### PR #187 — what was correct

**CONFIRMED:** persisted `prev_hash`, `entry_hash`, `chain_key_version`;
HMAC-SHA256; dedicated production secret validation; SQLAlchemy mapper listener;
PostgreSQL transaction advisory lock; direct row-change/deletion tests.
Production proof after the re-audit: a deliberate read-only full-history scan
verified 2 chained rows from genesis, 436 honestly labelled legacy rows and 0
bypass rows among 438 rows at that time.

**PARTIALLY CONFIRMED / overstated:**

- "single enforcement point" covered ORM mapper inserts, not SQLAlchemy Core,
  bulk helpers or direct SQL. Supported production code had no such bulk path,
  but the database allowed one. The re-audit added global bypass detection and
  a static production-path gate; direct SQL inserts are still possible to a
  credential with INSERT (expected for the app role) and are detected if
  unchained.
- `resolve_key(key_version)` ignored `key_version`; rotation was documented but
  not implemented. PR #201 implemented active/retired version resolution and
  fail-closed tests.
- canonical v1 used `\x1f` while claiming the separator could not appear in
  fields. `ip_address`/other free text could contain it. PR #201 sanitises the
  delimiter at the one supported write path and tests crafted boundary shifts.
- the chain was **tamper-evident**, never immutable.

### PR #188 — what was correct

**CONFIRMED:** the Admin Analytics view used the public `/health` result; fetch
failure rendered UNKNOWN; blocking/degraded names were visible. Persisted
verification runs enabled a later run to detect deletion of a previously
recorded head; behavioural tail-truncation tests exist.

**PARTIALLY CONFIRMED / overstated:**

- `audit_verification_runs` was described as immutable but production had no
  triggers and `confit_app_rw` held UPDATE/DELETE/TRUNCATE. Rolled-back real
  production probes all succeeded. Migration 0022 (#201) revoked them and
  installed defence-in-depth triggers on both audit tables. After migration,
  the same runtime probes returned `permission denied`; owner UPDATE/DELETE/
  TRUNCATE hit the append-only trigger.
- a 200 malformed/partial `/health` response could crash the banner or be
  trusted by erased TypeScript types. Runtime parsing now sends it to UNKNOWN.
- public `/health` omitted `unprobed_capabilities`; supporting unknowns were
  hidden from the banner. Names (not sensitive details) are now exposed.
- the old pure readiness contract said `core + not_probed => ready=true`.
  Re-audit correction: UNKNOWN core capability now blocks readiness.

### PR #189 — what was correct

**CONFIRMED:** zero denominators became JSON `null` and UI N/A while measured
zero remains `0`; operational metrics were labelled not-a-ledger; covered admin
order transition/demo capture mutation + primary audit event share one DB
transaction and rollback tests prove both-or-neither.

**PARTIALLY CONFIRMED / overstated:**

- N/A for zero did not define a statistical minimum-sample policy. The API now
  carries sample size and explicitly publishes `threshold: null`,
  `pending_business_decision`; no threshold was invented.
- financial prose did not stop `total_gmv` from summing USD + EGP and the UI
  printing `$`. The currency hardening partitions GMV/attribution by
  `Order.currency`; mixed populations publish a null flat total and no FX.
- the windowed dashboard paired windowed GMV with an all-time attribution
  ledger. Attribution now receives the same `Order.created_at` bounds.
- the returns denominator used eligible orders while the numerator counted all
  ReturnRequest rows and used a different cohort flag. It now counts distinct
  eligible orders with ≥1 non-rejected request; numerator and denominator both
  group by `Order.try_on_assisted`; duplicate requests count once.
- adding a `financial_semantics` sentence did not create a financial ledger.
  The API now also says machine-readably: `recorded_attributed_unsettled`,
  `unreconciled`, `reconciled_against: null`. No ledger was fabricated.

## 3. Evidence matrix

| Claim | Source | Runtime evidence | Test evidence | Status |
|---|---|---|---|---|
| Audit rows after 0020 are HMAC chained | `core/audit_chain.py`, migration 0020 | production full CLI: 2 chained rows, no breaks (point-in-time) | `test_audit_hash_chain.py` | CONFIRMED |
| Historical legacy rows were protected at creation | none | 436 production rows had no hash | tests label them unchained; no backfill | NOT CONFIRMED (intentionally never claimed) |
| Runtime role cannot mutate audit tables | migration 0022, `audit_db_guard.py` | production UPDATE/DELETE/TRUNCATE as `confit_app_rw` blocked | PG trust-boundary tests | CONFIRMED |
| Verification-run table is immutable | no external/WORM boundary | owner can DROP trigger using DDL | trigger + privilege tests only | PARTIALLY CONFIRMED: database-restricted append-only, not immutable |
| Dashboard integrity verifies all history | no | API mode is `window_sample` | coverage contract tests | NOT CONFIRMED (claim removed) |
| Deliberate full-history path exists | `scripts/verify_audit_chain.py` | production read-only scan executed | trust-boundary tests | CONFIRMED |
| Tail deletion after a persisted run is detected | migration/service 0021 | production run history not exercised with destructive test | real DB behavioural delete test | CONFIRMED locally; production destructive test not performed |
| K1→K2 mixed rows verify | `resolve_key` + runbook | no production rotation performed | wrong/missing/mixed-key tests | CONFIRMED locally; production rotation UNVERIFIED |
| Admin readiness uses one source | public `/health` + hook | production `/health`: healthy but ready=false, VTON blocking (point-in-time) | backend + banner/parser tests | CONFIRMED |
| Malformed/partial health is not ready | runtime parser | no safe production fault injection | parser cases + UNKNOWN banner | CONFIRMED locally |
| Mixed currencies are never summed | repository currency partition | production payload after deployment pending | mixed/single-currency DB tests | CONFIRMED locally |
| Return cohorts use matching boundaries | repository distinct-order query | production values not independently recomputed | duplicate/rejected/window tests | CONFIRMED locally |
| External WORM anchoring exists | none | none | none | REQUIRES INFRASTRUCTURE |
| 390px navigation keeps all actions | navbar + native detail button | local Chromium 153 at 390/414/768/1024: no page overflow; 7 links; governance links initially visible; own table scroller; keyboard Enter expanded | structural/axe tests + `docs/evidence/admin-governance-browser-report.json` | CONFIRMED locally; production authenticated UI UNVERIFIED |
| WCAG 2.2 conformance | no conformance evaluation | none | axe excludes contrast/target-size in jsdom | UNVERIFIED — no compliance claim |

Allowed status vocabulary is intentional: CONFIRMED, PARTIALLY CONFIRMED,
NOT CONFIRMED, UNVERIFIED, REQUIRES INFRASTRUCTURE, REMAINS OPEN.

## 4. Architecture decisions

### Audit write and verification

- Primary business mutation + primary audit event: **one local DB transaction**.
- External replication: no requirement and no independently controlled sink;
  therefore **no Transactional Outbox**. If external WORM arrives, use an
  outbox row in the same transaction, deterministic event id, at-least-once
  relay, idempotent sink, retry/backlog/error visibility. Never claim exactly
  once.
- Dashboard verification: bounded O(k) sample (k ≤ 500) plus predecessor/global
  head queries; it never full-scans per request.
- Full verification: O(n), batched offline CLI.

### External anchoring alternatives

| Alternative | Decision |
|---|---|
| HMAC chain only | Implemented; catches DB-only tampering, not actor I (DB + key). |
| Signed checkpoint in same DB | Rejected as boundary theatre; same attacker rewrites it. |
| Merkle root in same DB | Rejected for same reason; adds complexity, no new trust. |
| External audit sink/outbox | Appropriate only when an independent sink/operator exists. |
| KMS/HSM asymmetric signing | Valuable: DB writer cannot derive private key, but infrastructure/key custody is not provisioned. |
| S3 Object Lock compliance mode | Suitable WORM tier only with a real Object-Lock bucket, retention policy and independent credentials. None is configured/proven. |

Status: **REQUIRES INFRASTRUCTURE**. The app's ordinary S3-compatible storage
credentials live in the same deployment secret boundary; writing a JSON file
there and naming it WORM would be false.

### Canonicalization

RFC 8785/JCS was evaluated. Canonical v1 hashes a flat fixed-order list and the
exact stored JSON strings, not an arbitrary JSON object. Re-parsing and JCS-
normalising old payloads would change what is protected and introduce parser
number semantics. Decision: keep versioned fixed-order v1, enforce delimiter
absence, retain `CANONICAL_VERSION` for a deliberate future v2.

## 5. Security event taxonomy (current)

| Class | Required event | Current event/decision |
|---|---|---|
| Authentication | login success/failure | `USER_LOGIN_SUCCESS`, `USER_LOGIN_FAILED` |
| MFA | success/failure/change/recovery | `MFA_TOTP_STEP_ACCEPTED`, `MFA_FAILED`, `MFA_ENABLED`, `MFA_DISABLED`, `MFA_CODES_REGENERATED` plus reauth failures |
| Session | logout | `USER_LOGOUT` |
| Authorization | authenticated denied operation | `AUTHORIZATION_DENIED` (path/method/roles only; no query/token/body) |
| Privileged audit read | row trail/search | `ADMIN_AUDIT_VIEW`, includes filters/counts; recursion-safe because insert occurs after query |
| Integrity operation | verify | `ADMIN_AUDIT_INTEGRITY_CHECK` |
| Aggregate-only audit reads | facets/stats | deliberately not logged: no row content; avoids recursive noise; main trail search is logged |
| Business admin mutation | order state/demo capture | `ADMIN_ORDER_TRANSITION`, `ADMIN_DEMO_CAPTURE`, atomic with mutation |
| Brand/catalog privileged change | import | `BRAND_CATALOG_IMPORTED` |
| Data rights | export/delete | `GDPR_DATA_EXPORT`, `ACCOUNT_DELETED` |

## 6. Sensitive data

Central enforcement: `core/audit_redaction.py` runs from
`UserRepository.log_audit`. Credential-bearing field names and recognised token, PEM and payment-card patterns;
free-text values are scrubbed centrally; booleans such as
`password_updated=true` are retained because they carry no password. Tests use
fake passwords/tokens/TOTP/card data and assert storage contains redaction
markers, not values. The integrity verifier reports any residual secret match.

Residual privacy fact: actor ID, IP, resource IDs and before/after fields can be
personal data. Audit access remains admin-only and is itself audited. A legal
retention period has not been supplied.

## 7. Retention

**REMAINS OPEN — business/legal policy decision.** No 90-day/7-year rule is
invented. Current hot storage is PostgreSQL/Neon and normal backups inherit the
provider's controls. There is no archive/disposal workflow. Any future disposal
must define legal basis, period, backup handling, approved owner-only procedure,
audited tombstone/checkpoint semantics and impact on chain verification.
Runtime/admin API deletion of history remains prohibited.

## 8. Research used

Primary/authoritative material:

1. OWASP Logging Cheat Sheet — events, sanitisation, data exclusion and log
   protection: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
2. OWASP ASVS 5.0 V16 — auth/authz events, sensitive data, injection and
   logically separate protection:
   https://github.com/OWASP/ASVS/blob/master/5.0/en/0x25-V16-Security-Logging-and-Error-Handling.md
3. NIST SP 800-92 / current log-management project — generation, storage,
   access, analysis and disposal planning:
   https://csrc.nist.gov/projects/log-management
4. NIST SP 800-57 Part 1 Rev.5 — key inventory, protection, lifecycle,
   compromise/recovery:
   https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final
5. RFC 8785 JCS — deterministic canonical JSON:
   https://www.rfc-editor.org/rfc/rfc8785.html
6. PostgreSQL 16 privileges/roles and transaction advisory locks:
   https://www.postgresql.org/docs/16/ddl-priv.html
   https://www.postgresql.org/docs/16/explicit-locking.html#ADVISORY-LOCKS
7. WCAG 2.2 Recommendation and WAI table/status guidance:
   https://www.w3.org/TR/WCAG22/
   https://www.w3.org/WAI/tutorials/tables/
8. AWS S3 Object Lock — actual WORM modes/configuration (evaluated, not
   claimed): https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html
9. Transactional Outbox pattern (architecture reference):
   https://microservices.io/patterns/data/transactional-outbox.html

Mature designs evaluated conceptually: immudb (verifiable append-only DB),
Sigstore Rekor (transparency/Merkle log), Trillian (verifiable log), AWS S3
Object Lock. None was copied into CONFIT without its required operational trust
boundary.

## 9. Evidence discipline / limitations

- A passing test proves only its asserted path.
- CI success is not production verification.
- A Vercel READY deployment proves deployment, not correct DB privileges.
- Hash-chain intact proves integrity under its key/DB threat model, not
  immutability.
- Automated axe/jsdom checks cannot measure paint, colour contrast, clipping,
  real focus scrolling or screen-reader speech.
- No production destructive tamper test will be run merely to make a report
  green; local/isolated PostgreSQL performs destructive cases.
