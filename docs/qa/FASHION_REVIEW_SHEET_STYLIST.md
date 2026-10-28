# Fashion Expert Review Sheet — CONFIT AI Stylist

**Status: PENDING — no qualified fashion reviewer has evaluated these outputs.**
Human-quality sign-off is **withheld**. Nothing in this sheet is a reviewer score; the
"assistant pre-read" column is a non-expert machine observation provided only to speed up the
reviewer's work and must not be reported as human validation.

## Reviewer qualification (to be filled by the reviewer)
| Field | Value |
|---|---|
| Name / role | _pending_ |
| Qualification (styling / fashion-design / retail-styling experience) | _pending_ |
| Review date | _pending_ |
| Approval status | ☐ approved ☐ approved with remediation ☐ rejected |

## Scope of what a photograph can and cannot establish
Wardrobe metadata comes from photos plus user edits. It **cannot** establish body measurements,
garment sizing, fabric composition or actual fit. Reviewers must not score "fit" unless the
wardrobe record carries user-provided size/fit data (none of the evaluation scenarios do).

## Method
- Source runs: `docs/qa/eval/wardrobe_stylist_eval_live_20261028.json` (ibm/granite-4-h-small,
  prompt wx-stylist-1.1, server reconciliation + rule completion active). Each record has the
  request, the seeded wardrobe (ids, titles, colours, patterns, occasion tags, seasonality), the
  raw model output, and the final validated outfit shown to the user.
- Score each dimension 1–5; mark severity of issues: **S1 blocking · S2 major · S3 minor · S4 cosmetic**.
- Record disagreements with the automated/heuristic scores explicitly; subjective preference is
  not a defect unless it contradicts the stated occasion, season, or constraint.

## Dimensions
1 Colour coordination & contrast · 2 Pattern compatibility · 3 Occasion appropriateness ·
4 Seasonal appropriateness · 5 Category/styling compatibility · 6 Formality consistency ·
7 Footwear suitability · 8 Layering & accessories · 9 Practicality for the environment ·
10 Fit (ONLY if fit data exists — otherwise N/A) · 11 Truthfulness & quality of explanation

## Sample set (16 primary scenarios; the reviewer may add the 6 repeats)
| Scenario | Request (abridged) | Final outfit (10-28 run) | Assistant pre-read (not a score) | Reviewer scores 1–11 | Severity | Remediation | Comments |
|---|---|---|---|---|---|---|---|
| S01 | Casual, park, autumn morning, relaxed/layered | Plaid flannel · dark jeans (rule-completed in some runs) · olive field jacket · brown boots | Conventional autumn palette; one run needed rule completion after an id mix-up | | | | |
| S02 | Business formal meeting | Navy blazer · white poplin · navy wool trousers · black oxfords | Coherent | | | | |
| S03 | Interview, exclude black, autumn | Navy chinos · white oxford · brown derbies (± camel coat) | Fine; coat dropped in later runs — reviewer to judge | | | | |
| S04 | Smart casual rooftop dinner, 31 °C | Linen camp shirt · linen trousers · tan loafers | Model called linen "moisture-wicking" — unsupported by metadata (H10) | | | | |
| S05 | Winter morning commute | Charcoal overcoat · grey trousers · navy merino · black Chelsea boots | Coherent | | | | |
| S06 | Smart casual, no footwear in wardrobe | Navy blazer · stone chinos · striped oxford; footwear missing (honest) | Correct disclosure | | | | |
| S07 | Cocktail, dress-only wardrobe | Emerald satin midi · gold clutch · black strappy heels (rule-completed) | Model omitted the heels and said none existed; server added them, labelled | | | | |
| S08 | Two-item wardrobe | Black joggers · grey hoodie; footwear missing | Honest | | | | |
| S09 | 24-item wardrobe, gallery opening, spring | Camel trench · ecru wide-leg · black loafers · Breton top (rule-completed) | Model ignored two available tops; reviewer to judge Breton + trench | | | | |
| S10 | Black tie, exclude black/grey/navy | White dress shirt only; incomplete, explained | Unsatisfiable by design; check honesty of text | | | | |
| S11 | Poorly described items ("thing from grandma") | Floral blouse · beige trousers · white shoes | Model stated its assumption | | | | |
| S12 | Arabic — casual family picnic, spring | تيشيرت رمادي · بنطلون كاكي · حذاء رياضي أبيض | Clean | | | | |
| S13 | Arabic — interview, free-text «بدون أسود» | قميص أبيض · بنطلون كحلي · حذاء بني | Model breached the exclusion in one run; server guard caught it | | | | |
| S14 | Arabic — winter wedding, formal evening | فستان سهرة كحلي · شال صوف أسود · كلاتش ذهبي · كعب فضي (rule-completed) | Gold + silver metallics together — reviewer to judge | | | | |
| S15 | Pattern-heavy wardrobe, brunch | Plain white shirt · navy chinos · white sneakers | Model chose the solids — reviewer to judge if too safe | | | | |
| S16 | Gym workout, formal-only wardrobe | Marked **unsuitable**; suit pieces shown as "closest available, not a fit" | Honesty behaviour is the thing to verify | | | | |

## Reviewer summary (to be filled)
- Overall rubric average: _pending_ (provisional gate ≥ 4.0, no dimension < 3.5 — product-owner approval required)
- Blocking issues: _pending_
- Disagreements with heuristic scores (`rubric` in the JSON): _pending_
