# VTON GATE SPEC v1 — CONFIT_A multi-garment layered pipeline

Date: 2026-09-15 · Status: **DRAFT v1 — PENDING APPROVAL** (no production
implementation until approved, per master prompt §20).
Evidence base: Phase 0.5 calibration (good=54, bad=13, FINAL) + Phase 1
pre-implementation measurements (2026-09-15): AdaFace clean-swap test,
lightness-conditioned ΔE recalibration, 52-job long-sleeve root-cause set +
true short-sleeve control, 4-job local-market Arabic/mixed/English OCR set.
Every threshold below is **UNFROZEN** unless marked otherwise; none is an
intuition value — each carries its measured evidence and status tags.

Policy anchors (§18/§19):
- STRUCTURAL gates may be HARD (presence/consistency facts).
- QUALITY gates may be HARD only when statistically justified (AUC,
  FPR/FNR at target, human correlation). Currently NO quality gate qualifies
  (Gate A human calibration BLOCKED) → all quality gates are SOFT with a
  mandatory-human-review band.
- Hybrid rule: a render is DISPLAYED only when all hard gates PASS and no
  soft gate is in its failure/review band. Auto-accept is BLOCKED until
  Gate A + threshold freeze; auto-reject applies to hard-gate failures;
  review-required applies to soft-gate bands. NO fake fallbacks, no silent
  single-garment substitution, no cached/placeholder outputs.

---

## G1 — Face presence (STRUCTURAL, HARD)

- Purpose: reject renders where the person's face is absent/destroyed.
- Input: output image. Metric: MediaPipe Face Landmarker (478 lm) present or not.
- Model/version: face_landmarker.task (Apache-2.0 model), sha256 in
  evaluation/weights_local/model_manifest.json.
- Threshold: face present = pass (binary).
- Calibration evidence: 54/54 good detected, 13/13 bad detected (all bad
  cases retained a detectable face by construction; KB12 deformation still
  detected). FPR 0.0, FNR 0.0 on the set.
- Human correlation: n/a (structural fact) — VERIFIED by construction.
- Failure code: `NO_FACE_IN_OUTPUT` → AUTO-REJECT (refuse display).
- Remediation: retry once; then reject.
- Cost: ~0.3 s CPU.
- Re-cal trigger: face model version change; new person cohort (hijab,
  heavy occlusion) — add cohort fixtures before trusting.

## G2 — Pose presence + torso alignment (STRUCTURAL presence HARD; quality SOFT)

- Purpose: person pose preserved; torso not structurally broken.
- Metric: MediaPipe Pose (33 lm, Apache-2.0 model) present; torso MPJPE norm.
- Calibration evidence: presence 54/54 + 13/13 (KB10 distorted pose still
  detected). `pose_mpjpe_torso_norm` AUC 0.332 — REJECTED as discriminator
  (too weak); kept as SOFT signal in the composite, no threshold frozen.
- Failure codes: `NO_POSE_IN_OUTPUT` (HARD, auto-reject);
  `POSE_DISPLACED` (SOFT, review band) — band UNFROZEN, needs Gate A.
- Cost: ~0.4 s CPU. Re-cal trigger: pose model version; new pose cohort
  (arms-raised, 3/4 — §8).

## G3 — Identity preservation (STRUCTURAL-critical, HARD-DETECT + calibrated band)

- Purpose: detect identity swap/destruction (incl. clean swap — the
  Phase 0.5 failure mode where DINOv2 face cosine was BLIND: KB04 cos 0.865).
- Metric (measured 2026-09-15): AdaFace iResNet-IR101 cosine, aligned crop
  (eye-midpoint + IOD→35.2 px, axis-aligned), 512-d L2-norm.
  - License: code MIT (VERIFIED); weights trained on MS1MV2 — **NO
    established commercial license** → **LICENSE-GATED / EVALUATION-ONLY**.
    NOT a production gate until commercial rights resolved (licensed FR
    model or dataset license). Weights never committed.
  - Measured: good cohort min 0.265, p05 0.281, median 0.663 (n=54);
    KB04 clean swap = **0.255** (below good p05 → DETECTED); KB12
    deformation = 0.561 (NOT detected — deformation is a different
    defect class, covered by G4); garment-level bad cases 0.51–0.90
    (correctly not identity-flags).
- Candidate operating point (UNFROZEN): reject/flag if cos < 0.28 →
  FPR 1/54 (1.85%), catches KB04; GRAY ZONE 0.28–0.40 → MANDATORY HUMAN
  REVIEW / LIMITED CONFIDENCE (satisfies §5: clean swap is detected OR
  explicit human review — both, here).
- DINOv2 face cosine (Apache-2.0 weights): REJECTED as identity gate
  (AUC 0.613; KB04 blind). May remain a drift proxy only.
- **Hard-cohort artifact (measured 2026-09-15, onboarding probe n=10):**
  arms-raised pose render (visually identity-correct) → cos 0.214;
  dim-lighting render (visually identity-correct) → cos 0.215 — both
  below the 0.28 candidate reject line. A fixed raw-cosine threshold
  mis-fires ~20% on hard cohorts. Rule: for hard-pose/hard-lighting
  cohorts (arms-raised, 3/4, dim, backlit), cos < 0.28 = REVIEW, not
  reject; reject reserved for the standard cohort until a
  cohort-conditioned calibration (or AdaFace quality-margin decision)
  is measured against Gate A ratings.
- Failure codes: `IDENTITY_SWAP_SUSPECTED` (cos < band low),
  `IDENTITY_LOW_CONFIDENCE` (gray zone → human review).
- Production path (§5 outcomes, ordered):
  1. licensed commercial FR model (rights verified) → production gate;
  2. else AdaFace-eval + mandatory human review in gray zone (limited
     confidence, explicitly surfaced — NEVER an automatic hard guarantee);
  3. human fallback = Gate A raters (BLOCKED pending).
- Cost: ~0.2 s CPU per image (IR101). Re-cal trigger: FR model/version
  change; new demographics cohort; human correlation (Gate A) — threshold
  MUST be re-fit to human ratings before freeze.

## G4 — Face geometry & aligned similarity (QUALITY, SOFT)

- Metric: `face_geo_mean_disp` (AUC 0.537), `face_aligned_ssim` (AUC 0.544),
  `landmark_mpjpe_norm` (AUC 0.474).
- Evidence: all below the statistical bar for a hard quality gate;
  KB12 (deformation) is the case they should catch — SSIM/geo move on it,
  but separation is weak (no FPR≤5%/FNR≤15% point).
- Policy: SOFT inputs to a composite face-quality score; composite threshold
  UNFROZEN pending Gate A (human correlation is the freeze precondition).
- Failure code: `FACE_DEFORMATION_SUSPECTED` (composite in review band).
- Cost: ~0.5 s CPU. Re-cal trigger: Gate A results; model changes.

## G5 — Garment region presence & occlusion (STRUCTURAL, HARD)

- Purpose: the garment region exists in the output and its visibility state
  is classified (FULLY_VISIBLE / PARTIALLY_VISIBLE / OCCLUDED_VERIFIED /
  UNDETERMINED).
- Metric: pose+slot tier-1 region (regions.py) + occlusion state machine.
- Evidence: 54/54 good region OK (Phase 0.5); UNDETERMINED → treated as
  unverifiable, not pass.
- Failure codes: `REGION_UNDETERMINED` (auto-reject: cannot verify garment
  application), `GARMENT_REGION_EMPTY` (auto-reject).
- Policy: HARD structural. Occlusion state conditions downstream leniency
  (G6/G9 occlusion-verified lenient regime — measured regime exists in
  ocr_metrics; color leniency pending measurement).
- Cost: ~0.4 s CPU (shared pose pass).

## G6 — Garment color fidelity (QUALITY, SOFT — no hard gate justified)

- Metric family (all measured, good=54 vs bad=13):
  | metric | AUC | status |
  |---|---|---|
  | garment_delta_e_mean (raw CIEDE2000) | 0.437 | REJECTED (systematic ~ΔE24 lightness bias) |
  | garment_delta_e_lc_mean (lightness-conditioned, NEW) | 0.368 | REJECTED as gate; BUT removes the bias (good std 11.9→6.4, p95 42.1→28.5) — kept as the calibrated color metric of record |
  | garment_lightness_offset (dL, diagnostic) | — | diagnostic only (relighting characteristic, not defect) |
  | garment_dominant_match | 0.515 | SOFT |
  | garment_histogram | 0.464 | REJECTED standalone (Phase 0.5 decision retained — not reintroduced as hard gate) |
  | dinov2_garment_cos | 0.423 | REJECTED |
  | garment_lightness_residual_std (NEW) | 0.487 | diagnostic (non-uniform shading) |
- Policy: NO hard gate (no metric statistically justified; §18). Composite
  color score (LC-ΔE + dominant + histogram weights UNFROZEN) → review band;
  extreme points (LC-ΔE > good p95 = 28.5 AND dominant mismatch) →
  `COLOR_MISMATCH_SUSPECTED` → human review. Same-color-pair cases
  (dark-on-dark etc.) are the hardest — cohort §9.
- Failure codes: `COLOR_MISMATCH_SUSPECTED` (review), `COLOR_DRAMATIC_OFFSET`
  (|dL| > 40 → region mislocalization or garment absent → auto-reject
  review-escalation; measured dL range good: −64…+28, median −3 — the −64
  tail = content mismatch, verified cases reviewed individually).
- Cost: ~0.3 s CPU. Re-cal trigger: Gate A; new palette cohort; engine
  version (relighting mode shifts → dL re-measured).

## G7 — Texture / pattern preservation (QUALITY, SOFT — best-in-class, still soft)

- Metric: `texture_period_ok` (AUC **0.875** — best in class; candidate
  threshold 0.250 with FPR 0.000 / FNR 0.000 on the set — MEASURED),
  `texture_edge_density` (diagnostic).
- Evidence: strongest measured quality signal, but n=54/13 and NO human
  correlation yet → §18 forbids a hard quality gate on this alone.
- Policy: SOFT with the sharpest band: period mismatch on a
  pattern-type garment (stripes/checks, from manifest) →
  `PATTERN_LOST` → review; auto-accept of pattern garments BLOCKED until
  Gate A confirms. Stripes/checks fixtures: g005, g006 (+ Phase 1 §9
  expansion pending).
- Failure codes: `PATTERN_LOST`, `TEXTURE_ANOMALY`.
- Cost: ~0.2 s CPU. Re-cal trigger: Gate A; engine version.

## G8 — Sleeve completeness (STRUCTURAL, HARD for long-sleeve candidates) — NEW

- Purpose: close the long-sleeve defect class (§7 root cause: engine clips
  vertically-separated sleeves → sleeveless/partial renders).
- Metric: `garment_sleeve_drop` (product-image geometry; long-sleeve
  candidate if drop > 0.45) × `arm_coverage` (pose arm sampling: d_input
  change > 10 AND d_garment ΔE2k < 12 → arm PRESENT).
- Evidence (52-job set + true short-sleeve control, measured):
  catches g012 10/10, g111 3/3 (partial), g001/g002 4/4, g010 7/10 (the 3
  white-on-white accepts are behaviorally correct: arms covered in garment
  color); true short-sleeve g011 → N/A (drop 0.0), behavior as expected;
  Phase 0.5 catch-up: S_g001 (judge 10/10) → FAIL (gate detects a defect
  the Phase 0.5 pipeline missed). Regression-tested (test_sleeve_gate.py).
- Thresholds (UNFROZEN candidate set): drop > 0.45 (long-sleeve candidate);
  arm changed > 10; arm garment-match < 12. FPR on non-long-sleeve = 0 by
  design (N/A); FNR on the defective set = 3/24 (the g010 white-on-white
  cases — accepted as behavioral passes, documented).
- KNOWN LIMITATION (documented, not hidden): no separated-sleeve signature
  for flat lays with connected sleeves (g003, g004, g015, g016, g019:
  drop 0.0) → gate N/A for those; production catalog metadata must carry a
  sleeve-length claim + arm-change check (tracked TODO in this spec).
- Failure codes: `FAIL_SLEEVES_INCOMPLETE` (long-sleeve candidate, arms not
  covered) → AUTO-REJECT (refuse display); `NO_POSE` → region unverifiable
  → reject (shared with G5).
- Cost: ~0.8 s CPU (pose + 8 arm samples). Re-cal trigger: new garment
  geometries; engine version (if sleeve behavior changes, re-run the 52-job
  set); catalog metadata policy change.

## G9 — Text fidelity (QUALITY, SOFT-with-review; auto-accept BLOCKED for has_text)

- Purpose: text on garments preserved (local-market critical: Arabic).
- Metric: EasyOCR (Apache-2.0) per-language readers — English and Arabic
  measured SEPARATELY (no cross-language assumption); mixed via combined
  reader.
- Evidence (measured 2026-09-15, n=4 renders):
  - Arabic 1-line, white-on-dark (g120): PRESERVED 2/2 — exact match,
    score 1.0, conf 0.72/0.73.
  - English 1-line, white-on-dark (g009): CORRUPTED — "STUDIO 2026" →
    "STUDID 2IQ6", score 0.0.
  - Mixed 2-line, dark-on-light (g121): DESTROYED — both languages 0.0.
  - Phase 0.5: `ocr_text_score` INSUFFICIENT (too few text fixtures) —
    retained status, now expanded (g120/g121; §9/§12 expansion pending).
- Policy: ANY has_text garment with score < 1.0 → `TEXT_CORRUPTED` /
  `TEXT_MISSING` → MANDATORY HUMAN REVIEW (never silent auto-accept — the
  measured corruption is severe and language/contrast/layout-dependent).
  Auto-accept of text garments: BLOCKED until a larger measured OCR matrix
  (≥8 fixtures per §6) shows a statistically clean operating point.
- Failure codes: `TEXT_CORRUPTED` (detected but ≠ expected),
  `TEXT_MISSING` (not detected), `TEXT_HALLUCINATED` (unexpected text on
  plain garment — G6-absence sanity, score 1.0→0.0).
- Cost: ~1–3 s CPU per render (per language). Re-cal trigger: OCR model
  version; new scripts (RTL, ligatures); engine version.

## G10 — Artifacts (edge anomaly, blockiness) (QUALITY, SOFT)

- Metric: `edge_anomaly`, `blockiness` (Phase 0.5, implemented; per-sample
  values in offline eval; aggregate AUC not computed — MEASURED PER-SAMPLE
  only).
- Policy: diagnostic now; band undefined (no AUC yet → cannot be a gate,
  hard or soft, until measured against the bad set + humans).
- Failure codes: reserved `ARTIFACT_EDGE` / `ARTIFACT_BLOCKY`.
- Cost: ~0.2 s CPU. Re-cal trigger: bad-set re-run (pending recalibration
  cycle), Gate A.

## G11 — Determinism & integrity (STRUCTURAL, HARD)

- Purpose: identical inputs → identical outputs; provenance chain intact.
- Metric: sha256 of inputs/outputs; worker determinism (Phase 0.5:
  identical sha256 VERIFIED on repeat runs); fixture manifests sha256-attested.
- Failure codes: `NON_DETERMINISTIC_OUTPUT` (retry → reject),
  `FIXTURE_MISMATCH` (sha mismatch vs manifest → reject + flag).
- Cost: ms. Re-cal trigger: engine version (determinism re-verified).

## G12 — Worker verify enhancement (TO IMPLEMENT in production work)

- Phase 0.5 worker verify (pixel_change / color_shift / stddev) is BLIND to
  the sleeve-missing class (17/20 defective renders passed verify — §7).
- Change: verify must include the G8 arm-region check when the garment is a
  long-sleeve candidate (or catalog metadata claims long sleeves);
  weak-change + unchanged arms = verify FAIL (honest failure, no downgrade).
- Status: NOT IMPLEMENTED (production work item; branch
  feat/vton-multigarment-layered-fashn after Gate Spec approval).

---

## Hybrid decision policy (§19)

| Outcome | Condition |
|---|---|
| AUTO-REJECT (refuse display, honest failure reason) | any HARD gate fail: G1, G2-presence, G5, G8, G11, G12; `COLOR_DRAMATIC_OFFSET` review-escalation |
| MANDATORY HUMAN REVIEW (limited confidence surfaced) | G3 gray zone (0.28–0.40) or `<0.28` without licensed model; G4 composite band; G6 `COLOR_MISMATCH_SUSPECTED`; G7 `PATTERN_LOST` (pattern garments); G9 any text score < 1.0 |
| AUTO-ACCEPT | **BLOCKED** until Gate A (≥3 human raters) + threshold freeze + this spec approved. No render is auto-accepted today. |
| Display | all hard PASS + no review-band flag |

## Gate status table (as of 2026-09-15)

| Gate | Type | Status | Blockers |
|---|---|---|---|
| G1 face presence | hard | READY (structural) | — |
| G2 pose presence/alignment | hard+soft | READY (presence); band PENDING | Gate A |
| G3 identity | hard-detect + band | EVAL-ONLY (LICENSE-GATED AdaFace) + human-review policy | commercial FR license OR Gate A |
| G4 face quality | soft | PENDING calibration | Gate A |
| G5 region/occlusion | hard | READY (structural) | — |
| G6 color | soft | PENDING (LC-ΔE of record; no hard justified) | Gate A |
| G7 texture/pattern | soft | PENDING (AUC 0.875 — strongest candidate) | Gate A (n, human corr.) |
| G8 sleeves | hard (long-sleeve candidates) | READY (structural, regression-tested) | connected-sleeve catalog metadata (TODO) |
| G9 text | soft+review | MEASURED (n=4; auto-accept BLOCKED) | OCR matrix ≥8 fixtures, per language |
| G10 artifacts | soft | UNMEASURED aggregate | bad-set re-run |
| G11 determinism | hard | READY (VERIFIED Phase 0.5) | re-verify per engine version |
| G12 worker verify | hard (production) | NOT IMPLEMENTED | Gate Spec approval → production work |

## Model & license register (gate-relevant)

| Component | License | Commercial rights | Gate use |
|---|---|---|---|
| MediaPipe Face/Pose (Apache-2.0 models) | Apache-2.0 | OK | G1/G2/G5/G8 |
| EasyOCR 1.7.2 | Apache-2.0 | OK (models: see EasyOCR license — recognition models trained on public datasets; document per model at freeze) | G9 |
| AdaFace IR101 (mk-minchul/AdaFace) | code MIT; MS1MV2 data license UNRESOLVED | **UNRESOLVED — evaluation-only** | G3 (eval) |
| DINOv2 (Apache-2.0 weights) | Apache-2.0 | OK | drift proxy only (REJECTED identity gate) |
| FASHN fashn-vton-v1.5 @ 7c0f10af | Apache-2.0 (fork) | OK | generation engine |
| Noto Naskh Arabic | SIL OFL 1.1 | OK | fixture generation (G9 fixtures) |

## Research-refresh notes feeding model selection (§15, 2026-09-15)

- UniFit (AAAI 2026, native multi-garment + model-to-model): **CC BY-NC-SA 4.0**
  + Flux.1 [dev] NC base → LICENSE VETO for commercial production
  (RESEARCH-ONLY).
- Garments2Look (CVPR 2026): dataset (80K outfit pairs) + explicit finding
  "current methods struggle to try on complete outfits seamlessly and to
  infer correct layering" → supports layered-sequential-composition
  architecture; usable as benchmark/judge reference.
- MV-Fashion (CVPR 2026): non-commercial research only, agreement-gated →
  excluded (consistent with training re-entry gates).
- Conclusion: FASHN "layered sequential composition" remains the selected
  production architecture (naming rule §14 applies everywhere).
