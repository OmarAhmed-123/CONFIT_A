---
description: "Task list for Brand Catalog Management"
---

# Tasks: Brand Catalog Management

**Input**: `specs/006-brand-catalog-management/{spec.md, plan.md}`
**Tests**: REQUIRED (RBAC/tenant, import isolation, storage honesty).

## Phase 1: Setup
- [ ] T001 [FOUND] Link BRD-03/04/11/18; confirm `ProductCreateInput` shape and current import path; agree async-job abstraction with workstream 008.

## Phase 2: Foundational
- [ ] T002 [FOUND] Author (test DB) migration `00NN_product_lifecycle_and_import_jobs` (lifecycle state + import_jobs + media URL fields); reconcile via 011. Linked: FR-001/002/003.
- [ ] T003 [FOUND] Storage adapter interface with honest-unavailable behavior when no provider. Linked: FR-004.

## Phase 3: US1 — Product lifecycle (P1) 🎯
### Tests first
- [ ] T004 [P] [US1] `backend/tests/test_brand_product_lifecycle.py`: manager create→publish→archive scoped to brand; staff blocked; cross-tenant denied. Linked: FR-001/006, SC-001. Acceptance: fails now.
### Implementation
- [ ] T005 [US1] Wire `ProductCreateInput` into create/edit/publish/archive endpoints with role+tenant checks. Linked: FR-001.
- [ ] T006 [US1] Product editor UI. Linked: FR-001.

## Phase 4: US2 — Async import + report (P2)
### Tests first
- [ ] T007 [P] [US2] `backend/tests/test_catalog_import_async.py`: large import processed out-of-request (no timeout); mixed rows → valid imported, invalid reported with reasons, row isolation. Linked: FR-002/003, SC-002/003. Acceptance: fails now (synchronous).
### Implementation
- [ ] T008 [US2] Move import to async job (shared mechanism w/ 008); row-isolated processing; status + per-row report. Linked: FR-002/003.
- [ ] T009 [US2] Import uploader + partial-failure report UI. Linked: FR-003.

## Phase 5: US3 — Durable media (P2)
### Tests first
- [ ] T010 [P] [US3] `backend/tests/test_product_media_storage.py`: provider configured → media survives simulated redeploy; no provider → honest 503, no fake success; format/size validation. Linked: FR-004/005, SC-004. Acceptance: fails now.
### Implementation
- [ ] T011 [US3] Media pipeline to object storage (URLs in DB, not bytes); validation. Linked: FR-004/005.
- [ ] T012 [US3] Media manager UI. Linked: FR-004.

## Phase N: Polish
- [ ] T013 [POLISH] Confirm honest imagery (no placeholder masquerade); record final commit + env; `/speckit.analyze`.

## Dependencies
- Role/tenant checks depend on workstream 005 memberships. Async mechanism shared with 008. Migration prod-apply gated by 011.
