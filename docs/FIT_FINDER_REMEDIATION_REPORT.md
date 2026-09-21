# Fit Finder & Size Recommendation — Remediation Report

**Slice:** Fit Finder / body measurements / size recommendation
**Repository:** `OmarAhmed-123/CONFIT_A` · **Production:** https://confit-a.vercel.app/
**Branch:** `feat/fit-finder-sizing-engine` (one branch) · **PRs:** #123, #125, #126
**Date:** 2026-09-21

---

## 0. اطمن — التقرير ده مش هيعاقب حد

**هذا التقرير ليس لمعاقبة أحد.** الهدف منه إننا نصلّح ونتعلّم، مش إننا نلوم.

كل حاجة مكتوبة هنا هي وصف لكود، مش حكم على شخص. الميزة دي كانت شغالة ومربوطة
وبتطلع نتيجة للمستخدم — المشكلة إن النتيجة دي مكانتش مبنية على مقاسات المنتج
الحقيقية. ده نوع من الأخطاء اللي بيحصل كتير جدًا في المنتجات اللي بتتبني بسرعة:
حد عايز يوصّل الميزة، فبيحط منطق مؤقت عشان الشاشة تشتغل، وبعدين الشغل بيكمل
والمنطق المؤقت بيفضل مكانه. ده مش إهمال، ده الطريقة الطبيعية اللي الديون التقنية
بتتراكم بيها.

اللي يستاهل التقدير إن المراجعة اتعملت أصلًا، وإن التقرير الأصلي كان أمين: قال
**"partially verified — routes exist, computation unproven"** بدل ما يقول
"شغال". الجملة دي بالظبط هي اللي خلّت الإصلاح ده ممكن.

> **In English:** this report will not punish anyone. Every finding below
> describes code, not a person. The feature was wired, deployed and returning
> answers — the problem was only that the answers were not derived from the
> garment. That is one of the most common ways software decays: someone ships a
> placeholder so the screen works, the work moves on, and the placeholder stays.
> The credit here belongs to the audit that said *"computation unproven"*
> instead of *"working"*. That honesty is what made this fix possible.

---

## 1. What the audit said, and what was actually true

The audit rated the feature **"partially verified — routes exist, computation
unproven"** and listed these gaps:

| # | Audit gap | Verdict after investigation |
|---|---|---|
| 1 | No measured accuracy or explanation | **Confirmed** — no accuracy could exist; see §2 |
| 2 | Bounds, units, cm/in conversion, missing measurements unverified | **Confirmed** — and worse than suspected |
| 3 | Brand-specific size charts unverified | **Confirmed** — charts were never read at all |
| 4 | No guard when inventory / size chart is absent | **Confirmed** — a size was always returned |
| 5 | Measurement-session ownership unvalidated | **Partly incorrect** — ownership *was* correctly enforced; consent was not |

Finding 5 is worth stating plainly: `measurement_service.py` already implemented
a correct owner-gating model (F-14). The audit flagged it as unverified, not as
broken, and on inspection it was sound. **Not every flagged item was a defect.**

### 1.1 The core finding

`no_photo_fit_service.py` computed a size from **BMI alone**. It never opened
`products.size_chart_json`. The same body received the same letter for a slim
tuxedo and a relaxed poplin shirt, from every brand in the catalogue.

Two reproductions **against live production**, before any change:

| Input | Response |
|---|---|
| chest 130 cm, waist 120 cm, weight 52 kg (a physically impossible body) | `recommended_size: "S"`, `confidence_score: 85` |
| `body_shape: "dragon"`, `chest: -50` | `recommended_size: "M"`, `confidence_score: 70` |

A negative chest measurement and a mythical body shape both produced a
confident recommendation. The confidence number was a constant in the source.

---

## 2. What was built

A new package, `backend/app/services/fit/` — 1,143 lines across five modules,
one responsibility each:

| Module | Responsibility |
|---|---|
| `units.py` | One conversion boundary; `BOUNDS_CM` plausibility ranges |
| `size_charts.py` | Parse `size_chart_json` (two shapes, aliases, cm/in); EN 13402-3 fallback; provenance |
| `anthropometry.py` | Estimate girths from height/weight **with a stated residual SD** |
| `ease.py` | Ease targets per garment class, material and preferred fit |
| `engine.py` | Score every candidate size, rank, decide, explain, refuse |

### 2.1 The algorithm

Modelled on *"An Interpretable Multi-Dimensional Fit Evaluation Framework for
Online Apparel Size Recommendation"* (Textiles, 2026,
[doi:10.3390/textiles6030075](https://doi.org/10.3390/textiles6030075)), which
reports 98.9–99.6% top-3 accuracy on 270 participants:

1. For each candidate size, compute **garment ease** per fit point (chest,
   waist, hip, shoulder, inseam, neck) from the chart.
2. Compare against the **ideal ease** for that garment class, material and the
   user's preferred fit.
3. Convert each deviation to a penalty via a **strictly decreasing** curve.
4. Aggregate with segment weights into an overall fit score; rank the sizes.

Every number the user sees is a real output of this computation.

### 2.2 The refusal path

The engine is allowed to say **no**, and does so as a `200` with
`recommended: false` plus a `reason_code` and the list of missing inputs:

```
oxford shoes → recommended=False, reason=NO_SIZE_CHART
               "any size we named would be a guess"
```

This directly answers audit gap #4. A wrong size is a return; a *confident*
wrong size is worse.

### 2.3 Provenance

Every response names the chart it used, whether the brand published it, and
when it was last updated — audit gap #3.

---

## 3. Findings we did not go looking for

These surfaced while fixing the above. They are listed because a report that
only contains what was expected is not a real report.

| # | Finding | Status |
|---|---|---|
| 1 | The `save-to-profile` route the frontend had always called **did not exist** | Fixed |
| 2 | Measurement writes were accepted against sessions created **without consent** | Fixed (gate + tests) |
| 3 | UI claimed `confidence_score: 95`, `body_shape: "Athletic"` and "on-device pose landmarks" — none computed | Fixed |
| 4 | `product_context_service.py` held a **duplicate** sizing implementation, so the PDP and Fit Finder could disagree about one garment | Fixed — one engine |
| 5 | On `createSession` failure the client returned the literal id `1`, writing the user's measurements into **session #1 — someone else's session** | Fixed |
| 6 | A failed measurement save was reported to the user as success | Fixed |
| 7 | UI claimed measurements were "encrypted with Fernet-256" — not a real cipher name | Fixed |
| 8 | `consent_granted` defaulted `True` in the model, `False` in the schema | Fixed — both `False` |
| 9 | Parity gate pinned `0018_partner_onboarding_email_lifecycle`, **a revision that has never existed** | Fixed |
| 10 | All nine seeded products had `size_chart_json = "{}"` | Fixed |

### 3.1 A defect found by testing the merged code in production

After all three PRs were merged and deployed, the audit's original impossible
body (chest 130, waist 120) was replayed against production. The engine had
clearly improved — confidence fell 85 → 50, the provenance was disclosed, and
the breakdown read `"your 130 cm vs 86-94 cm for size S: too tight (+36 cm)"`
with `fit_verdict: "Does not fit"`.

**But it still returned `recommended: true` and named size S.**

Two thresholds disagreed. The refusal gate fired only at `score <= 0`, which the
penalty curve never reaches because it is floored above zero, while the
presentation layer labels anything below 45 "Does not fit". The engine was
recommending a garment it simultaneously described as not fitting.

The confidence floor could never have caught this: confidence measures *how sure
we are*, and the engine was quite sure this did not fit. Fit quality needed its
own gate. Fixed in PR #134 with the two thresholds tied together and the
production case pinned as a regression test.

This is recorded prominently because it is the most important thing in this
report: **the fix was not finished when the tests passed and the PRs merged.**
It was finished when someone ran the original failing input against the deployed
system and read the output.

### 3.2 A mistake made during this work

Seeding real charts (finding 10) introduced a *new* false claim: the parser
labelled any product chart `"Brand-published size chart"`, which would have told
users that COS published measurements COS never published.

It was caught before merge and fixed — such charts now report as
`product_chart_derived` with the source named and `is_brand_published: false`.
It is recorded here because the point of this exercise is that overstatement is
easy and needs checking, including in the fix.

---

## 4. Evidence

Everything below is reproducible from the repository.

| Check | Result |
|---|---|
| Backend suite | **1,307 passed, 2 skipped** |
| Fit-specific tests | **116 passed** (acceptance + API + charts + session security) |
| Frontend typecheck | `tsc --noEmit` clean |
| Frontend tests | **110 passed**, 21 files |
| Frontend build | succeeds, 2,071 modules |
| CI on each PR | `backend`, `frontend`, `release gate` — all green |

Two caveats, stated rather than hidden:

- `test_upgrade_downgrade_round_trip` is deselected **in the local sandbox
  only**. It shells out to the system `python3`, which has no alembic here. It
  fails identically on an unmodified tree, and passes in CI.
- `Workers Builds: confit-a` fails on this branch. It alternates
  success/failure across `main`'s own history, is not a required check, and this
  branch touches no Workers configuration.

### 4.1 What "accuracy" does and does not mean here

The acceptance suite covers **multiple bodies, sizes and brands with an expected
*range*** rather than a single size, as the audit recommended. It proves the
engine reproduces published size charts for bodies whose correct size is known
by construction.

**It is not a measured real-world accuracy figure.** That requires labelled
purchase-and-return outcomes from real customers, which CONFIT_A does not yet
have. The honest claim is: *the computation is now correct and explainable
against published charts.* Claiming a percentage would repeat the original
error in a more sophisticated form.

The public fit datasets (ModCloth / RentTheRunway, Misra–Wan–McAuley RecSys'18)
were reviewed as a source for this and rejected: they carry small/fit/large
feedback labels but almost no body measurements, so they cannot validate a
measurement-driven engine.

### 4.2 The tests found a real bug

Writing the acceptance suite before the implementation was finished paid for
itself: `section_score` returned a flat `100.0` anywhere inside the tolerance
band, so several sizes tied and the tie-break returned **S** to a body the chart
places in **L**. A test written after the fact, against the implementation's own
behaviour, would have agreed with the bug.

---

## 5. Pull requests

| PR | Title | Scope |
|---|---|---|
| [#123](https://github.com/OmarAhmed-123/CONFIT_A/pull/123) | Fit Finder (1/3): a real size-recommendation engine replacing the BMI guess | Backend engine, 79 tests |
| [#125](https://github.com/OmarAhmed-123/CONFIT_A/pull/125) | Fit Finder (2/3): surface the real engine output in the UI | Frontend contract, refusals, units |
| [#126](https://github.com/OmarAhmed-123/CONFIT_A/pull/126) | Fit Finder (3/3): seed real size charts, close the remaining audit items | Charts, consent, rate limits, gate pin |
| [#127](https://github.com/OmarAhmed-123/CONFIT_A/pull/134) | Fit Finder (4/4): never recommend a size the engine itself calls "Does not fit" | Post-deploy production finding (§3.1) |

All four on one branch, all merged to `main` via merge commits.

Backwards compatibility was preserved throughout: legacy `*_cm` / `weight_kg`
request fields and the `return_risk_score` response string are still accepted
and returned. **No migration was required.**

---

## 6. What is still not done

Stated so nobody has to discover it later:

- **No measured real-world accuracy.** Needs return-outcome data (§4.1).
- **The demo catalogue's charts are standards-derived, not brand-published.**
  They say so in their own output. Real brand charts need a brand-portal upload
  path.
- **Shoes and one-size accessories cannot be sized.** The engine refuses for
  them, correctly. Footwear needs a last-length model, which is a different
  problem.
- **No feedback loop.** The engine does not learn from returns, because nothing
  yet records whether a recommendation was right.

---

## 7. Closing

The single lesson worth keeping: **the code was not broken, it was
unsubstantiated.** Every endpoint returned `200`, every screen rendered, and
every number looked plausible. Nothing would have alerted a monitor. What
exposed it was someone asking *"where does this number come from?"* and writing
down "unproven" when there was no answer.

The engine is now built so that the same question has an answer every time — the
measurements used, the chart, its date, the ease targets, the per-section
verdicts, the confidence factors, and an explicit refusal when the data will not
support a claim. If a future reviewer finds something overstated in this work,
that finding will be as welcome as this one was.

**ولو حد لقى في الشغل ده حاجة غلط أو مبالغ فيها، يقولها. ده بالظبط اللي خلّى
الإصلاح ده يحصل.**
