# Fit Finder — Final Engineering Closure Report

**Scope:** Fit Finder / body measurements / size recommendation only.
**Branch:** `feat/fit-finder-sizing-engine` (single branch, as instructed)
**Baseline audited:** `main` @ `662df4a`
**Production:** https://confit-a.vercel.app/

---

## 0. This report is not punitive

This document exists to make the system's real state legible so it can be
improved — not to assign blame. Every defect described here was found by
deliberately attacking our own work, and several were introduced by the very
commits that claimed to fix the feature. That is normal engineering. The
valuable output is the set of invariants that now make those mistakes
structurally hard to repeat.

The rule applied throughout: **no claim appears here unless it was executed and
observed.** Where something could not be verified, it is marked BLOCKED or NOT
VERIFIED rather than softened.

---

## 1. Status summary

| Area | Status |
|---|---|
| Deterministic size engine (measurements → size) | VERIFIED |
| Refusal instead of fabrication when data is insufficient | VERIFIED |
| Units / bounds / outlier handling | VERIFIED |
| Inventory honesty (tri-state) | VERIFIED |
| Confidence expressed as band, never a probability | VERIFIED |
| Size-chart provenance disclosed | VERIFIED |
| Measurement-session ownership | VERIFIED |
| Production DB backfill of real brand charts | **BLOCKED** (credentials) |
| Measured recommendation **accuracy** | **NOT VERIFIED** (no ground-truth data) |

**Test evidence at closure:** backend **2350 passed, 5 skipped, 0 failed**;
frontend **254 passed / 31 files**; `tsc --noEmit` clean; `npm run build` OK.

---

## 2. What was actually wrong, and what fixed it

### 2.1 A size was recommended for a body nothing fits
The engine computed a fit score, labelled it *"Does not fit"*, and returned it
as a recommendation anyway. The refusal floor and the label threshold were two
independent literals that disagreed.

**Fix.** `NoPhotoFitService._DOES_NOT_FIT_BELOW` is now *bound by import* to
`_MIN_FIT_SCORE_FOR_RECOMMENDATION`. They are one number; they cannot drift.
Asserted by `test_rating_label_threshold_is_bound_to_the_engine_refusal_floor`.

*Verified in production:* chest 130 / waist 120 / h170 / w52 → `recommended:
false`, `NO_SIZE_FITS` (previously `S`, "85% confidence").

### 2.2 Unknown stock was reported as "in stock"
`level is None or level > 0` turned a size that had never been checked into an
available one. Inventory is now tri-state: `in_stock` / `out_of_stock` /
`unknown`, with `in_stock: null` for unknown, rendered as **"Not confirmed"**.
A size may only be *recommended* if availability is positively confirmed.

### 2.3 A rule score was presented as a probability
`confidence_score` is an evidence tally, never calibrated against fit outcomes.
Rendering "66% confidence" implied a measured frequency that does not exist.
Responses now carry `confidence_band` (high/medium/low),
`confidence_band_reason`, and `confidence_is_probability: false`.

**Found during this closure pass:** `FitFinderView` had been fixed, but
`NoPhotoFitModal.tsx` — mounted in `ConsumerLayout`, i.e. on *every* consumer
page — still rendered `{confidence_score}% confidence`. Fixing one surface and
declaring the class of bug closed is exactly the failure mode this pass existed
to catch. Now fixed and covered.

### 2.4 Measurements could be written to another user's session
A failed `createSession` returned id `1`, and results were submitted against
`sessionId || 1` — writing body measurements into session #1. The client code
had been corrected earlier, but **no test protected it**. Five regression tests
now assert: null (never `1`) on failure, *no* write attempted, no success toast
for a save that did not happen, correct id on success, and consent never
defaulted to true. The server-side owner gate (13 tests) remains the real
defence.

### 2.5 Provenance type drift (found this pass)
The backend emits four chart sources; the frontend union declared three,
omitting `product_chart_derived`. Corrected, with a comment tying the type to
its backend definition.

### 2.6 A test that could only pass in CI (found this pass)
`test_upgrade_downgrade_round_trip` shelled out to the bare name `python3`,
resolved via `PATH` — not the interpreter running the suite. It failed for
every developer using a virtualenv and passed in CI only because CI installs
into the system interpreter. It was previously dismissed as "environment-only".
It was a harness bug: it now uses `sys.executable`. **Result: the backend suite
has zero failures for the first time.**

---

## 3. Honest limits

### 3.1 Accuracy is NOT measured — and no figure is claimed
There is no ground-truth dataset of *(body measurements, garment, size actually
kept)* for this catalogue. The acceptance suite
(`backend/tests/fixtures/fit_acceptance_cases.json`, 21 cases) checks that
outputs fall in an expected **range** and that refusals fire — it measures
**self-consistency against a published standard, not real-world accuracy.**

Any "% accuracy" figure for this feature would be fabricated. None is given.
Measuring it requires post-purchase return/fit feedback.

### 3.2 Production runs on a generic chart — BLOCKED
Production products carry no per-product size chart, so the engine falls back
to EN 13402-3 and **correctly** reports `source: standard_en13402`,
`is_brand_published: false`, and caps confidence at `low`. This is honest, but
it is not brand-accurate sizing.

`backend/scripts/backfill_size_charts.py` is written and tested but **has never
run against production.** Blocked because the available `DATABASE_URL` is
rejected by Neon (`password authentication failed for user 'neondb_owner'`),
and the Vercel token can list the project but lacks permission to decrypt the
production env var (`decrypt=true` returns ciphertext). No workaround was
attempted beyond the project's own configuration.

**Operator command, once valid credentials are supplied:**
```bash
export DATABASE_URL='<production connection string>'
python -m backend.scripts.backfill_size_charts --dry-run   # inspect first
python -m backend.scripts.backfill_size_charts             # apply
```
The script is idempotent and never overwrites a brand-published chart.
Until it runs, confidence stays `low` in production **by design**.

---

## 4. Invariants now enforced

`backend/tests/test_fit_invariants.py` sweeps 315 combinations of body × chart ×
stock × fit preference (**633 assertions**) through the real service path:

1. A size rated "Does not fit" is never recommended.
2. The recommended size is confirmed available — never unknown.
3. Unknown stock renders as unknown, never as confirmed.
4. A non-brand chart never claims `is_brand_published`.
5. A generic fallback chart can never yield better than `low` confidence.
6. Every refusal carries a machine code *and* a human explanation.
7. Missing girths either refuse, or are disclosed as estimated at low confidence.

---

## 5. Requirement verification table

| # | Requirement | Status | Evidence |
|---|---|---|---|
| A | Recommendation computed from measurements, not BMI | VERIFIED | `fit/engine.py`; ease-based scoring per section |
| B | Refuse when data insufficient | VERIFIED | `NO_SIZE_CHART`, `NO_SCOREABLE_SIZE`, `NO_SIZE_FITS`, `NO_SELLABLE_SIZE`, `INVENTORY_UNKNOWN`; prod-verified |
| C | Value bounds / units / cm–in conversion | VERIFIED | `allow_inf_nan=False, gt=0`; invalid input → HTTP 422 in prod |
| D | Outlier & malformed-chart handling | VERIFIED | inverted ranges corrected, bad rows dropped with warnings, malformed JSON refused |
| E | Measurements used are surfaced | VERIFIED | `body_used` incl. estimated fields |
| F | Chart source + update date surfaced | VERIFIED | `size_chart_source` in API and both UI surfaces |
| G | No recommendation without confirmed inventory | VERIFIED | tri-state availability + invariant sweep |
| H | Confidence not presented as probability | VERIFIED | bands everywhere; both consumers fixed |
| I | Session ownership / permissions | VERIFIED | 13 backend security tests + 5 new client regressions |
| J | Brand-specific charts live in production | **BLOCKED** | backfill unrun; credentials unavailable (§3.2) |
| K | Measured accuracy | **NOT VERIFIED** | no ground-truth dataset (§3.1) |

---

## 6. Sources

- EN 13402-3 letter-code and girth-interval tables (primary chart basis).
- *An Interpretable Multi-Dimensional Fit Evaluation Framework for Online
  Apparel Size Recommendation*, Textiles 2026 — informed ease-vs-ideal-ease
  scoring, per-section labels and ranked candidates. Its reported accuracy is
  **its own**, on its own dataset; it is not a claim about this system.

---

## 7. If you continue this work

1. Obtain a working production `DATABASE_URL`, run the backfill (§3.2), then
   re-verify that confidence rises above `low` for products with real charts.
2. Capture post-purchase fit feedback — the only route to a defensible accuracy
   figure.
3. Confirm `engine_version` reports `fit-engine/2.1.0` in production after this
   merge deploys. Note for the record: an earlier note suspected production was
   "lagging" at `2.0.0`. That was wrong — the repository itself still said
   `2.0.0`; no `2.1.0` had ever been built. Production was reporting its version
   correctly. The constant is bumped to `2.1.0` in this change.
