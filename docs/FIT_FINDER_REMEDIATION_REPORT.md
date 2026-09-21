# Fit Finder — Final Semantic Closure Audit

| | |
|---|---|
| **Repository** | `OmarAhmed-123/CONFIT_A` |
| **Branch audited** | `feat/fit-finder-sizing-engine` → merged to `main` |
| **Commit audited (pre-change baseline)** | `d417131` (contains `59ad0e0` = PR #159) |
| **Engine version before this pass** | `fit-engine/2.1.0` (observed in production) |
| **Engine version after this pass** | `fit-engine/2.2.0` |
| **Production** | https://confit-a.vercel.app/ |
| **Audit performed** | 2026-09-21, ~20:45–21:10 UTC |
| **Scope** | Fit Finder / body measurements / size recommendation only |

> **Metadata note (§2).** The previous report opened with `main @ ae228ed` while
> its closing section described PR #159 and `main @ 59ad0e0`. That mixed a
> mid-pass baseline with the final state. This report states one audited
> baseline above and marks every later state change explicitly. Nothing has been
> rewritten to look tidier: `ae228ed` really was the baseline of the *previous*
> pass, and `59ad0e0` really was its result.

---

## 0. This report is not punitive

It exists to make the system's real state legible. Several defects below were
introduced by commits that claimed to close this feature. Finding them is the
purpose of the exercise, not evidence of failure.

**Rule applied:** no claim appears here unless it was executed and observed.

| Status | Meaning |
|---|---|
| **VERIFIED** | Observed by execution; evidence cited. |
| **PARTIALLY VERIFIED** | Correct under tested conditions, with a stated limit. |
| **BLOCKED** | Cannot proceed due to a legitimate access limitation. |
| **NOT VERIFIED** | Requires ground-truth evidence that does not exist. |

---

## A. What was re-audited

The decision itself: *does the evidence available justify naming **one** size?*
Specifically — whether an uncertain estimate can still choose a size (§3/§4),
whether "one measured dimension" is universally sufficient (§5/§6), overlapping
ranges (§7/§8), tie-breaking (§9), explanation honesty (§10), estimation
provenance wording (§11), confidence semantics (§12), inventory interaction
(§13), and the production backfill (§15/§16).

---

## B. Estimated measurements — a real defect found and fixed

### B.1 Estimates were scored as exact values

`residual_sd()` appeared **only** in refusal diagnostics and a confidence
string — **never in scoring**. An estimated girth was fed into the scoring
function as if it were measured.

**Consequence, reproduced end-to-end.** A user who measured only their hip,
against a trouser chart in 5 cm waist steps:

```
measured:  hip 99
estimated: waist 83.5  (±7.0 cm, our own documented spread)
result:    size 32, "just right", is_ambiguous: FALSE, band: medium
```

Sliding that estimate within its own error bar produced **three different
sizes**:

| estimated waist | winner |
|---|---|
| 76.5 | 30 |
| 83.5 | 32 |
| 90.5 | 34 |

The waist is the *primary* trouser dimension, it was invented by us, and the
response asserted a single size with no ambiguity. This is the same class of
error as the earlier "66% confidence": our uncertainty was silently converted
into apparent precision.

### B.2 The fix — an interval robustness check

`FitEngine._estimate_robustness()` replays the **real scoring** with each
estimated field moved to each end of its documented ±SD interval (one field at a
time). If a different size wins anywhere in that range, the result is marked
ambiguous, the alternative size is named, confidence cannot be `high`, and the
user is told why:

> "Your waist was estimated from your height and weight, not measured, and that
> estimate is uncertain enough to reach into a neighbouring size. 32 is our best
> reading of the evidence, but we cannot narrow it to one size with confidence —
> measure your waist for a firm answer."

It is deterministic and conservative — an interval check, **not** a probability
model. It produces no percentage.

| Case | Before | After |
|---|---|---|
| hip measured, waist estimated | `32`, ambiguous **false**, band medium | `32`, ambiguous **true**, alt `30`, band medium |
| waist **and** hip measured | `32`, band high | `32`, band high (**unchanged**) |

The scoring loop was extracted into `_rank_candidates()` so the probe reuses the
exact production scoring rather than a second copy that could drift (DRY).

### B.3 A second defect found while testing: `decision.top`

`FitDecision.top` returned `candidates[0]` — the best-*scoring* size, which is
not always the *recommended* one. With `M` out of stock and `L` recommended,
`top` described `M`, so `top.in_stock` read `False` on a successful
recommendation. Existing invariant tests asserting `top.in_stock is True` had
passed only because stock usually coincided. `top` is now anchored to
`recommended_size`.

---

## C. Evidence sufficiency is dimension-aware — VERIFIED

The brief warned against "one measured dimension ⇒ enough evidence". Tested:
against a **waist/hip** trouser chart, a user who measured **only chest** is
**refused** (`INSUFFICIENT_EVIDENCE`), because the existing rule counts only
sections the chart actually scores. Measuring the *relevant* dimension unlocks a
recommendation. No change was needed; this is now locked down by test.

---

## D. Overlapping ranges and tie-breaking — VERIFIED, no change

Per §7 these were **not** assumed to be bugs, and they are not:

* **Case A — multidimensional overlap** (M chest 94–102/waist 78–86, L chest
  98–106/waist 82–90): legitimate; the second dimension separates them. Left intact.
* **Case B — ambiguous one-dimensional overlap** (M chest 94–104, L 98–108,
  user 101): scores tie at exactly **100.0/100.0**; the engine reports
  `is_ambiguous: true` and names `L` as the alternative. The ambiguity is
  exposed, not hidden.
* **Tie-break** is an explicit documented product rule — *on equal score prefer
  the smaller size* — applied via `sort(key=(-score, size_sort_key))`. Verified
  deterministic across repeated runs **and** independent of chart row order, so
  it does not rely on dict/DB/sort-stability accidents.

---

## E. Inventory — VERIFIED

| Case | Behaviour |
|---|---|
| Two sizes genuinely fit, only one in stock | Available one recommended (permitted: both valid) |
| Fitting size out of stock, non-fitting size in stock | `NO_SIZE_FITS` — inventory never promotes a bad fit |
| No stock information at all | `INVENTORY_UNKNOWN`, `inventory_checked: false` |

---

## F. Confidence — VERIFIED

Bands only (`high`/`medium`/`low`), `confidence_is_probability: false`. Confirmed
the band is **not** a disguised uncertainty channel: an interval-unstable
estimate is forced ambiguous and therefore cannot reach `high`, regardless of how
high the heuristic tally is. A repo-wide sweep (backend, frontend, schemas,
i18n, docs, fixtures) found **no live user-facing percentage**.

---

## G. Provenance — VERIFIED

`brand_published` / `product_chart_derived` / `standard_en13402` / `none`;
frontend union matches the backend. §11 wording sweep removed the last two
phrases implying a fitted model ("the fitted BMI support", "validated
plausibility window"). The estimator is labelled a **product heuristic**
throughout, with the single genuine citation (waist/BMI direction) and an
explicit statement that chest/shoulder/neck have **no** external backing —
NHANES does not measure chest circumference.

---

## H. Security — VERIFIED (unchanged)

13 backend measurement-session tests (ownership, cross-user denial as 404-not-
oracle, consent never fabricated) plus 5 client regressions for the historical
`sessionId || 1` cross-user write. Not re-modified this pass.

---

## I. Test results

| Suite | Result |
|---|---|
| Backend | **2418 passed, 8 skipped, 0 failed** |
| Frontend | **254 passed / 31 files** |
| `tsc --noEmit` | clean |
| `npm run build` | succeeds |

New this pass: `backend/tests/test_fit_evidence_sufficiency.py` (20 tests —
interval ambiguity, dimension-aware sufficiency, overlap, ties, inventory,
explanation honesty), all through the real engine path.

---

## J. Production verification (live, read-only)

| Check | Result |
|---|---|
| Height + weight only | `INSUFFICIENT_EVIDENCE` — no unique size |
| Normal supported garment (id 3) | `M`, band `medium` |
| Provenance after backfill | `product_chart_derived`, `is_brand_published: false`, updated `2026-09-21` |
| Impossible body | `NO_SIZE_FITS` |
| Invalid input (`chest: -50`) | **HTTP 422** |
| Footwear / accessories (ids 6–9) | refused — no generic EN 13402 recommendation |
| Confidence semantics | band + reason + `confidence_is_probability: false` |

No customer records were mutated; only `products.size_chart_json` was written
(§K).

---

## K. Production database / backfill — **COMPLETED** (previously BLOCKED)

Working Neon credentials were supplied in this pass, so the long-standing
blocker is resolved. Executed against the production database:

1. **Dry run** — planned 5 updates; verified afterwards that **0** products had
   a chart, i.e. it genuinely wrote nothing.
2. **Applied** — 5 products updated.
3. **Idempotency re-run** — `updated: 0, already correct (no-op): 5`.

| Product | Category | Result |
|---|---|---|
| tailored-italian-wool-double-breasted-blazer | outerwear | chart written |
| tuxedo-peak-lapel-evening-dinner-jacket | outerwear | chart written |
| relaxed-organic-poplin-oxford-shirt | tops | chart written |
| pleated-tapered-virgin-wool-trousers | bottoms | chart written |
| silk-slip-column-maxi-dress | dresses | chart written |
| goodyear-welted-leather-oxford-shoes | footwear | **untouched** |
| strappy-metallic-leather-heeled-sandals | footwear | **untouched** |
| silk-jacquard-evening-necktie | accessories | **untouched** |
| structured-metallic-evening-box-clutch | accessories | **untouched** |

**Observed production effect:** product 3 moved `standard_en13402` →
`product_chart_derived`, and confidence rose `low` → `medium`.

**Provenance remains honest:** these are **standards-derived** charts.
`is_brand_published` stays **false** — they are *not* the brands' own
measurements and must never be relabelled as such. Rollback (documented in the
script output): set those 5 slugs' `size_chart_json` back to `'{}'`.

---

## L. Accuracy — **NOT VERIFIED**

No ground-truth dataset of *(measurements, garment, size actually kept)* exists.
2418 passing tests prove **implementation behaviour and internal consistency**,
not real-world accuracy. Consistency is not accuracy; a public standard is not a
measurement of our users. **No accuracy figure is claimed anywhere.**

To measure it, the minimum needed is: customer measurements, product,
recommended size, size retained, exchange/return reason, fit feedback.

---

## M. Remaining limitations

1. **Charts are standards-derived, not brand-published.** Production sizing is
   better than the generic fallback but is still not the brands' own data;
   confidence is correspondingly capped below `high` for chart provenance.
2. **Accuracy unmeasured** (§L).
3. **Girth estimation remains a heuristic**, externally supported only in
   direction and only for waist. It cannot name a size alone, and can no longer
   assert a size its own error bar contradicts.
4. **Robustness probing uses ±1 SD**, a deliberate conservative choice, not a
   calibrated interval. A wider probe would refuse more often; this is a product
   judgement, documented in code.
5. **Fallback eligibility is a fixed allow/deny list.** New categories default to
   ineligible — safe, but extending it requires a code change.
6. The four remaining `fit_confidence_score` fields on the Try-On session model
   are a **different feature** (VTON) and were deliberately left untouched.

---

## N. Final classification

### PARTIALLY VERIFIED

The engine, its refusal paths, and all safety invariants are **VERIFIED** under
the tested conditions, locally and in production. The production chart backfill
is now **COMPLETED** rather than BLOCKED. Real-world accuracy remains **NOT
VERIFIED** for want of ground-truth data.

*The implementation and core invariants are verified under the tested
conditions; production charts are standards-derived rather than brand-published,
and real-world fit accuracy remains unmeasured.*

---

## O. Sources

- Bozeman SR et al., *Predicting waist circumference from body mass index*, BMC
  Medical Research Methodology 2012;12:115 — supports the waist/BMI **direction**
  only.
- CDC/NHANES Anthropometry Procedures Manual — establishes that chest
  circumference is **not** an NHANES measure, which is why the chest coefficients
  are labelled unvalidated.
- EN 13402-3 — letter codes and girth intervals for the fallback chart.
