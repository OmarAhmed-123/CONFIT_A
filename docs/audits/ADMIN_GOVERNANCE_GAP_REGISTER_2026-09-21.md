# Admin Governance / Audit / Telemetry — Gap Register

**Feature scope:** platform analytics, brand comparison, attribution, returns, heatmaps,
audit trail, admin order transitions, health / observability.
**Repo:** `OmarAhmed-123/CONFIT_A` · **Baseline commit inspected:** `cd17a220677efe0f39b60157e7acfd888f4df351` (tree at `037d01e`)
**Date:** 2026-09-21
**Branch:** `fix/admin-governance-audit-telemetry`

> Every row below cites the file + line that proves the gap. Rows marked
> **VERIFIED** were reproduced by running code; rows marked **CODE-READ** were
> established by reading the implementation. Nothing here is inferred from the
> UI alone.

---

## Status summary (updated as PRs merge)

| Gaps | Status | PR |
|---|---|---|
| G-05, G-06, G-07, G-16 — audit trail truth, redaction, UI, honest tests | ✅ shipped | #135 |
| G-01, G-02, G-03, G-04 — style heatmap honesty and one contract | ✅ shipped | #143 |
| G-08, G-09, G-17 — public health is minimal, readiness cannot lie | ✅ shipped | #152 |
| G-10, G-11, G-12 — every alias tested, one token extractor, a safe bootstrap | ✅ shipped | #154 |
| G-13, G-14, G-15 — one revenue vocabulary, flat query cost, real time window | ✅ shipped | #148 |

This register is a teaching artefact, not a scorecard: every row exists so the
next person can see *why* the fix looks the way it does.

---

## G-01 — Admin analytics ships hardcoded fake data on an empty database  *(VERIFIED — code read + reproduction test)*

**Status:** ✅ **FIXED** — PR #143. The fabricated block is deleted; the endpoint returns `data_available: false` and empty lists instead.

`backend/app/repositories/brand_repository.py:674-684`

```python
# Fallback if no data
if not top_aesthetics:
    top_aesthetics = [
        {"name": "Quiet Luxury / Old Money", "share": 38},
        {"name": "Modern Minimalist", "share": 29},
        ...
    ]
if not trending_colors:
    trending_colors = ["#1B1F3B (Navy)", "#C5A059 (Gold/Beige)", ...]
```

`/api/v1/admin/analytics` returns these four fabricated percentages and four
fabricated colour chips whenever the real aggregation is empty. The view that
renders them is titled *"Platform Administration & Revenue Attribution - Real
Data"* and states *"No fake numbers"* (`AdminAnalyticsView.tsx:26-31`).

Present since the first commit (`1e82eb9`). No test caught it: the only
assertion touching this block is `test_group6_production_hardening.py:388`,
`assert "top_aesthetics" in data or "top_colors" in data` — satisfied by the
fake rows, so it can never fail.

**Fix:** delete the fabricated fallbacks; return an explicit
`data_available: false` + empty lists; add a regression test that fails if any
hardcoded aesthetic/colour ever reappears.

---

## G-02 — Privacy (k-anonymity) threshold is bypassable and the sample size is inflated  *(CODE-READ)*

**Status:** ✅ **FIXED** — PR #143. `sample_size` is the analysed sample, cells below `k_anonymity_floor: 5` are suppressed and counted in `suppressed_cells`.

`brand_repository.py:659-672`

```python
sample_size = len(outfits) if len(outfits) >= 10 else max(len(outfits), total_users)
...
if count >= 3 or sample_size >= 50:      # "Privacy threshold"
```

Two defects:

1. When fewer than 10 outfits exist, `sample_size` is reported as
   `total_users` — the platform's *registered user count*, not the number of
   records actually aggregated. The published "privacy threshold: sample size N"
   statement is therefore false.
2. `or sample_size >= 50` lets a **single** occurrence be published once the
   sample is large — the k-anonymity floor is switched off exactly when the
   dataset is biggest. `top_occasions` applies no threshold at all.

**Fix:** one honest `sample_size` = records actually aggregated; hard k-floor
with suppression below it; threshold applied uniformly to aesthetics, colours
and occasions; `data_available`/`suppressed` flags so the UI can say "insufficient
sample" instead of guessing.

---

## G-03 — `region` is a filter that does not filter, and `period` is a constant  *(CODE-READ)*

**Status:** ✅ **FIXED** — PR #143. `region` is accepted and echoed as `requested_region` with `region_filter_applied: false` plus a `limitations` entry, matching the convention #132 set on the partner endpoint. `period` is a real `{from,to}` or `null`.

`brand_repository.py:926` (`get_user_preference_heatmaps(region=...)`) never
uses `region`; it returns `"region": region` alongside platform-wide numbers.
`get_platform_admin_analytics` hardcodes `"region": "MENA & GCC"`
(`brand_repository.py:704`) regardless of any input. `period: "monthly"`
(`:994`) is a constant — no date predicate exists anywhere in the aggregation.

`GET /admin/analytics/heatmaps?region=EU` therefore returns MENA-wide data
labelled `EU`. That is a mislabelled metric, not a filter.

**Fix:** either apply a real region predicate or publish
`region_scope: "platform_wide"` and reject the unsupported parameter; same for
`period`.

---

## G-04 — Two divergent heatmap implementations, one contract the frontend cannot render  *(VERIFIED)*

**Status:** ✅ **FIXED** — PR #143. One builder (`get_style_heatmap`), one cell contract (`{name, raw_name, share, count}`) on all three endpoints.

| | `get_platform_admin_analytics` (`:616-672`) | `get_user_preference_heatmaps` (`:926-1000`) |
|---|---|---|
| source | ~60 lines inline | separate method |
| outfit scan | `limit(1000)` | `limit(2000)` |
| product fallback trigger | `len(style_counter) < 3` | `len(outfits) < min_sample_size` |
| threshold | `>=3 or sample>=50` | `>=3 if sample>=50 else >=5` |
| aesthetics shape | `{name, share}` | `{name, weight, count}` |
| colours shape | `trending_colors: string[]` | `top_colors: {color,weight,count}[]` |

The frontend model (`frontend/src/models/index.ts:693-699`) and
`AdminAnalyticsView.tsx:115-134` read `share` and `trending_colors`. So
`/admin/analytics/heatmaps` returns a payload that renders `undefined%` bars and
then throws on `trending_colors.map` — the endpoint is contract-broken for the
only consumer that exists. ~60 duplicated lines is also a direct DRY violation.

**Fix:** one `StyleHeatmap` builder (single source of truth) used by both
endpoints, one wire contract, one frontend type.

---

## G-05 — Audit trail endpoint discards half the audit row  *(CODE-READ)*

**Status:** ✅ **FIXED** — PR #135. The endpoint returns the full row incl. `before`/`after`/`changed_fields`/`request_id`, paginated.

`admin_controller.py:178-197` returns only `id/action/actor/entity/details/timestamp`.
The model (`models/user.py:103-119`) also stores `before_json`, `after_json`,
`request_id`, `ip_address` — the exact columns migration
`0017_audit_before_after_request_id` added. Consequences:

- an auditor cannot see what changed (before/after) from the trail,
- an audit row cannot be correlated back to its HTTP request from the trail,
- `actor` is the string `"User #7"` — no identity, so the trail cannot answer
  *who* did it,
- `db.query(AuditLog)...limit(100)` — hardcoded, no pagination, no `total`, no
  filters (action / resource / actor / date range), no ordering control,
- reading the audit trail is itself a privileged act and is **not audited**,
- no client IP is ever recorded by `_audit_admin` (`admin_controller.py:21-35`
  never passes `ip_address`), so the column is NULL for every admin action.

**Fix:** repository + service + schema layer; paginated, filterable, enriched
trail; the read itself audited; client IP captured for every admin action.

---

## G-06 — Audit write path has a documented redaction contract and no enforcement  *(CODE-READ)*

**Status:** ✅ **FIXED** — PR #135. `core/audit_redaction.py` enforces the contract on write; regression test fails if a secret survives.

`repositories/user_repository.py:56-88` — the docstring says *"Callers must never
pass sensitive values in details/before/after"*. Nothing enforces it. There are
**30 `log_audit(` call sites** across 6 modules; the contract rests entirely on
every future author remembering a comment.

The test that supposedly guards this (`test_audit_logging.py:67-77`) inspects the
*docstring* for the word "sensitive". It cannot fail if a token is written.

**Fix:** central scrubber applied inside `log_audit` (so all 30 call sites are
covered by construction), plus a behavioural test that writes a token and
asserts it never lands in the row.

---

## G-07 — `/admin/audit` has no UI; the route renders the analytics dashboard  *(CODE-READ)*

**Status:** ✅ **FIXED** — PR #135. `/admin/audit` renders `AdminAuditView`; navbar link added in PR #136 (it was lost resolving a merge conflict).

`frontend/src/router/AppRoutes.tsx:211` → `<Route path="audit" element={<AdminAnalyticsView />} />`.
`adminService.getAuditLogs()` (`services/apiServices.ts:936`) has no caller
anywhere in `frontend/src`. The audit trail is unreachable from the product.

**Fix:** a real `AdminAuditView` (filters, pagination, before/after diff,
request-id correlation) wired to the route.

---

## G-08 — Public `/health` publishes internal configuration  *(VERIFIED against production)*

**Status:** ✅ **FIXED** — PR #152. `/health` is now a minimal public surface: liveness status, readiness verdict, the names of blocked/degraded capabilities, the database verdict and `checks.schema.database_revision` (retained because the release gate certifies deploys from it), and the contract that defines each field. The provider inventory, storage provider and its environment-variable names, the VTON engine's licence and fork provenance, and the schema's missing tables/columns/findings moved to **`GET /health/ready`**, which is admin-only. Verified live against production before the change: the public endpoint was publishing all five.

`curl https://confit-a.vercel.app/api/v1/health` → 200, body includes:

- `ai_providers.{openai,groq,gemini,nvidia,unorouter}.configured: true` — an
  unauthenticated enumeration of which AI vendors the platform is paying for,
- `checks.storage.{provider,production_grade,writable,detail}` — the storage
  posture and its remediation instructions,
- `checks.vton_engine.license` / `source` — the full engine provenance and
  licence text,
- `checks.schema.{expected_head,database_revision,missing_tables,missing_columns}`
  — the internal migration state.

None of it is needed by an uptime monitor, which only greps `"status":"healthy"`.

**Fix:** split liveness from readiness. Public `/health` = liveness + version +
an explicit non-empty `degraded` list (never empty-and-lying). New ops-gated
`/health/ready` carries the internals and returns 503 when not ready.

---

## G-09 — `storage.production_grade=false` hides behind `status: healthy`  *(VERIFIED against production)*

**Status:** ✅ **FIXED** — PR #152. `status` and `ready` are now separate fields with separate, testable meanings. `status` is liveness scope (database reachable + schema present); `ready` is capability scope and goes false when any **core** capability is blocked, naming it in `blocking_capabilities`. Production's broken upload path (`storage.production_grade=false`, `writable=false`) can no longer read as healthy: it surfaces as `ready: false, blocking_capabilities: ["file_uploads"]`. `core/readiness.py` owns the vocabulary — `ready` / `degraded` / `blocked` / `not_probed` × `core` / `supporting` — and the uptime monitor now runs liveness and readiness as separate jobs, with readiness allowed to fail.

`telemetry_controller.py:198`:

```python
overall = "healthy" if (db_status == "healthy" and schema.get("acceptable") is True) else "degraded"
```

Storage is not an input. Production currently reports `status: healthy` while
`storage.production_grade=false, writable=false`, i.e. every upload feature is
dead (`require_production_storage` → 501). A green health endpoint next to a
dead feature is the exact failure mode the schema gate was written to stop
(`schema_gate.py:1-30`) — applied to the wrong subsystem.

**Fix:** readiness computes per-feature verdicts; a non-production storage
backend in production is a **blocker** that forces `ready=false` and is listed
by name in the public liveness payload.

---

## G-10 — No test proves a consumer cannot reach an admin alias  *(VERIFIED)*

**Status:** ✅ **FIXED** — PR #154. `backend/tests/test_admin_route_governance.py` enumerates the application's own OpenAPI registry and parametrizes over every path whose segments include `admin` — **51 routes across all three prefixes** (`/admin`, `/api/v1/admin`, `/v1/admin`). Guest, consumer and malformed-token requests must each get 401/403, and a 404 is treated as a failure rather than a pass so a missing guard cannot hide behind routing. An endpoint added next week is covered the moment it is registered. Three meta-tests stop the suite passing vacuously: the enumeration must find ≥20 routes, all three prefixes must be present, and every route must exist under every alias.

Admin endpoints are registered with **five aliases**:
`/admin/analytics`, `/admin/overview`, `/admin/analytics/overview`,
`/admin/analytics/features`, `/admin/analytics/attribution`
(`admin_controller.py:82-84, 129-130`). The whole suite asserts denial on
**two** paths only (`test_auth_rbac_and_gating.py:114`, `test_register_role_escalation.py:155`).
An alias added tomorrow is unguarded by tests.

**Fix:** a data-driven test that enumerates every route under `/api/v1/admin`
straight off `app.routes` and asserts guest→401 / consumer→403 / brand→403. New
aliases are covered automatically.

---

## G-11 — `require_admin_recent` does not use the platform's token extractor  *(CODE-READ)*

**Status:** ✅ **FIXED** — PR #154. `require_admin_recent` now calls `_extract_token`. It previously read `credentials.credentials` or the cookie directly, skipping the bare `Authorization` header and the Vercel `***` redaction marker that the shared extractor handles — so the same token authenticated for `require_role` but failed step-up, leaving an admin who could read the dashboard and not act on it. The regression test runs on a **cookie-free** client on purpose: `TestClient` keeps a jar per instance and the httpOnly cookie fallback was masking the bug, which is why the first version of the test passed against the broken code.

`core/dependencies.py:120-138` reads the token as
`credentials.credentials if credentials else request.cookies.get("confit_token")`,
while every other endpoint goes through `_extract_token` (`:37-52`), which
exists specifically to recover the Vercel `Authorization: ***<jwt>` redaction
documented at `:18-35`. An API-only admin client on Vercel (no cookie) gets
`ADMIN_REAUTH_REQUIRED` / "invalid token" on the step-up endpoints while the
rest of the API works.

**Fix:** reuse `_extract_token` — one extractor, one behaviour (DRY).

---

## G-12 — No production admin account and no sanctioned way to create one  *(VERIFIED)*

**Status:** ✅ **FIXED** — PR #154. `backend/scripts/bootstrap_admin.py` promotes an **existing, verified, active** account; it never creates a user and never sets a password. Requires `ADMIN_BOOTSTRAP_TOKEN` (≥32 chars) from the environment plus `--confirm`; the token is never printed, logged or audited. Idempotent — a retry writes no second escalation row. `--revoke` refuses to remove the last active admin. Every change is audited through the same `log_audit` path as the API, so G-06's redaction applies. Verified end to end through the CLI: promote → idempotent retry → revoke, with the rows read back from the database.

`seed_data.py:68-78` creates `admin@confit.io / Password123!` and refuses to run
when `ENVIRONMENT=production` (`:23-31`). That refusal is correct — but it leaves
production with **no** admin bootstrap path at all, which is why the audit found
all five accounts answering `403` with role `consumer`. The entire admin surface
is therefore unexercisable and unverifiable in production.

**Fix:** `backend/scripts/bootstrap_admin.py` — promotes an *existing, already
verified* account, requires a one-time `ADMIN_BOOTSTRAP_TOKEN` in production,
never creates an account with a known password, never prints a secret, and
writes an audit row. Plus an opt-in anonymised staging dataset so the dashboards
can be exercised end to end.

---

## G-13 — GMV is computed two different ways in the same dashboard  *(CODE-READ)*

**Status:** ✅ **FIXED** — PR #148. `core/revenue_policy.py` owns one classification of all 22 `ORDER_TRANSITIONS` states. GMV, the attribution ledger and every revenue aggregate now filter through `revenue_eligible()`; return-rate denominators use `return_denominator_eligible()`, which deliberately keeps refunded orders. An unclassified status raises instead of defaulting to revenue, and a test fails if the state machine grows a state nobody classified. Bonus finding: three return-rate denominators excluded refunded orders, so the return rate *fell* every time a return succeeded — fixed by the same split.

`brand_repository.py:503` uses `notin_(["cancelled", "refunded"])`;
`get_revenue_attribution` (`:893`) uses `self.INELIGIBLE_ORDER_STATUSES`, which
also excludes `failed` / `rejected`. `total_gmv` and
`attribution_base_item_subtotal` therefore rest on different order populations
and cannot be reconciled by an analyst reading the same screen.

**Fix:** one `ELIGIBLE_ORDER_STATUSES` constant, used everywhere, surfaced in
the payload's methodology text.

---

## G-14 — N+1 query storm on the admin analytics endpoint  *(CODE-READ)*

**Status:** ✅ **FIXED** — PR #148. The brand table and the most-styled ranking are now grouped aggregates. Measured: **19 statements** for one dashboard load at 4, 14 and 34 brands (flat); the previous shape cost ~31 / ~82 / ~182 and grew without bound.

`brand_repository.py:578-611` — per brand, five separate queries
(orders, products, views, try-ons, returns) inside a Python loop over
`db.query(BrandProfile).all()`, plus `most_styled_items` issuing one
`SELECT ... WHERE id = ?` per product (`:562-573`). With 50 brands this is
~260 round trips for one dashboard render — on a serverless function billed per
millisecond against a pooled cross-region Postgres.

**Fix:** set-based `GROUP BY` aggregation — one query per metric, then an
in-memory join.

---

## G-15 — No time-range dimension anywhere in admin analytics  *(CODE-READ)*

**Status:** ✅ **FIXED** — PR #148. `days` / `date_from` / `date_to` on `/admin/analytics` (and its two aliases), resolved by `core/timeutils.TimeRange` and pushed into the SQL predicate of every aggregate. Bounds are inclusive on both ends to match the contract `/admin/audit` already publishes; the resolved window and its boundary semantics are echoed in the payload. Invalid, inverted or conflicting windows are rejected with 422.

Every admin analytics query is lifetime-only. An admin cannot answer "GMV in the
last 30 days", so the dashboard cannot support the one question a dashboard
exists for.

**Fix:** `date_from` / `date_to` (or `days`) accepted and pushed into the SQL
predicates of every aggregate.

---

## G-16 — Tests that cannot fail  *(CODE-READ)*

**Status:** ✅ **FIXED** — PR #135. The source-inspection assertions were replaced with behavioural ones that fail on a reverted implementation.

- `test_audit_logging.py:77` — `assert ... or True`.
- `test_audit_logging.py:67-77` — asserts a docstring contains a word.
- `test_audit_logging.py:127-146` — asserts `inspect.getsource()` mentions `AuditLog`.
- `test_group6_production_hardening.py:388` — satisfied by the G-01 fake rows.
- `test_group6_production_hardening.py:509-518` — builds an admin, calls
  `/admin/audit`, then `for item in data[:3]: ... pass`.

Source-inspection tests pass on a reverted implementation. They are replaced
with behavioural tests in this branch.

## G-17 — The health endpoint asserted two verdicts it never measured  *(VERIFIED against production)*

**Status:** ✅ **FIXED** — PR #152. Both strings were deleted; the states are now
probed by `capability_service.capability_probes()`.

Found while closing G-08/G-09, not in the original report.

`backend/app/controllers/telemetry_controller.py:209-210`

```python
"ai_stylist_engine": "operational",
"bnpl_gateway": "operational"
```

These are string literals. No probe stands behind either one. `bnpl_gateway`
reported `operational` on a deployment with no PSP key configured — where the
platform's own `/catalog/capabilities` endpoint correctly reports
`bnpl_live: false`. The same file was therefore telling two different stories
about the same deployment, and the one an operator reads during an incident was
the false one.

This is the failure mode the whole register exists to catch: a field whose
value is asserted rather than measured. `capability_service` is now the single
source of truth for what a deployment can do; `/capabilities` and both health
surfaces read from it, so they cannot disagree. Where a designed fallback
exists (the deterministic grounded stylist answers without a provider key) the
state is `degraded`, not `blocked` and not `operational`.

---

## Verified evidence log

| Check | Command | Result |
|---|---|---|
| Suite baseline for this feature | `pytest backend/tests/test_admin01_governance.py test_audit_logging.py test_b2b_audit_call_sites.py -q` | **17 passed** |
| Production liveness | `curl https://confit-a.vercel.app/api/v1/health` | 200, `status: healthy`, `storage.production_grade: false`, 5 providers `configured: true` |
| Production admin RBAC (guest) | 12 admin aliases probed | all **401** |
| Production DB direct inspection | `pg8000` → Neon pooler + direct host | **`28P01 password authentication failed`** — the Neon password supplied in chat is rejected by both hosts, so no production DB row-level evidence is claimed anywhere in this document |
