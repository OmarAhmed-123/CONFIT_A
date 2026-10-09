# Feature Specification: StyleList AI — Mode A (Multi-Image/Vision), Wardrobe Grounding & Provider Failover

**Feature Branch**: `009-stylelist-ai-modes`

**Created**: 2026-10-09

**Status**: Draft (planning only)

**Input**: Findings STY-01..17 (`STYLELIST_AI_REPAIR_PLAN.md`). Constitution Principle IV (honest AI, grounded in real catalog) and I.

## Problem Context *(evidence)*

- **STY-01 (BUG-VERIFIED, P0):** Mode A (multi-image) is **not implemented**. `ChatRequest` in `backend/app/schemas/stylist.py` has only text/scalar fields (`prompt`, `occasion`, `budget_limit`, `voice_input_used`, `include_wardrobe_items` at `:83`, `recommendation_constraints`) — **no image/images field** (verified by direct inspection). **STY-02 (GAP, P0):** no image upload UI in the stylist drawer.
- **STY-05 (GAP, P0):** user outfit-photo comparison ("what I'm wearing") is unsupported — no vision path. **STY-07 (BUG-VERIFIED, P1):** no vision/multimodal model is wired despite `gemini`/`nvidia` providers being present.
- **STY-03 (BUG-VERIFIED, P1):** `include_wardrobe_items` is accepted (`stylist.py:83`) but **ignored** — it does not influence recommendations.
- **STY-04 (BUG-VERIFIED, P1):** the NVIDIA model registry/failover chain is **not fully used** by the orchestrator.
- **STY-06 (VERIFIED):** color coordination is rules-only (`ColorHarmonyEngine`, deterministic) — no image color extraction (becomes possible once vision lands).
- **STY-08/09 (P2):** no per-user AI cost/rate budget; no image content-safety on stylist uploads.
- **STY-10/11/14/15/16/17 (P2/P3):** Mode-A results not persisted as shareable looks; no streaming/agentic multi-turn; drawer a11y/i18n gaps (workstream 010); no eval harness; model IDs not centrally documented; Mode-A results don't feed VTON (cross-feature, workstream 008).

**Verified positives to preserve:** Mode B catalog grounding + honest fallback (STY-12); outfit items reference real products with currency (STY-13, `OutfitItemOut`).

**Model research (from audit):** a multimodal/vision model is reachable through the existing OpenAI-compatible NVIDIA path (e.g., an NVIDIA multimodal NIM such as `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`); Google `gemini-3-pro-preview` / `gemini-2.5-flash(-lite)`; OpenAI `gpt-5.2` / `gpt-5-mini`. The served model MUST be reported truthfully (Principle IV).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Mode A: user uploads outfit image(s) and gets grounded recommendations (Priority: P0)

As a customer, I can upload one or more photos (what I'm wearing / inspiration) to the stylist and receive recommendations grounded in the real catalog that account for my images.

**Why this priority**: STY-01/02/05/07 — the headline multimodal capability is entirely absent.

**Acceptance Scenarios**:

1. **Given** the stylist, **When** I attach image(s), **Then** the request carries them and the derived mode is `A` (vs text-only `B`).
2. **Given** an uploaded outfit photo, **When** the stylist responds, **Then** recommendations are produced via a real vision/multimodal model and reference real catalog products with currency (STY-13 preserved).
3. **Given** the vision provider is unavailable/unconfigured, **When** I submit images, **Then** I get an honest unavailable state (no fabricated analysis, Principle IV), optionally falling back to text-only Mode B with a clear reason.
4. **Given** a response, **When** returned, **Then** it reports the actually-served model and the mode (A/B).

---

### User Story 2 - Wardrobe grounding actually influences recommendations (Priority: P1)

As a customer, when I ask the stylist to use my wardrobe (`include_wardrobe_items`), my wardrobe items demonstrably shape the recommendations.

**Why this priority**: STY-03 — the flag is accepted but silently ignored (dishonest affordance).

**Acceptance Scenarios**:

1. **Given** `include_wardrobe_items=true` with wardrobe items, **When** I request recommendations, **Then** the output provably incorporates wardrobe items (e.g., complementary pairings reference them).
2. **Given** `include_wardrobe_items=false`, **When** I request, **Then** wardrobe items are not used.

---

### User Story 3 - Provider failover chain is fully exercised (Priority: P1)

As the platform, the stylist orchestrator uses the NVIDIA model registry/failover chain fully, degrading across configured providers and always reporting the served model honestly.

**Why this priority**: STY-04/16 — reliability + honest model reporting.

**Acceptance Scenarios**:

1. **Given** the primary provider fails, **When** a request runs, **Then** the orchestrator fails over through the registry chain and returns a result reporting the served model.
2. **Given** all providers fail, **When** a request runs, **Then** an honest unavailable state is returned (no fabricated recommendation).

---

### User Story 4 - Image color extraction improves coordination (Priority: P1)

As a customer in Mode A, color coordination uses colors extracted from my image(s), not rules alone.

**Why this priority**: STY-06 — unlocks real value once vision lands.

**Acceptance Scenarios**:

1. **Given** an uploaded image, **When** coordination runs, **Then** extracted colors feed `ColorHarmonyEngine` and influence the palette.

---

### User Story 5 - Upload safety and per-user AI budget (Priority: P2)

As the platform, stylist image uploads are content-safety screened and per-user AI cost/rate budgets are enforced.

**Acceptance Scenarios**:

1. **Given** an unsafe upload, **When** submitted, **Then** it is rejected.
2. **Given** a user over budget, **When** they submit, **Then** they are rate/cost-limited honestly.

### Edge Cases

- Image size/format guardrails; images never persisted as raw base64 in DB (same privacy rule as VTON — short-TTL/discard).
- Mixed text+image requests; multiple images.
- Provider returns low-confidence/empty — honest fallback to Mode B with reason, never fabricated products.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `ChatRequest` MUST accept optional `images[]` and the service MUST derive `mode` (A when images present, else B). (STY-01)
- **FR-002**: The stylist drawer MUST provide an image upload UI. (STY-02)
- **FR-003**: A real vision/multimodal model MUST analyze uploaded images via the existing provider abstraction (NVIDIA OpenAI-compatible path and/or Gemini vision); the served model and mode MUST be reported truthfully. (STY-05/07, Principle IV)
- **FR-004**: `include_wardrobe_items` MUST provably influence recommendations when true. (STY-03)
- **FR-005**: The orchestrator MUST fully use the provider registry/failover chain and MUST return an honest unavailable state if all providers fail (never fabricated output). (STY-04)
- **FR-006**: All recommendations MUST be grounded in the real catalog with real products + currency (preserve STY-12/13). No fabricated products/stock/prices.
- **FR-007**: Image color extraction MUST feed `ColorHarmonyEngine` in Mode A. (STY-06)
- **FR-008**: Stylist uploads MUST be content-safety screened and size/format-guarded; images MUST NOT be stored as raw base64 in the DB (short-TTL/discard). (STY-09, privacy)
- **FR-009**: Per-user AI cost/rate budgets MUST be enforced. (STY-08)
- **FR-010**: Model IDs/providers MUST be centrally documented and validated. (STY-16)

### Key Entities

- **ChatRequest**: text fields + optional `images[]`; derived `mode`.
- **StylistResponse**: recommendations, served-model, mode, honest fallback reason; `OutfitItemOut` real products (existing positive).
- **Provider Registry**: ordered failover chain; vision-capable + text providers.

## Success Criteria *(mandatory)*

- **SC-001**: A Mode-A request with image(s) returns recommendations grounded in real catalog products, reporting a real served vision model (integration test with provider mocked/recorded; no fabricated products).
- **SC-002**: With `include_wardrobe_items=true`, output provably references wardrobe items; with false, it does not (test-verified).
- **SC-003**: On primary-provider failure, failover produces a result and reports the served model; on total failure, an honest unavailable state (0 fabricated recommendations).
- **SC-004**: In Mode A, extracted image colors change the coordination palette vs rules-only (test-verified).
- **SC-005**: Unsafe/oversized uploads rejected; over-budget users limited; 0 raw base64 images in DB.
- **SC-006**: Mode B catalog grounding + honest fallback (STY-12) and real-product/currency outputs (STY-13) remain green.

## Assumptions

- Vision reaches through the existing OpenAI-compatible NVIDIA path and/or Gemini; exact model IDs are configuration-driven and centrally documented; no paid AI request is triggered during planning (tests mock/record providers).
- Shareable "looks" from Mode A (STY-10), streaming/agentic multi-turn (STY-11), eval harness (STY-15), and Mode-A→VTON handoff (STY-17) are P2/P3 scheduled later; drawer a11y/i18n (STY-14) aligns with workstream 010.
