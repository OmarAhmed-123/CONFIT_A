# IBM watsonx.ai Granite Wardrobe Stylist — Implementation Summary

Date: 2026-10-26 · Companion documents: `IBM_WATSONX_STYLIST_AUDIT.md`
(gap analysis G1–G7, written before coding) and
`IBM_WATSONX_STYLIST_ACCEPTANCE.md` (FR/scenario → evidence, honest report).

## What was built (and what was deliberately kept)

The brief was to bring IBM's "Build an AI stylist with Granite" tutorial into
CONFIT **without replacing** the existing wardrobe pipeline. The pre-existing
upload/validation/storage/dedupe path, the Gemini → NVIDIA → Qwen vision chain,
the deterministic outfit scorer, the React + Tailwind + i18next frontend and
the MVVM layout are all untouched in behaviour; watsonx is added as a new
provider in front of them and as a new reasoning service beside them.

### Backend (FastAPI)

| Area | File | Notes |
|---|---|---|
| Config | `backend/app/core/config.py` | `WATSONX_APIKEY`, `WATSONX_PROJECT_ID`, `WATSONX_URL` (default `https://us-south.ml.cloud.ibm.com`), `WATSONX_VISION_MODEL_ID`, `WATSONX_REASONING_MODEL_ID`, `WATSONX_API_VERSION`, `WATSONX_TIMEOUT_SECONDS`, `WATSONX_MAX_RETRIES`, `WARDROBE_VISION_PROVIDER` (`auto|watsonx|legacy`), `WARDROBE_STYLIST_PROVIDER` (`auto|watsonx|deterministic`). Helper `watsonx_configured`. |
| HTTP client | `backend/app/providers/watsonx/client.py` | Stdlib + `httpx` (already a dependency — no SDK added, so the Vercel/Docker import-closure gate stays green). IAM token exchange with expiry cache, `POST /ml/v1/text/chat`, retries with jittered backoff on 429/5xx/timeouts, `WatsonxError(code=…)` for `auth_failed`, `model_not_supported` (parses the `{"errors":[{"code":"model_not_supported"}]}` 404 body), `rate_limited`, `timeout`, `upstream_error`, `malformed_output`. Surfaces `system.warnings` (model deprecation notices) in logs. Key redacted to last-4 in every log line. |
| Prompts | `backend/app/providers/watsonx/prompts.py` | `STYLIST_SYSTEM_PROMPT` ("CONFIT Stylist", verbatim from the brief), `STYLIST_PROMPT_VERSION = "wx-stylist-1.1"` (1.0 at first commit; bumped 2026-10-28 with the colour-constraint and completion wording), vision prompt + JSON schema text, user-message builder that serialises only garment descriptors. |
| Vision provider | `backend/app/providers/watsonx/vision.py` | Downscales to ≤1024 px JPEG, base64 data-URL, `temperature=0`, strict JSON parse (tolerates fenced blocks), taxonomy normaliser mapping free-text categories onto CONFIT's six categories — unknown → `null`, never guessed. |
| Wardrobe service | `backend/app/services/wardrobe_service.py` | Provider chain honours `WARDROBE_VISION_PROVIDER`; persists `analysis_source` (model id, `manual (was …)` after user edit, `deterministic` for the no-model path) and `analysis_description`. |
| Stylist service | `backend/app/services/wardrobe_stylist_service.py` | Loads the caller's `ready` items, builds the closet descriptor list, calls Granite, parses JSON, **validates each `wardrobe_item_id` against the caller's rows** (rejects unknown / foreign / duplicate ids and counts them), derives `role` from the stored category (logging `wardrobe_stylist_role_corrected` when the model disagrees), computes `missing_categories` / `is_complete`, and only in `auto` mode falls back to the deterministic scorer with `source="deterministic_fallback"`, `ai_generated=false`, `fallback_reason`. |
| Schemas | `backend/app/schemas/wardrobe_stylist.py`, `schemas/wardrobe.py` | Request (occasion, time_of_day, season, location, activity, dress_code, style/colour preferences, comfort_needs, exclusions, excluded_item_ids, previous_item_ids, `language` en/ar) and response contract; new optional wardrobe-item fields. |
| API | `backend/app/controllers/wardrobe_controller.py` | `POST /api/v1/wardrobe/outfit-recommendation` (auth, `40/hour`), `GET /api/v1/wardrobe/stylist/status`. Also fixed pre-existing ordering bug in `_require_safe_image` (deterministic validation now precedes the safety model call). |
| Migration | `backend/alembic/versions/0047_wardrobe_analysis_source.py` | Adds `wardrobe_items.analysis_source` (varchar 128) and `analysis_description` (text), both nullable; downgrade drops them. Local upgrade/downgrade exercised; **not applied to Neon** (see acceptance §5). |
| Tests | `backend/tests/test_watsonx_stylist.py` (34), `backend/tests/test_wardrobe_upload_safety_order.py` (5) | Mocked HTTP via `httpx.MockTransport`; IAM URL pointed at `iam.invalid` by an autouse fixture so no test can reach the network. |
| Operator smoke | `scripts/watsonx_smoke.py` | Live: IAM → reasoning → vision (on a provided photo or a synthetic swatch) → stylist round-trip; prints PASS/FAIL per stage and the model's actual output. |

### Frontend (React 18 + TypeScript + Tailwind + i18next)

| Area | File | Notes |
|---|---|---|
| Types + API | `src/models/index.ts`, `src/services/apiServices.ts` | `OutfitRecommendationRequest/Response`, `StylistStatus`; `recommendOutfit()`, `getStylistStatus()`. |
| Panel | `src/components/wardrobe/WardrobeStylistPanel.tsx` | Editorial layout: context form (occasion, time of day, season, location, preferences chips, comfort notes), readiness strip from `/stylist/status` (which categories are present, which model will answer, or "not configured"), result as a lookbook — hero summary, one card per garment with its photo (resolved from trusted wardrobe rows, never from the model), the model's reason, styling notes, limitations, missing-category callouts, provenance footer (`model_id`, `prompt_version`), and the "Rule-based match — not AI" badge when `source !== "watsonx"`. "Try another combination" re-requests with `previous_item_ids`. `aria-live` status region, labelled controls, focus management, `motion-safe:` animation. |
| Wardrobe view | `src/views/consumer/WardrobeView.tsx` | New "AI Stylist" tab; per-card provenance line (`analysis_source` + model description); per-card category `<select>` for user correction (FR-05). |
| View-model | `src/viewmodels/useWardrobeViewModel.ts` | `setCategory(itemId, category)` → `PATCH /wardrobe/items/{id}` with optimistic update + revert on failure. |
| i18n | `src/i18n/en.json`, `src/i18n/ar.json` | `wardrobe_stylist.*` namespace, full EN/AR parity (`npm run i18n:check`). |
| Tests | `src/components/wardrobe/__tests__/wardrobeStylistPanel.test.tsx` (7) | Form submit payload, loading/empty/error states, fallback badge, missing-category callout, axe 0 violations in EN and AR/RTL. |

### Documentation

`README.md` (new section + feature-status row), `backend/.env.example` §4b and
root `.env.example` (placeholders only), the three `docs/IBM_WATSONX_STYLIST_*`
files, `docs/STATUS_MATRIX.md` row.

## Design decisions worth knowing

1. **Model ids are data.** The tutorial's `ibm/granite-vision-3-2-2b` and
   `ibm/granite-3-2-8b-instruct` are respectively removed and withdrawn in
   watsonx.ai (verified live: 404 `model_not_supported`; IBM lifecycle table).
   Defaults are therefore the models IBM currently serves in the project's
   region — `ibm/granite-4-h-small` for reasoning (Granite) and, because no
   Granite vision model is served multitenant in `eu-de`/`us-south` today,
   `meta-llama/llama-4-maverick-17b-128e-instruct-fp8` for vision. The actual
   answering model is recorded on every item and every outfit; nothing is
   presented as Granite that is not.
2. **No new dependency.** `ibm-watsonx-ai` pulls a large tree (pandas, etc.)
   that would break the serverless import-closure gate; the REST surface the
   tutorial uses is two endpoints, so a 200-line `httpx` client is used.
3. **Validation by id, not by filename.** The tutorial matches the model's
   free-text answer against filenames by substring; here the model must return
   `wardrobe_item_id` integers that exist in the caller's own rows. Anything
   else is dropped and counted — this is the single most important
   correctness property of the feature.
4. **Three provider modes, one honest default.** `auto` gives the best
   available answer and labels it; `watsonx` is strict (errors instead of
   fallbacks, for demos/acceptance); `deterministic` disables model calls.
5. **Privacy.** The reasoning model receives only ids, category, colour,
   pattern, tags and the one-line description — no photos, URLs or user data.

## Final gate (recorded at commit time, 2026-10-26)

| Gate | Result |
|---|---|
| Backend `pytest backend/tests --ignore=backend/tests/test_vton_integrity.py` | **4,561 passed, 0 failed, 25 skipped** (11 min 15 s) |
| Frontend `npm run verify` (i18n:check → tsc → vitest → vite build) | **156 files / 2,352 tests passed**, build OK |
| `ruff check --select E9,F` on new/changed Python | 0 |
| `backend/scripts/check_runtime_imports.py` | OK (Vercel + Docker) |
| Live smoke `scripts/watsonx_smoke.py` (eu-de) | 4/4 PASS |
| Live UI journey (headless Chromium, EN + AR) | PASS, 0 console errors — screenshots in `docs/qa/watsonx_stylist_*.png` |

`test_vton_integrity.py` was excluded because it requires the GPU worker
fixtures unrelated to this work; it was not run and no claim is made about it.

Known cosmetic limits after the final run: item titles inside the Arabic
lookbook are the stored English vision labels (not translated); Granite's
Arabic prose has not had native-speaker review.
