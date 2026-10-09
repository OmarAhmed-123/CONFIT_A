---
description: "Task list for UI/UX, Accessibility, i18n/RTL & Motion System"
---

# Tasks: UI/UX, Accessibility, i18n/RTL & Motion System

**Input**: `specs/010-uiux-accessibility-system/{spec.md, plan.md}`
**Tests**: REQUIRED (axe + i18n lint + reduced-motion).

## Phase 1: Setup
- [ ] T001 [FOUND] Link ADM-18/19, CUS-19/21/22, BRD-12/15, VTON-13/14, STY-14 (A11Y-05/MOT-06/IMG-03); inventory existing `HonestProductImage` + i18n framework.

## Phase 2: Foundational (primitives)
- [ ] T002 [FOUND] Shared primitives: accessible form controls, reduced-motion wrapper, Empty/Loading/Error components. Linked: FR-001/004/005/007.
- [ ] T003 [FOUND] i18n lint rule for hardcoded strings; `HonestProductImage` structural lint for raw `<img>`. Linked: FR-002/003.

## Phase 3: US1 — Accessibility (P1) 🎯
### Tests first
- [ ] T004 [P] [US1] axe scans for VTON upload, stylist drawer, checkout, admin/brand consoles asserting 0 critical/serious; manual keyboard/SR checklist. Linked: FR-001, SC-001. Acceptance: fails now.
### Implementation
- [ ] T005 [US1] Add accessible names/labels, focus management; replace emoji-only controls across targeted surfaces. Linked: FR-001.

## Phase 4: US2 — Honest imagery (P1)
### Tests first
- [ ] T006 [P] [US2] Structural test: 0 raw `<img>` for product/try-on imagery. Linked: FR-002, SC-002. Acceptance: fails now (VTON-14).
### Implementation
- [ ] T007 [US2] Replace raw `<img>` with `HonestProductImage` incl. honest failure state. Linked: FR-002.

## Phase 5: US3 — i18n/RTL (P2)
### Tests first
- [ ] T008 [P] [US3] i18n lint: 0 hardcoded strings on targeted surfaces; AR/RTL visual checks. Linked: FR-003, SC-003.
### Implementation
- [ ] T009 [US3] Complete EN/AR catalogs + RTL for B2B + AI surfaces. Linked: FR-003.

## Phase 6: US4 — Motion + states (P2)
### Tests first
- [ ] T010 [P] [US4] Reduced-motion test; state-coverage test (empty/loading/error; live order tracking). Linked: FR-004/005, SC-004/005.
### Implementation
- [ ] T011 [US4] Apply reduced-motion wrapper; standardize states; live order tracking; admin confirmation/rollback UX. Linked: FR-004/005/006.

## Phase N: Polish
- [ ] T012 [POLISH] Publish primitives for consuming workstreams (004/006/007/008/009); record axe + manual results; `/speckit.analyze`.

## Dependencies
- This workstream is a dependency of the UI portions of 004/006/007/008/009; prioritize primitives (Phase 2) early.
