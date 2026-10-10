---
description: "Task list for StyleList AI Mode A / grounding / failover"
---

# Tasks: StyleList AI — Mode A, Wardrobe Grounding & Failover

**Input**: `specs/009-stylelist-ai-modes/{spec.md, plan.md}`
**Tests**: REQUIRED (AI honesty, grounding). Providers are mocked/recorded — no paid calls.

## Phase 1: Setup
- [x] T001 [FOUND] Link STY-01..17; confirm `ChatRequest` text-only (`schemas/stylist.py`, wardrobe field `:83`); map provider registry + orchestrator.

## Phase 2: Foundational
- [x] T002 [FOUND] Central model-ID/provider registry doc + validation (STY-16); define vision-capable providers (NVIDIA OpenAI-compatible, Gemini vision). Linked: FR-010.
- [x] T003 [FOUND] Short-TTL/discard upload handling (no base64 in DB) shared with workstream 008 privacy pattern. Linked: FR-008.

## Phase 3: US1 — Mode A vision (P0) 🎯
### Tests first
- [x] T004 [P] [US1] `backend/tests/test_stylist_mode_a_grounding.py`: images[] ⇒ mode A; recommendations grounded in real catalog + currency; served model + mode reported; provider-unavailable ⇒ honest state (no fabrication). Linked: FR-001/003/006, SC-001. Acceptance: fails now (no image field).
### Implementation
- [x] T005 [US1] Extend `ChatRequest` with optional `images[]`; derive mode A/B. Linked: FR-001.
- [x] T006 [US1] Wire vision/multimodal model through provider abstraction; report served model + mode; honest fallback to Mode B with reason. Linked: FR-003/006.
- [x] T007 [US1] Stylist drawer image upload UI. Linked: FR-002.

## Phase 4: US2 — Wardrobe grounding (P1)
### Tests first
- [x] T008 [P] [US2] `backend/tests/test_stylist_wardrobe_influence.py`: include_wardrobe_items true ⇒ output provably references wardrobe; false ⇒ not. Linked: FR-004, SC-002. Acceptance: fails now (ignored).
### Implementation
- [x] T009 [US2] Make `include_wardrobe_items` influence recommendations. Linked: FR-004.

## Phase 5: US3 — Full failover (P1)
### Tests first
- [x] T010 [P] [US3] `backend/tests/test_stylist_failover.py`: primary fails ⇒ failover result w/ served model; all fail ⇒ honest unavailable (0 fabricated). Linked: FR-005, SC-003. Acceptance: fails now (chain underused).
### Implementation
- [x] T011 [US3] Orchestrator fully uses provider registry/failover chain. Linked: FR-005.

## Phase 6: US4 — Image color extraction (P1)
### Tests first
- [x] T012 [P] [US4] `backend/tests/test_stylist_color_extraction.py`: extracted colors change coordination palette vs rules-only. Linked: FR-007, SC-004. Acceptance: fails now.
### Implementation
- [x] T013 [US4] Feed extracted image colors into `ColorHarmonyEngine` in Mode A. Linked: FR-007.

## Phase 7: US5 — Safety + budget (P2)
### Tests first
- [x] T014 [P] [US5] `backend/tests/test_stylist_upload_safety_budget.py`: unsafe/oversized rejected; over-budget limited; 0 base64 images in DB. Linked: FR-008/009, SC-005.
### Implementation
- [x] T015 [US5] Content-safety + size/format guardrails + per-user AI budget. Linked: FR-008/009.

## Phase N: Polish
- [ ] T016 [POLISH] (partial: eval harness and STY-12/13 green; `/speckit.analyze` not run; see verification.md) Confirm STY-12/13 positives green (SC-006); drawer a11y/i18n via workstream 010; schedule STY-10/11/15/17 later. Record final commit + env; `/speckit.analyze`.

## Dependencies
- T002/T003 block Mode A. Upload privacy pattern shared with workstream 008. Mode-A→VTON (STY-17) depends on workstream 008.
