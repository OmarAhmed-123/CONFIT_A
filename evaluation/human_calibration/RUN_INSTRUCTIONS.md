# Human calibration — run instructions

## 1. Rater eligibility

- ≥3 REAL, independent human raters (no AI/VLM assistance — hard rule).
- No rater has seen this project's prior labels or gate verdicts.
- Raters do not communicate about items until all three sheets are done.
- Raters confirm they have normal color vision (sufficient to distinguish
  navy/charcoal; the low-contrast items are intentionally hard).

## 2. Materials per rater

- `ARTIFACT_MANIFEST.json` (paths + display order; open images by path).
- One `LABELING_SHEET_raterN.csv` to fill in.
- Nothing else. **Not** the gate verdicts, **not** `UNBLINDING_SHEET.csv`,
  **not** the Phase-5/6 reports.

## 3. Presentation

- Work strictly in `display_order` (fixed-seed randomization, recorded in
  the manifest; identical order for all raters).
- For Type S: view `input` (person before), then `render` (person after),
  then `garment_ref` (the requested garment). Judge the render.
- For Type L: view `input`, `render`, `garment_ref`. Judge whether the
  requested bottom visibly replaced the original.
- **Blinding (Phase 7):** raters work only with the opaque `blind_id`
  (item-01 … item-73) + item type. Case names, person identities,
  garment names, gate verdicts, and agent labels live in
  `UNBLINDING_SHEET.csv` and are never shown to raters. For the 10
  Phase-7 fresh bases the garment is visible on the subject in the
  reference image (noted per item in the manifest).

## 4. Core set vs full set

- **Full set (73 items):** 66 Type-S + 7 Type-L. Preferred.
- **Core set (23 items)** if session length forces a cut: all 7 Type-L,
  plus the 16 Type-S items marked `core: true` in the manifest (the
  decision-critical ones: thin-margin, borderline partial, asymmetric
  composites, class-E, synthetic drops, pose rows, and the two Phase-7
  3/4-sleeve renders whose REFUSE needs human confirmation). Marking is
  recorded in the manifest; do not change it per rater.

## 5. Aggregation

1. Per item: primary judgment from each rater.
2. Discordance (≥2 distinct primary labels among the three): the three
   raters review only those items together and record a consensus label
   (unanimous or majority); the per-rater raw labels stay in the sheets
   (no overwriting).
3. Report: per-type accuracy of (a) agent labels vs human consensus,
   (b) gate verdict vs human consensus; Fleiss' kappa across raters;
   per-item table with confidence.
4. Every gate-vs-human disagreement = a defect report with the image path,
   hashes, and the human label; fix-forward per the normal standard
   (generic fix + regression pin; no label negotiation).

## 6. Privacy/consent

- All items are synthetic/AI-generated person images or studio cohort
  images already used in evaluation; no real user images are in this
  package.
- Raters must not store copies of the images outside the evaluation
  directory; the sheets record item IDs, not image data (P8 hygiene).

## 7. Closure

Barrier 3 closes ONLY when: 3 raters complete, aggregation reported,
defect reports from disagreements resolved, and the Phase-6 report's
barrier table updated. Otherwise `HUMAN CALIBRATION = BLOCKED` remains.
