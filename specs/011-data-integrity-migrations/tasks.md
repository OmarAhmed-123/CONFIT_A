---
description: "Task list for Data Integrity & Migration Reconciliation"
---

# Tasks: Data Integrity & Migration Reconciliation

**Input**: `specs/011-data-integrity-migrations/{spec.md, plan.md}`
**Tests**: REQUIRED (single-head, round-trip, dedup).

## Phase 1: Setup
- [ ] T001 [FOUND] Record current repo head `0034_mfa_email_codes`; record prod-reported `0035_product_images` as UNVERIFIED-pending-authorized-check (§21). Completion: documented in `docs/roadmap/DEPENDENCY_AND_RELEASE_GATES.md`.

## Phase 2: Foundational — reconciliation gate (P1) 🎯
- [ ] T002 [FOUND] Define the authorized, READ-ONLY production-head check procedure (NOT executed during planning); make it a hard gate blocking any migration wave until the real prod head is confirmed. Linked: FR-001, SC-001.
- [ ] T003 [FOUND] Reconcile the chain: import or explicitly supersede the prod `0035_product_images` so repo+prod share one linear history; assign a collision-free numbering plan for 002/005/006/007/008/011 migrations. Linked: FR-002/003.

## Phase 3: US2 — Single linear chain (P1)
### Tests first
- [ ] T004 [P] [US2] `backend/tests/test_migration_single_head.py` + `test_migration_roundtrip.py`: exactly one `alembic heads`; `upgrade head`/`downgrade base` succeed on test DB; no shared `down_revision`. Linked: FR-003/004, SC-002/003. Acceptance: fails if collisions introduced.
### Implementation
- [ ] T005 [US2] Apply the numbering plan to each workstream migration at the time it is authored during execution (coordination task; no migration file is created during planning). Linked: FR-003.

## Phase 4: US3 — Recently-viewed dedup (P2)
### Tests first
- [ ] T006 [P] [US3] `backend/tests/test_recently_viewed_dedup.py`: one row per (user,product), most-recent timestamp. Linked: FR-005, SC-004. Acceptance: fails now (DB-01).
### Implementation
- [ ] T007 [US3] Migration `00NN_recently_viewed_unique` + model unique `(user_id, product_id)` + upsert. Linked: FR-005.

## Phase N: Polish
- [ ] T008 [POLISH] Money-column grep gate: 0 conversions away from `Numeric(12,2)` (SC-005, DB-19). Confirm no prod migration executed. `/speckit.analyze`.

## Dependencies
- This workstream GATES execution of migrations in 002/005/006/007/008. The authorized prod-head check (T002) is a prerequisite for ANY migration deploy wave.
