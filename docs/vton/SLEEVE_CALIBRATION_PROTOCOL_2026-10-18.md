# VTON Sleeve-Gate Calibration Protocol — 2026-10-18

Status: **INTEGRATED, DEFAULT OFF, ENFORCEMENT BLOCKED** pending this protocol's
completion on the current engine build. The gate code, mode plumbing, manifest
validation, and the harness (`scripts/vton_sleeve_calibration.py`) ship now;
the calibration numbers do NOT — the historical 2026-09 measurements are
reference only (see `backend/app/services/vton_sleeve_gate.py` docstring) and
were explicitly recorded as "calibration margin, not a statistical guarantee".

## Approval contract (all required before enforce is legitimate)

1. **Dataset (immutable, versioned).** ≥50 real captured cases for the CURRENT
   engine build: for each, the layer's rendered output, its exact layer input,
   and the exact garment image sent to the engine, plus labels —
   `expected_sleeves` (human ground truth), garment type, pose class,
   occlusion class, quality class, declared `sleeve_length`. Collect via
   `VTON_SLEEVE_GATE_MODE=observe` on staging (the gate records its per-layer
   verdicts and coverage into every job's `metrics_json`), then capture the
   artifacts alongside the job. Freeze with
   `python3 scripts/vton_sleeve_calibration.py freeze-dataset --dir DATASET`
   → `approved.jsonl` + `dataset.sha256` + deterministic 60/40
   calibration/evaluation split (`splits.json`). Frozen datasets are
   immutable; new data = new directory = new version.
2. **Three independent human raters** review every case before it enters
   `approved.jsonl` (per-case verdict + identity recorded in `label.json`).
   AI/synthetic judgments and self-sign-off are not approvals; the harness
   refuses to freeze cases with fewer than 3 distinct rater names, and
   `publish-manifest` refuses again at manifest time. A `synthetic: true`
   case can never enter an approved dataset.
3. **Threshold selection** on the CALIBRATION split only, by the encoded rule:
   the most conservative pass-threshold achieving ZERO false accepts on that
   split (never a line moved to raise a displayed success rate; all
   thresholds are constrained to the documented sane envelope in
   `vton_sleeve_gate._THRESHOLD_BOUNDS`).
4. **Evaluation split reported separately** (FAR/FRR, precision, coverage,
   inconclusive rate, per-subgroup table). A manifest with missing evaluation
   numbers is rejected by runtime validation.
5. **Engine binding.** The manifest records `gate_version`, `engine`,
   `engine_build.worker_git_sha` and `model_used` of the build that produced
   the renders. The gate re-validates this at startup and per render: after
   ANY engine upgrade or gate-version change the manifest is invalid and
   enforce refuses to initialize until recalibration. Revocation: set
   `"revoked": true` in the manifest (or unset the env var) — the gate fails
   closed, never open.

## What is required from the environment (currently unavailable here)

* A reachable VTON GPU worker running the current `fashn_vton_segfee` build
  (staging), with `VTON_WORKER_URL` + `VTON_WORKER_ADMIN_TOKEN`. This
  workspace has **no GPU/engine credentials** — nothing in this PR exercises
  the gate against a live engine, and no calibration numbers are claimed.
* An operator to run the 5 steps above (≈one staging work-session with
  observe mode + a review session for the three raters).

## Mode semantics (shipped, default off)

| mode | behavior |
|---|---|
| `off` | no probe, no claims — today's production behavior |
| `observe` | probe + record honest verdicts in `metrics_json` (and the sync response's `sleeve_gate`); **never blocks** a render |
| `enforce` | probe + REFUSE fails the job/render with canonical `VTON_SLEEVES_NOT_VERIFIED` (502 class), **no image delivered**; additionally refuses to initialize (startup) or to serve (per render) without a valid, current manifest; an unrecognised mode value fails startup |

`VTON_SLEEVE_GATE_MODE=off` is the default and is proven by tests
(`backend/tests/test_vton_sleeve_gate_unit.py`,
`backend/tests/test_tryon_sleeve_gate_integration.py`). Missing verification
(undecodable images, missing garment reference, degenerate dominant color,
undeclared catalog metadata) is always NOT_VERIFIED → refuse under enforce,
recorded under observe — never a pass.

## Historical evidence inventory (reference only — do NOT treat as current approval)

Recovered from the 2026-09-15..19 line (`/home/user/sleeve_ref/` outside this
repo; the audit report shipped with it): 57 measured artifacts (50-row matrix
+ 7 adversarial composites), thresholds REFUSE<0.15 / NOT-VERIFIED
[0.15,0.35) / PASS≥0.35 + anatomy channels 0.10/0.15/0.05, measured class-E
false-pass 0.2965, thin margins documented (E-1 1.01x; TP-side new-skin
1.11x), known residual limitations (dark-on-dark over-refusal, white-on-white
blind spot, composition-specific margins). The historical report's own words:
"calibration margin, not a statistical guarantee"; rater sign-off for that
line predates this repo's gate version and is not transferable.
