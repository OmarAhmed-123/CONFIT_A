# Feature 03 — Multi-Garment Virtual Try-On (fashn_v15)

**Status:** backend + worker shipped (this PR); Modal deploy + Vercel cutover
immediately after merge. Supersedes the single-garment `fashn_vton_segfee`
worker.

## What changed

| Piece | Before (segfee) | After (fashn_v15) |
|---|---|---|
| Garments per job | 1 (backend chained N calls) | 1–3 in **one** worker call |
| Composition | full re-render per layer (drift risk) | layer 1 segmentation-free, layer k>1 **parser-masked** (earlier layers pixel-exact) |
| Garment photos | flat-lay only | flat-lay **and on-model** (parser segments the garment; auto-detected per garment) |
| Verification | per-layer via backend chaining | per-layer inside the worker, returned in `layers[]`, aggregated honestly by the backend |

## Architecture

```
Vercel backend (tryon_service)
  └── ONE POST /process  {person, garments[1..3], overlay_mode}
        Modal app confit-vton-worker (A10G, scale-to-zero)
          └── engine.fashn_v15.render_outfit()
                ├── normalize_garments()   # canonical order tops→bottoms,
                │                          # one-pieces alone, conflicts rejected
                ├── layer 1: upstream pipeline, segmentation_free=True
                ├── layer k: upstream pipeline, parser-masked region
                │           (overlay_mode='segfree' = full re-gen, tunable)
                └── per-layer verify (no echo / not blank / real change)
                    → a non-applied layer FAILS the job (never stacked on)
```

* Upstream pipeline: **pristine** `fashn-AI/fashn-vton-1.5 @ 7c0f10af`
  (`vendor/fashn-vton-1.5`, unmodified).
* Weights: same shared Modal volume `confit-vton-fashn-weights`
  (model.safetensors + dwpose). Parser weights (~244 MB) live in
  `HF_HOME=/weights/hf-cache`; warm once with
  `modal run services/vton-worker/modal_app_v15.py::warm_parser_cache`.

## License record (honest)

* Pipeline / model / DWPose / YOLOX: **Apache-2.0**.
* `fashn-human-parser` (SegFormer fine-tune): **NVIDIA Source Code License —
  non-commercial.**
* **Owner decision (2026-10-01):** ship it while the project is early-stage;
  **swap to a licensed parser before commercial scale.**
* The swap is engineered, not promised: the parser is injected via
  `FashnV15MultiGarmentEngine(parser_impl=...)` (duck-typed `.predict()`);
  the upstream pipeline only ever calls `self.hp_model.predict(...)`, so a
  licensed replacement is a one-class change with zero upstream modification.
* Every health/response payload reports `commercial: false` + the parser
  license until the swap lands. Nothing is mislabelled.

## Cutover plan (this week)

1. `modal deploy services/vton-worker/modal_app_v15.py` → app
   `confit-vton-worker` (canonical name; the old stopped app is superseded).
2. Surgical GPU verification (2 jobs: single tops; tops+bottoms multi).
3. Warm parser cache into the volume (CPU, no GPU cost).
4. Vercel env: `VTON_WORKER_URL` / `VTON_WORKER_HEALTH_URL` /
   `VTON_WORKER_READINESS_URL` / `VTON_WORKER_PROCESS_URL` → new app URLs.
5. Production end-to-end test on Vercel.
6. `modal app stop confit-vton-worker-segfee`; delete
   `modal_app_segfee.py` + `engine/fashn_segfee.py` + `_bundled_catvton`
   (single worker file remains — no duplication).

## Tests

`backend/tests/test_vton_fashn_v15_multigarment.py` (32 tests, zero-GPU):
engine ordering/conflicts/photo-type detection, fake-pipeline composition
(masked vs segfree, sequential layering, honest abort), worker request
contract, backend registry honesty, vendored-upstream integrity, provenance
record. `test_vton_person_reference.py` re-pinned to the ONE-call contract
(+ honest unverified-layer reporting). Full suite: **3392 passed / 0 failed**.
