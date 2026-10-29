# Vision Provider Decision — wardrobe garment understanding

Decision date 2026-10-29. Consolidates `docs/vision-integration-decision.md` (eighth pass) with the live findings; the earlier document remains the detailed record.

## Facts (verified)

| Fact | Evidence |
|---|---|
| IBM Granite Vision models (`granite-vision-3-2-2b`, `granite-vision-3-3-2b`) return **404 `model_not_supported`** on the multitenant eu-de endpoint for this project | live probe 2026-10-27; IBM lifecycle page lists 3.2 withdrawn, 3.3 not available multitenant in eu-de |
| `meta-llama/llama-4-maverick-17b-128e-instruct-fp8` (currently configured `WATSONX_VISION_MODEL_ID`) **is served** on the same endpoint | live functional probe recorded in `docs/vision-integration-decision.md` ("Live, verified eu-de") and `docs/IBM_WATSONX_PRODUCTION_VERIFICATION_REPORT.md` |
| Reasoning model `ibm/granite-4-h-small` works end to end | live eval 2026-10-28, 22 calls, 0 violations |
| Model IDs are centralised (`WATSONX_VISION_MODEL_ID`, `WATSONX_REASONING_MODEL_ID`) and the UI labels the source (`ai=True/False`, provider name) | `backend/app/core/config.py`, `WardrobeStylistPanel.tsx` source badge |
| Vision provider modes: `auto` (watsonx when configured) / `legacy` (existing heuristic chain, never a model call) | `WARDROBE_VISION_PROVIDER` |

## Decision

1. **Garment vision stays on the configurable watsonx vision slot; the current configured model is Llama-4-Maverick on watsonx.ai because no Granite Vision model is served to this project.** This is **not** Granite and is labelled as such everywhere (`provider=watsonx`, `model_id=<configured>`); it is never described as Granite inference. If IBM re-enables a Granite Vision model in eu-de multitenant, switching is a one-line env change plus the acceptance run in `docs/IBM_WATSONX_STYLIST_ACCEPTANCE.md`.
2. **Outfit reasoning stays on `ibm/granite-4-h-small`** (verified live). The deterministic engine remains the labelled fallback (`deterministic_fallback`), never presented as AI.
3. **Not adopted**: third-party vision APIs outside watsonx (would violate the "never silently substitute provider" constraint and the EU data-residency note in the GDPR copy); client-side models (bundle size, no auditability).

## Acceptance status

| Item | Status |
|---|---|
| Granite Vision live acceptance | **BLOCKED** (model not served) — remains unverified |
| Llama-4-Maverick vision live acceptance | **NOT TESTED under load**; single-image functional probe only (see the verification report; Deploy-on-Demand Granite Vision = paid instance, item S3) |
| Manual-entry path (no photo) | **VERIFIED** (browser E2E, en + ar) |

## Owner actions

* Confirm with IBM account team whether a Granite Vision deployment (dedicated or new multitenant region) is available; if yes, run the acceptance script and flip `WATSONX_VISION_MODEL_ID`.
* Until then product copy must say "AI tagging (watsonx)" not "Granite Vision".
