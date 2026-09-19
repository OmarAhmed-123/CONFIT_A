# Phase 0.5 — Calibration, Metric Validation & Benchmark Harness (2026-09-15)

Purpose: prove the MEASUREMENTS are trustworthy before any production gate.
Nothing here changes production behavior (see BENCHMARK_REPORT § production impact).

## Documents
| File | Content | Status |
|------|---------|--------|
| PROTOCOL.md | Frozen arm definitions, pairing, worker-under-test, measured quantities, budget | FROZEN |
| METRICS.md | Metric inventory, licenses, roles, proxy-vs-validated distinctions | complete |
| RUBRIC.md | Frozen 8-dimension human rubric + rater protocol + tooling | FROZEN; raters PENDING |
| LICENSE_AUDIT.md | Full dependency/weight license register with sha256 manifests | complete |
| BASELINE_REPORT.md | Run-1 + run-2 baseline measurements (latency, VRAM, dims, determinism) | data being written |
| CALIBRATION_REPORT.md | Per-metric distributions, AUC, FPR/FNR candidate points, status assignments | data being written |
| ../benchmarks/2026-09-15/BENCHMARK_REPORT.md | Arm comparisons (single / N=2 / N=3), judge results, cold start | data being written |

## Results data (gitignored)
`evaluation/results/` — baseline_runs.json (+ run-1 archive), offline eval,
known-bad, calibration.json/csv, judge results. Output images carry sha256
sidecars; no image bytes in any record (enforced by test).

## Stop-condition compliance
No stop condition tripped during execution. Deviations from plan (all
documented, none silent):
1. Tesseract not installable (no root) → EasyOCR (Apache-2.0) substitution.
2. Person fixtures: 10/40 generated this turn (image-gen limit) → canonical set
   = 10 stratified synthetic persons (2 body types × pose/lighting/hair/
   accessory/tattoo variants); 30-person extension is a follow-up with no
   protocol change (manifest-driven).
3. Garment fixtures: procedural flat-lays (deterministic, exact ground truth)
   instead of photographic product shots — documented as a fidelity limitation
   of the reference set, not of the pipeline.
4. DINOv2 revision pinned to verified main sha f9e44c81… (initial placeholder
   revision did not exist on HF; corrected before first use).
