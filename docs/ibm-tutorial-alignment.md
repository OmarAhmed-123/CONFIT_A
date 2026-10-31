# IBM tutorial alignment — traceability matrix

Reference: IBM Think tutorial *"Build an AI stylist with Granite, Python and
watsonx.ai"* (fetched 2026-07-20 / re-checked 2026-10-28). This matrix maps each
tutorial step to what CONFIT implements, where, how it is verified, and where CONFIT
deliberately departs. Deep detail lives in `IBM_WATSONX_STYLIST_IMPLEMENTATION.md`
(what/why) and `IBM_WATSONX_STYLIST_ACCEPTANCE.md` (requirements + evidence); this
file is the one-page index.

Legend — **VERIFIED**: automated test or recorded live run exists · **PARTIAL** ·
**DEPARTURE**: intentional, documented · **BLOCKED**: not achievable with the
current IBM account / platform (evidence cited).

| # | Tutorial step | CONFIT implementation | Verification | Status |
|---|---|---|---|---|
| T1 | watsonx.ai project + Runtime association + API key | `WATSONX_APIKEY`, `WATSONX_PROJECT_ID`, `WATSONX_URL` in `backend/app/core/config.py`; IAM exchange with expiry cache in `backend/app/providers/watsonx/client.py` | `backend/tests/test_watsonx_stylist.py` (IAM, 401 → `auth_failed`); live calls 2026-10-28 eu-de (`docs/qa/eval/wardrobe_stylist_eval_live_20261028.json`) | VERIFIED |
| T2 | `ibm-watsonx-ai` SDK `ModelInference(...).chat()` | Thin `httpx` client calling `POST /ml/v1/text/chat` directly — same wire payload (`messages`, `max_tokens`, `temperature`), no SDK so the Vercel/Docker import-closure gate stays green; handles the documented 404 `model_not_supported` body | client unit tests; `test_watsonx_stylist.py::*model_not_supported*` | DEPARTURE (equivalent, documented) |
| T3 | Vision: Granite Vision (`granite-vision-3-2-2b`) describes each closet photo (`image_url` data-URL, `temperature 0`) | `backend/app/providers/watsonx/vision.py` — same request shape; model id is configurable (`WATSONX_VISION_MODEL_ID`). **Granite Vision returns 404 in all 6 multitenant regions on this account (deploy-on-demand only); `granite-vision-3-2-2b` was withdrawn by IBM.** Current default is `meta-llama/llama-4-maverick-17b-128e-instruct-fp8`, labelled as such in `analysis_source`; manual entry always available | `docs/GRANITE_VISION_AVAILABILITY_INVESTIGATION.md`; `docs/vision-integration-decision.md`; vision parser tests | BLOCKED for Granite Vision; alternative VERIFIED and labelled |
| T4 | Structured closet descriptions persisted (list of items) | `wardrobe_items` table (Alembic 0047/0048), `analysis_source`, `analysis_description`, taxonomy normalisation (`wardrobe_taxonomy.py`) | `test_wardrobe*`; migration checklist `docs/qa/MIGRATION_0047_0048_CHECKLIST.md`; clean PG17 up/down 2026-10-29 | VERIFIED |
| T5 | Reasoning model Granite instruct with `{"role":"control","content":"thinking"}` + closet list + occasion/time_of_day/location/season | `ibm/granite-4-h-small` (tutorial's 3.x instruct models withdrawn 22 Feb 2026 — IBM lifecycle page). Prompt `wx-stylist-1.1` (`prompts.py`) sends the **id-tagged** closet, occasion, time of day, season, location, activity, preferences/exclusions; JSON response mode; `temperature 0.2`. The `control/thinking` turn is **not** sent: granite-4-h-small answers in strict JSON without it and the hidden reasoning would not be shown to users anyway | 16-scenario deterministic + live eval (`scripts/eval/wardrobe_stylist_quality_eval.py`); `test_stylist_*` | VERIFIED with documented DEPARTURE |
| T6 | Match model output to closet items by **filename substring** | Replaced by **id validation**: the model must cite `wardrobe_item_id`s from the prompt; unknown ids are rejected (`rejected_references`), never fuzzy-matched | `test_watsonx_stylist.py::*invented*`; eval "invented ids 0/16" | DEPARTURE (hardening) |
| T7 | Return outfit text to the user | Structured `OutfitRecommendation` (items with role/reason/`selected_by`, summary, styling notes, limitations, `fit_status`, `is_complete`, `missing_categories`, provenance `source`/`model_id`/`prompt_version`/`ai_generated`) rendered in `WardrobeStylistPanel.tsx`, EN + AR | 76 backend tests (stylist suites), 901 vitest, browser E2E 2026-10-29 | VERIFIED |
| T8 | Occasion/time/location/season context | Full request schema `OutfitRecommendationRequest` (season literal-validated → 422 on bad value, verified 2026-10-29) | schema tests; API probe | VERIFIED |
| T9 | (tutorial has none) Fallback when model unavailable | Labelled deterministic matcher (`source=deterministic_fallback`, `ai_generated=false`, `selected_by=rule_matcher` on every item — D13 fix 2026-10-29); strict mode fails instead | `test_d11_*`, `test_d13_*` | VERIFIED (CONFIT addition) |
| T10 | (tutorial has none) Core-position completion when the model leaves a slot empty | D12: rule-completed pieces tagged `selected_by=rule_matcher`, disclosed in `limitations` EN/AR and with the UI badge "Added by rules / أُضيفت وفق القواعد" | `test_d12_*`; live eval 3 rule-completed, all disclosed | VERIFIED |
| T11 | (tutorial has none) Colour exclusions respected server-side | Banned-family filter before and after the model; prose rewritten when items dropped (D10) | `test_stylist_colour_constraints_eval.py`, `test_d10_*`; cumulative model colour compliance 67/70 | VERIFIED |
| T12 | (tutorial has none) Persist chosen look | `POST /wardrobe/outfits`, provenance cannot be forged at save time | `test_watsonx_look_cannot_claim_a_foreign_model_id`; browser save verified EN/AR | VERIFIED |

## Deliberate departures, in one place

1. **No SDK** (T2) — same REST contract, smaller import closure, explicit error taxonomy.
2. **Model ids** (T3, T5) — tutorial models are withdrawn/unavailable; ids are
   configuration, defaults are the currently served Granite reasoning model and a
   labelled non-Granite vision model. A fixture is never presented as Granite.
3. **Id validation instead of filename matching** (T6) — eliminates the
   description/item mix-ups the tutorial's approach allows (our D12 class of defects).
4. **No `thinking` control turn** (T5) — see row; revisit if a Granite model that
   needs it becomes the default.

## Open items relative to the tutorial

* Granite Vision path exists in code but is **unverified live** on this account
  (BLOCKED, not a code gap). Decision record: `docs/vision-integration-decision.md`.
* Human fashion-expert and native-Arabic reviews of model output are **pending**
  (`docs/fashion-expert-review.md`, `docs/qa/ARABIC_REVIEW_SHEET_STYLIST.md`).
