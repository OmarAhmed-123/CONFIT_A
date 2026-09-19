# BENCHMARK REPORT — FASHN single vs chained N=2 vs chained N=3 (2026-09-15)

Protocol: `docs/calibration/2026-09-15/PROTOCOL.md` (FROZEN before run-2).
Paired evaluation: same persons, garments, preprocessing, resolution across arms.
All numbers MEASURED from run-2 (54 inferences, 38 outfits) unless tagged.

## Arms actually run
| Arm | Outfits / inferences | Notes |
|-----|---------------------|-------|
| 1. FASHN single baseline | 24 / 24 | one garment per job, production-identical behavior |
| 2. FASHN chained N=2 (eval mode) | 12 / 24 | top+bottom (7), inner+outer (3), worst-case bulky-over-slim + dark-on-dark (2) |
| 3. FASHN chained N=3 (eval mode) | 2 / 6 | shirt→trench→trousers; long-coat→jacket→chinos (long-over-short stress) |
| FastFit | NOT RUN | LICENSE-GATED (LavieAI NC) — excluded per scope |
| API editors | NOT RUN | no privacy approval — excluded per scope |

## Headline measurements
| Quantity | SINGLE | N=2 | N=3 | Tag |
|----------|--------|-----|-----|-----|
| success rate | 24/24 (100%) | 24/24 inferences (100%) | 6/6 (100%) | MEASURED |
| wall latency / layer | 19.48 s (19.06–23.09) | 19.53 s | 19.55 s | MEASURED |
| engine inference / layer | 18520 ms | 18535 ms | 18569 ms | MEASURED |
| end-to-end per outfit | ~19.5 s | ~39 s (2×19.5) | ~58.5 s (3×19.5) | MEASURED (sum of layer walls) |
| VRAM allocated / reserved | 1.82→1.83 GB / 3.83→3.50 GB | same | same | MEASURED (/health before/after) |
| cold start (first request) | 17.8 s (run-1) | — | — | MEASURED |
| determinism (re-run sha256) | identical | — | — | VERIFIED |
| output dims | 576×768 uniform | same | same | MEASURED |
| worker verify PASS | 24/24 minus weak-change cases | 44/54 overall | — | MEASURED |

**No VRAM growth with chain depth** (each layer is an independent inference on
the same 1.8 GB footprint) — the cost of chaining is TIME (×N), not memory.

## Qwen2.5-VL-7B judge (config v1 FROZEN — `evaluation/config/judge_config.yaml`)
- Deployment `confit-vlm-worker-eval`, revision cc594898…, greedy decoding
  (do_sample=False), temperature-0-equivalent, labeled composite
  (reference garment LEFT, output RIGHT — fixed order), 2 calls/sample.
- **Consistency: 38/38 samples, 38/38 two-call agreement (100%)** on complete
  pairs (2 initial transport failures retried and completed; no judge
  disagreement observed). MEASURED.
- Latency per call: mean 5.4 s (3.6–35.2 s; the 35 s is a cold container).

| Arm | n | garment /10 | layering /10 | styling /10 |
|-----|---|-------------|--------------|-------------|
| SINGLE | 24 | 7.83 (min 0) | 9.17 | 8.67 |
| N=2 | 12 | 8.00 | 8.67 | 8.67 |
| N=3 | 2 | 8.00 | 8.00 | 8.50 |

- The two **0-garment** singles (S_g010 white long-sleeve shirt, S_g012 black
  long-sleeve tee) are genuine rendering failures (output ≈ input; judge notes
  quote the visible base clothing). MEASURED failure cases, retained as
  negative evidence — not averaged away.
- N=3 n=2 → UNDERPOWERED for any claim (documented; more N=3 pairs needed
  before layering-depth conclusions).
- Judge ≠ ground truth (opinion source per task §23). Human comparison:
  PENDING raters.

## Garment-fidelity observations (deterministic metrics, run-2)
- garment_delta_e_mean good-range 7.8–57.2 (mean 23.9) — systematic
  flat-lay→on-body bias; see CALIBRATION_REPORT for the normalization follow-up.
- Pattern fixtures (g005 stripes, g006 check): period retained in 3/4 good
  renders (texture_period_ok 0.75) — one engine case lost the period.
- OCR g009 "STUDIO 2026": detected exactly (score 1.0) on the single render.
- Logo (g008) covered by DINOv2+edge proxies (no invented detector).

## What this benchmark does NOT prove (scope honesty)
- N=2/N=3 results are CHAINED single-garment inferences (client-side, the
  backend's existing layering pattern) — this is evidence about the chaining
  REGIME, not about native multi-garment rendering.
- 10 persons / 24 procedural garments ≠ a full coverage study; body-type and
  garment diversity is a follow-up (manifest-driven, no protocol change).
- No production gate is implied by any number here (task §31).

## Cleanup checklist (phase end)
- [ ] `modal app deploy --delete confit-vton-worker-segfee-eval` (or dashboard)
- [ ] `modal app deploy --delete confit-vlm-worker-eval`
- [ ] `modal secret delete confit-vton-eval-admin-token confit-vlm-eval-admin-token`
- [ ] delete `evaluation/.eval_env`, `.eval_urls`, `.eval_vlm_urls` (tokens)
- [ ] rotate any Modal token used (advisory)
