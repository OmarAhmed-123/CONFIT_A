# Wardrobe Stylist — AI Recommendation Quality Report

Date: 2026-10-27 · Branch: `feat/watsonx-granite-stylist` · Prompt: `STYLIST_PROMPT_VERSION` unchanged
Dataset: `docs/qa/eval/wardrobe_stylist_eval_dataset.json` (v2026-10-27.1, 16 scenarios)
Harness: `scripts/eval/wardrobe_stylist_quality_eval.py` (FastAPI TestClient + SQLite, one user, items re-seeded per scenario)
Raw evidence: `docs/qa/eval/wardrobe_stylist_eval_deterministic_20261027.json`, `docs/qa/eval/wardrobe_stylist_eval_live_20261027.json`
(inputs, item ids, served model id, prompt version, raw + parsed model output, final outfit, scores, latency, attempts).

> **Honesty labels.** "Live" = real inference against watsonx.ai, served model `ibm/granite-4-h-small`, 22 calls, 0 retries, 0 fallbacks.
> "Deterministic" = CONFIT's rule-based fallback with the model disabled — it is a baseline, **not AI**.
> Hard failures are computed by code. Rubric scores are a code heuristic plus an **assistant (non-human) review**; no human
> stylist or native Arabic speaker has scored these outputs. Thresholds below are proposals **requiring product-owner approval**.

## 1. Headline results

| Metric | Deterministic baseline | Live Granite (granite-4-h-small) |
|---|---|---|
| Scenarios | 16 | 16 (+6 consistency repeats) |
| Hard failures (H1–H9, system level) | 0 (after fixes D7–D9; was 3× H5 before) | **0** |
| Hard-constraint violations in final outfit | 0.0 | **0.0** |
| Inventory hallucination (item not in closet) | 0.0 | **0.0** (`rejected_references` empty in all 22 calls) |
| Response language matches request (EN/AR) | 16/16 | 16/16 |
| Latency p50 / max (whole request incl. app) | 0.008 s / 0.01 s | 3.25 s / 5.30 s |
| Consistency (Jaccard of item sets, 3 repeats × 3 scenarios) | 1.0 | 0.83 / 0.83 / 0.83 |
| Rubric mean (heuristic): constraint / inventory / completeness | 5 / 5 / 5 | 5 / 5 / 5 |
| Rubric mean (heuristic): seasonal / colour / pattern / explanation / occasion | 5 / 4.75 / 5 / 3 / 4.94 | 4.87 / 4.5 / 5 / 4.75 / 4.94 |

Model latency vs app overhead: deterministic path 8 ms end-to-end ⇒ ≈99.7 % of live latency is model time (consistent with the load-test split in `docs/qa/LOAD_TEST_STYLIST.md`).

## 2. Findings the automated rubric under-penalises (assistant review)

| ID | Scenario | Finding | Severity | Proposed action |
|---|---|---|---|---|
| **Q1** | S10 black tie + exclude dark colours | Model **disobeyed the colour exclusion**: raw output picked black tuxedo jacket, navy trousers, black patent shoes. The server-side filter (defect D1 fix, previous round) removed them, so the *final* outfit is compliant (1 item) and a limitation explains why. But the model's summary ("classic black-tie look using the available tuxedo jacket…") and two limitations still describe the stripped items. | P1 — misleading prose, no constraint breach | (a) Keep the server-side guard as the compliance mechanism (verified necessary: 1/16 model-level breaches). (b) When items are stripped, replace the model summary with a neutral server summary, or re-prompt once with the banned items removed from the closet list. Track as **D10**. |
| **Q2** | S16 gym workout, formal-only wardrobe | Model rationalised an unsuitable outfit with fabricated attributes ("white dress shirt … wicks sweat", "oxfords … choose a cushioned version for gym use"). Limitations do say "no dedicated gym shoes; oxfords are a compromise", so it is not silent, but the tone presents a bad outfit as acceptable. Deterministic fallback now says plainly "Nothing in your wardrobe is tagged for Active; this is the closest match, not a fit." | P1 — confident wrong advice | Prompt rule: when no item fits the occasion/activity, state that first and do not invent fabric/performance properties. Add to rubric as hard failure **H10 fabricated attribute** once a checker exists (needs human spot-check for now). Assistant score: occasion_fit 2, explanation 2 (heuristic gave 4/5). |
| Q3 | S07 cocktail dress | "Gold clutch … matches the metallic tone of the strappy heels" — heels are black. Minor factual slip in reasoning. | P3 | Human spot-check item; no code change. |
| Q4 | S08 two-item wardrobe | Model wrote "assume sneakers are available" while the server appended "No footwear in your wardrobe". Contradictory limitations. | P3 | Server should de-duplicate/override model limitations on the same missing category. |
| Q5 | S13, S14 Arabic | Grammatically odd phrases: S14 summary "…في قاعة مغطى باللون الأسود", S13 assumption "…وليس بدون تيشيرت أو بدلة رسمية". Meaning is recoverable but not native quality. S12 is clean. | P2 — needs native review | Add to `docs/qa/ARABIC_REVIEW_SHEET_STYLIST.md` sample set; native Arabic review remains **BLOCKED** (no reviewer available). |
| Q6 | S01, S03, S14 colour_coordination = 3 | Heuristic flags 4-colour outfits (navy/blue/green/brown; navy/white/tan/brown; navy/gold/silver). Assistant review: S01 and S03 are conventional menswear palettes and read as 4–5; S14 mixes gold and silver metallics (3 is fair). | Rubric calibration | Keep heuristic conservative; record disagreement; product owner to decide. |
| Q7 | S09 seasonal = 3 | Items seeded without season tags in the 24-item scenario, so the heuristic cannot credit the (reasonable) linen/ecru spring pick. | Dataset gap | Add season tags to S09 items in dataset v2. |
| Q8 | Consistency 0.83 | Each repeated scenario swapped exactly one item across three runs at temperature 0 (model non-determinism). Acceptable for a stylist UI; would matter for cached/shared results. | Info | Threshold proposal below. |

Model-level vs system-level compliance: **model-level colour-exclusion compliance 15/16; system-level 16/16.** The product guarantee must continue to rest on the server-side guard, not on the prompt.

## 3. Where the model is clearly better than the fallback

- Explanations are specific and item-aware (S04 explicitly declines a jacket for a humid rooftop; S09 names the trench as too formal and gives its id; S11 interprets "thing from grandma" from its tags as a floral blouse and *states the assumption*).
- Arabic: full Arabic prose with correct item names (S12 good; S13/S14 acceptable but see Q5). Fallback Arabic is template-grade and leaves enum values ("Casual") in English.
- Dress-based outfits (S07, S14) are composed sensibly with accessory + footwear without being forced into top/bottom.
- Missing-category honesty is equal in both (S06/S08 report missing footwear).

## 4. Proposed acceptance thresholds (REQUIRE PRODUCT-OWNER APPROVAL)

| Dimension | Proposed gate | Live result | Status |
|---|---|---|---|
| Inventory hallucination in final outfit | 0 % | 0 % | meets |
| Hard-constraint violation in final outfit (system level) | 0 % | 0 % | meets |
| Model-level constraint compliance (pre-filter) | ≥ 95 % (informational, not a release gate while server guard exists) | 93.75 % (15/16) | below — monitor |
| Language match EN/AR | 100 % | 100 % | meets |
| Unsuitable inventory: explicit "not a fit" statement, no fabricated properties | 100 % of unsatisfiable scenarios | 0/1 (S16) | **fails — Q2** |
| Rubric mean per dimension (human-scored) | ≥ 4.0, no dimension < 3.5 | heuristic only; not human-scored | **unverified** |
| Consistency Jaccard at temperature 0 | ≥ 0.66 | 0.83 | meets |
| Latency p95 end-to-end (single user) | ≤ 6.5 s | max 5.30 s on 22 calls (p95 not meaningful at n=22; see load tests) | meets (small n) |

## 5. Defects raised/closed in this round

- D7 (closed): fallback replied in English to Arabic requests — localized title/summary/limitations/reasons (`_FALLBACK_TEXT`, `_*_AR` maps). Verified: H5 count 3 → 0.
- D8 (closed): fallback added a down parka for a summer evening — outerwear no longer added for summer evenings. Verified S04.
- D9 (closed): fallback gave no warning when nothing matched the occasion — new `no_occasion_match` limitation. Verified S16.
- D10 (open, P1): model prose references items stripped by the server colour filter (Q1).
- D11 (open, P1): model rationalises unsuitable inventory with invented attributes (Q2).
- Q5 Arabic phrasing (open, P2, blocked on native reviewer).

## 6. How to re-run

```bash
# deterministic baseline (no network)
PYTHONPATH=. .venv/bin/python scripts/eval/wardrobe_stylist_quality_eval.py --mode deterministic
# live (needs WATSONX_* in the environment; ~22 calls; never commit the env file)
set -a && source ~/.env.local && set +a
PYTHONPATH=. .venv/bin/python scripts/eval/wardrobe_stylist_quality_eval.py --mode live
```
Outputs: `docs/qa/eval/wardrobe_stylist_eval_{mode}_{YYYYMMDD}.json`. Fill the `*_REVIEWER` fields when a human scores a run.
