# BASELINE & BENCHMARK PROTOCOL (FROZEN) — Phase 0.5 §24-26

**FROZEN 2026-09-15 BEFORE the final measurement runs (run-2).**
Protocol changes after freezing require a new version + full re-run.

## Arms (paired evaluation — same person, garments, preprocessing, resolution)
| Arm | Definition | Status |
|-----|-----------|--------|
| 1 — FASHN single baseline | current production FASHN single-garment path, unmodified, one garment per job | MANDATORY |
| 2 — FASHN chained N=2 (eval mode) | client-side sequential chain: layer-1 output = layer-2 person input (same pattern as CONFIT backend slot layering). top+bottom and inner+outer pairs | MANDATORY (initial production candidate) |
| 3 — FASHN chained N=3 (eval mode) | 3-layer chains incl. worst cases (long-inner→outer→bottom; long-over-short; bulky-over-slim) | EVAL REGIME ONLY — never a production claim |
| FastFit arm | NOT RUN — license-gated (LavieAI NC) | EXCLUDED |
| API-editor arms | NOT RUN — no privacy approval | EXCLUDED |

Chaining is CLIENT-SIDE: the eval harness (this repo) performs the sequential
compositing calls against the eval worker. **Zero production code change.**

## Worker under test
- Deployment: `confit-vton-worker-segfee-eval` — a SEPARATE Modal app from
  production `confit-vton-worker-segfee`. Code = production `services/vton-worker/`
  with exactly 2 identifier changes (app name, secret name) + 1 engine-path
  correction (points at the same vendored engine dir) — diff documented in
  `evaluation/modal/README.md`.
- Engine: `fashn_vton_segfee` = FASHN v1.5 fork @ 7c0f10af (Apache-2.0), UNMODIFIED.
- GPU: A10 (allocated; requested A10G tier). Weights: Modal volume
  `confit-vton-fashn-weights` (shared read-only with production).
- Job contract: POST /process, X-VTON-Admin auth, seed fixed by engine (42),
  `gender_mode=infer_from_image` (default), `output_aspect` declared but
  **NEVER APPLIED** (repo defect D1 — engine renders at input aspect ratio;
  documented, not "fixed", in this phase).

## Input standardization (applied to ALL arms, identical)
- Persons: 10 synthetic AI fixtures (no real persons) standardized to 768×1024
  (3:4) by deterministic bg-bbox-crop + pad + resize
  (`evaluation/scripts/standardize_persons.py`; per-fixture bbox + transform
  recorded in `person_manifest.json`; originals preserved as `.orig.jpg`).
- Garments: 24 procedural flat-lay fixtures (800×1000, deterministic PIL,
  seed=20260915) with exact ground-truth metadata (color hex, pattern type,
  stripe count, text string, logo) in `garment_manifest.json`.

## Measured quantities (every value tagged)
- latency: wall (client), `execution_time_ms` (engine inference), `total_time_ms` (worker) — MEASURED
- VRAM: /health `gpu_memory.allocated_gb / reserved_gb` before/after — MEASURED
- cold start: first-request latency after deploy — MEASURED (run-1: 17.8 s VTON; 23 s VLM)
- output dims: per job — MEASURED
- success/failure rate: per job http + verify block — MEASURED
- determinism: identical job re-run, sha256 comparison — MEASURED
- identity/garment/pose/layering scores: offline metric suite (METRICS.md) — MEASURED
- human scores: PENDING raters — UNMEASURED
- Qwen judge scores: MEASURED after run (config frozen in `config/judge_config.yaml`)

## Determinism & reproducibility
- engine seed = 42 (hard-coded in engine, repo-attested)
- fixture generation deterministic (seed 20260915)
- every input/output image sha256-recorded in run records (no bytes in logs)
- run record: `evaluation/results/baseline_runs.json` (run-1 archived as
  `baseline_runs_run1.json` — mixed-orientation inputs, pipeline-validation only)

## Budget guardrails (stated BEFORE runs)
- run-2 matrix: 38 outfits / 54 inferences + 1 determinism re-run ≈ 55 × ~20 s
  ≈ 20 min GPU (A10).
- judge: 2 calls/sample on singles + final chain layers (≈ 34 samples → 68 calls).
- no production deployments touched; eval apps deleted at phase end (cleanup
  checklist in BENCHMARK_REPORT.md).
