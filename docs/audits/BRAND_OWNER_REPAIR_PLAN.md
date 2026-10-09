# BRAND_OWNER_REPAIR_PLAN.md — CONFIT_A Brand Owner Role: Forensic Audit & Repair Plan

> **Document type:** Role-based repair plan (PLANNING / AUDIT ONLY — no application code changed).
> **Target repo:** `OmarAhmed-123/CONFIT_A` · **Branch:** `main` @ `a44f1fb` (clean).
> **Audit date:** 2026-10-09.
> **Siblings:** `ADMIN_REPAIR_PLAN.md`, `CUSTOMER_REPAIR_PLAN.md`, `VIRTUAL_TRY_ON_REPAIR_PLAN.md`, `STYLELIST_AI_REPAIR_PLAN.md`.

---

## 1. Title & Scope

The **Brand Owner / brand partner** role: onboarding & account provisioning, team/RBAC, product catalog management (create/publish/archive), catalog import, advertising (campaign setup → delivery → tracking → billing), brand analytics/funnels, and billing statements. Covers backend brand services and the B2B brand UI under `frontend/src/views/b2b/`.

**Out of scope:** admin-side brand governance/verification/suspension (owned by `ADMIN_REPAIR_PLAN.md`), customer commerce (`CUSTOMER_REPAIR_PLAN.md`), try-on (`VIRTUAL_TRY_ON_REPAIR_PLAN.md`), stylist (`STYLELIST_AI_REPAIR_PLAN.md`).

---

## 2. Status & Severity Legend

**Status:** `VERIFIED` · `IMPLEMENTED` · `TESTED-PASS` · `TESTED-FAIL` · `GAP` · `BUG-VERIFIED` · `LIKELY` · `UNVERIFIED` · `BLOCKED` · `NO-GO` · `NOT FOUND IN SEARCHED SCOPE`.
**Severity:** P0 (blocking/security) · P1 (major) · P2 (defect w/ workaround) · P3 (polish). Evidence cites `path:line` where inspected.

---

## 3. Executive Summary

The brand role has **excellent isolation security** (tenant fail-closed, `_assert_brand_ownership`, IDOR regression tests) but is **functionally a shell**: a prospective partner can submit a lead, but there is **no path to an actual working brand account that can list products and run ads**. The advertising loop is also broken end-to-end (no consumer-facing ad serving; tracking is brand-authenticated rather than impression-driven).

- **P1 (capability gaps):** onboarding is lead-capture only, no provisioning (**BRD-01**); no multi-user team/RBAC — `BrandProfile.user_id` is 1:1 (**BRD-02**); no product create/publish/archive for partners (`ProductCreateInput` unused) (**BRD-03**); ad delivery loop broken (**BRD-05**).
- **P2:** catalog import runs synchronously (Vercel timeout risk) (**BRD-04**); dashboard ad spend from counters not a ledger (**BRD-06**); billing statement/PDF backend-only (**BRD-07**); funnel computed but not displayed (**BRD-08**).
- **Verified-positive (preserve):** tenant isolation fail-closed, `_assert_brand_ownership` at `backend/app/services/brand_service.py:203–221`, IDOR regression coverage.

**Baseline tests (this audit):** backend 3732 passed / 4 env-only failed / 21 skipped; frontend build PASS.

---

## 4. Baseline & Environment Evidence

| Item | Evidence | Status |
|---|---|---|
| Brand ownership guard | `backend/app/services/brand_service.py:203–221` (`_assert_brand_ownership`) | VERIFIED (positive) |
| 1:1 brand↔user | `BrandProfile.user_id` single-owner | VERIFIED (limitation) |
| Product create schema unused | `ProductCreateInput` present but not wired to a partner endpoint | BUG-VERIFIED |
| Brand controller | `backend/app/controllers/brand_controller.py` | VERIFIED |
| Lead capture | `frontend/src/views/b2b/LeadForm` + `PartnerGatewayView` | VERIFIED |
| Backend suite | 3732 passed / 4 env-only failed / 21 skipped | TESTED-PASS |
| Frontend build | tsc + vite build | TESTED-PASS |
| Spec Kit | absent → documentation-based process | VERIFIED (absent) |

---

## 5. Current-State Inventory (Brand Owner)

**Frontend:** `frontend/src/views/b2b/` — `PartnerGatewayView`, `LeadForm`, `Brand*` dashboards.
**Backend:** `brand_controller.py`, `brand_service.py`, `brand_analytics` model, `catalog_import` model/service, ad-billing service.

| Capability | Backend | UI | Status |
|---|---|---|---|
| Lead capture | yes | LeadForm | VERIFIED |
| Account provisioning after lead | **NOT FOUND** | none | GAP (BRD-01) |
| Team members / RBAC | 1:1 only | none | GAP (BRD-02) |
| Product create/publish/archive | schema exists, unused | none | GAP (BRD-03) |
| Catalog import | synchronous | partial | PARTIAL (BRD-04) |
| Ad campaign setup | partial | partial | PARTIAL |
| Ad serving to consumers | **NOT FOUND** | none | GAP (BRD-05) |
| Ad tracking | brand-authenticated | n/a | BUG (BRD-05) |
| Ad billing ledger | counters | dashboard | PARTIAL (BRD-06) |
| Billing statement/PDF | backend-only | none | GAP (BRD-07) |
| Funnel analytics | computed | not shown | GAP (BRD-08) |
| Tenant isolation | fail-closed | n/a | VERIFIED (positive) |

---

## 6. Findings Register (Brand Owner)

| ID | Title | Sev | Status | Evidence |
|---|---|---|---|---|
| BRD-01 | Onboarding is lead-capture only; no account provisioning | P1 | GAP | LeadForm → no brand account created |
| BRD-02 | No multi-user team/RBAC; `BrandProfile.user_id` 1:1 | P1 | GAP | single-owner model |
| BRD-03 | No product create/publish/archive for partners | P1 | GAP | `ProductCreateInput` unused |
| BRD-04 | Catalog import synchronous (Vercel timeout risk) | P2 | BUG-VERIFIED | import runs in-request |
| BRD-05 | Ad delivery loop broken (no consumer serving; brand-auth tracking) | P1 | BUG-VERIFIED | no impression serving path |
| BRD-06 | Dashboard ad spend uses counters, not ledger | P2 | BUG-VERIFIED | counter drift risk |
| BRD-07 | Billing statement/PDF backend-only | P2 | GAP | no UI/download |
| BRD-08 | Funnel analytics computed but not displayed | P2 | GAP | data exists, no view |
| BRD-09 | Tenant isolation fail-closed | — | VERIFIED (positive) | `brand_service.py:203–221` |
| BRD-10 | IDOR regression tests present | — | VERIFIED (positive) | test suite |
| BRD-11 | No product media manager / image pipeline for partners | P2 | LIKELY | depends STORAGE_PROVIDER |
| BRD-12 | Brand dashboard not dynamic/live (static KPIs) | P2 | LIKELY | UX |
| BRD-13 | No campaign budget pacing / cap enforcement | P2 | LIKELY | ties BRD-06 |
| BRD-14 | No brand-side order/returns visibility for own products | P2 | LIKELY | fulfillment insight |
| BRD-15 | Brand i18n/RTL + a11y gaps on B2B views | P2 | LIKELY | §15 |
| BRD-16 | No revenue attribution shown to brand (double-count fixed server-side) | P2 | LIKELY | attribution tests exist |
| BRD-17 | No self-serve API keys/webhooks for brand integrations | P3 | GAP | enhancement |
| BRD-18 | Catalog import lacks partial-failure report in UI | P2 | LIKELY | import isolation exists in tests |

---

## 7. Root-Cause Analysis

1. **Marketing funnel built before the product.** The partner gateway collects leads but there is no provisioning workflow that turns an approved lead into a usable brand account (BRD-01). Everything downstream (products, ads, billing) is therefore unreachable by a real partner.
2. **Single-owner data model.** `BrandProfile.user_id` is 1:1, so teams/RBAC are impossible without a join table (BRD-02).
3. **Unwired write path.** `ProductCreateInput` exists but no partner endpoint/UI uses it (BRD-03) — classic backend-ahead-of-frontend.
4. **Ads modeled as analytics, not delivery.** There is tracking/billing scaffolding but no consumer-facing ad serving, and tracking is tied to brand auth instead of real impressions (BRD-05), so spend counters cannot reflect reality (BRD-06).
5. **Serverless-unaware import.** Synchronous import risks the Vercel `maxDuration` ceiling (BRD-04).

---

## 8. Target Architecture / Desired State

- **Provisioning workflow:** approved lead → brand account + initial owner user (admin-governed; ties to `ADMIN_REPAIR_PLAN.md` T-ADM-06).
- **Team model:** `brand_members(brand_id, user_id, role)` join table with roles (owner/manager/staff — enum already has `BRAND_OWNER/BRAND_MANAGER/BRAND_STAFF`), all tenant-scoped via the existing fail-closed guard.
- **Catalog management:** partner product CRUD using `ProductCreateInput`, with publish/archive lifecycle and a media manager.
- **Async import:** move catalog import to a background worker / chunked job to respect serverless limits.
- **Real ad loop:** consumer-facing ad serving → impression/click tracking → ledger-based spend → billing statements/PDF, with budget pacing.
- **Analytics surfacing:** render the already-computed funnels + attribution.

---

## 9. Specification (Specify)

**Spec A — Brand provisioning (BRD-01).** An admin can convert an approved lead into a brand account with one owner user; the owner can log in and reach the brand dashboard. Acceptance: lead→account→login→dashboard works; audited; tenant-scoped.

**Spec B — Team & RBAC (BRD-02).** A brand owner can invite members with roles; permissions enforced server-side and tenant-isolated. Acceptance: owner/manager/staff capabilities differ; no cross-brand access (IDOR tests stay green).

**Spec C — Catalog management (BRD-03/BRD-11/BRD-18).** A partner can create, publish, archive products with media; bulk import is async with a partial-failure report. Acceptance: `ProductCreateInput` wired; published product appears in discovery; archived hidden; import does not time out; failures reported per row.

**Spec D — Advertising loop (BRD-05/BRD-06/BRD-07/BRD-13).** Campaigns serve to consumers; impressions/clicks tracked from real events; spend is ledger-based and paced to budget; billing statements downloadable. Acceptance: ad serves in discovery; tracked spend matches ledger; budget cap stops delivery; statement/PDF downloads.

**Spec E — Analytics surfacing (BRD-08/BRD-16).** Funnel + attribution rendered to the brand without double counting. Acceptance: funnel view matches computed data; attribution sum ≤ total (matches server-side tests).

---

## 10. Plan (Plan)

1. Provisioning (admin-driven) → owner account (Spec A). 2. `brand_members` join + RBAC middleware (Spec B). 3. Partner catalog CRUD + media + async import (Spec C). 4. Ad serving + event tracking + ledger + billing (Spec D). 5. Analytics views (Spec E). 6. UX/a11y dynamism + animation pass. 7. Converge; keep isolation tests green.

---

## 11. Tasks (Tasks)

**T-BRD-01 · Brand provisioning workflow**
- **Sev:** P1 · **Linked:** BRD-01
- **Preconditions:** admin brand governance (ADMIN T-ADM-06).
- **Steps:** approved lead → create `BrandProfile` + owner user (invite/first-login set password) → audited. No auto-provisioning without admin approval.
- **Files:** `brand_service.py`, `admin_controller.py`, brand onboarding UI.
- **Acceptance:** Spec A; audited; tenant-scoped.
- **Tests:** provisioning happy path; unauthorized provisioning refused; audit emitted.
- **Rollback:** behind flag. · **Risk:** medium. · **Status:** GAP → planned.

**T-BRD-02 · Team membership + RBAC**
- **Sev:** P1 · **Linked:** BRD-02
- **Steps:** add `brand_members(brand_id, user_id, role)`; migrate existing 1:1 owners into it; enforce role capabilities server-side; invitations.
- **Files:** Alembic migration (forward from head; mind prod `0035`, §19), `brand_service.py`, dependencies, brand team UI.
- **Acceptance:** Spec B; existing owners preserved; IDOR tests green.
- **Tests:** role-capability matrix; cross-brand denial; migration back-fill test.
- **Rollback:** keep owner fallback. · **Risk:** high (authz + migration). · **Status:** GAP → planned.

**T-BRD-03 · Partner product CRUD + lifecycle**
- **Sev:** P1 · **Linked:** BRD-03
- **Steps:** wire `ProductCreateInput` to `POST /brand/products`; add publish/archive transitions; tenant-scoped; published → discovery, archived → hidden.
- **Files:** `brand_controller.py`, catalog service, brand catalog UI.
- **Acceptance:** Spec C (CRUD + lifecycle).
- **Tests:** create/publish/archive; discovery visibility; tenant scope.
- **Rollback:** disable routes. · **Risk:** medium. · **Status:** GAP → planned.

**T-BRD-04 · Product media manager + storage**
- **Sev:** P2 · **Linked:** BRD-11
- **Preconditions:** `STORAGE_PROVIDER` set to a durable provider in prod (local storage breaks on Vercel's ephemeral FS — cross-ref VTON plan storage note).
- **Steps:** upload UI (launch animation), object-storage persistence, `HonestProductImage` rendering, remove-on-delete.
- **Files:** storage provider, brand media UI.
- **Acceptance:** images persist across deploys; consistent presentation.
- **Tests:** upload→persist→render; delete removes object.
- **Rollback:** disable uploads. · **Risk:** medium. · **Status:** planned.

**T-BRD-05 · Async catalog import + partial-failure report**
- **Sev:** P2 · **Linked:** BRD-04, BRD-18
- **Steps:** move import off the request path (background job / chunked); per-row validation; UI report of succeeded/failed rows (import isolation already proven in tests).
- **Files:** `catalog_import` service, worker/job, import UI.
- **Acceptance:** large import does not hit serverless `maxDuration`; per-row report.
- **Tests:** large-file import; partial-failure isolation (extend existing).
- **Rollback:** keep sync path behind flag for small files. · **Risk:** medium. · **Status:** BUG-VERIFIED → planned.

**T-BRD-06 · Real ad serving + event tracking**
- **Sev:** P1 · **Linked:** BRD-05
- **Steps:** serve sponsored placements in consumer discovery; record impressions/clicks from real consumer events (not brand-auth); dedupe/fraud guards.
- **Files:** ad service, discovery query, consumer UI, tracking endpoints.
- **Acceptance:** Spec D (serving + tracking); tracking driven by consumer events.
- **Tests:** impression recorded on serve; click recorded; no brand-auth leakage into tracking.
- **Rollback:** disable serving. · **Risk:** high. · **Status:** BUG-VERIFIED → planned.

**T-BRD-07 · Ledger-based spend + budget pacing + billing statements**
- **Sev:** P2 · **Linked:** BRD-06, BRD-07, BRD-13
- **Preconditions:** T-BRD-06.
- **Steps:** derive spend from an append-only ad ledger (idempotent — ad-ledger idempotency already VERIFIED, DB-21); enforce budget cap stops delivery; generate downloadable statements/PDF.
- **Files:** ad billing service, ledger, billing UI.
- **Acceptance:** dashboard spend == ledger; cap halts delivery; statement/PDF downloads.
- **Tests:** spend==ledger; cap-stop; statement generation.
- **Rollback:** fall back to counters display (read-only). · **Risk:** medium. · **Status:** planned.

**T-BRD-08 · Brand analytics surfacing (funnel + attribution)**
- **Sev:** P2 · **Linked:** BRD-08, BRD-16, BRD-14
- **Steps:** render computed funnel + attribution; show brand's own orders/returns; attribution sum ≤ total (server tests already enforce no double count).
- **Files:** brand analytics UI, read endpoints.
- **Acceptance:** Spec E.
- **Tests:** funnel matches computed; attribution invariants.
- **Rollback:** hide views. · **Risk:** low. · **Status:** planned.

**T-BRD-09 · Brand UX dynamism + a11y + animation**
- **Sev:** P2 · **Linked:** BRD-12, BRD-15, §14/§15
- **Steps:** dynamic dashboards (live KPIs, skeletons), shared tokens, `<LaunchButton>` on create/publish/upload, RTL/i18n, axe pass.
- **Files:** `frontend/src/views/b2b/*`.
- **Acceptance:** §14/§15.
- **Tests:** axe, RTL, reduced-motion.
- **Rollback:** revert styles. · **Risk:** low. · **Status:** planned.

---

## 12. Data Model / Migration Considerations

- **`brand_members` join table** (BRD-02): `(brand_id, user_id, role)` with a uniqueness constraint; back-fill existing 1:1 owners; keep the fail-closed ownership guard semantics. Forward Alembic revision (mind prod `0035`, §19).
- **Ad ledger** (BRD-06/07): append-only, idempotent (DB-21 already proven) as the single source of truth for spend; counters become a cache/derived read.
- **Impression/click events** (BRD-05): event tables keyed to real consumer sessions; attribution joins must avoid the double-count the existing tests guard against.
- **Product lifecycle** (BRD-03): status column (draft/published/archived) if not present; discovery query filters on it.
- **No migration authored in this document.** Money stays `Numeric(12,2)`.

---

## 13. API Contract Changes (proposed)

| Endpoint | Method | Guard | Note |
|---|---|---|---|
| `/brand/products` | POST/PATCH | brand member (manager+) | wire `ProductCreateInput` (BRD-03) |
| `/brand/products/{id}/publish|archive` | POST | brand member | lifecycle |
| `/brand/import` | POST | brand member | async job (BRD-04) |
| `/brand/team` | CRUD | owner | RBAC (BRD-02) |
| `/brand/ads/*` | — | brand member | serving/tracking/ledger (BRD-05/06/07) |
| `/brand/analytics/funnel` | GET | brand member | surface (BRD-08) |
| `/brand/billing/statement` | GET | owner | PDF (BRD-07) |

Explicit Pydantic schemas; tenant-scoped; `await` all async; never trust client-supplied brand_id (resolve from membership).

---

## 14. UI/UX Plan (colors · animation · dynamism)

- Canonical gold token; consistent focus rings.
- **Dynamic dashboards:** live KPI tiles, animated charts, skeleton loaders, explicit empty/error states.
- **Launch animation:** `<LaunchButton>` on "Create product", "Publish", "Upload", "Launch campaign" — rising rocket (bottom→top) + success color shift → check; reduced-motion fallback.
- **Professional media:** product media manager with `HonestProductImage`, drag-reorder, aspect-ratio-consistent thumbnails.
- Full RTL/i18n across B2B views.

---

## 15. Accessibility Plan (WCAG 2.2 AA)

- Accessible names on all controls (incl. media remove/close buttons — class of A11Y-04).
- Modal focus trap (A11Y-03) for invite/confirm dialogs.
- Visible consistent focus ring; `aria-live` on async actions (don't drop focus when a pending button disables — MOT-02).
- Charts have text/table equivalents.
- RTL parity; reduced-motion respected.

---

## 16. Security & Privacy

- Preserve tenant isolation fail-closed + `_assert_brand_ownership` (`brand_service.py:203–221`) and IDOR regression coverage (BRD-09/10).
- Resolve `brand_id` from membership, never from the request body.
- RBAC enforced server-side (not just UI hiding).
- Ad tracking must not expose brand auth to consumers; dedupe to resist click fraud.
- Provisioning is admin-gated + audited.

---

## 17. Testing & Verification Plan

- RBAC capability matrix + cross-brand denial; migration back-fill.
- Catalog CRUD/lifecycle + discovery visibility; async import partial-failure isolation.
- Ad serving/tracking correctness; spend==ledger; budget cap stops delivery; ledger idempotency (preserve DB-21).
- Attribution no-double-count (preserve existing green tests).
- Frontend axe/RTL/reduced-motion; dashboard e2e.
- **Baseline to preserve:** 3732 passed / 21 skipped; frontend build PASS. No new TESTED-FAIL; isolation tests stay green.

---

## 18. Rollout / Deployment / Flags

- Provisioning, RBAC, ad serving behind flags for staged rollout.
- Async import requires a worker/queue compatible with the deployment (Vercel serverless: use a background/queued job, not an in-request loop).
- Ensure `STORAGE_PROVIDER` is a durable provider in prod before enabling media uploads (ephemeral FS warning).

---

## 19. Risks, Assumptions, Open Questions

- **R1 (migration drift):** prod `0035_product_images` ahead of `main` `0034` — chain `brand_members`/ad-ledger/product-status migrations after `0035`. **UNVERIFIED in `main`.** Note `0035_product_images` likely relates to product images (BRD-11 media) — confirm before adding overlapping columns.
- **R2:** ad serving is a substantial new subsystem; phase it (serve → track → bill).
- **A1:** roles map to existing `BRAND_OWNER/BRAND_MANAGER/BRAND_STAFF` enum values.
- **Q1:** are leads approved manually by admins only, or is there a self-serve tier? (Assumed admin-approved.)

---

## 20. Acceptance Criteria / DoD + Traceability

**Role is "done" when:** an approved lead becomes a working brand account with a team (RBAC), partners can create/publish/archive products with persistent media and non-timing-out imports, ads actually serve to consumers with real tracking and ledger-based paced billing + downloadable statements, and analytics/funnels are visible — all tenant-isolated (IDOR tests green), dynamic, animated, image-polished, RTL, WCAG 2.2 AA.

| Finding | Task | DoD signal |
|---|---|---|
| BRD-01 | T-BRD-01 | Lead→account→login→dashboard. |
| BRD-02 | T-BRD-02 | Team RBAC; IDOR green. |
| BRD-03 | T-BRD-03 | Product CRUD/lifecycle live. |
| BRD-11 | T-BRD-04 | Persistent media. |
| BRD-04/18 | T-BRD-05 | Async import + report. |
| BRD-05 | T-BRD-06 | Real ad serving/tracking. |
| BRD-06/07/13 | T-BRD-07 | Ledger spend, pacing, statements. |
| BRD-08/16/14 | T-BRD-08 | Analytics surfaced. |
| BRD-12/15 | T-BRD-09 | UX/a11y/animation. |

**Preserve:** BRD-09, BRD-10, DB-21 idempotency, attribution no-double-count.
