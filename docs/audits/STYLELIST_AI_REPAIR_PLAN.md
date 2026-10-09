# STYLELIST_AI_REPAIR_PLAN.md — CONFIT_A StyleList AI Stylist: Forensic Audit, Model Research & Repair Plan

> **Document type:** Standalone AI-feature plan with evidence-based model research (PLANNING / AUDIT ONLY — no application code changed).
> **Target repo:** `OmarAhmed-123/CONFIT_A` · **Branch:** `main` @ `a44f1fb` (clean).
> **Audit date:** 2026-10-09.
> **Siblings:** `ADMIN_REPAIR_PLAN.md`, `CUSTOMER_REPAIR_PLAN.md`, `BRAND_OWNER_REPAIR_PLAN.md`, `VIRTUAL_TRY_ON_REPAIR_PLAN.md`.

---

## 1. Title & Scope

The **StyleList AI stylist**: a conversational/agentic styling assistant that must support **two modes**:
- **Mode A — Multi-image styling:** the customer uploads one or more images (garments and/or a photo of themselves wearing an outfit) and gets a best-outfit recommendation + color-coordination guidance grounded in the real catalog.
- **Mode B — Text-only styling:** the customer describes an occasion/need in words (no image) and gets catalog-grounded outfit recommendations.

In the codebase the feature is named **"AI Virtual Stylist"** (`VirtualStylistDrawer`); there is no literal `"StyleList"` string. This plan treats "StyleList" as the product name for the existing stylist subsystem: `backend/app/controllers/stylist_controller.py`, `backend/app/schemas/stylist.py`, the stylist service + AI provider orchestrator, the deterministic `ColorHarmonyEngine`, and the frontend stylist drawer (route `/stylist`, which currently aliases `DiscoverView`).

---

## 2. Status & Severity Legend

**Status:** `VERIFIED` · `IMPLEMENTED` · `TESTED-PASS` · `TESTED-FAIL` · `GAP` · `BUG-VERIFIED` · `LIKELY` · `UNVERIFIED` · `BLOCKED` · `NO-GO` · `NOT FOUND IN SEARCHED SCOPE`.
**Severity:** P0 (blocking the feature's core promise) · P1 (major) · P2 (defect w/ workaround) · P3 (polish). Evidence cites `path:line`.

---

## 3. Executive Summary

Mode B (text-only) is **real, catalog-grounded, and honest** (it recommends only actual catalog products and degrades honestly when the provider fails). **Mode A (multi-image) does not exist**: the stylist chat request accepts **no image input at all**, so a customer cannot upload garments or an outfit photo and the "upload images → best outfit + color coordination" promise is unmet.

- **P0 — Mode A missing (STY-01):** `ChatRequest` in `backend/app/schemas/stylist.py` (fields `prompt`, `occasion`, `budget_limit`, `voice_input_used`, `include_wardrobe_items`, `recommendation_constraints` — all text/scalar; **no** image/images field). Verified by direct inspection.
- **P0 — User outfit-photo comparison unsupported (STY-05):** no vision path to analyze "what I'm wearing".
- **P1 — `include_wardrobe_items` accepted but ignored (STY-03):** field exists (`stylist.py:83`) but does not influence recommendations.
- **P1 — Provider failover not fully exercised (STY-04):** the NVIDIA model registry/failover chain is not fully used by the orchestrator.
- **Color analysis** is a deterministic `ColorHarmonyEngine` (rules), **not** vision — fine for text, insufficient for real image color extraction in Mode A.

**Model research (evidence-based, this audit):** the app already speaks the OpenAI-compatible NVIDIA NIM API, and NVIDIA now ships a **multimodal** NIM, `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` (image+video+audio+text), callable via the **same `/v1/chat/completions` endpoint with `image_url` content parts** the app already uses — so Mode A can be added **through the existing NVIDIA provider** with minimal new infrastructure. For highest outfit-task quality, Google **`gemini-3-pro-preview`** leads an independent fashion VLM benchmark; **`gemini-2.5-flash` / `gemini-2.5-flash-lite`** are strong cost-efficient tiers; OpenAI **`gpt-5.2` / `gpt-5-mini`** are viable alternatives. Full citations + links in §8.

**Baseline tests (this audit):** backend 3732 passed / 4 env-only failed / 21 skipped (the 4 are VTON mediapipe `libEGL` env failures — unrelated to stylist); frontend build PASS. Stylist attribution tests (`test_stylist_style_attribution.py`) pass on a clean DB.

---

## 4. Baseline & Environment Evidence

| Item | Evidence | Status |
|---|---|---|
| Chat request is text-only (no image) | `backend/app/schemas/stylist.py` `ChatRequest` fields (`prompt`, `occasion`, `budget_limit`, `voice_input_used`, `include_wardrobe_items` at L83, `recommendation_constraints`) | VERIFIED (Mode A absent) |
| Product naming | `VirtualStylistDrawer` / "AI Virtual Stylist"; no `"StyleList"` string | VERIFIED |
| Providers configured | `AI_PROVIDERS=local_gpu,nvidia,groq,gemini,openai,unorouter` | VERIFIED |
| Text models bound | primary `nvidia/nemotron-3-super-120b-a12b` → `nemotron-3-ultra-550b-a55b` | VERIFIED |
| Color engine | deterministic `ColorHarmonyEngine` (rules, not vision) | VERIFIED |
| Mode B grounding | recommends real catalog products; honest fallback | VERIFIED (positive) |
| Stylist route | `/stylist` aliases `DiscoverView`; stylist is a drawer | VERIFIED |
| NVIDIA multimodal NIM exists | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`, OpenAI-compatible, `image_url` parts | VERIFIED (official docs, §8) |
| Backend suite | 3732 passed / 4 env-only failed / 21 skipped | TESTED-PASS |
| Spec Kit | absent → documentation-based process | VERIFIED (absent) |

---

## 5. Current-State Inventory (StyleList)

- **Backend:** `stylist_controller.py` (chat endpoint), `stylist.py` schemas (text-only `ChatRequest`; `OutfitOut`/`OutfitItemOut` reference **real** catalog products with currency), stylist service + AI orchestrator (provider failover across `local_gpu,nvidia,groq,gemini,openai,unorouter`), `ColorHarmonyEngine` (deterministic color scoring).
- **Frontend:** `VirtualStylistDrawer` (chat UI), route `/stylist` → `DiscoverView` alias.
- **What works (Mode B):** text prompt → provider → catalog-grounded outfit(s) with honest fallback when providers fail.
- **What's missing (Mode A):** image intake, vision analysis of uploaded garments / user outfit photo, image-derived color extraction, wardrobe-grounded recommendations actually using `include_wardrobe_items`.

| Capability | Backend | UI | Status |
|---|---|---|---|
| Text styling (Mode B) | yes | drawer | VERIFIED |
| Catalog grounding | yes | yes | VERIFIED |
| Honest provider fallback | yes | yes | VERIFIED |
| Image upload to stylist (Mode A) | **none** | **none** | GAP (STY-01) |
| Vision analysis of outfit photo | **none** | **none** | GAP (STY-05) |
| Image color extraction | rules only | n/a | GAP (STY-06) |
| Wardrobe-grounded recs | field ignored | n/a | BUG (STY-03) |
| Provider failover (full chain) | partial | n/a | BUG (STY-04) |

---

## 6. Findings Register (StyleList)

| ID | Title | Sev | Status | Evidence |
|---|---|---|---|---|
| STY-01 | Mode A (multi-image) not implemented — no image fields on chat | P0 | BUG-VERIFIED | `schemas/stylist.py` `ChatRequest` text-only |
| STY-02 | No image upload UI in stylist drawer | P0 | GAP | `VirtualStylistDrawer` |
| STY-03 | `include_wardrobe_items` accepted but ignored | P1 | BUG-VERIFIED | `stylist.py:83`; not used in recs |
| STY-04 | NVIDIA registry failover chain not fully used by orchestrator | P1 | BUG-VERIFIED | orchestrator |
| STY-05 | User outfit-photo comparison unsupported | P0 | GAP | no vision path |
| STY-06 | Color coordination is rules-only (no image color extraction) | P1 | VERIFIED | `ColorHarmonyEngine` deterministic |
| STY-07 | No vision/multimodal model wired despite `gemini`/`nvidia` providers | P1 | BUG-VERIFIED | providers present, vision path absent |
| STY-08 | No per-user AI cost/rate budget for stylist calls | P2 | LIKELY | cost control |
| STY-09 | No image content-safety on stylist uploads | P2 | GAP | moderation |
| STY-10 | Recommendations not persisted as shareable "looks" from Mode A | P2 | LIKELY | enhancement |
| STY-11 | No streaming/agentic multi-turn tool use (ChatGPT-like) | P2 | LIKELY | UX ask |
| STY-12 | Mode B catalog grounding + honest fallback | — | VERIFIED (positive) | service |
| STY-13 | Outfit items reference real products w/ currency | — | VERIFIED (positive) | `OutfitItemOut` |
| STY-14 | Stylist drawer a11y/animation/i18n gaps | P2 | LIKELY | §14/§15 |
| STY-15 | No evaluation harness for recommendation quality | P2 | GAP | quality regression |
| STY-16 | Model IDs/providers not centrally documented/validated | P2 | LIKELY | ops |
| STY-17 | Mode A results don't feed Virtual Try-On | P3 | GAP | cross-feature (VTON) |

---

## 7. Root-Cause Analysis

1. **Text-first design.** The stylist was built as a text chat with catalog retrieval; the request schema never grew image fields, so Mode A was never reachable (STY-01/02/05).
2. **Vision providers present but unused.** `gemini` and `nvidia` are listed providers, but no code path sends images to a vision model; color is handled by deterministic rules (STY-06/07).
3. **Partial feature wiring.** `include_wardrobe_items` was added to the schema before the logic that would consume it (STY-03) — the same backend-ahead-of-frontend pattern seen elsewhere.
4. **Failover under-exercised.** The orchestrator doesn't fully traverse the NVIDIA model registry chain (STY-04), reducing resilience.

---

## 8. AI Model Research (Evidence-Based) — with official links & exact model IDs

> **Method:** independent fashion VLM benchmarks + official provider model cards (retrieved 2026-10-09). Exact IDs are quoted; always re-validate against the live catalog URL before pinning, since providers rotate IDs.

### 8.1 Recommended primary (Mode A vision) — reuse the existing NVIDIA provider
- **Model ID:** `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` — NVIDIA NIM **multimodal** (image + video + audio + text), OpenAI-compatible `/v1/chat/completions` with `image_url` content parts.
- **Why:** the app **already** integrates the NVIDIA OpenAI-compatible API for the text stylist; Mode A can be added by sending `image_url` content parts to this model via the **same provider path** — minimal new infrastructure, consistent auth, and it keeps the honest-fallback orchestrator intact.
- **Official links:**
  - Model card: https://build.nvidia.com/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning/modelcard
  - API usage (image_url example): https://docs.nvidia.com/nim/vision-language-models/1.7.0/examples/nemotron-3-nano-omni-30b-a3b-reasoning/api.html
  - API reference: https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-nano-omni-30b-a3b-reasoning
  - NGC container: https://catalog.ngc.nvidia.com/orgs/nim/nvidia/containers/nemotron-3-nano-omni-30b-a3b-reasoning/-

### 8.2 Recommended quality leader (Mode A, when top outfit accuracy matters)
- **Model ID:** `gemini-3-pro-preview` (Google) — **highest scores on outfit tasks** in an independent fashion VLM benchmark [B1].
- **Cost-efficient tiers:** `gemini-2.5-flash` and `gemini-2.5-flash-lite` — Flash-Lite retains ~83% of flagship performance at ~5% of the cost [B2][B3]; Gemini-2.5-Flash scores strongly on style/occasion/color fashion tasks [B4].
- **Official links:**
  - Gemini API + model list: https://ai.google.dev/gemini-api/docs/models
  - Gemini (DeepMind) model cards: https://deepmind.google/models/ (e.g. Flash-Image card: https://deepmind.google/models/model-cards/gemini-3-1-flash-image/)
- **Note:** the app already lists `gemini` as a provider — adding a vision call here is a natural second path/failover.

### 8.3 Alternative (Mode A)
- **Model IDs:** OpenAI `gpt-5.2` (flagship) and `gpt-5-mini` (efficient) — competitive on fashion item/outfit tasks [B1][B2].
- **Official link:** https://platform.openai.com/docs/models

### 8.4 Text model (Mode B) — keep what works
- **Model IDs (already bound):** primary `nvidia/nemotron-3-super-120b-a12b` → failover `nemotron-3-ultra-550b-a55b`, plus `groq`/`gemini`/`openai`/`unorouter` in the chain. Keep Mode B on these text models; add vision only for image turns.

### 8.5 Color coordination
- Keep the deterministic `ColorHarmonyEngine` for **explainable** harmony scoring, but **feed it real colors extracted from uploaded images** (palette extraction) in Mode A, rather than inferring from text. The vision model can also return dominant garment colors directly; cross-check against the engine for an explainable, non-hallucinated palette.

### 8.6 Evidence citations
- **[B1]** *Preliminary Study of an Evaluation Benchmark for Vision–Language Models in Fashion E-Commerce* — ACM: https://dl.acm.org/doi/pdf/10.1145/3805712.3808442 (gemini-3-pro-preview leads outfit tasks; models evaluated incl. gpt-5.2/5.1/5-mini, gemini-2.5-pro/flash-lite).
- **[B2]/[B3]** *Zero-Shot Product Attribute Labeling with VLMs: A Three-Tier Evaluation Framework* — arXiv https://arxiv.org/pdf/2601.15711 / summary https://exa.ai/library/publication/wlfffjl8lwm (Gemini 2.5 Pro best overall; Flash-Lite ~83% perf at ~5% cost; efficient tiers ≥90% of flagship).
- **[B4]** *OmniFashion: Towards Generalist Fashion Intelligence via Multi-Task Vision-Language Learning* — arXiv https://arxiv.org/pdf/2603.02658 (Gemini-2.5-Flash strong on style/occasion/color; multi-task fashion VLM).

> **Honesty note:** exact provider model IDs change frequently. The plan pins IDs **and** the official catalog URL so the implementer re-validates availability before shipping. If a pinned ID is retired, fall back along the configured provider chain.

---

## 9. Specification (Specify)

**Spec A — Mode A multi-image styling (closes STY-01/02/05/06/07).** The customer can attach 1..N images (garments and/or an outfit photo of themselves) to a stylist turn; the system analyzes them with a vision model, extracts garment attributes + dominant colors, and returns a best-outfit recommendation + color-coordination guidance grounded in the **real catalog** (same honesty contract as Mode B). Acceptance: image turn returns real catalog products; colors derive from the image; no hallucinated products; honest fallback if the vision provider fails.

**Spec B — Mode B parity preserved (STY-12/13).** Text-only turns keep working exactly as today (catalog-grounded, honest fallback). Acceptance: existing stylist tests stay green.

**Spec C — Wardrobe grounding (STY-03).** When `include_wardrobe_items=true`, recommendations consider the user's wardrobe items and can suggest "pair with items you already own." Acceptance: toggling the flag measurably changes recommendations; wardrobe items appear in output where relevant.

**Spec D — Resilient provider orchestration (STY-04/07/16).** The orchestrator traverses the full provider/model chain (text and vision) with honest degradation; the served model is reported truthfully (the schema already reports the model actually served). Acceptance: forced primary failure falls through to the next provider; response states which model answered.

**Spec E — Safety, cost, UX (STY-08/09/10/11/14).** Image uploads are content-safety screened and size/format-validated; per-user AI budget/rate limit applies; Mode A results can be saved as shareable "looks"; the drawer supports streaming multi-turn (ChatGPT-like), is i18n/RTL, accessible, and animated (launch upload button). Acceptance: §14/§15 + budget/moderation tests.

---

## 10. Plan (Plan)

1. Extend `ChatRequest` with optional image inputs (base64/data-URL or uploaded refs) + a `mode` discriminator (auto: images present ⇒ Mode A). 2. Add a vision path in the orchestrator using `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` (primary) with `gemini-2.5-flash`/`gpt-5-mini` failover for image turns. 3. Extract image colors; feed `ColorHarmonyEngine`. 4. Implement wardrobe grounding (STY-03). 5. Complete failover traversal (STY-04). 6. Add moderation + budget. 7. Rebuild drawer UX (upload, streaming, save-as-look, i18n/a11y/animation). 8. Add a recommendation-quality eval harness. 9. Converge; keep Mode B tests green.

---

## 11. Tasks (Tasks)

**T-STY-01 · Add image inputs + mode discriminator to stylist request**
- **Sev:** P0 · **Linked:** STY-01
- **Steps:** extend `ChatRequest` with `images: Optional[List[ImageInput]]` (data-URL or storage ref; max N; size/format validated) and derive `mode` (A if images present, else B). Keep all existing fields.
- **Files:** `backend/app/schemas/stylist.py`, `stylist_controller.py`.
- **Acceptance:** image turns accepted + validated; text turns unchanged (Spec B).
- **Tests:** schema validation (max images, size/format); text-turn regression.
- **Rollback:** images field optional + flag. · **Risk:** low. · **Status:** BUG-VERIFIED → planned.

**T-STY-02 · Vision path in the AI orchestrator (Mode A)**
- **Sev:** P0 · **Linked:** STY-05, STY-07, STY-04
- **Steps:** for image turns, call `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` via the existing OpenAI-compatible NVIDIA provider with `image_url` content parts; failover to `gemini-2.5-flash` then `gpt-5-mini`; **ground output in the real catalog** (retrieve candidate products, never invent); report the served model truthfully.
- **Files:** AI orchestrator/provider modules, stylist service.
- **Acceptance:** Spec A; honest fallback; no hallucinated products; served-model reported.
- **Tests:** image turn → real catalog products; forced primary failure → failover; "no product outside catalog" assertion.
- **Rollback:** flag-off reverts to Mode B only. · **Risk:** medium (new provider path + cost). · **Status:** GAP → planned.

**T-STY-03 · Image color extraction → ColorHarmonyEngine**
- **Sev:** P1 · **Linked:** STY-06
- **Steps:** extract dominant palette from uploaded images (deterministic palette extraction and/or the vision model's reported colors); pass real colors into `ColorHarmonyEngine` for explainable coordination; cross-check vision colors vs. extracted palette to avoid hallucinated colors.
- **Files:** color pipeline, stylist service.
- **Acceptance:** color guidance derives from the image, not text; explainable.
- **Tests:** known-palette image → expected harmony scoring; mismatch guard.
- **Rollback:** fall back to rules-only. · **Risk:** low. · **Status:** planned.

**T-STY-04 · Wardrobe grounding (honor `include_wardrobe_items`)**
- **Sev:** P1 · **Linked:** STY-03 (finding)
- **Steps:** when `include_wardrobe_items=true`, fetch the user's wardrobe and let the recommender pair catalog items with owned items; surface "pairs with your [item]".
- **Files:** stylist service, wardrobe read path.
- **Acceptance:** Spec C; toggling the flag changes recommendations.
- **Tests:** flag on vs off differs; wardrobe items appear where relevant.
- **Rollback:** ignore flag (current behavior). · **Risk:** low. · **Status:** BUG-VERIFIED → planned.

**T-STY-05 · Complete provider/model failover traversal**
- **Sev:** P1 · **Linked:** STY-04, STY-16
- **Steps:** ensure the orchestrator walks the full configured chain for both text and vision; centralize model IDs + catalog URLs in config; validate configured IDs at startup (honest warning if an ID is unavailable — no secrets logged).
- **Files:** orchestrator, config, readiness.
- **Acceptance:** Spec D; forced failures fall through; served model reported.
- **Tests:** multi-provider failover; startup validation.
- **Rollback:** revert to current chain. · **Risk:** medium. · **Status:** BUG-VERIFIED → planned.

**T-STY-06 · Safety + per-user AI budget**
- **Sev:** P2 · **Linked:** STY-08, STY-09
- **Steps:** content-safety screen on uploaded images (e.g. NVIDIA content-safety NIM or provider moderation); size/format guardrails; per-user rate/cost budget for stylist AI calls.
- **Files:** stylist intake, moderation hook, slowapi limits.
- **Acceptance:** Spec E (safety/budget); unsafe/oversized refused; budget enforced.
- **Tests:** unsafe/oversized refused; budget enforced.
- **Rollback:** disable moderation flag (keep size/format). · **Risk:** medium. · **Status:** GAP → planned.

**T-STY-07 · Drawer UX: upload + streaming + save-as-look + i18n/a11y/animation**
- **Sev:** P2 (a11y P1) · **Linked:** STY-02, STY-10, STY-11, STY-14, §14/§15
- **Steps:** add multi-image upload to `VirtualStylistDrawer` with the shared `<LaunchButton>` (rocket rising bottom→top + color shift) honoring reduced motion; streaming multi-turn responses (ChatGPT-like); "Save as look" from Mode A results; render products with `HonestProductImage`; full EN/AR + RTL; focus-trapped drawer; accessible names.
- **Files:** `VirtualStylistDrawer` + shared components.
- **Acceptance:** Spec E UX; axe passes; RTL correct.
- **Tests:** axe a11y; RTL snapshot; reduced-motion; upload keyboard flow.
- **Rollback:** revert UI layer. · **Risk:** medium. · **Status:** GAP → planned.

**T-STY-08 · Recommendation-quality eval harness**
- **Sev:** P2 · **Linked:** STY-15
- **Steps:** build a small offline eval set (occasions, uploaded-image fixtures) + metrics (catalog-grounding rate, color-coordination sanity, no-hallucination rate); run in CI to catch regressions when model IDs change.
- **Files:** eval harness under `backend/tests` or a tools dir.
- **Acceptance:** eval runs; thresholds enforced.
- **Tests:** the harness itself + threshold gate.
- **Rollback:** advisory-only. · **Risk:** low. · **Status:** GAP → planned.

**T-STY-09 · (Optional) Feed Mode A result into Virtual Try-On**
- **Sev:** P3 · **Linked:** STY-17 (cross-ref `VIRTUAL_TRY_ON_REPAIR_PLAN.md`)
- **Steps:** add a "Try this on" action that hands the recommended outfit to the VTON async pipeline (after VTON T-VTON-01).
- **Acceptance:** recommended outfit launches a try-on job. · **Risk:** low. · **Status:** GAP → planned (depends on VTON async).

---

## 12. Data Model / Migration Considerations

- **Message persistence:** stylist messages/outfits already persist with real product refs + currency (preserve). If Mode A images are retained, treat them like VTON person images — **do not** store raw base64 in the DB; use short-TTL encrypted storage or discard after analysis (consistent with `VIRTUAL_TRY_ON_REPAIR_PLAN.md` T-VTON-03 and DB-11). Prefer **not persisting** uploaded stylist images at all unless the user saves the look.
- **Save-as-look:** reuse the existing looks/outfit sharing model (token lifecycle already exists) for Mode A results.
- **Config, not schema, for models:** model IDs + catalog URLs live in configuration, not the DB.
- **Migration hygiene:** any new column chains forward from head `0034_*` (prod is at `0035_product_images`, §13/§risks). **No migration authored here.**

---

## 13. API Contract Changes (proposed)

| Endpoint | Change | Note |
|---|---|---|
| `POST /stylist/chat` | accept optional `images[]` + derive `mode` A/B | STY-01 |
| response | include served-model + `mode` + honest reason on fallback | STY-04 (schema already reports served model) |
| image handling | validate size/format; moderate; don't persist raw base64 in DB | STY-06/09, privacy |
| wardrobe | honor `include_wardrobe_items` | STY-03 |

Explicit Pydantic schemas; `await` all async; never return a product outside the catalog; never log provider secrets.

---

## 14. UI/UX Plan (colors · animation · dynamism)

- **Multi-image upload (core of Mode A):** drag-and-drop / picker for 1..N images; thumbnails via `HonestProductImage`; the **upload button uses the shared launch animation** (rocket rising bottom→top + color shift to success token; reduced-motion → fade) — directly fulfilling the requested button behavior.
- **ChatGPT-like dynamism:** streaming tokens, typing indicator, multi-turn history, inline product cards with real images + prices + currency.
- **Color coordination display:** show the extracted palette (swatches) and the harmony explanation so advice is transparent, not a black box.
- **Save-as-look + share:** animated save action; shareable look using the existing token lifecycle.
- Canonical gold token; consistent focus rings.

---

## 15. Accessibility Plan (WCAG 2.2 AA)

- Stylist drawer is focus-trapped (A11Y-03); every control (upload, send, save) has an accessible name; emoji are not used as sole controls.
- Streaming output announced politely via `aria-live` without stealing focus (MOT-02 pattern).
- Image thumbnails have meaningful alt text; palette swatches have text labels (not color-only).
- Full EN/AR + RTL (the drawer currently has i18n gaps).
- Launch/streaming animations respect `prefers-reduced-motion`.

---

## 16. Security & Privacy

- Treat uploaded stylist images (especially outfit photos of the user) as sensitive: moderate at intake, validate size/format, **avoid DB persistence of raw image bytes** (mirror VTON privacy stance), scrub on deletion if retained.
- Per-user AI budget/rate limit to control provider cost (STY-08).
- Never return a hallucinated/out-of-catalog product (preserve Mode B honesty in Mode A).
- Never log or expose provider API keys; report only the served model name.
- Content-safety screening before sending images to third-party providers.

---

## 17. Testing & Verification Plan

- Mode A: image turn → real catalog products; color derived from image; no hallucination; honest fallback on provider failure.
- Mode B: regression (stays catalog-grounded + honest); keep `test_stylist_style_attribution.py` green.
- Wardrobe grounding on/off differs; provider failover traversal; startup model-validation.
- Safety/budget: unsafe/oversized refused; budget enforced.
- Eval harness thresholds in CI (grounding rate, no-hallucination rate).
- Frontend: axe, RTL, reduced-motion, upload keyboard flow, streaming.
- **Baseline to preserve:** 3732 passed / 21 skipped; frontend build PASS. No new TESTED-FAIL.

---

## 18. Rollout / Deployment / Flags

- Mode A behind a `STYLIST_VISION_ENABLED` flag; Mode B unaffected.
- Vision calls are short enough for serverless, but enforce a per-request timeout and the per-user budget; heavy future work (if any) should use the async pattern from the VTON plan.
- Centralize + validate model IDs at deploy; honest readiness reports which providers/models are configured (no secrets).

---

## 19. Risks, Assumptions, Open Questions

- **R1 (model ID drift):** provider model IDs rotate; pin IDs **and** keep the official catalog URL + failover chain so a retired ID degrades gracefully. **Re-validate before shipping.**
- **R2 (cost):** vision calls cost more than text; the per-user budget (T-STY-06) is required, not optional.
- **R3 (privacy):** outfit photos of users are sensitive — default to **not persisting** uploaded images.
- **R4 (migration drift):** prod `0035_product_images` ahead of `main` `0034`; any save-as-look schema change chains after `0035`. **UNVERIFIED in `main`.**
- **A1:** NVIDIA multimodal NIM is reachable via the app's existing OpenAI-compatible provider (verified from official docs, §8).
- **Q1:** which provider is default for Mode A — cost-optimized (NVIDIA Nemotron Omni / Gemini Flash-Lite) or quality-first (`gemini-3-pro-preview`)? Recommend cost-optimized default with a quality-first failover/escalation.

---

## 20. Acceptance Criteria / DoD + Traceability

**StyleList is "done" when:** a customer can upload one or more images (garments and/or their own outfit photo) and receive a best-outfit recommendation + image-derived color-coordination guidance grounded in the real catalog (Mode A), **and** can still get text-only recommendations (Mode B); wardrobe grounding works; the provider chain fails over honestly and reports the served model; uploads are moderated, budgeted, and privacy-safe; and the drawer is streaming, animated (launch upload button), image-polished, i18n/RTL, and WCAG 2.2 AA — with Mode B honesty preserved and documented, cited model choices.

| Finding | Task | DoD signal |
|---|---|---|
| STY-01/02 | T-STY-01, T-STY-07 | Image upload accepted + UI live. |
| STY-05/07 | T-STY-02 | Vision path → real catalog products. |
| STY-06 | T-STY-03 | Image-derived color coordination. |
| STY-03 | T-STY-04 | Wardrobe grounding honored. |
| STY-04/16 | T-STY-05 | Full failover; served model reported. |
| STY-08/09 | T-STY-06 | Safety + budget enforced. |
| STY-10/11/14 | T-STY-07 | Streaming/save/i18n/a11y/animation. |
| STY-15 | T-STY-08 | Eval harness gates quality. |
| STY-17 | T-STY-09 | (Optional) feeds Try-On. |

**Preserve:** STY-12 (Mode B honesty), STY-13 (real-product grounding).
