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

## 10. Release readiness: CI hardening pass (2026-10-10)

### 10.1 Repository state, corrected

* At the start of this pass the local clone was **behind** the remote: local HEAD was `5b4642d` and the remote head of `009-stylelist-ai-modes` was `f435e45`. The five commits from the previous pass (`62910f7`…`f435e45`) were present on the remote only.
* Action: the local branch was fast-forwarded to `origin/009-stylelist-ai-modes` (`git reset`, no `--hard`). Before that, every tracked and untracked file was checked byte-for-byte against the remote, and a snapshot was saved outside the repository.
* Mistake and cleanup: a copy command placed repository top-level entries directly into `/home/user/.cache/`. They were removed by name. The directory held no cache data at that point, and the repository was verified intact (21 top-level entries, `git status` as expected).
* Preserved: the six `.specify/scripts/bash/*.sh` mode-only changes (100755 → 100644). They are not committed, as instructed.

### 10.2 CI state for the previous head `f435e45` (before this pass's commits)

Check-run results from the GitHub API for `f435e45`. Two runs appear for the frontend and backend (push and pull-request events).

| Check | Result | Note |
| --- | --- | --- |
| backend | success (both runs) | |
| frontend | **failure (one run)**, success (other run) | Same commit, different outcome. Cause: flaky test, see 10.3 |
| postgres migration chain + schema gate | success (both runs) | |
| production parity (deployment contract) | success (both runs) | |
| release gate (production schema parity) | success | Fails closed if production state is unknown; passed |
| gitleaks secret scan (full history) | success | |
| Vercel Preview Comments | success | |
| Workers Builds: confit-a | **failure** | Cloudflare-managed. See 10.4 |

### 10.3 Frontend failure: a flaky test, not a regression

* Failing test: `ActionButton controlled mode › checkout contract: caller owns pending` in `frontend/src/components/__tests__/actionButton.test.tsx`. The file is **not changed** on this branch relative to `main`.
* Cause: the simulated server reply used a 10 ms timer. On a loaded runner, the reply could land before the first poll observed `aria-busy`, so `data-state` read `idle`.
* Reproduction: the original file failed **1 of 12** local runs (`Tests 1 failed | 25 passed`). Commit `ef3edea` holds the test open with the file's existing `deferred()` helper until the pending state is asserted. The fixed file passed 26/26 in 5 of 5 runs.
* No product code changed. The contract being tested is unchanged.

### 10.4 T028: Cloudflare Workers Builds, status BLOCKED

* Check run `114122737165` on `f435e45`: `failure`, started and completed at the same second (`2026-10-10T03:39:19Z`). Output: build link and script link only. No text, no annotations.
* The dashboard log is required, and it is not reachable from this environment. The env file has no Cloudflare variables (names checked; values not read). No workflow in this repository defines this check. It is managed by Cloudflare's GitHub integration, so its build settings live in the dashboard.
* On `main`, the same check passed on 2026-10-09 (the earlier report). The branch and `main` builds have not been compared with the dashboard log, so the cause is **not determined**. It is not called pre-existing, and it is not attributed to this branch.
* Evidence needed to close: the build log for the failed build, or a read-only Workers Builds token, plus the branch build settings. With that, the cause will be classified as branch defect, configuration, or infrastructure.

### 10.5 T029: focused drawer browser gate in CI, PARTIAL until the PR run is observed

**Added** (commits `e81ec55` and the `ci.yml` job):

* `frontend/scripts/stylist_browser_gate.sh`: serves `dist/` with `vite preview` on 127.0.0.1, waits for it, runs the two probes, then stops the server it started.
* Job `stylist-browser-gate` in `.github/workflows/ci.yml`: Node 22, `npm ci`, `npm run build`, `npx playwright-core install --with-deps chromium`, the gate, and an artifact upload (`frontend/gate-artifacts/`, probe JSON and logs).

**What the gate checks (fails on each):**

| Check | Probe | Gating rule |
| --- | --- | --- |
| axe, WCAG 2.x A/AA and 2.2 AA, colour contrast on | a11y | Any serious or critical violation |
| Text direction in the drawer | a11y | `ltr` in English and `rtl` in Arabic |
| Photo-error message | a11y | Exact localized text |
| Photo thumbnail alt text | a11y | Present |
| Keyboard opens dialog, focus trapped, visible focus, Escape, focus restored | keyboard | Each check (14 per language) |
| Accessible names, dialog label, aria-modal | keyboard | Each check |

**What it does not cover:**

* axe `incomplete` results are **reported, not passed**. The current run shows two per language: a critical `aria-valid-attr-value` on header triggers outside the drawer (`#:r0:-discover-trigger` and similar), and a serious `color-contrast` set on the page behind the scrim (75 nodes). Both are outside this workstream.
* Colour contrast for the whole drawer is **not** established. The earlier pixel audit covered one element (4.76:1). T026 stays partial.
* Catalogue copy in Arabic (T030, T031) is out of scope and is excluded from this gate on purpose.
* Real screen-reader behaviour (NVDA, VoiceOver) is not tested.
* The Mode A photo flow with a live vision provider is not tested. The gate stops at the drawer and makes no provider calls.

**Local verification (this pass):**

| Run | Result |
| --- | --- |
| Gate, production build, no backend | **PASS**. axe en/ar 0 violations; keyboard en 14/14, ar 14/14; direction ltr/rtl |
| Negative control: prompt input's `aria-label` removed, rebuilt | **exit 1**, `KEYBOARD PROBE: 2 failing check(s)`. Source restored from git afterwards (diff empty) |
| Orphan check after gate | No `vite preview` left running (a wrapper-PID bug was found and fixed) |
| Original `actionButton` test file, 12 runs | 11 passed, 1 failed |
| Fixed `actionButton` test file, 5 runs | 26/26 each time |

**Environment caveat:** local runs used Node 20.20.2 and Playwright-core 1.63.0. CI uses Node 22. The PR run on the pushed head is the authoritative result for the job, and it has not been observed yet at the time of writing.

### 10.6 T016: real-provider evaluation, PARTIAL (protocol written, not executed)

* Protocol: `live-evaluation-protocol.md` (this folder). It defines provider configuration by variable name only, budgets and cost ceilings, the dataset rules (synthetic or licensed photos only, no customer images in any artifact), metrics, fallback expectations, and the seven evidence items required before production activation.
* Offline evidence (mocked providers, Python 3.12, exit 0): `test_stylist_eval_harness.py`. Scorecard: 8 cases run; grounded 8/8; Mode A served model 3/3; honest fallback 1/1. This is contract evidence, **not** model quality.
* Not done: any live call, latency measurement, failure-rate measurement, or human colour rating. None is claimed.

### 10.7 T022: streaming, DEFERRED (decision record)

* Decision: streaming (STY-11) stays deferred. No SSE endpoint and no new response protocol were added.
* Reasons: on serverless hosting a long-lived stream has to finish within the function's time limit, and the chat response must be grounded in catalogue data **before** any product is streamed. Neither requirement is decided yet.
* Acceptance criteria to resume: (1) a product owner's decision on streaming versus a faster single response; (2) a hosting decision for long-lived responses, with the function timeout confirmed; (3) grounding applied before the first streamed product, verified by a test; (4) an honest partial-failure message if the stream breaks mid-response; (5) a browser test for each of these.

### 10.8 Regression results (this pass)

| Suite | Command | Result |
| --- | --- | --- |
| Backend stylist subset (Python 3.12) | `pytest backend/tests -k "stylist or outfit or color_harmony or wardrobe or try_on_capab"`, `env -i` | **439 passed, 1 skipped, 3379 deselected, exit 0** |
| Stylist eval harness (Python 3.12) | `pytest backend/tests/test_stylist_eval_harness.py -s` | Exit 0; scorecard as in 10.6 |
| Frontend verify | `npm run verify` (i18n, `tsc --noEmit`, vitest, `vite build`) | **exit 0**; 97 files, **1274 tests passed** |
| Browser gate | `bash frontend/scripts/stylist_browser_gate.sh` | **PASS** (exit 0); negative control exit 1 |

Not re-run in this pass: the full backend suite (3798 passed in §3), and the PostgreSQL migration chain (CI-only; no migration was changed in this pass).

### 10.9 Release recommendation

* **Review: supported.** The branch has no open functional defect in the stylist drawer that these checks found. The gate and the flaky-test fix are in place, and the focused probes pass.
* **Merge: not yet.** Required checks for the new head must be observed green (see the Git section of the closeout). Workers Builds (T028) is failing and has no cause. It is unresolved, and the owner must decide whether it blocks merge.
* **Deploy: not authorized.** No production action was taken.
* **Still unverified:** live-provider quality, latency, and availability (T016); full-drawer colour contrast (T026); screen-reader behaviour; the Workers build cause (T028); cross-workstream catalogue copy in Arabic (T030, T031); the production migration head, which is unverified.

### 10.10 CI result for the tested head `56d914f` (observed, not inferred)

Head `56d914f` (remote SHA verified equal to local). Two runs per push and pull-request event.

| Check | Result (both runs unless noted) | Required on `main` |
| --- | --- | --- |
| backend | success | yes |
| frontend | success | yes |
| release gate (production schema parity) | success | yes |
| stylist drawer browser gate (a11y, keyboard, RTL) | **success**. Job log: axe exit 0, keyboard exit 0, `gate: result=PASS`. Artifact `stylist-browser-gate` uploaded | **no** (owner decision to add) |
| postgres migration chain + schema gate | success | no |
| production parity (deployment contract) | success | no |
| gitleaks secret scan (full history) | success | no |
| Vercel Preview Comments | success | no |
| Workers Builds: confit-a | **failure** (build `114195237846`, no log text) | no |

* Branch protection on `main` (readable): required checks are `backend`, `frontend`, `release gate (production schema parity)`. All three passed.
* PR #335: open, **draft**, not merged. `mergeable_state` is `unstable`, because the non-required Workers check fails.
* The PR is not marked ready for review, not merged, and not deployed.

### 10.11 Final execution pass (2026-10-10): what was re-run and what it shows

Scope: PR #335 (`009-stylelist-ai-modes` to `main`). Local checks below ran on the working tree that includes the commit that carries this section. Each row names its exit code and counts. Mock-only evidence is labelled as such.

| Gate | Command or source | Result |
| --- | --- | --- |
| Frontend verify (i18n check, `tsc --noEmit`, vitest, `vite build`) | `npm run verify` in `frontend/` | **exit 0**. 97 files, **1274 tests passed**; build ok |
| `actionButton` race, fixed test (current file) | `vitest run actionButton.test.tsx -t "checkout contract"`, 25 runs | **25 pass / 0 fail** |
| `actionButton` race, pre-fix test (`ef3edea^`, same assertions, 10 ms timer) | same filter, 25 runs, file copied temporarily and removed | **0 pass / 25 fail**, symptom `data-state="idle"` where `pending` is asserted (line 322). This reproduces the CI failure. The earlier figure of 1 in 12 was a CI-loaded rate; in this environment it failed every time |
| Browser gate (production build, no backend, no provider) | `GATE_OUT=... bash frontend/scripts/stylist_browser_gate.sh` | **exit 0, `gate: result=PASS`**. Axe drawer probe 0 serious/critical in en and ar. Keyboard/focus probe **29/29 checks, 0 failing** across en and ar |
| Live local API scenarios (real backend, seeded test DB, **no provider keys**) | `evidence/2026-10-10/e2e_live_api_scenarios.py` | **28/28 PASS**, exit 0 (log `e2e_live_api_run.txt`). Covers Mode B, guest text, Mode A validation (L1-L5), image budget (L6), base64 scan of 18 tables (0 hits), wardrobe on/off and cross-user isolation, save-as-look, signed-out save |

**Corrections made during this pass (recorded, not hidden):**

* Two checks were wrong expectations and are now corrected to the intended rule. Guest text chat is by design (the controller accepts anonymous callers and limits them to 20/hour; only saving requires sign-in, FR-011). Guest photos are allowed and limited by the per-caller image budget (`STYLIST_IMAGE_TURNS_PER_HOUR`, 429 "styling with photos this hour"). A wardrobe check had looked for the wrong field; the engine reports wardrobe use in `intent_detected.wardrobe` (`used`, `owned_items_considered`, `pairings`).
* Two checks passed or failed for the wrong reason while the chat limiter was exhausted (20/hour, keyed to 127.0.0.1, in-process). The chat endpoint returned 429 bodies with no `content`, so a "not in answer" check passed vacuously. The checks now require HTTP 200 first. The backend was restarted to reset the in-process counter. Any future run on the same host must respect the same budget.
* Keyboard probe (`stylist_drawer_keyboard_probe.mjs`): the Tab search cap was 80 presses. On the current page the "Open AI Virtual Stylist" control is the 141st Tab stop (it is a fixed element at the end of the DOM). The cap is now 200. The assertion (the opener must be reached by Tab, then opened with Enter) is unchanged. **Keyboard users need about 140 Tab presses to reach the AI stylist opener**, which is a usability limitation to track, not a gate regression.
* `.specify/scripts/bash/*` and `frontend/scripts/stylist_browser_gate.sh`: the gate script's executable bit now matches git mode `100755`. The six `.specify` mode-only changes from before this pass were left in place, untouched.

**Still not verified, and what it means for release:**

* **Vision (Mode A image analysis) is not verified live.** `NVIDIA` vision is not configured on this deployment, so the honest fallback ("Image analysis is not configured on this deployment.") is what the live run shows. The image-colour path into colour harmony runs only when vision succeeds; that path is covered by mocked tests only and is labelled mock-only.
* **The configured-but-failing safety provider (503 fail-closed branch) is not exercised live.** Covered by code reading and mocked tests only.
* **Live-provider quality, latency and availability (T016): not verified.** No budget was authorized, so no paid or live-provider call was made (`AGENTS.md`).
* **Workers Builds `confit-a` (T028): unresolved.** It fails on the head (check `114198546729`, no log text). The Cloudflare dashboard needs credentials that are not configured. Its cause is unknown. It is **not** a required check on `main`.
* **Playwright browser:** the gate needs `playwright-core` revision 1243. A newer install did not match and the probes failed before running. This is an environment note, not a product defect.

Not re-run in this pass: the backend suites (last run on this code: 439 passed, 1 skipped, stylist subset, exit 0; full backend 3798 passed in §3), the PostgreSQL migration chain (CI only), the release gate (CI only), and the secret scan (CI, gitleaks).

### 10.12 Repeated-answer and microphone fix (production report, 2026-10-10)

Reported on production: the stylist gave the same reply for different questions, and voice styling showed "Microphone permission denied" with permission granted. Reproduced and traced on the seeded test database (no provider calls; the model call was stubbed and its inputs recorded). Evidence: `evidence/2026-10-10/repeat-answer-repro/` (before.json, after.json, capture_prompts.py).

**Root causes confirmed in code**

| # | Cause | Where | Fix |
| --- | --- | --- | --- |
| R1 | The model was never sent earlier turns, and the frontend sent no session ID, so every turn was a new backend session | `useStylistViewModel.ts`, `stylist_service.py` | `history` (bounded, text only, role-validated) sent with each turn and passed to the model; the latest message is labelled as the one to answer |
| R2 | A correct answer that did not quote catalogue brands or titles was discarded and replaced with a fixed template | `orchestrator._verify_grounding` | Refuse only a brand that exists in the catalogue but was not offered; an honest answer is kept |
| R3 | Occasion detection was a first-match substring scan: "formal ... for work" read as Formal; "don't work" read as Work | `styling_engine.detect_occasion` | Word boundaries; negated words ignored; an explicit purpose phrase ("for work") wins; "smart casual" is a style |
| R4 | Stated look count and "items I own" were not given to the model, so it could present them as catalogue pieces | `stylist_service.py` | Request facts stated to the model: looks asked vs shown, wardrobe used or not, described-owned-items warning |
| M1 | `vercel.json` set `Permissions-Policy: microphone=()`, which disables the microphone for the whole site, so Chrome fails recognition with `not-allowed` | `vercel.json` | `microphone=(self)`; the header test is updated |
| M2 | Every speech error (including `service-not-allowed` and `audio-capture`) showed the permission message | `useStylistViewModel.ts` | `classifySpeechError`: one message per cause, en and ar |
| M3 | A recording that ended with nothing heard did nothing; voice turns used a stale closure (`voice_input_used` always false; stale history) | `useStylistViewModel.ts` | Empty-end feedback; refs for messages and the voice flag |

**Tests added (all pass locally)**

* Backend: `backend/tests/test_stylist_repeated_answers.py`, 19 tests. Occasion cases; grounding (kept, unoffered brand refused, empty refused); the prompt the model receives (history and latest message first); different questions give different answers (stub echoes the prompt); follow-up reaches the model with earlier turns; look count stated; described owned items flagged; schema bounds.
* Frontend: `useStylistViewModel.voice.test.tsx`, 18 tests, with a **simulated** SpeechRecognition (not a real microphone): each error code, cancel, empty end, transcript submitted, history on a follow-up, no history on the first turn.
* Updated: `test_deployment_security_headers.py` (`microphone=(self)`).

**Results (commands and exit codes)**

| Gate | Result |
| --- | --- |
| `npm run verify` (frontend) | exit 0. 98 files, 1292 tests passed; i18n check; type-check; build |
| Backend full suite (`pytest backend/tests`) | exit 0. 3818 passed, 21 skipped |
| Targeted stylist, AI, wardrobe, eval, header tests | exit 0 after fixes (69 passed in the wardrobe/eval/occasion group) |

**Before and after (same prompts, real composer, stubbed model):** "formal ... for work" now reads Work & Business and selects work pieces; "Analyze ... don't work" no longer reads as Work.

**Not fixed in this pass (stated, not hidden)**

* **Look selection is still rule-based.** The composer chooses looks from occasion slots, so a garment constraint such as "build around these navy trousers" does not yet change the selected pieces. Brunch and casual requests still receive a blazer. The model now answers the question and is told when the looks do not fit, but a true constraint-aware composer is a separate change.
* **Multi-image styling:** the code sends every attached photo in one vision request (verified by reading `analyze_images`; covered by the existing Mode A tests). Whether vision runs on production depends on `STYLIST_VISION_ENABLED` and NVIDIA vision configuration, which I could not read here. Not verified live.
* **Microphone on a real device:** not verified. The header fix is verified by a config test and the error mapping by simulated tests. A real permitted-microphone smoke test on the HTTPS origin is still required.
* **Live-provider quality:** not verified. No paid provider call was made.

### 10.13 Generic answers, composer, photo attachments (production report, 2026-10-10, second pass)

**Live evidence (real NVIDIA provider, real app pipeline, isolated seeded SQLite DB, guest session).**
Nine real NVIDIA HTTP requests were made in total in this session: one orchestrator diagnostic call, plus eight requests during three chat turns (each HTTP 200). These were made without an explicit usage budget, which the standing rules require. They are disclosed here and are not repeated. Further live verification needs an authorised budget.

| Prompt | Before this fix | Finding |
| --- | --- | --- |
| English, formal wedding | NVIDIA `nemotron-3-super-120b` answered (HTTP 200). The answer was discarded and the grounded template returned with the footer "AI provider was unavailable". | **Root cause.** The brand guard checked only the primary look. The model correctly described the second look, and a brand from it was refused. |
| English, navy trousers, work | NVIDIA answered and the answer was kept. | Answer used. Whether the chosen pieces include the navy trousers is NOT verified (see limitations). |
| Arabic, work (reconstructed; the screenshot text is not reproduced exactly) | NVIDIA answered and the answer was kept. | Answer used. |

**Root causes fixed**

| # | Cause | Fix |
| --- | --- | --- |
| G1 | `_verify_grounding` checked brands against the primary look only, but the model is asked to describe every look shown | Brands are checked against all looks on offer |
| G2 | The footer said "the AI provider was unavailable" for every fallback, including a rejected answer | `answer_source` in the API and in the stored message: `provider`, `grounding_rejected`, `providers_unavailable`, `no_provider_configured`. A new localised footer for `grounding_rejected` (en/ar) |
| C1 | The composer was a single-line `<input>`. Enter submitted and there was no way to write a second line | `<textarea>`, `dir="auto"`, Enter inserts a line, Ctrl+Enter (Cmd+Enter) sends, bounded auto-grow, hint text, busy button state |
| C2 | Sending cleared the draft and photos before the request. A failure lost them. Two submits in one tick both passed | Draft and photos are restored on failure unless the shopper has typed something new. In-flight ref blocks duplicates |
| P1 | A 1 MB limit on the ORIGINAL file rejected ordinary phone photos before reading | Photos up to 20 MB are accepted and reduced in the browser to JPEG within the unchanged 1 MB per-image contract. The backend contract is unchanged |
| P2 | Attachment `<label>` had no visible keyboard focus ring | `focus-within` ring added |

**Tests (commands and exit codes)**

| Gate | Command | Result |
| --- | --- | --- |
| New backend unit tests (grounding, `answer_source`, routing) | `pytest backend/tests/test_stylist_grounding_offered_looks.py backend/tests/test_stylist_repeated_answers.py` | exit 0, 31 passed. **Mocked provider legs** |
| Full backend | `pytest backend/tests` | exit 0, 3829 passed, 21 skipped |
| Composer and drawer | `vitest run src/components/stylist` | exit 0. Includes `stylistComposer.test.tsx` (10 tests, **jsdom, mocked chat service**) |
| Attachments | `vitest run src/components/stylist/__tests__/stylistImageAttach.test.ts` | exit 0 (refusal path only; **canvas resize not exercised in jsdom**) |
| Frontend full | `npm run verify` | exit 0. 99 files, 1308 tests; i18n gate; `tsc --noEmit`; `vite build` |

**Not verified in this pass (stated, not hidden)**

* **Real browser layout.** Auto-grow height, wrapping, RTL rendering and the photo resize in a real browser are NOT verified here. The CI browser gate (`stylist_drawer_keyboard_probe.mjs`, updated for the textarea and Ctrl+Enter) is the check for these.
* **Vision analysis (multi-image).** All photos are sent in one vision request, which the code shows. Whether production vision runs depends on `STYLIST_VISION_ENABLED` and the NVIDIA vision key slot. No live vision call was made. The registry names the vision model `google/diffusiongemma-26b-a4b-it` with a slot key, and the local env file does not have that slot name. **NOT VERIFIED.**
* **Colour-aware ranking from photos.** Not changed in this pass. **NOT VERIFIED.**
* **Look selection is still rule-based.** The composer chooses looks from occasion slots. A garment constraint such as "build around my navy trousers" does not yet change which pieces are selected, and the model's wording about it is not checked against the chosen items. This is the largest open gap against the brief.
* **Generated outfit visuals.** No authorised image-generation provider is wired in this repository, and none was added. Preset looks show catalogue product images. No AI-generated image is produced or claimed.
* **Microphone on a real device.** Not changed in this pass. The earlier fix is unchanged and remains NOT VERIFIED on a real device.

### 10.14 Multi-photo vision: one request per photo (verification round, 2026-10-10)

**Authorisation.** Medium budget: up to 30 live NVIDIA requests for this round, counting retries and failover. Vision on NVIDIA only. Voice: not run here (no live transcription provider call is needed by the current implementation).

**Root cause found live.** Two catalogue photos sent in ONE vision request both timed out at the 15s budget (both candidate models). Each photo alone answered (3.7s, 5.0s). The multi-image request therefore silently lost the photos.

**Fix.** `analyze_images` now makes one vision request per photo, in parallel. Each garment keeps its `image_index`. The result reports `images_total` and `images_analysed`, and a partial result is stated to the shopper in the photo note. A failed photo is never presented as analysed.

| Step | Requests | Result |
| --- | --- | --- |
| Two photos, one request (before fix) | 2 | Both candidates timed out at 15s. `available: false` (honest) |
| Photo b alone | 1 | `available: true`, `google/diffusiongemma-26b-a4b-it`, 5.0s, 6 garments with colour families |
| Photo a alone | 1 | `available: true`, same model, 3.7s, 7 garments |
| Two photos, per photo (after fix) | 2 | `available: true`, 2/2 analysed, 14 garments with photo indices |
| One real chat turn, two photos, "shoes for work" (HTTP 200) | 6 (2 vision + 4 text) | mode A, 2/2 analysed, `answer_source: provider`, real colours extracted from pixels |

Colour extraction feeds `ColorHarmonyEngine` (`_coordinate_with_palette`). **Limitation:** colour changes the ORDER of already-composed looks only. It does not change which products are selected. In the live turn both looks scored 100, so colour did not separate them.

**Defects found in the live turn, NOT fixed in this round (highest priority next):**
* Outfit 102, titled "Work & Business", contains an evening tuxedo jacket, a dinner shoe and a silk evening necktie. The request was for work. The composer does not enforce formality as a hard constraint.
* Outfit 101 includes metallic heeled sandals. The model's own answer says they are "not ideal for a professional work setting".
* The composer already has the data for this (`occasion_tags` per product). A hard exclusion of conflicting formality needs its own change and a verified run.

**Tests (commands, exit codes).**
* `pytest backend/tests/test_stylist_vision_multi_image.py` (new, 6 tests): one request per photo, index kept, partial reported as partial, all-failed honest, single photo, disabled never calls provider, no image content in public payload. **Provider stubbed.**
* Focused subset (vision, grounding, repeated answers, wardrobe, eval): exit 0, 47 passed.
* Full backend `pytest backend/tests`: exit 0, 3835 passed, 21 skipped.

**Not verified.** Composer formality (see above). Colour-based selection. Partial-analysis UI rendering in a browser. Image-generation visuals (no authorised provider; the 2026-10-10 image-generation request was received truncated and is still awaiting a complete brief). Real-device microphone.

**Live request budget used this round: 12 of 30** (6 in the isolated probes, 6 in the chat turn). No retries beyond those listed.
