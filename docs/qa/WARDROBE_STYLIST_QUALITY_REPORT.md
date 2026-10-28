# Wardrobe Stylist — AI Recommendation Quality Report

Dates: 2026-10-27 (baseline, prompt wx-stylist-1.0) and 2026-10-28 (after D10/D11 fixes, prompt **wx-stylist-1.1**) · Branch: `feat/watsonx-granite-stylist`
Dataset: `docs/qa/eval/wardrobe_stylist_eval_dataset.json` (v2026-10-27.1, 16 scenarios)
Harness: `scripts/eval/wardrobe_stylist_quality_eval.py` (FastAPI TestClient + SQLite, one user, items re-seeded per scenario)
Raw evidence: `docs/qa/eval/wardrobe_stylist_eval_{deterministic,live}_20261027.json` (before fixes) and `…_20261028.json` (after fixes)
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


---

## 7. Post-fix re-evaluation — 2026-10-28 (prompt wx-stylist-1.1, server reconciliation active)

Live: 22 real calls to `ibm/granite-4-h-small`, 0 retries, 0 fallbacks, p50 2.95 s, max 5.27 s. Harness gained three
hard-failure classes: **H10** fabricated-attribute *suspected* (keyword heuristic — human confirmation required),
**H11** prose describes a server-removed item, **H12** unsuitable wardrobe presented as suitable.

| Metric | 10-27 (before) | 10-28 (after) |
|---|---|---|
| Final-outfit constraint violations / hallucinated ids | 0 / 0 | **0 / 0** |
| Model-level colour-exclusion breaches (pre-filter, raw output) | 1/16 (S10) | 1/16 (S10 again) — **plus** S13 breached in run #1 of the day (black blouse in a "no black" Arabic request). Cumulative **3 breaches / 48 constrained-scenario calls**. Server guard caught all. |
| D10 — prose describes removed garments | S10 yes | **S10 fixed** (summary rewritten: "Final selection: White Dress Shirt … incomplete"; kept-item reason neutralised; "no bottoms/footwear left once the colours you asked to avoid were excluded"). Arabic S13 run #1 also rewritten correctly after the Arabic-prefix tokeniser fix. Remaining H11 hit on S10 is the model's own limitation naming the *unselected* grey loafers ("do not match the black-tie requirement") — a legitimate why-not statement; counted but not a defect. |
| D11 — unsuitable wardrobe sold as suitable | S16 yes | **S16 fixed**: `fit_status=unsuitable`, summary "Your wardrobe has no items suited to gym workout…", first limitation is the insufficiency statement, every reason is "Closest available X; not tagged for Active", no performance claims. The *model's raw* output also improved under prompt 1.1 ("formal shoes; not designed for gym use"). H12 = 0. |
| H10 suspected fabricated attribute | n/a | 1 (S04: "moisture-wicking" linen shirt; material not in metadata). Linen breathability is common knowledge but unsupported by the record — left to human review; server does not scrub outside the unsuitable path to avoid damaging good explanations. |
| H4 incomplete when completable | 0 | 1 (S01, see D12) + in run #1: S09 (model claimed "no smart-casual tops" while a sage linen shirt exists), S14 (model told the user to "choose silver heels if available" while silver heels exist in the wardrobe). Model-side inventory-awareness lapses; server cannot fix without re-prompting. |
| Consistency (Jaccard, 3 repeats) | 0.83 / 0.83 / 0.83 | 0.58 / 0.67 / 0.83 — more variance under the longer prompt; still ≥ 0.5. |
| Rubric means (heuristic) | expl 4.75, compl 5 | expl 4.88, compl 4.81, colour 4.62, others 5 |

### New defect
**D12 (P1, open) — id/description mix-up.** S01 raw output cited `wardrobe_item_id 3` (White Cotton Tee) with the reason
"Dark wash jeans provide a relaxed base" (jeans are id 5). The server correctly trusts stored categories, so the second
top was dropped and the outfit had no bottom. Fixed today: the response now says "1 suggested piece duplicated a position
already filled and was left out; the stylist may have mixed up item ids" (EN/AR, test `test_d12_role_collision_is_explained`).
Proposed next step: deterministic completion of empty core positions from the wardrobe, labelled "added by CONFIT's matcher",
or one controlled re-prompt with the offending id removed — product decision needed because both change what the user sees.

### Status of thresholds (still REQUIRE PRODUCT-OWNER APPROVAL)
Inventory hallucination 0 % ✓ · system-level constraint violation 0 % ✓ · language match 100 % ✓ ·
unsuitable-inventory honesty 1/1 ✓ (was 0/1) · model-level constraint compliance 93.75 % (gate ≥ 95 % not met — informational while the server guard exists) ·
human-scored rubric **unverified** (no human reviewer) · consistency ≥ 0.66: 2 of 3 scenarios ✓, S01 0.58 ✗.

### Human review status
No qualified fashion reviewer and no native Arabic reviewer were available in this environment. All subjective judgements
above are assistant review. The JSON files carry empty `*_REVIEWER` slots for them.


---

## 8. D12 resolution and final re-evaluation — 2026-10-28 (second session)

### Decision: deterministic, constraint-aware completion (option 4) + mismatch neutralisation (option 2), no re-prompt
Trade-off considered:
| Option | Pros | Cons | Decision |
|---|---|---|---|
| Controlled re-prompt with offending id removed | Keeps all prose model-authored | +3 s latency and +1 billed call per incident; model may fail again (observed 3 colour breaches in 70 calls); still needs server validation afterwards | not chosen (kept as follow-up if product prefers) |
| **Deterministic completion, labelled** | 0 extra latency/cost; uses the same scorer as the audited fallback; respects excluded ids and banned colours by construction; fully testable | A rule-chosen piece is less "styled" — hence it is visibly labelled and disclosed | **implemented** |
| Leave incomplete | Simplest | Users got 2-piece outfits while owning the missing piece (S01, S07, S09, S14) | rejected |

Implementation (`wardrobe_stylist_service.py`): `_rule_score` extracted and shared; `_complete_core_positions` fills empty
core roles (top/bottom/footwear, or footwear for a dress) with the best eligible item; each added `RecommendedItem` carries
`selected_by="rule_matcher"` (new field, default `"model"`), a rule reason naming the real garment, and the response gets the
limitation "N piece(s) were added by CONFIT's rule-based matcher … not chosen by the AI stylist" (EN/AR). A model reason that
describes a *different* wardrobe item than the id it cites (role claim ≠ stored category AND the text names another item) is
replaced by a rule reason and disclosed. Model limitations claiming a position is missing are dropped when the server fills it.
UI: amber "Added by rules / أُضيفت وفق القواعد" badge on the item card.

### Final live run (22 calls, ibm/granite-4-h-small, prompt wx-stylist-1.1)
| Metric | Result |
|---|---|
| Final-outfit hard-constraint violations | **0 / 16** |
| Invented / foreign wardrobe ids in final output | **0** (`rejected_references` empty) |
| ID-to-description mismatches reaching the user | **0** (1 detected live in S09 and neutralised + disclosed) |
| Completeness when completable (H4) | **16/16** (was 13/16 before D12; 3 scenarios completed by the rule matcher: S03 derbies, S09 Breton top, S14 silver heels — all disclosed, H13 = 0) |
| Unsuitable-wardrobe honesty (H12) | **1/1** (S16) |
| Language match EN/AR | **16/16**; Arabic prose now free of English occasion enums |
| Prose describing server-removed items (H11) | **0** |
| Suspected fabricated attributes (H10) | 3 — on inspection all are *negated* statements ("lacks moisture-wicking tops", "sneakers are summer-seasonal"); the keyword heuristic cannot parse negation. Human review required; not counted as defects. |
| Consistency (Jaccard, 3×3) | S01 0.73 · S03 1.0 · S12 0.83 (all ≥ 0.66) |
| Latency (single user, n=22) | p50 2.91 s · max 6.21 s — n too small for a p95 claim |
| Model-level colour-exclusion compliance (raw output, cumulative since 10-27) | **67/70 calls (95.7 %)**; every breach caught by the server guard |

Sample-size caveat: 16 scenarios × ≤3 repeats. These numbers show the mechanisms work; they are not a statistically
powered quality estimate. Human fashion review: **pending** (`docs/qa/FASHION_REVIEW_SHEET_STYLIST.md`). Native Arabic
review: **pending** (`docs/qa/ARABIC_REVIEW_SHEET_STYLIST.md`).
