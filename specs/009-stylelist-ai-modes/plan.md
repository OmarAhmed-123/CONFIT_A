# Implementation Plan: StyleList AI — Mode A, Wardrobe Grounding & Failover

**Branch**: `009-stylelist-ai-modes` | **Date**: 2026-10-09 | **Spec**: [spec.md](./spec.md)

## Summary

Add multi-image/vision Mode A to StyleList: extend `ChatRequest` with optional `images[]` and derive mode (STY-01), add an upload UI (STY-02), wire a real vision/multimodal model through the existing provider abstraction with honest served-model reporting (STY-05/07), make `include_wardrobe_items` actually influence output (STY-03), fully exercise the provider failover chain with honest unavailability (STY-04), feed image-extracted colors into `ColorHarmonyEngine` (STY-06), and add upload safety + per-user AI budgets (STY-08/09). Preserve Mode B grounding/honesty (STY-12/13). Images are never stored as raw base64 in the DB.

## Technical Context

**Language/Version**: Python 3.13 (Dockerfile `python:3.13-slim`); TypeScript/React 18
**Primary Dependencies**: FastAPI, Pydantic v2 (`schemas/stylist.py`); provider abstraction (local_gpu, nvidia, groq, gemini, openai, unorouter); `ColorHarmonyEngine`; OpenAI-compatible NVIDIA path; Gemini vision
**Storage**: No new persistent image storage in DB; short-TTL/discard for uploads; recommendations reference existing catalog (`OutfitItemOut`)
**Testing**: pytest with provider mocks/recordings (Mode A grounding, wardrobe influence, failover, color extraction, safety/budget); frontend (upload UI)
**Target Platform**: Vercel serverless
**Project Type**: Web application
**Constraints**: No paid AI calls in tests/planning; honest model reporting; no fabricated products; no base64 images in DB.

## Constitution Check

- **I. Evidence Before Appearance**: PASS — Mode A proven by grounding + served-model tests; failover proven by induced-failure tests.
- **IV. Honest AI & Integrations**: PASS/core — real catalog grounding, honest unavailability, truthful served-model, honest `include_wardrobe_items`.
- **Data/privacy**: PASS — images not persisted as base64; short-TTL/discard.
- **IV** (no fabricated analysis, honest fallback) and **V** (tests first, E2E): upload safety and budgets are covered by backend tests; the save-as-look flow has an authenticated browser E2E. **I** and **II**: N/A to the safety pieces. (Principle III is authorization and is not the basis for upload safety.)

No violations.

## Project Structure

```text
backend/
├── app/
│   ├── schemas/stylist.py (ChatRequest + optional images[]; derived mode)
│   ├── services/ (orchestrator: vision path, full failover, wardrobe grounding, color extraction, budgets)
│   └── (provider registry wiring; central model-ID doc/validation)
└── tests/
    ├── test_stylist_mode_a_grounding.py   # NEW (SC-001)
    ├── test_stylist_wardrobe_influence.py # NEW (SC-002, STY-03)
    ├── test_stylist_failover.py           # NEW (SC-003, STY-04)
    ├── test_stylist_color_extraction.py   # NEW (SC-004, STY-06)
    └── test_stylist_upload_safety_budget.py # NEW (SC-005)
frontend/
└── src/components/stylist/VirtualStylistDrawer.tsx (image upload, save look, honest note; a11y/i18n via workstream 010 primitives)
    scripts/stylist_*.mjs (browser keyboard, contrast and save-look probes; not in CI, see verification.md §9)
docs/
└── (central model-ID/provider registry doc — STY-16)
```

**Structure Decision**: Web app; vision reaches through the existing provider abstraction (no new transport).

## Complexity Tracking

> No violations. Reusing the existing OpenAI-compatible provider path for vision avoids a new integration layer.
