# Fit Finder — Semantic Closure Audit

**Scope:** Fit Finder / body measurements / size recommendation only.
**Branch:** `feat/fit-finder-sizing-engine` (single branch, as instructed)
**Baseline audited:** `main` @ `ae228ed` (after closure PR #158)
**Production:** https://confit-a.vercel.app/

---

## 0. This report is not punitive

This document exists to make the system's real state legible so it can be
improved — not to assign blame. Several defects recorded here were introduced by
the very commits that claimed to fix this feature, including a docstring that
described a hand-tuned heuristic as a fitted scientific model. Finding that is
the point of the exercise, not evidence of failure.

The rule applied throughout: **no claim appears here unless it was executed and
observed.** Where something could not be verified it is marked BLOCKED or NOT
VERIFIED rather than softened.

**Status vocabulary**

| Term | Meaning |
|---|---|
| **VERIFIED** | Observed by execution; evidence cited. |
| **PARTIALLY VERIFIED** | Correct under tested conditions, with a stated limit. |
| **BLOCKED** | Cannot proceed due to a legitimate access limitation. |
| **NOT VERIFIED** | Requires ground-truth evidence that does not exist. |

---

## 1. Summary

| Area | Status |
|---|---|
| Deterministic size engine | VERIFIED |
| Refusal when data is insufficient | VERIFIED |
| Units / bounds / outliers | VERIFIED |
| **Estimated measurements never name a size** | **VERIFIED (changed this pass)** |
| **Generic fallback restricted by category** | **VERIFIED (changed this pass)** |
| Inventory honesty (tri-state) | VERIFIED |
| Confidence is a band, never a probability | VERIFIED |
| Provenance disclosure | VERIFIED |
| Measurement-session ownership | VERIFIED |
| Production brand-chart coverage | PARTIALLY VERIFIED |
| Production DB backfill | **BLOCKED** |
| Measured recommendation accuracy | **NOT VERIFIED** |

**Tests at closure:** backend **2382 passed / 5 skipped / 0 failed**; frontend
**254 passed / 31 files**; `tsc --noEmit` clean.

---

## 2. Estimated measurements — the honest account

### 2.1 What exists

`backend/app/services/fit/anthropometry.py` estimates missing girths from height
and weight:

```
girth_cm = a + b * BMI + c * (height_cm - 170)
```

It requires **both** height and weight (height alone invents nothing), refuses
to extrapolate outside BMI 15–45, labels every estimated field in
`estimated_fields`, surfaces them in the API response, and lowers confidence.

### 2.2 The defect found this pass: an unsupported scientific claim

The module previously stated its coefficients were *"fitted to the published
population girth/BMI relationships."* **That was false.** They were not fitted
to any dataset; they are hand-chosen values that reproduce plausible averages.
No citation existed anywhere in the file.

Checking each dimension against the literature:

| Dimension | Status | Evidence |
|---|---|---|
| **Waist** | Direction externally supported | Published NHANES regression `WC = 22.61 + 2.52·BMI + 0.158·AGE` (Bozeman et al., *BMC Med Res Methodol* 2012;12:115). Our BMI slope **2.55** ≈ published **2.52**. Our intercept is **~10 cm lower** — a product choice (no age term, younger cohort), **not a published finding**. |
| **Chest** | **NOT validated** | NHANES does not measure chest circumference at all; its circumference measures are waist and arm. No public regression backs these coefficients. |
| **Shoulder, neck** | **NOT validated** | Same — plausibility-tuned only. |
| **Hip** | Direction only | Girth rises with BMI and stature, but the coefficients are ours. |

Per §3 of the brief this is **Case B — a product heuristic**. The docstring now
says so explicitly, cites the one source that genuinely supports the waist
relationship, and states which dimensions have no backing.

### 2.3 The behavioural defect: an estimate was deciding the size

The estimator's own documented residual SD is **±5.5 cm (chest) to ±7.5 cm
(waist)**, widened further when sex is unknown. An EN 13402-3 men's chest band is
**8 cm** wide (S 86–94, M 94–102, L 102–110).

**±1 SD therefore spans ~11 cm — wider than a full size band.** Measured
directly: for h178/w78 the estimated chest of 99.6 cm carries a ±1 SD interval of
94.1–105.1 cm, which straddles **both M and L**.

Despite this, the engine was returning a **single definite size** for a body with
**zero measured girths**:

```
h170 w60 -> S      h178 w78 -> M      h170 w85 -> L
estimated_fields = ['chest_cm', 'hip_cm', 'waist_cm']   # nothing measured
```

Being labelled "estimated" at "low" confidence does not repair this: the output
still asserts one size when the underlying uncertainty cannot distinguish between
two. That is presenting a fabricated input as a finding.

**Fix.** `engine.py` now refuses when *every* comparable section is estimated:

```
reason_code: INSUFFICIENT_EVIDENCE
"We can't name a size from height and weight alone. Estimating your chest,
 waist from height and weight is typically off by more than a whole size…"
```

The refusal is deliberately **proportionate**, verified by test:

| Input | Outcome |
|---|---|
| height + weight only | **refused** (`INSUFFICIENT_EVIDENCE`) |
| + chest measured | `M`, band **medium** |
| + chest and waist measured | `M`, band **high** |

The estimates were not deleted — they still widen intervals and order
candidates. They may no longer *decide* a size. A scalar confidence score was
the wrong instrument for this structural question, so it is now an explicit
evidence rule.

---

## 3. Generic fallback eligibility

### 3.1 The defect

`ChartContext.category_slug` was populated by the service but **never read**.
`StandardChartSource` applied the EN 13402-3 **chest/waist/hip** chart whenever
size labels happened to be mappable. Observed directly:

| Product | Before |
|---|---|
| Footwear sold `S/M/L` | **chest-band sizing applied** |
| Accessories sold `S/M/L` | **chest-band sizing applied** |
| Unknown/missing category | **chest-band sizing applied** |
| Footwear sold `40/41/42` | refused — but **only by accident**, because "42" is not a letter code |

Production currently refuses its real footwear and accessory products
(ids 6, 7, 8, 9 → `NO_SIZE_CHART`) for that accidental reason alone. A sandal
sold in S/M/L would have been sized by chest girth.

### 3.2 The policy now enforced

`en13402_eligibility()` is the single source of truth:

* **Eligible:** `tops`, `bottoms`, `outerwear`, `dresses`.
* **Ineligible:** `footwear`, `shoes`, `accessories`, `bags`, `jewellery`.
* **Unknown or missing category → ineligible.** The system cannot show a
  body-girth chart applies to a product whose type it does not know, and
  "we don't know" must not resolve to "probably a t-shirt".

This is a **refusal**, not a confidence reduction, as §7 requires.

### 3.3 Precedence (unchanged, now tested)

1. Product/brand-published chart
2. Derived product chart
3. Compatible generic fallback — **only if the category is eligible**
4. Otherwise refuse

Eligibility gates only the **generic** chart. A real chart attached to a
footwear product is still authoritative for it (tested).

### 3.4 A note on the category model

`products.category_id` is `NOT NULL`, so every real product has a category —
the guarantee the gate relies on. Four acceptance-test fixtures omitted
`category_slug` and were therefore *less* realistic than production; they were
corrected rather than the gate weakened.

---

## 4. Earlier fixes — re-verified, not assumed

| Defect | Status |
|---|---|
| Size recommended for a body rated "Does not fit" | Fixed; thresholds bound by import |
| Unknown stock reported as in stock | Fixed; tri-state |
| Rule score rendered as "66% confidence" | Fixed in both consumer surfaces |
| Cross-user measurement write (`sessionId \|\| 1`) | Fixed, now covered by 5 regression tests |
| `python3` vs project interpreter in alembic test | Fixed; suite has zero failures |

**§12 sweep.** A repo-wide grep for percentage-style confidence across backend,
frontend, schemas, i18n, docs and fixtures found **no live user-facing
occurrence**. Remaining matches are historical comments and this report
describing the old behaviour. One unused i18n key (`"AI Confidence"`) exists but
is referenced by no component.

---

## 5. Invariants enforced

`test_fit_invariants.py` sweeps 315 combinations (**633 assertions**) through the
real service path:

1. A size rated "Does not fit" is never recommended.
2. The recommended size is confirmed available — never unknown.
3. Unknown stock renders as unknown, never confirmed.
4. A non-brand chart never claims `is_brand_published`.
5. A generic chart never yields better than `low` confidence.
6. Every refusal carries a machine code *and* a human explanation.
7. Missing girths refuse or are disclosed.
8. **A size is never named when every section is estimated.**

Plus `test_fit_estimation_and_fallback_policy.py` (32 tests) covering the
adversarial estimation matrix and fallback eligibility.

---

## 6. Production verification

Executed against the live deployment, read-only, no customer records touched.

| Check | Result |
|---|---|
| Engine version | `fit-engine/2.1.0` |
| Normal body (chest 98 / waist 84) | `M`, band `low`, `confidence_is_probability: false` |
| Chart provenance | `standard_en13402`, `is_brand_published: false` |
| Impossible body (chest 130 / waist 120 / 52 kg) | `recommended: false`, `NO_SIZE_FITS` |
| Invalid input (`chest: -50`) | **HTTP 422** |
| Tri-state inventory | `M/L/S` → `in_stock` |
| Footwear & accessories (ids 6–9) | `recommended: false`, `NO_SIZE_CHART` |

---

## 7. Production database and backfill — BLOCKED

Re-checked this pass through legitimate project configuration only:

* The available `DATABASE_URL` is still rejected by Neon
  (`password authentication failed`).
* The Vercel token can list the project and enumerate env var **names**, but
  `?decrypt=true` returns **ciphertext** — it lacks decrypt permission.

No other route was attempted. Status remains **BLOCKED**. **The production
database has not been modified.**

**§16 data-quality audit of what the backfill *would* write** (5 charts,
verified by execution):

* All resolve to `product_chart_derived`; **none** claims `is_brand_published`.
* Every chart cites its basis (EN 13402-3, UK/US tailoring convention, etc.).
* All 5 target slugs are torso/leg garments (`tops`, `bottoms`, `outerwear`,
  `dresses`) — **no footwear or accessories**, so none is semantically
  inapplicable.
* Units declared per chart (`cm` or `in`); dimensions appropriate per garment.

**Script safety** (covered by 3 tests): idempotent; `--dry-run` writes nothing;
never overwrites a chart it did not author. It now also prints a verification
command and a rollback statement for the operator.

```bash
export DATABASE_URL='<production connection string>'
python -m backend.scripts.backfill_size_charts --dry-run
python -m backend.scripts.backfill_size_charts
```

Expected effect: `size_chart_source.source` moves `standard_en13402` →
`product_chart_derived` for those products. `is_brand_published` **stays false**.
Until it runs, production confidence stays `low` **by design**.

---

## 8. Accuracy — NOT VERIFIED

No ground-truth dataset of *(measurements, garment, size actually kept)* exists
for this catalogue. The 21 acceptance cases and 2382 tests prove **implementation
behaviour and internal consistency**, not real-world accuracy. Consistency is not
accuracy, and a published standard is not a measurement of our users.

**No accuracy figure is claimed anywhere in this report.**

To measure it later, the minimum needed is: customer measurements, product,
recommended size, size retained, exchange/return reason, and fit feedback. No
analytics system was built for this, as none is currently justified.

---

## 9. Remaining limitations

1. **Production runs on the generic standard** for its garment products, so
   sizing is approximate and honestly capped at `low` confidence.
2. **Backfill unrun** (BLOCKED, §7).
3. **Accuracy unmeasured** (NOT VERIFIED, §8).
4. **Girth estimation is a heuristic**, externally supported only in direction
   and only for waist. It can no longer name a size alone.
5. **Eligibility is a fixed allow/deny list** of category slugs. New categories
   default to *ineligible* — safe, but requires a code change to extend.
6. Overlapping size ranges in a supplied chart are preserved without warning.

---

## 10. Final classification

### PARTIALLY VERIFIED

The engine, its refusal paths and all eight safety invariants are **VERIFIED**
under the tested conditions, locally and in production. Two genuine semantic
defects found in this pass — estimates deciding sizes, and generic charts applied
to incompatible categories — are fixed and covered by tests.

It is **not** "complete": production brand-specific chart coverage is BLOCKED on
credentials, and real-world accuracy is NOT VERIFIED for want of ground-truth
data. Those are separate facts and neither means the algorithm is invalid.

*The implementation and core invariants are verified under the tested
conditions; production brand-specific chart coverage and real-world fit accuracy
remain limited by the documented conditions above.*

---

## 11. Sources

- Bozeman SR et al., *Predicting waist circumference from body mass index*, BMC
  Medical Research Methodology 2012;12:115 — the one source genuinely supporting
  the waist/BMI relationship used here.
- CDC/NHANES Anthropometry Procedures Manual — establishes that chest
  circumference is **not** an NHANES measure, which is why the chest coefficients
  are labelled unvalidated.
- EN 13402-3 — letter codes and girth intervals for the fallback chart.
- *An Interpretable Multi-Dimensional Fit Evaluation Framework for Online Apparel
  Size Recommendation*, Textiles 2026 — informed ease-based scoring. Its reported
  accuracy is **its own**, on its own dataset, and is not a claim about this system.
