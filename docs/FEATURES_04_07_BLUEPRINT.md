# Features 04–07 — Engineering Blueprint (model-per-feature install plan)

**Status:** staged. Every feature below is fully specified with pinned sources,
licenses, integration design and a GPU budget. Execution order: one feature at
a time, each deployed → surgically GPU-verified on Modal → cut over to Vercel
production → live-tested on https://confit-a.vercel.app before the next one.
**Blocked on:** Modal workspace `omarsafealden` has no payment method attached
(2026-10-02: every new GPU deploy is rejected with "Please add a payment
method"). Existing deployed apps (moda-embed, vton-worker-segfee) keep serving.

Already live + verified on production (2026-10-02):
- **02 Visual Search** — HopitAI/moda-fashion-distilled on `confit-moda-embed`
  (self-match test: product ranked #1 with similarity 200 = embedding path).
- **Stylist** — NVIDIA nemotron-3-super primary; Arabic replies; budget
  parsing (٣/٤ آلاف, ١٥٠٠ جنيه all correct); 3392-test suite green.
- **03 VTON multi-garment** — code merged (PR #259/#260); worker staged at
  `services/vton-worker/modal_app_v15.py`; production runs the segfee chain
  until the v15 worker deploys (rollback-protected).

---

## 04 — Smart Wardrobe: `SCHP-ATR-18` + `BiRefNet` (both MIT)

| | Source | License | Size |
|---|---|---|---|
| Parser | `pirocheto/schp-atr-18` (HF; SCHP ATR, 18 classes, mIoU 82.29%, Transformers AutoModel + ONNX export) | MIT | ~100 MB |
| Cutout | `ZhengPeng7/BiRefNet` (0.2B; `BiRefNet_lite` 44.4M for warm-path speed) | MIT | 44–900 MB |

**Worker** `services/wardrobe-worker/` (new, one app: `confit-wardrobe-worker`, L4):
`POST /extract` — person/outfit photo → SCHP-ATR parse (18-class labels) →
per-garment region masks (ATR labels: upper-clothes, pants, skirt, dress,
belt, bag, scarf, outer) → BiRefNet matting per detected garment → cropped,
transparent-background PNG + slot classification (SLOT_TO_CATEGORY shared
with the VTON engine vocabulary) + honest per-garment confidence.

**Backend** wiring: existing `wardrobe_service` (G4 lifecycle tests already
pin the API) gains a real extraction provider — upload photo → worker →
wardrobe items with cutout images; keyword/fallback path stays explicit.
**GPU budget:** 1 cold start + 1 verification extraction (~20 s) at cutover.

## 05 — Gap Analysis + body measurement: `Landmarks2Anthropometry`

Model source to pin at build time (research repos; the exact checkpoint gets
vendored + provenance-filed exactly like fashn-vton-1.5). Pipeline:
person photo → whole-body landmarks → anthropometry (chest/waist/hip/inseam
estimates) → **hard disclaimer: ±2–3 cm** shown in API + frontend, stored with
every measurement row (`measurement_method: "ai_estimate"`,
`accuracy_note: "±2–3 cm"`), never presented as tailor-grade.
**Worker:** `confit-anthropometry-worker` (L4), `POST /measure`.
**Backend:** `gap_analysis_service` exists; wire the measurement provider,
keep the size-chart comparison (pure CPU, already seeded) as the fallback
input path (manual measurements remain first-class).

## 06 — Outfit Builder: `OutfitTransformer` + `TATTOO`

| | Source | Notes |
|---|---|---|
| Compatibility | `owj0421/outfit-transformer` (CVPR 2023 impl; CP AUC 0.93, FITB 67.10; +CLIP 0.95/69.24 SOTA) | item-set transformer, self-attention over outfit items |
| Type-aware eval | TATTOO benchmark (type-aware outfit compatibility) | pinned at build time |

**Worker** `confit-outfit-worker` (L4): `POST /compatibility` (score a set),
`POST /fill-in-the-blank` (complete an outfit from the catalogue).
Embeddings: item images via the **existing** moda-fashion-distilled worker
(no new embedding stack — no duplication), text via FashionCLIP2.0 in 07.
**Backend:** `outfit_controller` gains a compatibility provider with honest
fallback (heuristic layering already exists in SlotLayeringEngine).

## 07 — Brand Portal / Tagging: `FashionCLIP2.0` + `GLiNER2`

| | Role | Notes |
|---|---|---|
| FashionCLIP2.0 | fashion-domain multimodal embeddings for product tagging/auto-cataloging | pinned at build time (HF) |
| GLiNER2 | zero-shot NER over product titles/descriptions (brand, material, color, attribute extraction) for the Brand Portal | pinned at build time |

**Worker** `confit-tagging-worker` (L4): `POST /tag` — image → FashionCLIP2.0
embedding + attribute extraction; text → GLiNER2 entities. Tag vocabulary
shared with the catalogue taxonomy (no parallel taxonomies).
**Backend:** Brand Portal auto-tagging + a `tagging_provider` with explicit
provenance (model_used per tag batch).

---

## Execution rules (all features)

1. One feature at a time; GPU verification BEFORE cutover; scale-to-zero
   everywhere (scaledown_window=300) — the subscription is for live demos,
   not idle burn.
2. No app duplication on Modal: exactly one app per capability, canonical
   names (`confit-wardrobe-worker`, `confit-anthropometry-worker`,
   `confit-outfit-worker`, `confit-tagging-worker`) — plus the existing
   `confit-moda-embed` and the single VTON app `confit-vton-worker`.
3. Vendored models get provenance files (source, SHA, license) like
   `vendor/fashn-vton-1.5/UPSTREAM_PROVENANCE.txt`.
4. Every feature ships zero-GPU unit tests (contract + honesty gates) and
   merges through CI (backend/frontend/release-gate) before deploy.
5. Production cutover = Vercel env swap + redeploy + live verification on
   https://confit-a.vercel.app (the world-facing surface).
