---
description: "Task list for Advertising Delivery Loop, Ledger Billing & Analytics"
---

# Tasks: Advertising Delivery Loop, Ledger Billing & Analytics

**Input**: `specs/007-advertising-loop/{spec.md, plan.md}`
**Tests**: REQUIRED (consumer tracking, ledger reconciliation, pacing, statements).

## Phase 1: Setup
- [ ] T001 [FOUND] Link BRD-05/06/07/08/13/14/16 + ADM-14; map existing campaign/tracking models and the brand-auth tracking defect.

## Phase 2: Foundational
- [ ] T002 [FOUND] Author (test DB) migration `00NN_ad_ledger_and_pacing` (append-only ledger, pacing fields, impression/click); reconcile via 011. Linked: FR-003/004.

## Phase 3: US1 — Consumer serving + tracking (P1) 🎯
### Tests first
- [ ] T003 [P] [US1] `backend/tests/test_ad_consumer_tracking.py`: impression+click recorded from consumer context (no brand auth), attributed correctly; anti-fraud dedupe/rate works. Linked: FR-001/002, SC-001. Acceptance: fails now (no serving path; brand-auth tracking).
### Implementation
- [ ] T004 [US1] Consumer ad-serving selection endpoint (eligible, funded placements). Linked: FR-001.
- [ ] T005 [US1] Public impression/click tracking (no brand auth) + anti-fraud/rate safeguards. Linked: FR-002.
- [ ] T006 [US1] Storefront ad placement rendering. Linked: FR-001.

## Phase 4: US2 — Ledger billing + pacing (P2)
### Tests first
- [ ] T007 [P] [US2] `backend/tests/test_ad_ledger_reconcile.py`: spend == ledger sum (0 drift); admin KPIs reconcile. Linked: FR-003, SC-002.
- [ ] T008 [P] [US2] `backend/tests/test_ad_budget_pacing.py`: at cap, serving/billing stops; balance never negative. Linked: FR-004, SC-003.
### Implementation
- [ ] T009 [US2] Ledger-backed spend computation; dashboard + admin KPIs read from ledger (ADM-14). Linked: FR-003.
- [ ] T010 [US2] Budget pacing/cap enforcement in serving + billing. Linked: FR-004.

## Phase 5: US3 — Statements + analytics (P2)
### Tests first
- [ ] T011 [P] [US3] `backend/tests/test_ad_statement_totals.py`: statement total == ledger total; attribution not double-counted (regression). Linked: FR-005/006, SC-004/005.
### Implementation
- [ ] T012 [US3] Billing statement/PDF view + download. Linked: FR-005.
- [ ] T013 [US3] Funnel, attribution, and brand order/returns visibility views. Linked: FR-006.

## Phase N: Polish
- [ ] T014 [POLISH] Record final commit + env; `/speckit.analyze`; confirm ADM-14 consumes this ledger.

## Dependencies
- Brand views depend on workstream 005 memberships. Admin KPI panel (workstream 004) consumes this ledger. Migration prod-apply gated by 011.
