# Feature 06 (Outfit Builder) — Completion Report
**Date:** 2026-10-03 · **Status:** LIVE on production · PR #267 (merged 3fb46c4)

## What shipped

**Worker** `confit-outfit-worker` (Modal, CPU-only, scale-to-zero — 6th distinct app, zero duplicates):
- OutfitCLIPTransformer (bigohofone/outfit-transformer @ eef4be5, MIT, vendored at
  `vendor/outfit-transformer/` with full provenance): frozen FashionCLIP item encoder +
  6-layer transformer, Polyvore-trained. Upstream-reported CP AUC 0.95 / FITB 69.24 (+CLIP SOTA).
- `POST /compatibility` → sigmoid score + type-aware block (duplicate slots, coverage,
  slot→Polyvore mapping) + advisory TATTOO-style aesthetic axes (color/style/occasion/
  season/material/balance) via deterministic CLIP text-anchor projection.
- `POST /fill-in-the-blank` → CIR: query embedding of partial outfit + target category;
  candidates ranked by cosine in the learned space.
- Weights: Modal volume `confit-outfit-weights` (769MB × 2, sha256s in provenance).
  FashionCLIP encoder baked into image; complementary model lazy-loads on first FITB.
- URLs (label-stable): `https://omarsafealden--confit-outfit-worker-{compatibility,
  fill-in-the-blank,health,readiness}.modal.run`
- Warm CPU inference ~0.6-0.9s. Cold start ~30-60s (checkpoint from volume).

**Backend** (all honestly labeled — engine / compatibility_source / reason on every response):
- `OutfitCompatProvider` (TaggingProvider pattern; full-endpoint URLs; one attempt).
- `/stylist/compatibility`: model score when configured + all items have images;
  pre-06 heuristic numbers otherwise (legacy-equality pinned by test).
- `/outfits/fill-in-the-blank` (authed): CIR ranking over explicit or slot-filtered
  candidates; rules-engine ranking as labeled fallback.
- Slots via `SlotLayeringEngine.map_category_to_slot` (single source of truth).

## Live verification (2026-10-03, confit-a.vercel.app)

| Test | Result |
|---|---|
| /stylist/compatibility [blazer 1 + trousers 4 + oxfords 6] | engine=**outfit_transformer_clip**, score **70** (model 0.7046), axes overall 43 |
| /stylist/compatibility [dress 5 + sandals 7 + blazer 1] (clash) | score **54** (model 0.5378) — Δ16 separation |
| /outfits/fill-in-the-blank outfit=[1,4] target=footwear candidates=[6,7,5] | **oxfords #1** (0.0407) > sandals (0.0352) > silk dress (0.015) |
| FITB default pool (no explicit candidates) | footwear sweep works, 1.5s, same ranking |

Deployed-worker type-aware eval (TATTOO rubric, arXiv:2509.23242): **10/10 passed**
(formal 0.7237 > type-clash 0.6169; FITB ranks oxford > silk dress; auth, refusals,
duplicate-slot, honest contract).

## Test totals
50 worker pure-logic/shell (zero-GPU) + 21 backend contract + 10 live deployed-worker
eval + full backend suite green (only pre-existing failure: v15 uncommitted diff, out of
scope by standing decision). CI on PR #267: all repo checks green.

## Blueprint deviation (documented in vendor provenance)
Blueprint said reuse moda-embed embeddings; the trained checkpoint requires its OWN
FashionCLIP encoder space (aggregation=concat). FashionCLIP already in fleet (tagging
worker) → no new model family, no cross-worker calls. TATTOO = eval rubric + advisory
axes (pinned citation), NOT shipped as an MLLM pipeline.

## GPU platform keys (stored in vault, verified 2026-10-03)
- **Baseten ✓** (management + inference APIs reachable; 0 models; leading GPU candidate)
- HuggingFace ✓ (OmarSaifElDin; fine-grained token, inference perms)
- Cerebrium ? (control plane = CLI only; REST 502)
- Kaggle ? (unverified)
Feature 06 needed NO GPU (ResNet-free CLIP variant is CPU-friendly). Keys reserved for
the next genuinely-GPU need (e.g. feature 03 multi-garment fashn v1.5, still gated on the
Modal GPU card decision).

## Notes
- Vercel env (production, encrypted): OUTFIT_WORKER_COMPAT_URL, OUTFIT_WORKER_FITB_URL,
  OUTFIT_WORKER_ADMIN_TOKEN → manual redeploy dpl_Adm88f1kYcSZ9e29tNbQZjBgUTJT (READY).
- Modal secret `confit-outfit-admin-token` (token also in vault).
- External "Workers Builds: confit-a" check (Cloudflare connector) fails on main
  including pre-PR commits — pre-existing, outside this feature's scope.
- `services/vton-worker/modal_app_v15.py` local diff remains uncommitted (standing rule).
