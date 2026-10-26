# CONFIT × IBM watsonx.ai — Technical Audit & Gap Analysis

Date: 2026-10-26 · Reference: [IBM tutorial — Build an AI stylist with Granite](https://www.ibm.com/think/tutorials/build-ai-stylist-with-granite-python-watsonx-ai)

## 1. What the repository already is

CONFIT_A is **not** the tutorial's Streamlit notebook. It is a mature platform
(375+ merged PRs): FastAPI backend (`backend/app`, MVC, 181 modules, 258 test
files), React 18 + TypeScript frontend (`frontend/src`, MVVM, EN/AR i18n, WCAG
2.2 AA audited), Alembic migrations (0001–0046), Modal GPU workers, Vercel +
Neon production. Framework migration is therefore **not** justified; the
tutorial's architecture is mapped onto the existing modules.

### Existing wardrobe pipeline (verified by reading the code)

| Tutorial stage | Existing implementation | State |
|---|---|---|
| Upload wardrobe photos | `POST /api/v1/wardrobe/upload` (+ `/upload/bulk`), `WardrobeService._validate_image` (MIME allow-list, 15 MB cap, Pillow decode + format/MIME cross-check, extension check), sha256 duplicate guard, per-user storage namespace, soft-delete bin | ✅ working |
| Stable item identity | `wardrobe_items.id` (integer PK) + `image_url`; never filename-only | ✅ |
| Vision analysis → structured metadata | `WardrobeService._run_ai_analysis` → `VisualSearchAIProvider.analyze_wardrobe_image` (Gemini → NVIDIA → Qwen chain) → `wardrobe_taxonomy.normalize_wardrobe_analysis` → `processing_status` lifecycle `uploaded→processing→ready|failed` | ✅ working, **no IBM watsonx tier** |
| User corrects metadata | `PUT/PATCH /wardrobe/items/{id}`, `useWardrobeViewModel.updateItem` | ✅ |
| Occasion / time / season / location input | Only `occasion` (`GET /wardrobe/outfit-suggestions?occasion=`) | ❌ time-of-day, season, location, preferences missing |
| LLM outfit reasoning over the closet | `OutfitService.build_wardrobe_first_outfit` is a **deterministic scorer** (occasion match + favourite + wear count + neutral colour). No language model, no per-item explanation | ❌ |
| Validate model references against real items | n/a (no model) | ❌ |
| Show recommended item photos + reasons | Frontend has no wardrobe-outfit UI; `useWardrobeQuery.outfitSuggestions` hook exists but unused in `WardrobeView` | ❌ |
| Honest "mock vs real" labelling | Provider envelopes carry `analysis_available`/`analysis_source`; not persisted per item | ◐ partial |

## 2. Tutorial requirements verified against the live service (2026-10-26)

Checked with the operator's IBM Cloud key via IAM + `GET /ml/v1/foundation_model_specs` and
`POST /ml/v1/text/chat` (eu-de and us-south):

| Tutorial assumption | Verified reality |
|---|---|
| `WATSONX_URL = https://us-south.ml.cloud.ibm.com` | The account's watsonx.ai Runtime + project (`Ismaeil's sandbox`) live in **eu-de**. Endpoint must be configurable (it is). |
| Vision model `ibm/granite-vision-3-2-2b` | **Removed.** Live call → `404 model_not_supported`. IBM's v2.4 release notes list it as removed; no `granite-vision-*` model is served multitenant in either region today. Only `image_chat`-capable models: `meta-llama/llama-4-maverick-17b-128e-instruct-fp8`, `mistralai/mistral-small-3-1-24b-instruct-2503`. |
| Reasoning model `ibm/granite-3-2-8b-instruct` | **Withdrawn 22 Feb 2026**; IBM's lifecycle table names `ibm/granite-4-h-small` as the replacement. Live call OK (1.4 s). |
| SDK `ModelInference.chat(messages=…)` | The SDK is a wrapper over `POST /ml/v1/text/chat` (same body: `model_id`, `project_id`, `messages`, `max_tokens`, `temperature`; same response: `choices[0].message.content`). CONFIT's serverless function has an import-closure gate and already standardises on `httpx`; the integration therefore uses the REST contract directly over httpx with IAM bearer tokens. |
| `{"role":"control","content":"thinking"}` | Granite 3.2-specific; Granite 4 does not need it and the app must not expose chain-of-thought, so it is not used. |
| Filename substring matching to pick images | Replaced by structured `wardrobe_item_id` references validated against the caller's actual wardrobe rows. |

## 3. Gap table

| # | Requirement | Current | Work | Verification |
|---|---|---|---|---|
| G1 | watsonx.ai client (IAM, chat, retries, timeouts, no secret leakage) | none | `providers/watsonx/client.py` | unit tests with mocked httpx; live smoke |
| G2 | Vision tier via watsonx for wardrobe analysis | Gemini/NVIDIA/Qwen only | `providers/watsonx/vision.py`, chain insertion in `WardrobeService._run_ai_analysis` controlled by `WARDROBE_VISION_PROVIDER` | tests: malformed JSON, non-garment, timeout, source label |
| G3 | Context-aware outfit recommendation with Granite | deterministic only | `services/wardrobe_stylist_service.py`, `schemas/wardrobe_stylist.py`, `POST /wardrobe/outfit-recommendation` | tests: reference validation, missing categories, fallback labelled, 503 when unconfigured and no fallback |
| G4 | Versioned system prompt | none | `providers/watsonx/prompts.py` (`STYLIST_PROMPT_VERSION`) | prompt text asserted in tests |
| G5 | Persist which model produced metadata (FR‑18) | not stored | migration `0047` adds `wardrobe_items.analysis_source` | API returns `analysis_source`; UI badge |
| G6 | Preferences UI + recommendation workspace | none | `components/wardrobe/WardrobeStylistPanel.tsx`, new tab in `WardrobeView`, i18n EN/AR | vitest contract test; manual journey |
| G7 | Config + docs | `.env.example` lacks WATSONX_* | add vars, README section, troubleshooting | doc review vs. implementation |

## 4. Scope decisions

* Keep the existing Gemini/NVIDIA/Qwen chain intact; watsonx is an additional,
  configurable tier (default: preferred when configured). Nothing silently
  swaps providers — `analysis_source` records the actual `model_id`.
* The deterministic wardrobe scorer is retained as the **labelled fallback**
  (`source: "deterministic_fallback"`, `ai_generated: false`) so the product
  stays useful when watsonx is unreachable, without pretending to be AI.
* No new Python dependency (httpx + pydantic already declared).
