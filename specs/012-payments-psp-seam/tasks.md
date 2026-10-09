---
description: "Task list for Payments — Honest Demo Mode & PSP Seam"
---

# Tasks: Payments — Honest Demo Mode & Real-PSP Seam

**Input**: `specs/012-payments-psp-seam/{spec.md, plan.md}`
**Tests**: REQUIRED (honesty, fail-closed, idempotency).

## Phase 1: Setup
- [ ] T001 [FOUND] Link CUS-04/06/07/08 + CUS-16; confirm demo banner at `CheckoutView.tsx:217-226` and the fail-closed orchestrator + webhook verifier.

## Phase 2: Foundational
- [ ] T002 [FOUND] Define config/server-driven payment mode (demo|live) exposed to the client honestly (no secrets). Linked: FR-001.

## Phase 3: US1 — Honest demo banner (P2) 🎯
### Tests first
- [ ] T003 [P] [US1] `backend/tests/test_payment_mode_gating.py` + frontend test: banner shown iff demo active. Linked: FR-001, SC-001. Acceptance: fails now (always shown).
### Implementation
- [ ] T004 [US1] Gate the demo banner on real demo-mode state in `CheckoutView.tsx`. Linked: FR-001.

## Phase 4: US2 — Honest demo cards (P2)
### Tests first
- [ ] T005 [P] [US2] `backend/tests/test_demo_cards_honest.py`: no real token/PAN persisted in demo; saved cards labeled demo. Linked: FR-002, SC-002. Acceptance: fails/surfaces now.
### Implementation
- [ ] T006 [US2] Honest demo labeling for saved cards + card entry; ensure no real card data stored. Linked: FR-002.

## Phase 5: US3 — PSP seam (P2)
### Tests first
- [ ] T007 [P] [US3] `backend/tests/test_psp_seam_failclosed.py`: unconfigured live provider fails closed (CUS-06); amount charged == `price_quote()` total. Linked: FR-003/004/006, SC-003/005. Acceptance: covers new seam.
- [ ] T008 [P] [US3] `backend/tests/test_webhook_idempotency.py`: signature mismatch rejected; duplicate webhook idempotent (CUS-16). Linked: FR-005, SC-004.
### Implementation
- [ ] T009 [US3] Define PSP adapter interface (tokenize/authorize/capture/refund/webhook/idempotency/reconciliation) decoupled from commerce core. Linked: FR-003.
- [ ] T010 [US3] Preserve fail-closed live + webhook verification; reconcile payment records; charge only the server total. Linked: FR-004/005/006.

## Phase N: Polish
- [ ] T011 [POLISH] Secret scan: 0 PSP secret values in code/logs/responses (SC-006). Record final commit + env; `/speckit.analyze`.

## Dependencies
- Charge amount sourced from workstream 001 `price_quote()`. Reconciliation may share the ledger pattern with workstream 007.
