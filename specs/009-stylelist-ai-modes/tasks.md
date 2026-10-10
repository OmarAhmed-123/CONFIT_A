---
description: "Task list for StyleList AI Mode A / grounding / failover"
---

# Tasks: StyleList AI — Mode A, Wardrobe Grounding & Failover

**Input**: `specs/009-stylelist-ai-modes/{spec.md, plan.md}`
**Tests**: REQUIRED (AI honesty, grounding). Providers are mocked/recorded — no paid calls.

## Phase 1: Setup
- [x] T001 [FOUND] Link STY-01..17; confirm `ChatRequest` text-only (`schemas/stylist.py`, wardrobe field `:83`); map provider registry + orchestrator.

## Phase 2: Foundational
- [x] T002 [FOUND] Central model-ID/provider registry doc + validation (STY-16); vision-capable provider defined as NVIDIA OpenAI-compatible only. Gemini vision is NOT wired (deferred, see T025). Linked: FR-010.
- [x] T003 [FOUND] Short-TTL/discard upload handling (no base64 in DB). Implemented independently in 009; the 008 privacy pattern is NOT yet shared (008 is 0/16). Linked: FR-008.

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
- [ ] T016 [POLISH] PARTIAL. Protocol written (`live-evaluation-protocol.md`): provider config by name, budgets, dataset rules, metrics, fallback expectations, evidence list. Offline harness passes (8 cases; grounded 8/8; served model 3/3; fallback 1/1), which is contract evidence, not quality. NO live-provider run has happened. Needs written authorization, a call ceiling and a spend cap.

## Dependencies
- T002/T003 block Mode A. Upload privacy pattern shared with workstream 008. Mode-A→VTON (STY-17) depends on workstream 008.

## T-STY-07 frontend status (2026-10-10)

- [x] T017 [FE] Mode A fallback note rendered from `mode` / `fallback_reason` (localized). Evidence: `stylistModeA.test.tsx`, `verification.md` §7.
- [x] T018 [FE] Save look (Mode A, signed-in) via `POST /outfits/save`, with saving / saved / sign-in / error states. Evidence: `stylistModeA.test.tsx`; authenticated browser E2E `frontend/scripts/stylist_save_look_e2e.mjs` 18/18 against the local test DB (verification.md §8.2).
- [x] T019 [FE] Real-browser axe with colour contrast enabled: 0 serious/critical in en and ar. Evidence: `frontend/scripts/stylist_drawer_a11y_probe.mjs`. axe 'incomplete' items are NOT counted as passes. One element was measured at pixel level (4.76:1 vs 4.5:1); coverage is partial (see T026).
- [x] T020 [FE] RTL drawer verified in Chromium (en ltr, ar rtl). Evidence: `evidence/2026-10-10/stylist-drawer-ar.png` and `stylist-drawer-en.png`. Repo RTL tool on the stylist route: 0 axe violations in en/ar; 53 untranslated catalogue strings in ar remain (see T030).
- [x] T021 [FE] Keyboard and focus walk in Chromium with real key presses, en and ar: 14/14 checks per language (Tab trap, visible focus on every stop, photo removal, submit, Escape, focus restore). Evidence: `stylist_drawer_keyboard_probe.mjs`, `verification.md` §8.1.
- [ ] T022 [FE] Streaming (STY-11). DEFERRED. Decision record and resume criteria in `verification.md` §10.7. No SSE was added. Needs a product decision, a hosting decision, and grounding before any product is streamed.
- [ ] T023 [FE] T-STY-09 Try-On handoff. BLOCKED on workstream 008 (T004–T006; 008 is 0/16 done).

## T-STY-07 closure and analysis (2026-10-10, second pass)

- [x] T024 [FE] FR-011 save-as-look: authenticated browser E2E, persistence via `GET /outfits`, duplicate click, server error, signed-out, cross-user isolation, no image data stored. Evidence: `evidence/2026-10-10/save_look_e2e.json` (18/18).
- [x] T025 [FE] Keyboard, focus and dialog semantics (FR-012): probe 14/14 en and 14/14 ar; regression tests added for input name, focus on open, Escape. Evidence: `keyboard_probe.json`, `stylistModeA.test.tsx`.
- [ ] T026 [FE] Colour contrast, PARTIAL. Pixel audit measured 1 drawer element (step numeral, 4.76:1 vs 4.5:1, large text). The audit covers 1 element, so full drawer coverage is not shown. Shared gallery credit changed `text-slate-400` → `text-slate-600` but not pixel-measured. Evidence: `evidence/2026-10-10/contrast_audit.json`.
- [x] T033 [FE] Stabilise `actionButton.test.tsx` checkout pending-state test (CI flake). DONE in `ef3edea`: the reply is held open until the pending state is asserted. Original reproduced failing 1 of 12 runs; fixed 26/26 in 5 of 5. No product change.
- [ ] T027 [FE] Gemini vision as a second vision provider. NOT WIRED. Deferred; needs an owner decision (NVIDIA is the only verified vision path).
- [ ] T028 [OPS] Cloudflare `Workers Builds: confit-a` failure on the branch (passes on `main`). BLOCKED. Check run `114122737165` on `f435e45` fails with no text and no annotations. The dashboard build log is needed, or a read-only Workers Builds token plus branch build settings. Cause not determined; not called pre-existing, not attributed to the branch. See `verification.md` §10.4. BLOCKED: the build log is only in the Cloudflare dashboard, and no Cloudflare credential is configured. Needs the build log or a read-only token. Not claimed as resolved, and not claimed as pre-existing.
- [x] T029 [FE/OPS] Drawer browser gate in CI. Implemented: `frontend/scripts/stylist_browser_gate.sh` and job `stylist-browser-gate` (axe + keyboard/focus/RTL, en and ar; no backend; no provider calls). Verified locally (PASS; negative control exit 1) and in CI on `56d914f` (job success, `gate: result=PASS`). Open: the job is not yet a required check on `main` (owner decision). Not included: `browser_a11y_rtl.py` (catalogue copy, T030/T031). See `verification.md` §10.5.
- [ ] T030 [FE, cross-workstream] Stylist route (Discover) in Arabic: catalogue product names and brands are English data, and the language switcher shows "English" as a self-name. These are not drawer strings. Owned by catalogue/i18n content work, not 009.
- [ ] T031 [FE, cross-workstream] Discover catalogue error text (`catalogError`) reaches the UI raw. Seen in Arabic when the API is down. Not a drawer string; owned by the catalogue workstream.
- [ ] T032 [SPECKIT] Analysis findings A1–A21 in `verification.md` §9: fixes applied in this commit where they were within workstream scope; remaining items are owner decisions listed there.

## Task ID mapping (repair-plan labels to tasks.md)

The repair plan uses STY-nn and workstream labels such as "T-STY-07". `tasks.md` uses T001–T032. This table is the single mapping.

| Repair-plan label | Meaning | tasks.md |
| --- | --- | --- |
| STY-01, STY-02, STY-05, STY-07 | Mode A vision, upload UI, vision wiring | T004–T007 |
| STY-03 | Wardrobe grounding | T008–T009 |
| STY-04, STY-16 | Failover, model registry | T010–T011, T002 |
| STY-06 | Colour extraction | T012–T013 |
| STY-08, STY-09 | Budget, upload safety | T014–T015 |
| T-STY-07 (frontend) | Drawer UI, honest note, save look, a11y, RTL | T017–T021, T024–T026 |
| STY-10 (save-as-look) | Scope amendment 2026-10-10 | T018, T024 (FR-011) |
| STY-11 (streaming) | Deferred | T022 |
| STY-15 (eval harness) | Partly delivered (T016); extension deferred | T016 |
| T-STY-09 / STY-17 (Try-On handoff) | Blocked on workstream 008 | T023 |

