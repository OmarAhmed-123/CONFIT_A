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
