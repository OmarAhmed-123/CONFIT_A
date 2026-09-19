# SLEEVE GATE v2.4 — FROZEN STATE SPEC (Phase 7 P0, 2026-09-19)

Purpose: freeze the exact current gate implementation before any further
change, per the Phase 7 P0 mandate. No threshold experimentation occurs
against an unfrozen state. This document records what IS in production;
the threshold sweep (P1-B) is evaluation-only memory, not code.

**Frozen implementation:** `backend/app/services/vton_sleeve_gate.py`
(887 lines), called from `backend/app/services/tryon_service.py`
(`evaluate_layer_sleeves`, ~line 930) and surfaced by
`backend/app/controllers/tryon_controller.py`.

## 1. Exact constants (line numbers at freeze time)

| line | constant | value | role |
|---|---|---|---|
| 241 | `FOREARM_PASS_THRESHOLD` | **0.35** | S1: best-arm changed garment-color coverage PASS bound |
| 242 | `FOREARM_FAIL_THRESHOLD` | **0.15** | S1: best-arm coverage below this = sleeves absent |
| 243 | `DELTA_E_RADIUS` | **40.0** | CIE-Lab ΔE radius for "garment-colored" |
| 250 | `FOREARM_CHANGE_THRESHOLD` | **20.0** | ΔE(output, input) change condition (input-side contamination immunity) |
| 253 | `FOREARM_BANDS` | left (0.52, 0.70, 0.40, 0.55), right (0.28, 0.46, 0.40, 0.55) | fixed fractional bands (x0, x1, y0, y1); 3-px sampling stride |
| 258 | `SLEEVE_RELEVANT_SLOTS` | {upper_inner, upper_outer, dress} | slots with long-sleeve construction |
| 259 | `_NON_LONG_SLEEVE_VALUES` | {short, none} | catalog declarations with no long-sleeve expectation |
| 283 | `ANATOMY_NEW_SKIN_REFUSE` | **0.10** | S5: best-arm NEW-skin outer-band refuse bound (v2.3) |
| 299 | `ANATOMY_WRIST_REACH_REFUSE` | **0.05** | S6: best-arm wrist-reach refuse bound (v2.3) |
| 314 | `SKIN_LAB_WINDOW` | l 25–85, a 7–25, b 7–31 | calibrated human-skin window (Phase 5 calibration; do not revert to the old 8–30/10–55 window) |
| 317 | `ANATOMY_OUTER_FRACTION` | 0.65 | arm-side outer region of each band (excludes torso edge bleed) |
| 320 | `ANATOMY_WRIST_FRACTION` | 0.35 | wrist zone = bottom 35% of the band |
| 372 | `ANATOMY_ANY_SKIN_REFUSE` | **0.15** | **S5b: best-arm ANY-skin (new or not) outer-band refuse bound (v2.4)** |

**Confirmation:** `ANATOMY_ANY_SKIN_REFUSE = 0.15` IS the production
constant (line 372). There is no alternate tau anywhere in the file.

## 2. Exact decision order (evaluate_sleeves_sync)

1. `slot_type ∉ SLEEVE_RELEVANT_SLOTS` → **N/A** ("slot '…' has no long-sleeve construction to verify").
2. `sleeve_length ∈ {short, none}` → **N/A** ("catalog declares sleeve_length='…' — no long-sleeve expectation").
3. `sleeve_length ≠ long` (undeclared/unknown) → **REFUSE** (AT-19: never guess; safe explicit refusal).
4. Garment dominant color unmeasurable (degenerate, white-on-light blind spot) → **REFUSE**.
5. Probe exception → **REFUSE** (fail-safe, never a silent pass).
6. `best = max(coverage)` over the two bands:
   - `best ≥ 0.35` (coverage PASS path) → run anatomy probes (exception → REFUSE):
     - `ns_best = max(new_skin_outer) ≥ 0.10` → **REFUSE** (class-E channel)
     - `sa_best = max(any_skin_outer) ≥ 0.15` → **REFUSE** (asymmetric-drop channel, v2.4)
     - `wz_best = max(wrist_reach) < 0.05` → **REFUSE** (partial-drop channel)
     - else → **PASS** (reason cites coverage + all three anatomy readings)
   - `best < 0.15` → **REFUSE** ("long sleeves NOT present")
   - `0.15 ≤ best < 0.35` → **REFUSE** ("NOT VERIFIED … indeterminate; refusing rather than claiming success")

All four REFUSE paths are monotone: S5/S5b/S6 can only add a REFUSE on
the coverage-PASS path; they never convert a REFUSE into a PASS.

## 3. Exact status codes and error taxonomy

- Gate statuses: `N/A` | `PASS` | `REFUSE` (dict field `status`; human
  `reason` safe to store in job metrics; `coverage`/`anatomy` per-arm
  measurements included).
- REFUSE → `SleevesNotVerifiedError` via `raise_if_refused` (line 738) →
  job error string contains `VTON_SLEEVES_NOT_VERIFIED` →
  `tryon_service.py` maps to error_code `VTON_SLEEVES_NOT_VERIFIED`
  (line ~1070) → controller returns **HTTP 502** with
  `{"error": {"code": "VTON_SLEEVES_NOT_VERIFIED", "message": …}}` on
  BOTH try-on endpoints (lines 215–221, 276–282). No image is staged or
  delivered.
- Pre-existing taxonomy (not added by v2.4): `VTON_LAYER_NOT_APPLIED`
  (502, engine did not apply the garment — the low-contrast no-op
  path), `VTON_INPUT_INVALID`, `VTON_OUTPUT_INVALID`, `VTON_TIMEOUT`
  (504), `VTON_WORKER_UNAVAILABLE` (502), `VTON_WORKER_NOT_READY`.
  v2.4 added no new public error code.

## 4. Exact regression tests (frozen set)

`backend/tests/test_sleeve_gate_regression.py` (42 passed / 1 skipped):
- v2.2 coverage-channel pins (L1 defect refused, E-1/C-07/AT-16b/L2
  dress pass, thin-margin boundary).
- v2.3 pins: class-E refused (S5), partial-drop refused (S6),
  S5/S6 necessity.
- v2.4 pins:
  - `test_v24_refuse_asymmetric_drop_on_exposed_arm_input` (hermetic
    composite; asserts the any-skin mechanism, τ 0.15).
  - `test_replay_p1b_asymmetric_drop_composite_refused` (real
    Phase-6 adversarial artifact replay; skip-graceful if the gitignored
    PNG is absent).
- `test_gate_pass_low_margin_positive` — corrected in Phase 6 (the old
  version pinned the one-arm FP as "low-margin positive"; now pins the
  S1 0.35 boundary with the measured E-1 background-bleed composition).
  Documented in the Phase 6 report §E4; no assertion was changed to
  force a pass.

`evaluation/tests/test_sleeve_v23_matrix.py` (52 passed): the 50-row
decision table + adversarial composites, all asserting the v2.4
behavior (identical to v2.3 on the 50 rows; all 6 drops refused).

## 5. Production-code purity check (P0 items 7–8)

- **0.15 is the production constant:** yes (line 372; §1).
- **No experimental alternatives in production code:** verified by
  inspection — the only per-arm-AND, τ=0.10/0.20, and landmark/mediapipe
  variants exist in evaluation probes
  (`evaluation/probes/p6_sleeve_v24_measure.py`,
  `p6_sleeve_p1c_localization.py`) and their results JSONs, never in
  `vton_sleeve_gate.py`. Grep for `mediapipe|landmark|per-arm AND` in the
  production file: zero hits outside comments.
- **No probe-specific monkeypatch in production:** the production path
  (`tryon_service.py` → `evaluate_layer_sleeves` →
  `evaluate_sleeves_sync`) takes only (slot_type, sleeve_length,
  output/input/garment images). Probes import the same pure functions
  but apply no patches to production code; no `unittest.mock` or global
  mutation exists in the service/controller path.
- **v2.4 = v2.3 + S5b only:** S1/S5/S6 logic and thresholds byte-identical
  to v2.3; the only additions are `any_skin_outer` (in
  `forearm_anatomy_probes`) and the `sa_best ≥ 0.15` refuse step (order:
  after S5, before S6 — all three are independent monotone adds).

## 6. Frozen state declaration

`SLEEVE GATE v2.4 FROZEN` as of this document. Any change requires a new
phase with calibration evidence (P8 of Phase 6: re-run the security +
full suite after every instrumentation change).
