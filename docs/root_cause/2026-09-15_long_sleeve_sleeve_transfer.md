# ROOT CAUSE REPORT — Long-sleeve garment application failure (Phase 1 §7)

Date: 2026-09-15 · Branch: research/vton-phase05-calibration (work continues pre-implementation)
Status: **CLOSED AS ENGINE-LIMITATION-DECLARED + BOUNDED BY GATE + REGRESSION-TESTED**
(§7 closure criteria: "fixed+verified" is NOT claimed — the engine cannot be fixed
from CONFIT_A without upstream changes; "bounded+accepted" and
"engine limitation declared" ARE satisfied, see §8.)

---

## 1. Symptom (as discovered in Phase 0.5)

- 10 of 54 baseline worker-verify FAILs, all `weak-change` (metric_pixel_change < 1.0),
  all on long-sleeve garments (g010 white long-sleeve shirt, g012 black long-sleeve tee).
- 2 judge-zero renders: S_g010 ("white tank top" instead of expected shirt),
  S_g012 ("sleeveless top instead of the expected long-sleeve tee").
- Judge panel otherwise agreed 38/38 and scored remaining long-sleeve-geometry
  garments 8–10/10 (see §5, secondary finding).

## 2. Reproduction case (dedicated)

**Minimal case:** person `p001` (arms down, bare arms — white tank top input) +
garment `g012` (black long-sleeve tee, flat lay with sleeves laid vertically).

- Render job `RS-g012-p001-repro` (worker `fashn-vton-v1.5 @ 7c0f10af`, 2026-09-15):
  `http=200`, `verify.PASS=true` (pixel_change **7.58** — torso re-textured black),
  but output shows **sleeveless**: arms remain bare skin.
- Sleeve-region quantification (pose-derived arm boxes vs garment color #1B1B1F):
  `sleeve_delta_e = {left: 44.5, right: 45.6}` (skin vs black ≈ ΔE 44–46).
- Files: `evaluation/results/rootsleeve_runs.json`,
  `evaluation/results/outputs/rootsleeve/RS-g012-p001-repro.jpg`.

The verify block **passed** this render — the defect class is invisible to
`metric_pixel_change` (torso change dominates) and to `metric_color_shift`.

## 3. Root cause (MEASURED + visually VERIFIED)

**The FASHN engine's garment-to-body warp does not reliably transfer garment
sleeves whose geometry extends far from the torso in the product image.**

Transfer rate by sleeve geometry in the product image (29 renders, measured):

| Geometry | Fixture | Renders | Outcome (arm coverage, measured) |
|---|---|---|---|
| 0° horizontal sleeves | g110 | 3 | **FULL** — sleeves to wrist, pose-following (1 visual confirm: RS-g110-p007) |
| 45° raglan | g111 | 3 | **PARTIAL** — upper arm only (short-sleeve-length render) |
| 90° vertical, dark | g012 | 10 | **SLEEVELESS in 10/10** (ΔE 17–50; visual confirm RS-g012-p001) |
| 90° vertical, light | g010 | 10 | 3/10 arms covered in garment color (white-on-white — see ambiguity note), 7/10 sleeveless |
| 90° vertical, "tee"-labeled | g001, g002 | 2 each | sleeveless (see §5 — the labels were wrong; images ARE long-sleeve) |

**Mechanism (DERIVED from the geometry–outcome gradient):** the warp anchors the
garment torso to the person torso and compresses sleeve geometry toward the
shoulder; transferred sleeve length shrinks as the sleeve's vertical distance
from the torso in the product image grows. At 90° the sleeve is compressed out
of existence (sleeveless); at 45° it survives as a short sleeve; at 0° it
survives fully. The failure is also **person/garment-dependent** (g010: 3/10 vs
g012: 0/10 — dark-on-light failures are total; light-on-light renders sometimes
end with arms covered in garment color, which is visually acceptable).

**Ambiguity note (white-on-white):** the 3 g010 "passes" (e.g. RS-g010-p009) show
white arms matching garment color (d_garment ≈ 5, d_input ≈ 26–30). These are
behaviorally acceptable outputs, but color alone cannot distinguish "sleeve
texture transferred" from "white fill matching garment color". The gate treats
them as PRESENT, which is the correct behavioral call.

**Classification:** engine limitation of `fashn-vton-v1.5 @ 7c0f10af` (single-
garment engine; sleeve warping over extended limbs is not robust). NOT a
CONFIT_A integration bug — CONFIT_A submits correct person+garment inputs
(deterministic sha256-verified fixtures); the defect reproduces identically on
the raw worker endpoint.

## 4. Why the Phase 0.5 pipeline missed it (all three checks, measured)

| Check | Behavior on defect renders | Measured evidence |
|---|---|---|
| Worker verify (pixel_change) | PASS when torso changes enough (black-on-white = 7.5–12) | 17/20 vertical-sleeve renders passed verify despite missing sleeves |
| VLM judge (8-dim rubric) | Scores garment_accuracy vs the **text name**, not sleeve geometry vs the garment image | S_g012 (name contains "long-sleeve") → 0/0/0, note explicitly says "sleeveless top"; S_g001 (name "plain white tee", image actually long-sleeve) → **10/10** on a sleeveless render |
| Offline metrics | No sleeve/arm-region metric existed in Phase 0.5 | `garment_delta_e_mean` etc. measured the torso region only |

## 5. Secondary finding — fixture label defect (MEASURED, affects Phase 0.5 evidence base)

The procedural fixture generator rendered **full-length vertical sleeves** for
garments whose manifest silhouette is `tee` (short-sleeve implied):
`g001, g002, g005, g006, g007, g009, g018` (7 of 10 "tee" fixtures; measured
`rendered_sleeve_drop_ratio` 0.83–0.84). `g110` is the reverse (long-sleeve
label, horizontal geometry — no separated-vertical signature).

Consequences for Phase 0.5 evidence:
- The "known-good = 54" cohort contains sleeve-missing/partial renders for at
  least 9 garments (g001, g002, g005, g006, g007, g009, g018 + g010/g012
  partial cases). These remain valid for **face/pose/identity/torso-color**
  calibration (those attributes are unaffected), but are **invalid as
  sleeve-completeness ground truth**.
- The judge's rubric had no sleeve-completeness dimension and was conditioned
  on the (wrong) name — it is **not a reliable oracle for this defect class**
  (VERIFIED on S_g001: 10/10 for a sleeveless long-sleeve render).
- Manifest updated 2026-09-15 with measured `rendered_sleeve_drop_ratio`,
  `rendered_sleeve_geometry`, and `label_image_mismatch` flags (8 fixtures).
  Original labels preserved; no fixture image regenerated (baseline hashes stay
  valid; mismatch is documented, not hidden).

## 6. Mitigations

1. **Structural sleeve gate (IMPLEMENTED)** — `evaluation/vton_metrics/sleeve_metrics.py`:
   - `garment_sleeve_drop()`: deterministic product-image geometry classifier
     (separated-sleeve signature; candidate long-sleeve threshold drop > 0.45).
   - `arm_coverage()`: pose-derived arm sampling (55%/85% shoulder→wrist),
     per-sample d_input (change vs input) and d_garment (ΔE2k vs garment
     dominant Lab); candidate thresholds: changed > 10, garment < 12.
   - Gate: for long-sleeve candidates, output must be `SLEEVES_PRESENT` or it is
     **FAIL_SLEEVES_INCOMPLETE → refuse display** (never silent auto-accept).
   - Measured on the 52-job set: catches g012 10/10, g011 3/3 (partial),
     g001/g002 4/4, g010 7/10 (the 3 white-on-white accepts are behavioral
     passes); true short-sleeve control g011: gate N/A (drop 0.0), arm
     behavior as expected (forearm uncovered by design).
   - **Limitation (documented):** the geometry signature does not fire for
     flat lays where sleeves are drawn connected to the body outline (g003,
     g004, g015, g016, g019 measured drop 0.0). For those, the gate is N/A;
     production catalog metadata must carry a sleeve-length claim, and the
     arm-change check becomes the detector (TODO, tracked in gate spec §17).
2. **Worker verify enhancement (TO IMPLEMENT in Phase 1 production work):**
   add the arm-region check to the worker verify block so a render with
   expected-full-sleeves and unchanged arms FAILs verify (closes the
   pixel_change blind spot, §4).
3. **Catalog/fixture policy (DECIDED):** long-sleeve product images should be
   laid with sleeves horizontal (measured: full transfer, g110). Fixture
   generator defect (tees drawn with long sleeves) logged for regeneration in
   the next fixture revision; labels are NOT retroactively "corrected" against
   images — the images are the ground truth the engine sees.
4. **Judge/human rubric (GATE A dependency):** add explicit dimension
   "garment completeness — sleeve and hem extent match the reference garment
   **image** (not just its name)" to the frozen 8-dim rubric for human
   calibration (Gate A still BLOCKED pending raters).
5. **Engine limitation declared (THIS REPORT):** long-sleeve garments with
   vertical-sleeve product geometry are not supported by the current engine
   with guaranteed fidelity. Long-sleeve availability in production is
   **CONDITIONAL on the sleeve gate**; refused renders are visible
   (LIMITED_CONFIDENCE / rejected), never silently shipped.

## 7. Regression test (IMPLEMENTED)

`evaluation/tests/test_sleeve_gate.py` (deterministic, CPU, no GPU):
- drop-detector classification on all 26 fixtures matches the audited table;
- arm-coverage verdicts on saved renders: RS-g012-p001 → not PRESENT (gate
  FAIL), RS-g110-p007 → PRESENT, RS-g111-p007 → not PRESENT;
- Phase 0.5 catch-up: S_g001-L1-g001 (rated 10/10 by judge) → gate FAIL,
  proving the gate detects a defect the Phase 0.5 pipeline missed.

## 8. Measured results (all artifacts)

- `evaluation/results/rootsleeve_runs.json` — 52 jobs (29 renders: g010×10,
  g012×10, g001×2, g002×2, g110×3, g111×2 rendered + 3; orig re-render attempts
  422 by design), per-job verify block, pixel_change, sleeve-region ΔE.
- `evaluation/results/rootsleeve_control_g011.json` — 3 true short-sleeve
  control renders (g011×p001/p007/p010) + arm coverage.
- `evaluation/results/sleeve_gate_calibration.json` — gate over all renders:
  per-job drop, arm samples (d_input, d_garment, sample xy), verdicts.
- `evaluation/fixtures/garment_manifest.json` — measured sleeve geometry audit
  (26 garments; 8 `label_image_mismatch`).
- Visual confirmations (render vs garment fixture vs person input):
  RS-g012-p001 (sleeveless), RS-g110-p007 (full sleeves), RS-g111-p007
  (short), RS-g010-p004 (sleeveless tank), RS-g010-p009 (white full),
  S_g001 (sleeveless, judge 10/10), S_g005 (partial, judge 9/10).

## 9. Closure decision (§7)

- ROOT_CAUSE: identified and evidenced (§3).
- REPRODUCTION_CASE: p001+g012 (§2).
- MITIGATION: gate + verify enhancement + catalog policy + rubric fix (§6).
- REGRESSION_TEST: implemented (§7).
- MEASURED_RESULT: 52-job set + calibration + Phase 0.5 catch-up (§8).
- **NOT closed as "fixed"**: no engine change was made or possible from
  CONFIT_A. Closed as **engine limitation declared**, **bounded** (refuse-
  display gate; no silent shipping), **detected** (regression test green on
  historical renders). Long-sleeve production support remains CONDITIONAL
  (see gate spec + local validation report when Gate A unblocks).
