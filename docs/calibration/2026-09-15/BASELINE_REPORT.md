# BASELINE REPORT — FASHN single-garment pipeline, unmodified (2026-09-15)

Worker under test: `confit-vton-worker-segfee-eval` (separate eval Modal app;
production `confit-vton-worker-segfee` untouched). Engine `fashn_vton_segfee`
(FASHN v1.5 fork @ 7c0f10af, Apache-2.0) UNMODIFIED. GPU: A10.

## Run-1 (pipeline validation; archived as `baseline_runs_run1.json`)
25 inferences (24 singles + 1 smoke) on MIXED-orientation person fixtures.
Purpose: validate the eval deployment + request/response contract. Superseded
by run-2 for all protocol numbers. Findings that motivated run-2:
- AI-generated person fixtures came out in mixed orientations (1408×768 and
  768×1376). FASHN renders at the INPUT's aspect ratio (`output_aspect`
  declared-never-applied, repo defect D1) → output dims were 576×314 and
  482×864 depending on input aspect. Uncontrolled input aspect would confound
  the paired benchmark → persons standardized (see below), full re-run.
- cold start (first request after deploy, request-triggered): **17.8 s** MEASURED.

## Person standardization (applied to all arms)
`evaluation/scripts/standardize_persons.py`: deterministic bg-bbox-crop + 4%
margin + 3:4 pad (bg color) + resize 768×1024. Per-fixture bbox + transform +
bg color recorded in `person_manifest.json`; originals preserved as `.orig.jpg`.

## Run-2 (CANONICAL — `baseline_runs.json`)
- **54/54 jobs HTTP 200; 54/54 outputs saved; failure rate 0%** (MEASURED).
- Output dimensions: **576×768 uniform across all 54 jobs** (input 768×1024 →
  engine renders at input aspect, MEASURED — D1 behavior, not a regression).
- Determinism: identical job re-run → **identical sha256**
  (65aa1a86bbdc… both runs) — **DETERMINISM VERIFIED** (MEASURED; engine seed 42).

### Latency (MEASURED, per job)
| Arm | n | wall s (mean/min/max) | engine exec ms (mean) | worker total ms (mean) |
|-----|---|----------------------|----------------------|------------------------|
| SINGLE | 24 | 19.48 / 19.06 / 23.09 | 18520 | 18710 |
| N=2 (chained) | 24 inferences (12 outfits) | 19.53 / 19.40 / 20.61 | 18535 | 18715 |
| N=3 (chained) | 6 inferences (2 outfits) | 19.55 / 19.49 / 19.66 | 18569 | 18748 |

Each chain layer is a full independent inference → chain latency = N × ~19.5 s
(client-side, no shared state).

### VRAM (MEASURED via /health, A10)
- idle after load: allocated 1.82 GB / reserved 3.83 GB (before run)
- after full run: allocated 1.83 GB / reserved 3.50 GB (after run)
- model footprint ≈ 1.8–3.8 GB of 24 GB → single-GPU headroom for one A10
  worker is not the constraint; batching/throughput is (one job at a time,
  `max_inputs=1`).

### Worker self-verify (repo-attested check, MEASURED outcomes)
`verify.PASS` (echo/blank/genuine-change check): **44/54 PASS; 10 FAIL** —
the 10 are weak-change renders (e.g. white tee over white tank, pixel change
< 1.0). The worker does NOT fail the job (verify is advisory in current code)
— recorded as evidence that a genuine failure mode exists and is detectable by
the worker's own check.

### Cold start (MEASURED)
- VTON eval worker: first request 17.8 s (container boot + model load,
  request-triggered; volumes pre-loaded weights).
- VLM eval worker (Qwen2.5-VL-7B): first request 23 s.
- Steady-state: no cold starts observed within run (container warm).

## Reproducibility
- run record `evaluation/results/baseline_runs.json` (gitignored) carries per
  job: person/garment sha256 prefixes, output sha256, dims, worker timings,
  verify block. NO image bytes in any record (enforced by test).
- fixture set + generation scripts in git (deterministic, seeds recorded).
- eval worker code = production code + 2 identifiers + 1 path (diff in
  `evaluation/modal/README.md`).
