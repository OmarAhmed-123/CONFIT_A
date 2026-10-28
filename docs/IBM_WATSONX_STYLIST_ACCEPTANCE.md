# IBM watsonx.ai Granite Wardrobe Stylist — Acceptance Checklist & Honest Report

Date: 2026-10-26 · Branch: `feat/watsonx-granite-stylist` (PR #387) · Author: OmarAhmed-123

> **Second pass (production verification), same day:** see
> `docs/IBM_WATSONX_PRODUCTION_VERIFICATION_REPORT.md` for the re-verified
> baseline, the new save/revisit journey (FR-21 below), the Granite Vision
> Deploy-on-Demand finding, database/a11y/load status and blockers.

Legend — **VERIFIED**: executed in this session with the evidence named.
**MOCKED**: behaviour proven by automated tests that stub the watsonx HTTP
layer (no network). **LIVE**: executed against the real watsonx.ai endpoint in
`eu-de`. **NOT VERIFIED**: implemented but not exercised; stated plainly.

## 1. Functional requirements

| FR | Requirement | Status | Evidence |
|---|---|---|---|
| FR-01 | Upload wardrobe photos (JPEG/PNG/WebP, ≤15 MB, server-side Pillow decode, MIME/extension cross-check, sha256 dedupe) | VERIFIED (pre-existing, re-tested) | `test_wardrobe*.py` 48 pass; live E2E: 4 fixture photos → `201 ready`; `.gif` → `422 Unsupported image type`; 16 MB → now `422` (fixed, see §4) |
| FR-02 | Vision analysis via watsonx.ai with structured output (description, category, subcategory, colors, pattern, material, style, occasion, details, confidence) | LIVE + MOCKED | `providers/watsonx/vision.py`; `test_watsonx_stylist.py::TestVisionProvider` (parse, fenced JSON, malformed, unknown category → null); live: blazer→`Outerwear/Suit Jacket` 0.95, oxfords→`Footwear/Oxford Shoes`, gown→`Dresses/Evening Gown` |
| FR-03 | Wardrobe records persist analysis provenance (`analysis_source`, `analysis_description`) | VERIFIED | Alembic `0047_wardrobe_analysis_source`; model/schema columns; live rows show `analysis_source=meta-llama/llama-4-maverick-17b-128e-instruct-fp8` |
| FR-04 | Honest handling when vision model cannot classify (no invented category) | MOCKED + LIVE | Synthetic drawing → `category=null`, item left for manual categorisation (smoke script); test `test_unknown_category_is_null_not_guessed` |
| FR-05 | User can correct category/metadata; correction wins over model; provenance updated | VERIFIED (API live + UI built) | `PATCH /wardrobe/items/{id}` → `analysis_source="manual (was <model>)"`; `WardrobeView.tsx` per-card `<select>` → `setCategory` (tsc clean, `wardrobeStylistPanel.test.tsx`); second live recommendation used the corrected category as the role |
| FR-06 | Occasion / time of day / season / location / preferences / comfort inputs | VERIFIED | `schemas/wardrobe_stylist.py::OutfitRecommendationRequest` (validated enums + length caps); panel form; live request with all fields → 200 |
| FR-07 | Granite reasoning via watsonx.ai with the versioned "CONFIT Stylist" system prompt | LIVE + MOCKED | `providers/watsonx/prompts.py` (`STYLIST_PROMPT_VERSION="wx-stylist-1.1"` since 2026-10-28 — honesty-first + no-unsupported-attribute rules added, see docs/qa/WARDROBE_STYLIST_QUALITY_REPORT.md §7); response carries `prompt_version`; live `model_id=ibm/granite-4-h-small`, 2.3 s |
| FR-08 | Structured recommendation contract (`outfit_id`, `occasion`, `title`, `summary`, `items[{wardrobe_item_id, category, role, title, filename, reason}]`, `styling_notes`, `limitations`, `missing_categories`, `source`, `ai_generated`, `model_id`, `prompt_version`, `is_complete`) | VERIFIED | `schemas/wardrobe_stylist.py::OutfitRecommendationResponse`; FE types in `models/index.ts`; live payload printed in E2E run |
| FR-09 | Every model item reference validated against the caller's real wardrobe by **id** (no filename substring matching) | MOCKED + LIVE | `wardrobe_stylist_service._validate_items`: unknown ids / other users' ids / duplicates dropped and counted in `rejected_references`; tests Scenario D (`test_hallucinated_ids_rejected`, `test_cross_user_ids_rejected`, `test_duplicate_ids_collapsed`); live `rejected: []` |
| FR-10 | Role derived from stored category, not from the model's claim | LIVE | Log `wardrobe_stylist_role_corrected claimed=bottoms real=bottom`, `claimed=dress real=outerwear` (after user correction) |
| FR-11 | Missing categories reported, never fabricated | LIVE + MOCKED | Live: closet with no tops → `missing_categories=["Tops"]`, `is_complete=false`, limitation sentence; Scenario C test |
| FR-12 | Malformed / non-JSON / schema-violating model output handled honestly | MOCKED | `TestStylistService::test_malformed_json_*` → `502 PROVIDER_ERROR watsonx_stylist_malformed_output` in `watsonx` mode, labelled fallback in `auto` mode |
| FR-13 | Timeouts, 429, 5xx, 404 `model_not_supported`, IAM failure mapped to distinct error codes with retry/backoff | MOCKED + LIVE(404) | `client.py` (`WatsonxError.code`); tests Scenario F/G; live probe of `ibm/granite-vision-3-2-2b` reproduced the 404 body and the mapped error |
| FR-14 | Missing credentials → explicit `501 FEATURE_NOT_CONFIGURED` (strict mode) or labelled deterministic fallback (`auto`) — never a silent provider swap | MOCKED | Scenario E tests; `GET /wardrobe/stylist/status.watsonx_configured` |
| FR-15 | Model ids and region are configuration, never hard-coded in call sites | VERIFIED | `core/config.py` `WATSONX_*`; grep shows ids only in config defaults, docs, tests |
| FR-16 | Rate limiting on the recommendation endpoint | VERIFIED | `@limiter.limit("40/hour")` on `POST /wardrobe/outfit-recommendation`; `test_rate_limit_header_present` |
| FR-17 | Credentials never logged, returned, or shipped to the browser | VERIFIED | Status endpoint returns only booleans/model ids; client logs redact key to last-4; `frontend/dist` grep for `WATSONX` → 0 hits (after `vite build`) |
| FR-18 | Mock/fallback output is never labelled as Granite inference | VERIFIED | `source="deterministic_fallback"`, `ai_generated=false`, `fallback_reason`; UI badge "Rule-based match — not AI"; `test_fallback_is_labelled`; FE test `shows the not-AI badge for fallback` |
| FR-19 | Professional editorial UI in the existing React/Tailwind framework, bilingual EN/AR, accessible | VERIFIED | `WardrobeStylistPanel.tsx`; `wardrobe_stylist` namespace in `en.json`/`ar.json` (`npm run i18n:check` 0 missing); axe 0 violations EN & AR (`wardrobeStylistPanel.test.tsx` 7/7); `motion-safe:` spinner gate (`statusIconRepass.test.tsx` 8/8) |
| FR-20 | Documentation: README section, `.env.example` placeholders, audit, acceptance, troubleshooting | VERIFIED | `README.md` § "IBM watsonx.ai wardrobe stylist"; `backend/.env.example` §4b; root `.env.example`; `docs/IBM_WATSONX_STYLIST_AUDIT.md`; this file |
| FR-21 | Save a recommended look and revisit it (ids re-validated against the caller's wardrobe at save time; roles from stored categories; provenance kept; binned garments omitted and counted; cross-user 404) | VERIFIED (unit) + LIVE (browser EN/AR, Orca EN) | `0048_wardrobe_outfits`; `wardrobe_outfit_service.py`; `test_wardrobe_saved_outfits.py` 7/7; `savedWardrobeLooks.test.tsx` 5/5; `docs/qa/stylist_a11y_report.json`, `stylist_orca_report.json` |

## 2. Scenario matrix

| Scenario | Description | How exercised | Result |
|---|---|---|---|
| A | Happy path: upload 4 garments → analysis → occasion form → outfit | LIVE (uvicorn + real watsonx) via API **and** via the real UI in headless Chromium (`docs/qa/watsonx_stylist_result_en.png`, 0 console errors) | PASS — "Business Professional Look", 3 items with reasons + photos, honest `missing=["Tops"]`, provenance footer |
| B | Invalid uploads (unsupported type, empty, oversized, undecodable) | LIVE + new unit test | PASS — 422 with precise message; new `test_wardrobe_upload_safety_order.py` 5/5 |
| C | Sparse wardrobe (e.g. only footwear) | MOCKED | PASS — `is_complete=false`, `missing_categories` lists absent roles, no invented items |
| D | Model hallucinates ids / references another user's items / duplicates | MOCKED | PASS — dropped, `rejected_references` counted, log line emitted |
| E | No credentials | MOCKED | PASS — `auto` → labelled fallback; `watsonx` → 501 with hint naming `WATSONX_APIKEY` |
| F | Model removed in region (404 `model_not_supported`) | MOCKED + LIVE probe | PASS — `watsonx_model_not_supported` 502, no retry storm |
| G | Timeout / 429 / 5xx | MOCKED | PASS — bounded retries with backoff, then `watsonx_timeout` / `watsonx_rate_limited` / `watsonx_upstream_error` |
| H | User corrects a category, re-requests with exclusions (`previous_item_ids`) | LIVE | PASS — corrected category drives role; excluded ids not reused |
| I | Arabic locale + RTL rendering + screen-reader semantics | Vitest (jsdom, axe, `dir="rtl"`) + headless Chromium screenshot `docs/qa/watsonx_stylist_result_ar.png` | PASS — RTL chrome verified in a real browser render; request now carries `language: "ar"` so Granite writes prose in Arabic (model-authored text is `dir="auto"`); **no screen-reader pass** |
| J | Provenance in UI (which model analysed each item; fallback badge) | Vitest + live API | PASS — card shows `analysis_source`; badge test |
| K (2026-10-27) | Excluded colours: model returns a black top/shoes against "no black" (EN explicit list, EN negated free text, AR `بدون أسود`); fallback with banned colours; unknown/injected strings in the colour fields | MOCKED | PASS — offending items dropped server-side, limitation names colour + count, `is_complete` honest, prompt carries preferred and avoided colours, system prompt unchanged, unknown words never map to a ban. `test_stylist_colour_constraints_eval.py` 23/23. **Before this change the exclusion was prompt-only and a non-compliant model answer would have been shown as-is.** Live Granite compliance with the instruction: NOT RE-VERIFIED this pass (no live run) |
| L (2026-10-27) | Requested outfit count ("three distinct outfits") | Contract review | **NOT IMPLEMENTED** — single outfit per request; `count` rejected with 422; alternatives via `previous_item_ids` |

## 3. Quality gates

| Gate | Command | Result |
|---|---|---|
| Backend focused suites | `PYTHONPATH=. pytest backend/tests/test_watsonx_stylist.py backend/tests/test_wardrobe*.py backend/tests/test_wardrobe_upload_safety_order.py` | 34 + 48 + 5 → all pass |
| Backend full suite | `PYTHONPATH=. pytest backend/tests --ignore=backend/tests/test_vton_integrity.py` | **4,561 passed, 0 failed, 25 skipped** |
| Lint (new/changed Python) | `ruff check --select E9,F …` | 0 errors (4 unused imports fixed) |
| Runtime import closure | `python backend/scripts/check_runtime_imports.py` | OK for Vercel and Docker manifests (no new dependency — stdlib + httpx) |
| Frontend | `cd frontend && npm run verify` (i18n:check + tsc + vitest + vite build) | **156 files / 2,352 tests passed**, build OK |
| Live smoke | `PYTHONPATH=. python scripts/watsonx_smoke.py` | 4/4 PASS (IAM, reasoning, vision, stylist round-trip) |
| Live journey | uvicorn :8000 + scripted client (register → upload ×4 → status → recommend → PATCH → recommend) | PASS, transcript in implementation summary |

### 3.1 Re-validation 2026-10-26 (production-readiness pass)

| Gate | Result |
|---|---|
| Backend focused (`-k "watsonx or stylist or outfit or alembic or migration"`) | 510 passed, 2 skipped |
| Backend full suite | see `IBM_WATSONX_PRODUCTION_VERIFICATION_REPORT.md` §0.6 |
| Frontend `npm run verify` | 157 files / 2,361 tests, tsc, i18n gate, build — green |
| Alembic chain on PostgreSQL 16 (up → 0046 → up) + FK/index inspection | PASS |
| 20-VU mocked load on PostgreSQL / 2 workers | PASS (p95 1.69 s, p99 2.01 s, 0 errors, 400/400 Granite-labelled) |
| Live bounded probe (8 Granite calls) on the same rig | PASS (8/8 `ibm/granite-4-h-small`, p95 6.10 s) |
| Negative battery over HTTP on PostgreSQL (21 checks) | 20 PASS + 1 defect found (forgeable `model_id`) → fixed, see §4 item 6 |

## 4. Defects found and fixed along the way

1. **Upload size check ran after the content-safety model call.** With the
   NVIDIA classifier configured, a 16 MB file produced `503 safety screening
   unavailable` instead of `422 Image exceeds the 15MB size limit`.
   `_require_safe_image` now runs `WardrobeService._validate_image` first.
   Regression test: `backend/tests/test_wardrobe_upload_safety_order.py`.
2. **`animate-spin` without `motion-safe:` and buttons without `data-motion`
   intents in the new panel** — caught by the repo's own `statusIconRepass`
   and `buttonMotion.contract` gates; fixed (intents chosen by hand:
   `creative`, `filter`, `upload`, `recovery`, `auth`).
3. **Duplicate missing-category sentence** in the UI (API limitation + UI
   callout said the same thing); the panel now filters the server sentence.
4. **Arabic UI received English prose** — added `language` to the request
   contract; the prompt asks for Arabic prose while keeping JSON keys,
   category names and ids English.
5. **(2026-10-26 re-validation) API hung forever on a fresh PostgreSQL
   database** — the lifespan held the catalogue-probe session open while
   `seed_database()` ran `drop_all()` on a second connection (lock wait that
   PostgreSQL cannot flag as a deadlock). Probe now closes before seeding.
   Regression test: `backend/tests/test_startup_seed_no_open_session.py`.
   Production unaffected (never seeds); any Postgres staging first boot was.
6. **(2026-10-26 re-validation) A saved look could claim any `model_id`
   under `source=watsonx`** (`gpt-4o` was persisted on the Postgres rig and
   would have been badged as Granite). `WardrobeOutfitService.save` now
   accepts only the configured reasoning model / deployment id (422
   otherwise). Test: `test_watsonx_look_cannot_claim_a_foreign_model_id`.

## 5. Not verified / known limitations (read this)

* **Granite Vision was not used.** `ibm/granite-vision-3-2-2b` (the tutorial's
  model) returns `404 model_not_supported` in both `eu-de` and `us-south`;
  IBM removed it in watsonx.ai 2.4. No `granite-vision-*` model was listed in
  the project's region on 2026-10-26, so the configured vision default is
  `meta-llama/llama-4-maverick-17b-128e-instruct-fp8`. This is **labelled**
  everywhere (`analysis_source`, status endpoint, README). The reasoning step
  **is** Granite (`ibm/granite-4-h-small`, the IBM-named successor of the
  withdrawn `granite-3-2-8b-instruct`). Swapping to a Granite vision model is
  a one-line env change when IBM serves one in the region.
* **Migration `0047` has not been applied to the Neon staging/production
  databases.** It was exercised on the local dev schema only. The startup
  schema gate expects head `0047`; run `alembic upgrade head` against each
  target before deploying this code. Not done because deployment work was out
  of scope for this brief.
* **No screen-reader pass** on the new panel (jsdom + axe + headless Chromium
  screenshots only; no NVDA/VoiceOver/Orca run).
* **Scenario I (Arabic copy quality)** — strings were authored, i18n parity
  gate passes, but no native-speaker review.
* **Latency under load** not measured; single-user numbers only
  (vision 1.5–2.6 s/image, reasoning 2.3–2.8 s).
* Coverage percentages were **not** computed; none are claimed.

## Addendum 2026-10-28 — explanation/outfit consistency (D10, D11, D12)

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| FR-21 | After server-side filtering, summary / limitations / notes / reasons must not describe removed garments; emptied positions are explained | VERIFIED (mocked, from real captured outputs) + LIVE re-eval | `wardrobe_stylist_service.py::_reconcile`, `_mentions_any` (EN + Arabic clitic-aware tokens); tests `test_stylist_explanation_consistency.py::test_d10_*`; live S10/S13 2026-10-28 |
| FR-22 | Server-computed `fit_status` ∈ {suitable, partial, unsuitable}; unsuitable ⇒ insufficiency statement first, honest summary, no fabricated performance claims; UI badge EN/AR | VERIFIED (mocked) + LIVE S16 | schema `OutfitRecommendation.fit_status`; `_fit_status`, `_UNSUPPORTED_CLAIM_RE`; `WardrobeStylistPanel.tsx` badge; i18n `fit_partial`/`fit_unsuitable`; tests `test_d11_*` |
| FR-23 | Model id/description mix-ups that empty a core position are disclosed | VERIFIED (mocked) | `role_collision` limitation; `test_d12_role_collision_is_explained`; live S01 2026-10-28 |
| NFR | Fabricated-attribute detection | PARTIAL — keyword heuristic only (`H10` in eval harness); human confirmation required | `scripts/eval/wardrobe_stylist_quality_eval.py` |


## Addendum 2026-10-28 (second session) — D12 + classified requirements matrix

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| FR-24 | Empty core positions after validation are completed deterministically with an eligible wardrobe item, labelled `selected_by="rule_matcher"` and disclosed; impossible completion ⇒ explicit incomplete | VERIFIED (mocked) + LIVE (S03/S09/S14) | `_complete_core_positions`, `_rule_score`; tests `test_d12_*` (5); UI badge test |
| FR-25 | A reason describing a different garment than the cited id is never shown next to that item | VERIFIED (mocked) + LIVE (S09) | `_validate_selection` mismatch branch, `reason_mismatch` limitation |
| FR-26 | Arabic prose contains no English occasion enum values | VERIFIED (deterministic eval S12/S14) | `_OCCASION_AR`, `_occasion_label` |

### Requirements matrix (classification per master prompt §3)
| Requirement | Classification | Current state | Evidence | Action | Acceptance test |
|---|---|---|---|---|---|
| watsonx text inference with a verified supported model | Required | Implemented + tested (live) | 70 live calls 10-27/28, served `ibm/granite-4-h-small` | none | `test_watsonx_stylist.py`, live eval H6=0 |
| Wardrobe-grounded recommendations with stable ids | Required | Implemented + tested | H1/H8 = 0 across all runs | none | eval H1/H8; scenario G test |
| Server-side hard-constraint enforcement | Required | Implemented + tested | H3 = 0; 3 model breaches caught | none | `test_stylist_colour_constraints_eval.py` |
| ID ↔ description ↔ category ↔ image mapping | Required | Implemented + tested (D12) | FR-24/25 | none | `test_d12_*`, H8 |
| Honest unsuitable/insufficient wardrobes | Required | Implemented + tested (D11) | FR-22; live S16 | none | `test_d11_*`, H12 |
| Consistent summary/reasons/limitations/outfit | Required | Implemented + tested (D10) | FR-21; H11 = 0 | none | `test_d10_*` |
| EN + AR behaviour | Required | Implemented; **native review pending** | H5 = 0; Arabic sheet | native reviewer | sheet decisions |
| Regression tests D10/D11/D12 | Required | Implemented | 13 tests in `test_stylist_explanation_consistency.py` | none | CI backend |
| CI + security checks | Required | Implemented | gitleaks ✓, app jobs ✓ on HEAD | none | CI |
| Production-safe migrations | Required | CI-validated chain; **remote not executed** | migration gate ✓; Neon quota-locked | account owner | staging alembic upgrade + smoke |
| Error handling + rule-based fallback labelled | Required | Implemented + tested | `source=deterministic_fallback`, `ai_generated=false` | none | scenario J test |
| Evidence-backed quality evaluation | Required | Implemented (automated + assistant); **human pending** | eval JSONs, report §7–8 | fashion reviewer | review sheet |
| Deployment + DB blockers resolved | Required for production | **Blocked** (Neon quota, Vercel 402, Cloudflare build) | probes 2026-10-28 09:14Z | account owner | /health 200; DSN connects |
| Approved thresholds | Required for production | **Pending product owner** | report §4/§8 | product owner | sign-off recorded |
| Human fashion + Arabic review | Required for production | **Pending / blocked** | both sheets | reviewers | approval status set |
| PostgreSQL benchmark vs targets | Required for production | **Blocked** (no PG rig; historical p99 11.5 s) | `docs/qa/LOAD_TEST_STYLIST.md` | eng + infra | p95 ≤ 6.5 / p99 ≤ 8 or documented gap |
| Manual AT testing | Required for production | **Blocked** (no NVDA/VoiceOver platform) | `docs/qa/STYLIST_A11Y_REPORT.md` | QA | documented runs |
| Staging smoke + release gate | Required for production | **Blocked** (gate INDETERMINATE: prod /health 402) | CI log | account owner | gate exit 0 |
| Rollback / incident plan | Required for production | Partially documented | `docs/qa/MIGRATION_0047_0048_CHECKLIST.md` | eng | reviewed runbook |
| Image-based wardrobe recognition (Granite Vision) | Conditional | **Blocked** — no Granite vision model in any of 6 watsonx regions (2026-10-28); non-Granite `llama-4-maverick` configured but inactive | `docs/GRANITE_VISION_AVAILABILITY_INVESTIGATION.md` | product owner decision | real-image classification tests |
| Virtual try-on, e-commerce recs, chat follow-ups, body-shape personalisation | Optional / future | Not implemented | — | product owner | — |
