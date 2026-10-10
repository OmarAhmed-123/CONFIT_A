# 009 StyleList AI modes: verification record

Branch: `009-stylelist-ai-modes` (from `main` @ `9265ca0`). Author identity: `OmarAhmed-123`.
Scope: spec `spec.md` SC-001..SC-006, tasks T001..T016 in `tasks.md`.
Baseline reference `a44f1fb` is an ancestor of `main`.

Every number below is from a command run in this session. None is a projection.

## 1. Baseline (before any change)

| Check | Result |
| --- | --- |
| Full backend suite on `main` (`backend/tests`, Python 3.12 venv) | **3736 passed, 21 skipped, 0 failed**, EXIT 0 (507.95 s) |
| Stylist subset `-k stylist` on `main` | 138 passed, 1 skipped |

The repo plan's older claim ("3732 passed, 4 env-only failures") did not reproduce.

## 2. Red evidence (new tests against the unmodified baseline)

The six new test files were run against a clean worktree of `main` (`HEAD` before Phase 2):

```
pytest test_stylist_mode_a_grounding.py test_stylist_wardrobe_influence.py
       test_stylist_color_extraction.py test_stylist_failover.py
       test_stylist_upload_safety_budget.py test_stylist_model_registry.py
       --continue-on-collection-errors
=> 11 failed, 3 passed, 9 errors
```

Several files fail at import on the baseline because the modules do not exist there. The 3 passes are existing behaviour that must be kept. The new code turned these red tests green.

## 3. Final results (working tree after all Phase 2 changes)

| Check | Command | Result |
| --- | --- |
| Full backend suite | `pytest backend/tests -q` | **3798 passed, 21 skipped, 0 failed**, EXIT 0 (530.9 s) |
| Increase over baseline | 3798 − 3736 | +62 = 58 Phase 2 tests + 4 eval-harness tests |
| Stylist + AI + wardrobe + safety subset | `pytest -k "stylist or ai_ or orchestrator or nvidia or outfit or wardrobe or safety or content or rate or tryon"` | 721 passed, 5 skipped |
| Focused: new files + Mode B + STY-12/13 + truthfulness | `pytest test_stylist_arabic_and_grounding.py test_stylist_mode_a_grounding.py test_stylist_wardrobe_influence.py test_stylist_color_extraction.py test_stylist_failover.py test_stylist_upload_safety_budget.py test_stylist_model_registry.py test_stylist_eval_harness.py test_ai_model_truthfulness.py` | 85 passed |
| Eval harness scorecard | `pytest test_stylist_eval_harness.py -s` | cases 8; grounded 100% (8/8); Mode A served model 100% (3/3); honest fallback 100% (1/1) |
| Lint | `pyflakes` on all changed Python | only the pre-existing unused `user_msg` at `stylist_service.py:71` (not introduced here) |
| Frontend verify | `npm run verify` (i18n gate, `tsc --noEmit`, `vitest run`, `vite build`) | exit 0; i18n gate passed; vitest **96 files, 1259 tests passed**; build OK |

## 4. Task map (what each task delivered)

| Task | Delivered | Evidence |
| --- | --- | --- |
| T001 | Request schema accepts optional `images` and derives `mode` A/B; mapping done | schema tests in `test_stylist_mode_a_grounding.py` |
| T002 | `docs/STYLIST_MODEL_ROUTING.md`; `stylist_model_routing_report()` (no credential values) | `test_stylist_model_registry.py` (5 tests) |
| T003 | Images are decoded in memory and discarded; nothing is persisted | `test_image_bytes_are_never_persisted`; zero-base64 DB check |
| T004 | Mode A grounding tests | `test_stylist_mode_a_grounding.py` |
| T005 | `images[]` on request; mode derived | as T001 |
| T006 | Vision via NVIDIA chain (`GARMENT_VISION`), served model reported, honest fallback to Mode B with reason | `test_stylist_mode_a_grounding.py` vision tests |
| T007 | Drawer photo attach (JPEG/PNG/WebP, ≤3, ≤1 MB each, pre-checked client side, thumbnails, removable) | `stylistImageAttach.test.ts` (4 tests); `npm run verify` |
| T008 | Wardrobe-influence tests (flag on ⇒ pairings; off ⇒ none; toggle changes output) | `test_stylist_wardrobe_influence.py` |
| T009 | `include_wardrobe_items` now reaches the look builder; owned pieces reach the LLM via `extra_context` | as T008 |
| T010 | Failover tests (primary fails ⇒ served failover; all fail ⇒ honest unavailable, no fabricated items) | `test_stylist_failover.py` |
| T011 | Orchestrator walks the full NVIDIA chain (the original code reached only positions 0 and 1) | `test_stylist_failover.py` |
| T012 | Colour-extraction tests | `test_stylist_color_extraction.py` |
| T013 | Deterministic pixel palette feeds `ColorHarmonyEngine`; model colours are marked `confirmed` or `uncertain` | `test_image_palette_changes_the_coordination_score`; eval colour test |
| T014 | Upload safety/budget tests | `test_stylist_upload_safety_budget.py` (11 tests) |
| T015 | Safety screen (fail closed 503 when unmeasured, 422 when blocked, stands down visibly when unconfigured); per-caller image budget (5 image turns/hour, text turns not counted) | as T014 |
| T016 | Eval harness (golden set, scorecard, thresholds); STY-12/13 positives green | `test_stylist_eval_harness.py`; `test_stylist_arabic_and_grounding.py` in the full run |

## 5. Spec success criteria

| SC | Status | Evidence |
| --- | --- | --- |
| SC-001 Mode A grounded, served model reported | Met in tests (mocked vision) | grounding + eval scorecard |
| SC-002 Wardrobe on/off provably different | Met in tests | `test_eval_wardrobe_toggle_changes_output`, wardrobe tests |
| SC-003 Failover reports served model; honest unavailable on total failure | Met in tests | failover tests; eval honest-fallback |
| SC-004 Extracted colours change palette | Met in tests | colour tests; eval colour test |
| SC-005 Unsafe/oversized rejected, over-budget limited, 0 base64 in DB | Met in tests | upload/safety/budget tests; storage check |
| SC-006 Mode B and STY-12/13 green | Met | full suite; Arabic/grounding tests |

## 6. Not verified (stated plainly)

* **No live provider call was made.** AGENTS.md prohibits paid AI jobs in testing, so every provider was mocked. The NVIDIA vision request shape is taken from the NVIDIA docs, and the model choices are backed by the registry's measurements. Real-model accuracy and latency are unverified.
* **Gemini vision is not wired.** The spec allows NVIDIA and/or Gemini. NVIDIA is the verified path, so Gemini is deferred.
* **STY-10 (streaming), STY-11 (save-as-look), STY-15, STY-17 (VTON handoff, depends on workstream 008)** are deferred, as the spec's phasing allows.
* **No database migration was needed.** No models changed. Migrations are not authored (repo head `0034`, production head unverified).
* **`/speckit.analyze`** was not run.
* **Rollout default:** `STYLIST_VISION_ENABLED` defaults to `true` (documented in `.env.example` and the routing doc). It is a kill switch.
* **Historical plan:** `docs/audits/STYLELIST_AI_REPAIR_PLAN.md` is one of the five historical forensic plans and was not rewritten, per AGENTS.md. This file is the result record instead.
* **Pre-existing:** the `user_msg` unused variable in `stylist_service.py`.

## 7. Execution record: 2026-10-10 (T-STY-07 frontend, Mode A)

> **Correction (2026-10-10).** Section 6 above labels streaming as STY-10 and save-as-look as STY-11. That is backwards. Per `spec.md` (deferred scope, line 128): **STY-10 = shareable looks (save-as-look)**, **STY-11 = streaming / multi-turn**, STY-15 = eval harness, STY-17 = Mode-A→Try-On handoff. Section 6 is kept as the historical record and is not rewritten.

### 7.1 Red then green (frontend)

* `frontend/src/components/stylist/__tests__/stylistModeA.test.tsx` (12 tests) was written first. Against the code before this pass, **5 failed** (fallback note, save-as-look ×3, colour-contrast axe run). The other 7 passed, and they cover behaviour that already existed.
* After the change, **12/12 pass**.
* `npm run verify` exit 0: **97 files, 1271 tests passed** (was 96 files, 1259 before this pass).
* `tsc --noEmit` exit 0. `npm run i18n:check` exit 0. Logs: `/home/user/logs/fe_verify2.log`, `fe_tsc2.log`, `fe_i18n2.log`.

### 7.2 What changed (T-STY-07 items)

| Item | Status | Evidence |
| --- | --- | --- |
| Honest fallback shown to the shopper (FR-003) | Done for the UI. The note is localized and does not show the API's English sentence. | `stylistModeA.test.tsx`; screenshot in `/home/user/logs/` |
| Save look (STY-10), Mode A only, signed-in | Done, reusing `POST /outfits/save`. No schema change. Saving, saved, sign-in (401), and generic error states. | 3 tests in `stylistModeA.test.tsx` |
| RTL | Verified in a real browser: `dir="rtl"` on `<html>`, drawer mirrored, Arabic strings render. | `frontend/scripts/stylist_drawer_a11y_probe.mjs`; `/home/user/logs/stylist_drawer_a11y_run.log` |
| Axe with colour contrast enabled (real browser) | **Passes with 0 serious/critical violations in en and ar.** Found and fixed 4 real contrast issues (gold labels, attachment error text, step numerals, body copy). 75 (en) and 70 (ar) checks are **incomplete**, because axe cannot resolve the gradient backgrounds. Those are **not verified**. | `/home/user/logs/stylist_drawer_a11y.json` |
| Keyboard and focus order | **Not verified in this pass.** Only the existing jsdom checks. A keyboard walk in a browser is still needed. | none |
| Streaming (STY-11) | **Deferred.** It needs a decision: SSE on serverless, and grounding must be verified before streaming products. | spec deferred scope |
| Errors and loading | Attachment rejection is announced in an alert; save states are covered by tests. | `stylistModeA.test.tsx`, `stylistImageAttach.test.ts` |

### 7.3 Caveats

* **Save-as-look was not exercised in the browser.** The browser probe does not sign in and does not send chat requests, because no backend was run. The save flow is covered by the jsdom test, which mocks `stylistService.saveOutfit`. A signed-in browser run is still needed.
* The browser probe is a **reporting tool**. It exits non-zero on serious or critical violations. It needs `npm run dev` on port 43123, and it uses the repo's `playwright-core` and its Chromium build with system libraries installed (`install-deps`).
* The repo's existing Python tool `frontend/scripts/browser_a11y_rtl.py` was **not run**. It needs `pip install playwright`, and its surface list points at `/stylist`, not the drawer.

### 7.4 Git

* Branch `009-stylelist-ai-modes`, identity `OmarAhmed-123`.
* `865e0c6` feat(stylist): Mode A honest fallback note and save-as-look (T-STY-07). Grouped: the fix for the contrast issues is in the same file as the feature, so it is not a separate commit.
* `2fc71cf` chore(stylist): browser a11y probe for the drawer.

### 7.5 Still open (stated plainly)

* Live provider calls: none. Real-model accuracy and latency are unverified.
* `/speckit.analyze`: not run.
* T-STY-09 (Try-On handoff, STY-17) is **blocked on workstream 008** (0/16 complete).
* Migration head: repo `0034`, production head unverified. No migration was created or run.
* `Workers Builds: confit-a` check: pre-existing, dashboard-only, out of scope unless the owner provides its log.

## 8. Second execution pass, 2026-10-10 (evidence in `evidence/2026-10-10/`)

### 8.1 Browser keyboard, focus and RTL (Chromium, via the repo's Playwright scripts)

| Check | Result | Evidence |
| --- | --- | --- |
| Keyboard probe (real key presses), en | 14/14 PASS | `keyboard_probe.json` |
| Keyboard probe, ar | 14/14 PASS | `keyboard_probe.json` |
| Earlier defect found and fixed: prompt input had no accessible name (placeholder only) | FAIL before, PASS after; regression tests added | commit `62910f7` |
| Focus trap, visible focus on each stop, Escape closes, focus restored to opener | PASS (en+ar) | `keyboard_probe.log` |
| RTL in Chromium, Arabic drawer | Screenshot reviewed: Arabic copy, header and chips mirrored, close control on the left, step numerals `01`/`02` shown | `stylist-drawer-ar.png` |
| axe (WCAG 2.x A/AA and 2.2 AA tags), drawer, colour contrast enabled | 0 serious/critical in en and ar | `axe_probe.json` |
| Repo tool `browser_a11y_rtl.py --only stylist` (Python playwright 1.63.0) | Self-test PASS. Stylist route: 0 axe violations in en/ar; keyboard 30/30 stops, no indicator, no obscured. Exit 1 on 53 untranslated catalogue strings in ar (T030). | `repo_rtl_tool_stylist.json` |

**Colour contrast, measured not assumed.** axe's "incomplete" result is not a pass. The pixel-level audit measured **one** drawer element so far (coverage is still partial; see below):

* Pixel measurement (`stylist_contrast_audit.mjs`, `evidence/2026-10-10/contrast_audit.json`): the step numeral "02" in en, 18px weight 900 (large text), **4.76:1** worst-case against 4.5:1 for normal text. Pass.
* The audit measured **1 element and 0 failing**. That is not full coverage. The earlier 1-element run was a scoping defect. Coverage of all drawer text is NOT yet complete, and the gallery credit change is not pixel-measured. Those remain open under T026 and are not claimed as verified.
* Full-page axe incomplete items on the homepage sit behind the modal scrim and belong to another workstream. They are not claimed as drawer results.
* Fixes made in this pass: gallery credit `text-slate-400` → `text-slate-600` (Home and Discover, `DesignShowcases.tsx`; measured below AA in the repo tool).

**Unresolved accessibility items (stated plainly):**
* The catalogue cards behind the scrim on the homepage contain low-contrast text on photos. Not in this workstream (catalogue and home, workstream 010 scope).
* Screen-reader announcement text was checked in the DOM, not with a real screen reader. NOT VERIFIED with NVDA/VoiceOver.
* The browser probes are not wired into CI (T029).

### 8.2 Authenticated save-as-look, real backend and local test database

* Environment: local backend on `:8000`, SQLite file `/home/user/.cache/confit-e2e/e2e.db` (throwaway, seeded by `seed.py`, log `evidence/2026-10-10/e2e_seed.log`). `CONFIT_IGNORE_DOTENV=1` and an explicit SQLite `DATABASE_URL`, so the production URL in `backend/.env` was not used. No Alembic migration was created or run.
* Flow exercised: real login (`POST /api/v1/auth/login`) → cookie session → drawer → (chat response: the **real grounded Mode B engine** response, with `mode` set to `A` by the test so the Mode A control renders; no vision provider called) → Save look → `POST /api/v1/outfits` with CSRF header → `GET /api/v1/outfits`.

| Check | Result |
| --- | --- |
| Login through the real endpoint | 200 |
| Mode A control visible | PASS |
| Double-click creates exactly one request and one look | PASS (count +1) |
| Saved look retrievable by `GET /api/v1/outfits` with the same title | PASS |
| Request body: integer product ids and title; no image payload | PASS |
| Another user's list does not contain the look | PASS (isolation) |
| No `data:image…;base64` in any text column of the test DB | PASS (0 hits) |
| Server 500 on save → localized generic error; raw server detail not shown; retry available | PASS |
| Signed-out save → localized sign-in message; nothing persisted | PASS |
| **Total** | **18/18** (`save_look_e2e.json`) |

Limit: the Mode A flag is applied to a real Mode B response. The vision path itself (photo → provider) was **not** exercised live, because it needs a paid provider.

### 8.3 Backend tests

* `pytest backend/tests -k "stylist or outfit or color_harmony or wardrobe or try_on_capab"` with `env -i` and no keys: **439 passed, 1 skipped, 3379 deselected, exit 0** (`pytest_stylist_subset.log`). The full suite was not re-run in this pass; the earlier full run was 3798 passed, 21 skipped (§3).
* The stylist failover, Mode A grounding, wardrobe, colour and safety/budget tests are in that subset.

### 8.4 Frontend gates (commit `6b66f2f` working tree)

* `npm run verify` exit 0: i18n check, `tsc --noEmit`, Vitest **97 files, 1274 tests passed**, `vite build` ok.
* `npm run i18n:check` exit 0. `tsc --noEmit` exit 0.

### 8.5 Cloudflare `Workers Builds: confit-a`: investigation

* Observed in earlier work in this workstream: the Workers Builds check on `5b4642d` reports failure; the same check on `main` passes. Build identifiers were not preserved in the session record, so they are not cited here.
* Repo-side: no `wrangler.*` or Workers build config in the repo, and the branch diff against `main` touches no package manifest, lockfile, CI workflow or deploy config. No repo difference explains the failure from here.
* Cloudflare log access: no Cloudflare credential is present in the local env file (variable names checked, values not read), and the dashboard build log requires login.

**Status: BLOCKED.** Cause not determined. Not called resolved and not called pre-existing. An operator needs the build log for the failing build, or a read-only Workers Builds token, to decide whether this is branch-specific or a shared setting.

### 8.6 Migration-chain CI

* On `main`, the `postgres migration chain + schema gate` job was seen failing from Docker Hub pulls of `postgres:17` (timeouts and an unauthenticated rate limit). This is infrastructure, not code.
* The current branch head's CI results are recorded on the pull request, not here, to avoid a commit each time the head moves. They were not re-verified in this pass.
* No Alembic migration was created or run. Repo head `0034`; production head unverified (see the migration-head item).

## 9. `/speckit.analyze` (2026-10-10)

* Command: `.cursor/commands/speckit.analyze.md` (read-only analysis of spec, plan and tasks against the constitution). It was run as a manual analysis pass by the agent. Its prerequisite step, `check-prerequisites.sh`, ran with `SPECIFY_FEATURE_DIRECTORY=specs/009-stylelist-ai-modes` because branch-name detection did not resolve the feature directory. Output: `evidence/2026-10-10/speckit_prerequisites.json`. No `.specify/extensions.yml` exists, so no hooks ran.
* The analysis itself wrote no files. The fixes listed below were then applied as a separate commit.

| ID | Category | Severity | Finding | Status |
| --- | --- | --- | --- | --- |
| A1 | Coverage | HIGH | The 2026-10-10 amendment defines save-as-look, but no FR or task covered it | Fixed: FR-011, T024 |
| A2 | Completion label | HIGH | T002 was `[x]` and claimed Gemini vision was defined; Gemini vision is not wired | Fixed: wording corrected; T027 open |
| A3 | Unverified completion | HIGH | T018 was `[x]` but its text said "not yet exercised in a signed-in browser" | Fixed: E2E evidence added (T024) |
| A4 | Stale task | MEDIUM | T021 (keyboard walk) was `[ ]` after the probe ran | Fixed: `[x]` with evidence |
| A5 | Stale status | MEDIUM | Spec status read "Draft (planning only)" | Fixed |
| A6 | Stale content | MEDIUM | The model-research paragraph names retired IDs (`gemini-3-pro-preview`, nano-omni as primary) | Fixed: marked superseded, pointer to routing doc |
| A7 | Terminology | MEDIUM | Spec says `ChatRequest`; code class is `StylistPromptRequest` | Fixed: noted in Key Entities |
| A8 | Terminology | MEDIUM | "served-model" in requirements; code uses `engine`, `mode`, `image_analysis` | Fixed: mapping stated in Key Entities |
| A9 | Plan path | MEDIUM | Plan pointed at `components/VirtualStylistDrawer*`; the file is `components/stylist/VirtualStylistDrawer.tsx` | Fixed |
| A10 | Plan runtime | LOW | Plan said Python 3.12; Dockerfile is 3.13 | Fixed |
| A11 | Constitution mapping | MEDIUM | Plan cited Principle III (authorization) for upload safety | Fixed: mapped to IV and V |
| A12 | Identifier collision | MEDIUM | Repair-plan labels (T-STY-07/09/10/11) and tasks.md IDs were not mapped | Fixed: mapping table in tasks.md |
| A13 | Dependency claim | MEDIUM | T003 said the upload privacy pattern is shared with 008; 008 is 0/16 | Fixed: stated as independent |
| A14 | Open item | MEDIUM | T016 partial; analyze not run | Updated: analyze now run; live-provider quality remains open |
| A15 | Coverage | MEDIUM | No acceptance criterion for keyboard, RTL or contrast | Fixed: FR-012, SC-007 |
| A16 | Missing task | MEDIUM | `Workers Builds` release item was not in tasks | Added: T028 (BLOCKED) |
| A17 | Scope wording | MEDIUM | STY-14 said "aligns with workstream 010" with no split | Fixed: split stated in Assumptions |
| A18 | Scope wording | LOW | Assumption said vision uses NVIDIA and/or Gemini | Fixed: NVIDIA only, Gemini deferred |
| A19 | Verification gap | MEDIUM | Browser probes are not in CI; they are evidence, not a gate | Open: T029, owner decision |
| A20 | Verification gap | MEDIUM | Live-provider quality, latency and availability are not verified | Open: needs authorization for paid calls |
| A21 | Cross-workstream | MEDIUM | Stylist route (Discover) shows English catalogue text in Arabic and raw catalogue errors | Open: T030, T031, other workstreams |

**Constitution alignment.** No MUST principle is violated by the spec or code. Principle IV (honest AI): the served model and fallback reason are shown, and no fabricated products were found. Principle V (tests and E2E): the save flow now has an authenticated E2E, and the keyboard and contrast checks exist as scripts that are not yet in CI (A19).

**Remaining CRITICAL issues:** none in the spec artifacts. Two items block the release gate and need an owner: T028 (Workers build log) and the decision on live-provider quality (A20).

**Final task status (this pass):** T018 `[x]` (E2E), T019 `[x]`, T020 `[x]`, T021 `[x]`, T024 `[x]`, T025 `[x]`, T026 `[ ]` (partial: 1 element measured), T016 `[ ]` (partial), T022 `[ ]` deferred, T023 `[ ]` blocked on 008, T027 `[ ]` not wired, T028 `[ ]` BLOCKED, T029 `[ ]`, T030–T031 `[ ]` cross-workstream.
