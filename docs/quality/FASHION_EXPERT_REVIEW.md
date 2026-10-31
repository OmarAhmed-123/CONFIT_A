# Fashion Expert Review Package — 16 stylist cases (prepared 2026-10-29)

**Status: PREPARED, NOT REVIEWED.** No fashion reviewer has evaluated these cases yet; no reviewer is named or implied. This package exists so a qualified reviewer can score the outputs without touching the system. Reviewer sheet template: `docs/qa/FASHION_REVIEW_SHEET_STYLIST.md`.

## Source of the outputs
* **Live Granite outputs**: `docs/qa/eval/wardrobe_stylist_eval_live_20261028.json` — `ibm/granite-4-h-small` on watsonx.ai eu-de, 2026-10-28, 0 automated hard-rule violations across the run.
* **Deterministic engine outputs** (labelled `deterministic_fallback`, not AI): `docs/qa/eval/wardrobe_stylist_eval_deterministic_20261029.json`.
* Closets are synthetic fixtures (9–12 items each) defined in `scripts/eval/wardrobe_stylist_quality_eval.py`.

## How to score (per case)
| Criterion | 1–5 scale | Notes |
|---|---|---|
| Occasion appropriateness | 1 = wrong register, 5 = exactly right | consider location + time of day |
| Colour/pattern harmony | | penalise only real clashes, not personal taste |
| Season/climate fit | | |
| Constraint compliance | pass/fail | excluded colours, preferences, notes |
| Explanation honesty | 1–5 | does the summary claim anything not in the items? |
| Arabic quality (AR cases) | 1–5 | MSA, natural fashion vocabulary, no machine-translated feel |
| Overall verdict | Accept / Accept with edits / Reject | with one sentence |

## Cases

### Case 01 — `S01_casual_park_morning_autumn` (EN)

* **Request**: occasion *Casual*, season autumn, time morning, location park; excluded colours —; preferences —; notes —
* **Closet size**: 7 items
* **Live Granite look** (source `watsonx`): Olive Field Jacket (Green); Plaid Flannel Shirt (Navy); Dark Wash Jeans (Blue); Brown Leather Boots (Brown)
* **Granite summary**: A relaxed, layered look for a casual morning stroll in the park, using autumn-appropriate outerwear and footwear.
* **Automated hard-rule failures (live)**: ['H10_fabricated_attribute_suspected']
* **Deterministic look** (for contrast, not AI): White Cotton Tee (White); Khaki Chinos (Beige); Brown Leather Boots (Brown); Olive Field Jacket (Green)
* **Reviewer scores**: occasion ☐  harmony ☐  season ☐  constraints ☐  honesty ☐  arabic ☐  → verdict ☐  comment: ______________________

### Case 02 — `S02_business_formal_meeting` (EN)

* **Request**: occasion *Business Formal*, season spring, time afternoon, location client office; excluded colours —; preferences ['navy', 'white']; notes —
* **Closet size**: 9 items
* **Live Granite look** (source `watsonx`): Navy Blazer (Navy); Navy Wool Trousers (Navy); White Poplin Shirt (White); Black Cap-Toe Oxfords (Black)
* **Granite summary**: A classic navy blazer paired with navy wool trousers and a crisp white poplin shirt creates a polished business formal look suitable for an afternoon client meeting in spring.
* **Automated hard-rule failures (live)**: []
* **Deterministic look** (for contrast, not AI): White Poplin Shirt (White); Navy Wool Trousers (Navy); Black Cap-Toe Oxfords (Black)
* **Reviewer scores**: occasion ☐  harmony ☐  season ☐  constraints ☐  honesty ☐  arabic ☐  → verdict ☐  comment: ______________________

### Case 03 — `S03_interview_no_black` (EN)

* **Request**: occasion *Work & Business*, season autumn, time morning, location —; excluded colours ['black']; preferences ['navy', 'white', 'beige']; notes —
* **Closet size**: 7 items
* **Live Granite look** (source `watsonx`): Navy Chinos (Navy); White Oxford Shirt (White); Camel Coat (Tan); Brown Derbies (Brown)
* **Granite summary**: A clean, professional look in navy, white and camel that aligns with the interview setting and avoids black.
* **Automated hard-rule failures (live)**: []
* **Deterministic look** (for contrast, not AI): White Oxford Shirt (White); Navy Chinos (Navy); Brown Derbies (Brown); Camel Coat (Tan)
* **Reviewer scores**: occasion ☐  harmony ☐  season ☐  constraints ☐  honesty ☐  arabic ☐  → verdict ☐  comment: ______________________

### Case 04 — `S04_summer_evening_dinner` (EN)

* **Request**: occasion *Smart Casual*, season summer, time evening, location rooftop restaurant, 31°C; excluded colours —; preferences —; notes —
* **Closet size**: 7 items
* **Live Granite look** (source `watsonx`): Linen Camp Shirt (Ivory); Tailored Linen Trousers (Beige); Leather Loafers (Tan)
* **Granite summary**: A breathable linen shirt and tailored linen trousers create a relaxed yet polished smart‑casual outfit perfect for a hot summer evening on a rooftop restaurant.
* **Automated hard-rule failures (live)**: ['H10_fabricated_attribute_suspected']
* **Deterministic look** (for contrast, not AI): Linen Camp Shirt (Ivory); Tailored Linen Trousers (Beige); Leather Loafers (Tan)
* **Reviewer scores**: occasion ☐  harmony ☐  season ☐  constraints ☐  honesty ☐  arabic ☐  → verdict ☐  comment: ______________________

### Case 05 — `S05_winter_morning_commute` (EN)

* **Request**: occasion *Work & Business*, season winter, time morning, location city commute by metro; excluded colours —; preferences —; notes —
* **Closet size**: 7 items
* **Live Granite look** (source `watsonx`): Charcoal Wool Overcoat (Grey); Grey Wool Trousers (Grey); Merino Crewneck (Navy); Leather Chelsea Boots (Black)
* **Granite summary**: A smart, weather-appropriate work outfit that keeps you warm on a 20-minute metro walk.
* **Automated hard-rule failures (live)**: []
* **Deterministic look** (for contrast, not AI): Merino Crewneck (Navy); Grey Wool Trousers (Grey); Leather Chelsea Boots (Black); Charcoal Wool Overcoat (Grey)
* **Reviewer scores**: occasion ☐  harmony ☐  season ☐  constraints ☐  honesty ☐  arabic ☐  → verdict ☐  comment: ______________________

### Case 06 — `S06_missing_footwear` (EN)

* **Request**: occasion *Smart Casual*, season spring, time afternoon, location —; excluded colours —; preferences —; notes —
* **Closet size**: 3 items
* **Live Granite look** (source `watsonx`): Navy Unstructured Blazer (Navy); Stone Chinos (Beige); Striped Oxford Shirt (Blue)
* **Granite summary**: A refined yet relaxed look pairing a navy blazer with stone chinos and a blue striped Oxford shirt for a polished smart‑casual impression in spring.
* **Automated hard-rule failures (live)**: []
* **Deterministic look** (for contrast, not AI): Striped Oxford Shirt (Blue); Stone Chinos (Beige)
* **Reviewer scores**: occasion ☐  harmony ☐  season ☐  constraints ☐  honesty ☐  arabic ☐  → verdict ☐  comment: ______________________

### Case 07 — `S07_cocktail_dress_only` (EN)

* **Request**: occasion *Cocktail*, season summer, time evening, location hotel terrace; excluded colours —; preferences —; notes —
* **Closet size**: 3 items
* **Live Granite look** (source `watsonx`): Emerald Satin Midi Dress (Green); Gold Clutch (Yellow); Black Strappy Heels (Black)
* **Granite summary**: The emerald satin midi dress pairs with gold accessories for a vibrant, elegant cocktail look on a hotel terrace.
* **Automated hard-rule failures (live)**: []
* **Deterministic look** (for contrast, not AI): Emerald Satin Midi Dress (Green); Black Strappy Heels (Black)
* **Reviewer scores**: occasion ☐  harmony ☐  season ☐  constraints ☐  honesty ☐  arabic ☐  → verdict ☐  comment: ______________________

### Case 08 — `S08_tiny_wardrobe_two_items` (EN)

* **Request**: occasion *Casual*, season —, time —, location —; excluded colours —; preferences —; notes —
* **Closet size**: 2 items
* **Live Granite look** (source `watsonx`): Black Joggers (Black); Grey Hoodie (Grey)
* **Granite summary**: A relaxed, all-season look pairing the black joggers with the grey hoodie for effortless casual style.
* **Automated hard-rule failures (live)**: []
* **Deterministic look** (for contrast, not AI): Grey Hoodie (Grey); Black Joggers (Black)
* **Reviewer scores**: occasion ☐  harmony ☐  season ☐  constraints ☐  honesty ☐  arabic ☐  → verdict ☐  comment: ______________________

### Case 09 — `S09_large_wardrobe_24_items` (EN)

* **Request**: occasion *Smart Casual*, season spring, time afternoon, location art gallery opening; excluded colours —; preferences —; notes —
* **Closet size**: 24 items
* **Live Granite look** (source `watsonx`): Camel Trench (Tan); Ecru Wide-Leg Trousers (Ivory); Black Loafers (Black); Silk Scarf (Multi); Striped Breton Top (Navy)
* **Granite summary**: A clean, understated ensemble that balances smart casual formality with spring-appropriate comfort, anchored by a sleek trench and refined footwear.
* **Automated hard-rule failures (live)**: []
* **Deterministic look** (for contrast, not AI): Striped Breton Top (Navy); Ecru Wide-Leg Trousers (Ivory); Black Loafers (Black)
* **Reviewer scores**: occasion ☐  harmony ☐  season ☐  constraints ☐  honesty ☐  arabic ☐  → verdict ☐  comment: ______________________

### Case 10 — `S10_conflicting_constraints_black_tie_no_dark` (EN)

* **Request**: occasion *Black Tie*, season winter, time evening, location —; excluded colours ['black', 'navy', 'grey']; preferences —; notes —
* **Closet size**: 6 items
* **Live Granite look** (source `watsonx`): White Dress Shirt (White)
* **Granite summary**: Final selection: White Dress Shirt. Pieces in colours you asked to avoid were left out, so this look is incomplete.
* **Automated hard-rule failures (live)**: []
* **Deterministic look** (for contrast, not AI): White Dress Shirt (White)
* **Reviewer scores**: occasion ☐  harmony ☐  season ☐  constraints ☐  honesty ☐  arabic ☐  → verdict ☐  comment: ______________________

### Case 11 — `S11_ambiguous_item_descriptions` (EN)

* **Request**: occasion *Casual*, season spring, time afternoon, location —; excluded colours —; preferences —; notes —
* **Closet size**: 5 items
* **Live Granite look** (source `watsonx`): thing from grandma (Multi); trousers (old) (Beige); shoes 2 (White)
* **Granite summary**: A relaxed, layered look using the user's existing wardrobe, perfect for a casual afternoon in spring.
* **Automated hard-rule failures (live)**: []
* **Deterministic look** (for contrast, not AI): thing from grandma (Multi); trousers (old) (Beige); shoes 2 (White)
* **Reviewer scores**: occasion ☐  harmony ☐  season ☐  constraints ☐  honesty ☐  arabic ☐  → verdict ☐  comment: ______________________

### Case 12 — `S12_arabic_casual_weekend` (AR)

* **Request**: occasion *Casual*, season spring, time afternoon, location نزهة في الحديقة مع العائلة; excluded colours —; preferences —; notes —
* **Closet size**: 6 items
* **Live Granite look** (source `watsonx`): تيشيرت رمادي (Grey); بنطلون كاكي (Beige); حذاء رياضي أبيض (White)
* **Granite summary**: تيشيرت رمادي مع بنطلون كاكي وحذاء رياضي أبيض يخلق لباسًا مريحًا وبسيطًا مناسبًا لنزهة عائلية في الحديقة بعد ظهر يوم بهيج في الربيع.
* **Automated hard-rule failures (live)**: []
* **Deterministic look** (for contrast, not AI): تيشيرت رمادي (Grey); بنطلون كاكي (Beige); حذاء رياضي أبيض (White)
* **Reviewer scores**: occasion ☐  harmony ☐  season ☐  constraints ☐  honesty ☐  arabic ☐  → verdict ☐  comment: ______________________

### Case 13 — `S13_arabic_interview_no_black_free_text` (AR)

* **Request**: occasion *Work & Business*, season autumn, time morning, location —; excluded colours —; preferences —; notes —
* **Closet size**: 6 items
* **Live Granite look** (source `watsonx`): قميص أبيض (White); بنطلون كحلي (Navy); حذاء بني (Brown)
* **Granite summary**: قميص أبيض مع بنطلون كحلي وحذاء بني يشكلون ملابس عمل رسمية مناسبة لمقابلة عمل صباحية في الخريف، ويتجنب اللون الأسود المستبعد.
* **Automated hard-rule failures (live)**: []
* **Deterministic look** (for contrast, not AI): قميص أبيض (White); بنطلون كحلي (Navy); حذاء بني (Brown)
* **Reviewer scores**: occasion ☐  harmony ☐  season ☐  constraints ☐  honesty ☐  arabic ☐  → verdict ☐  comment: ______________________

### Case 14 — `S14_arabic_formal_evening_wedding` (AR)

* **Request**: occasion *Formal*, season winter, time evening, location حفل زفاف في قاعة; excluded colours —; preferences —; notes —
* **Closet size**: 6 items
* **Live Granite look** (source `watsonx`): فستان سهرة كحلي (Navy); حقيبة كلاتش ذهبية (Yellow); شال صوف أسود (Black); حذاء كعب فضي (Silver)
* **Granite summary**: فستان سهرة كحلي مع حقيبة كلاتش ذهبية وشال أسود يشكلون مجموعة رسمية متناسقة لحفل زفاف في قاعة مغطى بالشتاء.
* **Automated hard-rule failures (live)**: []
* **Deterministic look** (for contrast, not AI): فستان سهرة كحلي (Navy); حذاء كعب فضي (Silver); شال صوف أسود (Black)
* **Reviewer scores**: occasion ☐  harmony ☐  season ☐  constraints ☐  honesty ☐  arabic ☐  → verdict ☐  comment: ______________________

### Case 15 — `S15_pattern_heavy_wardrobe` (EN)

* **Request**: occasion *Smart Casual*, season spring, time afternoon, location brunch; excluded colours —; preferences —; notes —
* **Closet size**: 8 items
* **Live Granite look** (source `watsonx`): Navy Chinos (Navy); Plain White Shirt (White); White Sneakers (White)
* **Granite summary**: A refined yet relaxed look pairing navy chinos with a crisp white shirt and white sneakers for a smart casual brunch.
* **Automated hard-rule failures (live)**: []
* **Deterministic look** (for contrast, not AI): Plain White Shirt (White); Navy Chinos (Navy); White Sneakers (White)
* **Reviewer scores**: occasion ☐  harmony ☐  season ☐  constraints ☐  honesty ☐  arabic ☐  → verdict ☐  comment: ______________________

### Case 16 — `S16_unsatisfiable_gym_with_formal_wardrobe` (EN)

* **Request**: occasion *Active*, season summer, time evening, location —; excluded colours —; preferences —; notes —
* **Closet size**: 3 items
* **Live Granite look** (source `watsonx`): Black Suit Trousers (Black); White Dress Shirt (White); Black Oxfords (Black)
* **Granite summary**: Your wardrobe has no items suited to gym workout. The pieces below are the closest available, shown so you can see what you own — they are not a recommended outfit for this.
* **Automated hard-rule failures (live)**: ['H10_fabricated_attribute_suspected']
* **Deterministic look** (for contrast, not AI): White Dress Shirt (White); Black Suit Trousers (Black); Black Oxfords (Black)
* **Reviewer scores**: occasion ☐  harmony ☐  season ☐  constraints ☐  honesty ☐  arabic ☐  → verdict ☐  comment: ______________________

## Known caveats the reviewer should know
* The eval's H10 heuristic flagged 3 statements in the live run that were negations ("not too formal") — false positives, listed in `docs/qa/WARDROBE_STYLIST_QUALITY_REPORT.md §9`.
* Unknown colour words now normalise to `Unknown` (never Black) — fixtures predate this and use known colours only.
* Images are placeholders; judge on titles, colours, categories and the written rationale only.
