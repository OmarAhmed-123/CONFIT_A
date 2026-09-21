# Admin Governance, Audit, Analytics, Telemetry & Health — Closure Report

**Date:** 2026-09-21
**Scope:** Admin Governance · Admin Analytics · Audit Trail · Telemetry/Observability · Health/Readiness · admin access bootstrap
**Audited baseline:** `cd17a220677efe0f39b60157e7acfd888f4df351`
**Closure state:** all 17 gaps (G-01…G-17) shipped to `main`
**Branch:** `fix/admin-governance-audit-telemetry` — one branch, five pull requests

---

## 0. How to read this document

Every claim below carries a status from exactly four values, and nothing is
promoted between them:

| status | meaning |
| --- | --- |
| **VERIFIED** | the behaviour was executed and its output observed — locally, in CI, or read-only against production, as stated |
| **PARTIALLY VERIFIED** | some evidence exists, and the uncovered part is named |
| **NOT VERIFIED** | no evidence; the reason is stated |
| **BLOCKED** | verification was attempted and something outside this work prevented it |

The distinctions that were enforced throughout:

> Code exists ≠ feature works · Route exists ≠ feature works · UI exists ≠
> authorization exists · Audit table exists ≠ audit trail correct · Telemetry
> function exists ≠ observability works · Dashboard renders ≠ analytics correct ·
> HTTP 200 ≠ system healthy · Implemented ≠ tested · Tested locally ≠ verified
> in production

---

## A. What was found

Seventeen gaps. Each was established by reading the implementation or by
running it — never from a filename, a route declaration, or a component's
existence.

| # | gap | how established |
| --- | --- | --- |
| G-01 | Admin analytics fabricated `top_aesthetics` / `trending_colors` on an empty database | code read + reproduction test |
| G-02 | `sample_size = max(len(outfits), total_users)` made the k-anonymity floor unbreakable | code read |
| G-03 | `region` accepted as a filter and applied to nothing; `period` hardcoded | code read |
| G-04 | Two divergent heatmap implementations, one contract the frontend could not render | code read |
| G-05 | Audit endpoint discarded half the audit row | code read |
| G-06 | Redaction existed as a docstring contract with no enforcement | code read |
| G-07 | `/admin/audit` rendered the analytics dashboard — no audit UI, no nav entry | code read |
| G-08 | Public `/health` published provider inventory, storage config, engine licence, schema findings | **verified against production** |
| G-09 | `storage.production_grade=false` + `writable=false` reported as `status: healthy` | **verified against production** |
| G-10 | 51 admin routes across 3 prefixes; RBAC tests covered a handful | **verified** by enumerating the route registry |
| G-11 | `require_admin_recent` bypassed `_extract_token` | code read, then reproduced |
| G-12 | No sanctioned way to create a production admin | **verified** — `seed_data.py` refuses in production and nothing replaced it |
| G-13 | GMV and the attribution ledger filtered different order populations | code read, then reproduced |
| G-14 | Brand table issued 5 queries per brand; ranking 1 per row | code read, then measured |
| G-15 | No time dimension anywhere in admin analytics | code read |
| G-16 | Tests that cannot fail (`assert … or True`, `inspect.getsource()` checks, `for … : pass`) | code read |
| **G-17** | `/health` asserted `"ai_stylist_engine": "operational"` and `"bnpl_gateway": "operational"` with no probe behind either | **new — found while closing G-08/G-09; verified against production** |

Two findings arrived *during* the work rather than from the original register:

- **G-17** — two health fields were string literals. `bnpl_gateway` reported
  `operational` on a deployment with no PSP key while the platform's own
  `/catalog/capabilities` correctly reported `bnpl_live: false`. One process,
  two stories about itself, and the one an operator reads during an incident
  was the false one.
- **Return-rate survivorship bias** (folded into G-13) — three return-rate
  denominators excluded `refunded` orders. A completed return ends in
  `refunded`, so it left the denominator at the moment it succeeded: **the
  return rate fell every time a return worked.**

---

## B. Root causes

Not seventeen independent mistakes. Four patterns produced all of them:

**1. No single owner for a definition.** "Which orders count as revenue" was
answered by nine hand-written literals in three shapes. "Can this deployment do
X" was answered twice — once honestly in `/capabilities`, once by a string
literal in `/health`. Wherever a definition has no owner, each call site invents
its own and they drift.

**2. Assertions substituted for measurements.** `"operational"` with no probe.
`sample_size` inflated by `max(...)`. A `status` field that meant "the database
answered" while readers understood "the platform works". A number that is
asserted rather than computed is indistinguishable from a lie, and is usually
believed longer.

**3. One field asked to answer two questions.** `/health` was simultaneously a
public liveness signal and an internal diagnostic dump. It could not be minimal
and complete at once, so it was neither — leaking internals *and* hiding the one
blocker that mattered.

**4. Tests that verified code existed, not that it behaved.** `inspect.getsource()`
assertions pass on a reverted implementation. A hardcoded path list rots
silently. `assert x or True` cannot fail. These are the reason several gaps
survived previous passes.

---

## C. What changed

Five pull requests, each independently reviewable, merged in order.

### #135 — the audit trail becomes real *(G-05, G-06, G-07, G-16)*

`GET /admin/audit` returns the full row — `before`, `after`, `changed_fields`,
`request_id`, actor identity and role — in a paginated envelope with facets and
integrity reporting. Redaction moved from a docstring into
`core/audit_redaction.py`, enforced on the **single write path** every caller
funnels through, so the contract no longer depends on 30 call sites remembering
a comment. `/admin/audit` renders a real view. Source-inspection tests were
replaced with behavioural ones.

### #143 — the heatmap stops inventing data *(G-01…G-04)*

The fabricated block was deleted, not relabelled. One builder
(`get_style_heatmap`), one cell contract `{name, raw_name, share, count}` across
all three endpoints, a k-anonymity floor of 5 with `suppressed_cells` reported,
and an honest empty state (`data_available: false` + reason) instead of padding.
`region` is accepted, applied to nothing, and echoed as
`region_filter_applied: false` with a limitation entry — matching the convention
#132 had already set on the partner endpoint rather than inventing a second one.

### #148 — one revenue vocabulary, flat query cost, a real time window *(G-13, G-14, G-15)*

`core/revenue_policy.py` owns a **closed partition** of all 22
`ORDER_TRANSITIONS` states. `classify_order_status()` raises on an unknown state
rather than defaulting to revenue, and `unclassified_states()` makes a test fail
the moment the state machine grows a state nobody classified. `revenue_eligible()`
filters every revenue figure; `return_denominator_eligible()` filters return-rate
denominators and deliberately keeps refunded orders.

Measured query cost per dashboard load: **19 statements at 4, 14 and 34 brands**
(flat), where the previous shape cost ~31, ~82 and ~182 and grew without bound.

`days` / `date_from` / `date_to` are resolved by `core/timeutils.TimeRange` and
pushed into the SQL predicate of every aggregate. Bounds are inclusive on both
ends to match the contract `/admin/audit` already publishes.

### #152 — liveness separated from readiness *(G-08, G-09, G-17)*

`core/readiness.py` defines the contract: `status` is liveness scope, `ready` is
capability scope, and a blocked **core** capability sets `ready: false` and is
named. `capability_service` is the single source of truth for what a deployment
can do; `/catalog/capabilities` now delegates to it. Public `/health` is minimal;
`GET /health/ready` (admin-only) carries the diagnostics. The uptime monitor runs
liveness and readiness as separate jobs.

### #154 — every alias tested, one token extractor, a safe bootstrap *(G-10, G-11, G-12)*

`test_admin_route_governance.py` names no path: it reads the app's OpenAPI
registry and parametrizes over all 51 admin routes across all three prefixes.
`require_admin_recent` now uses `_extract_token`. `bootstrap_admin.py` promotes
an existing verified account, requires a strong token plus `--confirm`, is
idempotent, refuses to orphan the platform, and audits every change.

---

## D. Files changed

59 file-changes across the five merges; ~6,574 insertions, ~481 deletions.

**New — the abstractions that removed the duplication**

| file | why |
| --- | --- |
| `backend/app/core/revenue_policy.py` | one closed partition of order states; the single answer to "is this revenue?" |
| `backend/app/core/readiness.py` | the liveness/readiness contract; pure, no I/O, unit-testable |
| `backend/app/services/capability_service.py` | one source of truth for deployment capabilities, shared by `/capabilities` and both health surfaces |
| `backend/app/core/audit_redaction.py` | redaction enforced on the single audit write path |
| `backend/app/core/request_context.py` | request id + client IP from server-side context, never from a client payload |
| `backend/app/core/timeutils.py` | aware/naive UTC normalisation and the `TimeRange` value object |
| `backend/app/schemas/audit.py`, `repositories/audit_repository.py`, `services/audit_service.py` | the audit query/read layer |
| `backend/scripts/bootstrap_admin.py` | the sanctioned admin bootstrap |
| `frontend/src/views/b2b/AdminAuditView.tsx` | the audit UI that did not exist |

**Modified — where the bugs lived**

`brand_repository.py` (fabricated heatmap deleted; revenue predicates unified;
N+1 removed; time window threaded), `admin_controller.py` (audit endpoints, time
window), `telemetry_controller.py` (health split), `catalog_controller.py`
(delegates to the capability service), `dependencies.py` (unified token
extraction), `auth_controller.py`, `user_repository.py`, `schemas/brand.py`,
`BrandNavbar.tsx`, `AppRoutes.tsx`, `apiServices.ts`, `models/index.ts`,
`i18n/{en,ar}.json`, `uptime-monitor.yml`, `run_mutation_gates.py`.

**Tests added:** `test_admin_audit_trail.py`, `test_admin_style_heatmap_honesty.py`,
`test_revenue_policy.py`, `test_admin_analytics_efficiency.py`,
`test_admin_analytics_time_range.py`, `test_health_readiness_contract.py`,
`test_admin_route_governance.py`, `test_admin_stepup_token_extraction.py`,
`test_bootstrap_admin.py`, `AdminAnalyticsView.heatmapHonesty.test.tsx`.

---

## E. Database changes

**No migration. No new Alembic revision. No index, constraint or column added.**

This was a deliberate constraint, not an omission. `check_release_schema_parity.py`
compares the commit's expected head against the revision production reports; a
new revision without deploying it first is precisely the 2026-09-20 incident the
gate exists to prevent. Every fix here is expressible in application code.

One real interaction was handled rather than ignored: `main` advanced to
`0018_outfit_share_lifecycle` (PR #137) mid-work while this branch sat at `0017`.
`main` was merged so the gate compares like for like — **RELEASE GATE: PASS, head
`0018` == production `0018`**, re-confirmed on the final merged state.

---

## F. Security changes

| change | evidence |
| --- | --- |
| Every admin route tested on every alias, data-driven | 158 cases over 51 routes; a new route is covered on registration |
| Public health no longer discloses provider inventory, storage config, engine licence or schema findings | production `/health` now returns none of them — read back live |
| Diagnostics moved behind admin auth | production `/api/v1/health/ready` → **401** |
| Step-up re-auth accepts exactly the tokens ordinary auth accepts | regression test on a cookie-free client |
| Audit redaction enforced on the write path, not by convention | a known secret written in a test does not survive to the row |
| Audit identity comes from the authenticated principal, never a client payload | `request_context` supplies actor and IP server-side |
| Admin bootstrap cannot invent credentials, orphan the platform, or leak its token | 14 tests + CLI end-to-end |
| 404 treated as a failure in RBAC tests | a missing guard cannot hide behind routing |

**Production authorization, read-only, verified after deploy** — all twelve real
API admin paths return **401** to an unauthenticated caller:

```
/api/v1/admin/analytics                   401     /api/v1/admin/analytics/most-styled   401
/api/v1/admin/overview                    401     /api/v1/admin/analytics/returns       401
/api/v1/admin/analytics/overview          401     /api/v1/admin/analytics/heatmaps      401
/api/v1/admin/analytics/features          401     /api/v1/admin/audit                   401
/api/v1/admin/analytics/attribution       401     /api/v1/admin/audit/stats             401
/api/v1/admin/analytics/brands            401     /api/v1/admin/analytics/brand-performance 401
```

**A finding worth stating precisely, because it could be misread as a hole.**
`/v1/admin/analytics` and `/admin/overview` return **200** in production. They are
**not** serving admin data: the response is `text/html`, 1617 bytes, and
**byte-identical to the response for `/this-route-does-not-exist-xyz`** — the SPA
catch-all serving `index.html`. At the Vercel edge only `/api/v1/*` reaches the
backend. The three-prefix aliases are therefore an *in-process* concern, covered
by the 158 governance tests, not a production exposure.

---

## G. Tests added, and what each set proves

| suite | tests | what fails if the bug returns |
| --- | --- | --- |
| `test_admin_route_governance.py` | 158 | any admin route losing its guard, on any alias |
| `test_health_readiness_contract.py` | 27 | a core blocker hiding behind `status`, or internals leaking back into public health |
| `test_revenue_policy.py` | 10 | a status counted as revenue that should not be; refunded orders leaving a return denominator |
| `test_admin_analytics_time_range.py` | 19 | the window being accepted and ignored; a boundary contract drifting from `/admin/audit` |
| `test_admin_analytics_efficiency.py` | 6 | any N+1 returning to the dashboard |
| `test_admin_stepup_token_extraction.py` | 5 | step-up diverging from the shared extractor again |
| `test_bootstrap_admin.py` | 14 | the bootstrap creating identities, orphaning the platform, or leaking its token |
| `test_admin_style_heatmap_honesty.py` | 15 | fabricated rows or a dishonest empty state returning |
| `test_admin_audit_trail.py` | 36 | the audit row losing fields, or redaction being bypassed |
| `AdminAnalyticsView.heatmapHonesty.test.tsx` | 3 | the UI implying completeness it does not have |

**Every new defect was confirmed caught by reintroducing it.** This is the step
that distinguishes a test from a tautology:

| reintroduced defect | tests that fail |
| --- | --- |
| `'failed'` counted as revenue (original G-13) | 4 |
| refunded orders leave the return denominator | 3 |
| analytics silently ignores the caller's window (G-15) | 7 |
| per-brand query loop restored (G-14) | 3 |
| `ready` forced always-`true` (G-09) | 4 |
| provider inventory leaked back into public health (G-08) | 1 |
| step-up token extraction reverted (G-11) | 2 |

Two of these were caught **by the mutation check rather than by the first run** —
the step-up test initially passed against broken code because a shared
`TestClient` cookie jar was doing the authenticating. It was rewritten to run
cookie-free. A test that passes for the wrong reason is worse than no test.

`run_mutation_gates.py`: **16 killed, 0 survived, 0 not applicable** (M7
retargeted at the policy module; M15 and M16 added).

---

## H. Verification

### Final state, on the merged `main` (`2ceb279`)

| check | command | result |
| --- | --- | --- |
| Backend suite | `pytest backend/tests -q` | **1686 passed, 5 skipped** |
| Mutation gates | `python backend/scripts/run_mutation_gates.py` | **16 killed, 0 survived** |
| Import closure (both manifests) | `python backend/scripts/check_runtime_imports.py` | OK — vercel + docker |
| Release schema parity | `python backend/scripts/check_release_schema_parity.py` | **PASS** — head `0018` == production `0018` |
| Secret scan (full history) | `gitleaks detect` | no leaks |
| Frontend suite | `npm test` | **247 passed / 30 files** |
| Type check | `npx tsc --noEmit` | clean |
| Production build | `npm run build` | clean |
| i18n gate | `node scripts/check_i18n.mjs` | passed |
| CI on every PR head | GitHub Actions | `backend`, `frontend`, `release gate`, `postgres migration chain`, `production parity`, `gitleaks` — all **success** on all five |

### Production, read-only, observed after deploy

| requirement | status | evidence |
| --- | --- | --- |
| Public health no longer discloses internals | **VERIFIED** | live `/api/v1/health` contains no `ai_providers`, no `storage`, no `vton_engine`, no schema findings |
| Readiness reports the blocker honestly | **VERIFIED** | live payload: `status: healthy`, `ready: false`, `blocking_capabilities: ["virtual_try_on"]` |
| The contract travels with the payload | **VERIFIED** | live payload carries `contract` defining `status`, `ready`, all four states and both criticalities |
| Admin surface denies unauthenticated callers | **VERIFIED** | all 12 `/api/v1/admin/*` paths → **401** |
| Diagnostics are admin-only | **VERIFIED** | `/api/v1/health/ready` → **401** |
| Schema parity | **VERIFIED** | production reports `0018_outfit_share_lifecycle`, identical to head |
| Database reachable | **VERIFIED** | `checks.database: healthy` |

### Per-gap matrix

| Gap | Environment | Status | Evidence |
| --- | --- | --- | --- |
| G-01 fabricated analytics | local + CI | **VERIFIED** | fabricated block absent from `main`; honesty tests fail if it returns |
| G-02 inflated sample size | local + CI | **VERIFIED** | `test_admin_style_heatmap_honesty.py` |
| G-03 filter that does not filter | local + CI | **VERIFIED** | `region_filter_applied: false` + limitation entry asserted |
| G-04 two heatmap implementations | local + CI | **VERIFIED** | one builder; identical cell shape on all three endpoints |
| G-05 audit row discarded | local + CI | **VERIFIED** | `test_admin_audit_trail.py`; endpoint returns before/after/changed_fields |
| G-06 redaction unenforced | local + CI | **VERIFIED** | a known secret written in a test does not reach the row |
| G-07 no audit UI | local + CI | **VERIFIED** | route renders `AdminAuditView`; navbar link restored |
| G-08 public health leaks internals | **production read-only** | **VERIFIED** | live payload contains none of the five disclosed groups |
| G-09 blocker hidden behind healthy | **production read-only** | **VERIFIED** | live payload: `ready: false`, blocker named |
| G-10 alias coverage | local + CI + **production read-only** | **VERIFIED** | 158 cases over 51 routes; 12 production paths → 401 |
| G-11 divergent token extraction | local + CI | **VERIFIED** | mutation confirmed caught on a cookie-free client |
| G-12 no admin bootstrap | local + CI | **VERIFIED locally / NOT VERIFIED in production** | 14 tests + CLI end-to-end against the test database; **not run against production** |
| G-13 two revenue definitions | local + CI | **VERIFIED** | mutation confirmed caught; `revenue_excludes_statuses` published |
| G-14 N+1 query storm | local + CI | **VERIFIED** | measured 19 statements at 4/14/34 brands |
| G-15 no time dimension | local + CI | **VERIFIED** | window changes the numbers; empty window returns zeros |
| G-16 tests that cannot fail | local + CI | **VERIFIED** | replaced with behavioural tests; each mutation caught |
| G-17 asserted health verdicts | local + CI + **production read-only** | **VERIFIED** | both literals deleted; live payload carries no unmeasured verdict |

---

## I. Not verified / blocked

Stated plainly, with the reason.

| item | status | why |
| --- | --- | --- |
| **Admin functionality in production** | **NOT VERIFIED** | There is still no production admin account. `bootstrap_admin.py` was **not** run against production: promoting a real account is a deliberate operational act that needs `ADMIN_BOOTSTRAP_TOKEN` provisioned by someone with deploy access. Until then, admin dashboards, audit rows and transitions are **local + CI verified only**. |
| **Production database row-level inspection** | **BLOCKED** | Direct connection to Neon as `neondb_owner` returns `28P01 password authentication failed` on both the pooler and the direct host. No row-level production evidence is claimed anywhere in this report. |
| **`/health/ready` contents in production** | **NOT VERIFIED** | It requires admin authentication, which does not exist yet. Its 401 for anonymous callers *is* verified. |
| **Audit trail populated by real production activity** | **NOT VERIFIED** | Depends on the item above. |
| **Object-storage readiness in production** | **PARTIALLY VERIFIED** | `file_uploads` no longer appears in the live `blocking_capabilities`, which implies storage is now production grade. The per-capability detail that would confirm it lives on `/health/ready`, which needs admin auth. |
| **`Workers Builds: confit-a`** | **NOT APPLICABLE** | Fails on every PR branch head including branches this work never touched, passes only on `main`, and is not one of the three required checks. Pre-existing; Cloudflare dashboard-only logs. |

---

## J. Remaining risks

1. **No production admin.** The single largest residual risk, and it is
   procedural rather than technical. Every admin path is verified to *deny*;
   none is verified to *work* under real data.
2. **Try-on is blocked in production.** Live readiness reports
   `blocking_capabilities: ["virtual_try_on"]`. This is #142's finding — the GPU
   workspace exceeded its spend limit — surfaced honestly rather than hidden.
   It needs an infrastructure decision, not a code change.
3. **The readiness monitor will fail until that is resolved.** By design. A
   warning that never fails is a warning nobody reads; but a red monitor that
   stays red for weeks trains people to ignore it, so this should not be left
   unattended.
4. **The heatmap reads JSON string columns.** `style_tags` and `color_palette`
   are parsed in Python per row. Correct today, and bounded by a sample limit,
   but a normalised table or JSONB column is the right next step.
5. **Revenue basis is accrual, and stated as such.** `payment_pending` orders
   count as revenue. That is a defensible accounting choice published in the
   payload as `revenue_basis`, but a finance stakeholder may want cash basis —
   which is a new bucket in `revenue_policy.py`, not a new literal at a call site.
6. **Return rates are now higher than before.** Refunded orders stay in the
   denominator. This is the corrected number; anyone comparing to historical
   dashboards will see a step change and should be told why.

---

## K. Deployment notes

No migration to run. No configuration change is required for the code to work.

**To close the last gap — create the first production admin:**

```bash
export ADMIN_BOOTSTRAP_TOKEN="$(openssl rand -hex 32)"
python -m backend.scripts.bootstrap_admin --email <an existing, verified account> --dry-run
python -m backend.scripts.bootstrap_admin --email <an existing, verified account> --confirm
unset ADMIN_BOOTSTRAP_TOKEN        # single-use by procedure
```

The account must already exist, be verified and be active — the script refuses
otherwise and never creates an identity. Re-running is a no-op that writes no
second audit row. `--revoke` demotes, and refuses to remove the last active admin.

**To clear the readiness alert:** configure object storage
(`STORAGE_PROVIDER=s3|r2` + bucket + credentials) if uploads are still blocked,
and restore VTON worker spend. Confirm with `GET /api/v1/health/ready` as an admin.

**Two behaviour changes consumers may notice:**

- Public `/health` no longer carries `ai_providers`, `checks.storage`,
  `checks.vton_engine`, `checks.vton_pipeline` or the schema's
  `missing_*`/`findings`/`expected_head`. It gains `ready`,
  `blocking_capabilities`, `degraded_capabilities` and `contract`. It keeps
  `status`, `checks.database` and `checks.schema.database_revision`, so the
  uptime monitor's grep and the release gate both still work — and both are
  pinned by tests.
- Return rates are slightly higher, for the reason in J.6.

---

## L. A note on what this report is for

This document is a teaching artefact, not a scorecard.

Nothing in it is written to assign blame. Every gap above was produced by
patterns that are easy to fall into and hard to see from inside: a definition
nobody owned, a value asserted because measuring it was more work, one field
asked to answer two questions, and tests written to confirm that code exists.
Those are ordinary engineering conditions, not carelessness — and the fixes are
structural precisely so that the next person cannot repeat them by accident.

Where something could not be verified, this report says **Not Verified** or
**Blocked** and explains why, rather than rounding it up to "done". That is the
part worth keeping: a gap register that only ever reports success stops being
evidence and becomes decoration.

---

*Prepared 2026-09-21. All commands reproducible from the repository at
`2ceb279`. Production observations were read-only; no state-changing request was
sent to `https://confit-a.vercel.app/` at any point.*
