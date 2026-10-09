---
description: "Task list for Brand Account Provisioning & Team RBAC"
---

# Tasks: Brand Account Provisioning & Team RBAC

**Input**: `specs/005-brand-provisioning-rbac/{spec.md, plan.md}`
**Tests**: REQUIRED (RBAC, tenant isolation, migration).

## Phase 1: Setup
- [ ] T001 [FOUND] Link BRD-01/02; confirm current head + existing isolation code (`brand_service.py:203-221`) and IDOR suite.

## Phase 2: Foundational
- [ ] T002 [FOUND] Author (test DB only) migration `00NN_brand_memberships` + backfill from 1:1 profiles; `down_revision` = head (reconcile via 011). Linked: FR-002/005.
- [ ] T003 [FOUND] BrandMembership model + BrandProfile 1:many; membership-aware auth helper preserving isolation. Linked: FR-002/003.

## Phase 3: US1 — Provisioning (P1) 🎯
### Tests first
- [ ] T004 [P] [US1] `backend/tests/test_brand_provisioning.py`: approved lead → owner can log in → sees only own brand; self-register cannot get brand role. Linked: FR-001/004, SC-001. Acceptance: fails now.
### Implementation
- [ ] T005 [US1] Provisioning service/endpoint: lead→BrandProfile+owner(BRAND_OWNER), idempotent. Linked: FR-001.
- [ ] T006 [US1] Post-provision login→dashboard scoped to brand. Linked: FR-001/003.

## Phase 4: US2 — Team RBAC (P1)
### Tests first
- [ ] T007 [P] [US2] `backend/tests/test_brand_role_matrix.py`: (role × action) matrix enforced server-side. Linked: FR-003, SC-002. Acceptance: fails now.
- [ ] T008 [P] [US2] Extend `test_brand_tenant_isolation.py`: cross-tenant denied with memberships. Linked: FR-003, SC-003.
- [ ] T009 [P] [US2] `backend/tests/test_brand_membership_migration.py`: backfill preserves all brands/owners. Linked: FR-005, SC-004.
### Implementation
- [ ] T010 [US2] Team CRUD (invite/assign/remove) with role checks; prevent last-owner removal. Linked: FR-002/003/004.
- [ ] T011 [US2] Team management UI. Linked: FR-002.

## Phase N: Polish
- [ ] T012 [POLISH] Confirm BRD-09/10 positives remain green; record final commit + env; `/speckit.analyze`.

## Dependencies
- T002/T003 block stories. Lead approval ties to workstream 004 governance. Migration prod-apply gated by workstream 011.
