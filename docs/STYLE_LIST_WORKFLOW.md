# Style List — end-to-end workflow (P1)

## What "Style List" means in this repository

Two things carry the name; both were traced in code, not assumed:

| Surface | Where | What it is |
|---|---|---|
| **StyleList AI / "AI Stylist Director"** (spec 009) | `VirtualStylistDrawer`, `POST /stylist/recommend`, `backend/app/services/stylist_service.py` | Conversational, catalog-first stylist. `include_wardrobe_items=true` grounds answers in the signed-in shopper's wardrobe (STY-03) and the reply states whether the wardrobe was actually consulted (`intent.wardrobe.used/reason`). |
| **Wardrobe stylist** (this feature; FR-01..FR-20) | Wardrobe → *AI Stylist* tab, `WardrobeStylistPanel`, `POST /wardrobe/outfit-recommendation` | Outfit assembled **only** from the user's own garments for an occasion/time/season/location with preferences, with per-item reasons, model provenance and now **persistence** (`/wardrobe/outfits`). |

The "Style List" journey in the master prompt (upload → analyse → set context →
generate from real wardrobe → refine → save/revisit) maps to the second surface;
the first is verified to still work (existing tests `test_stylist_wardrobe_influence.py`,
`test_stylist_eval_harness.py`, `test_stylist_repeated_answers.py`).

## Journey, step by step (what is enforced, and where)

| Step | Endpoint / component | Integrity rule | Evidence |
|---|---|---|---|
| 1. Upload / select garments | `POST /wardrobe/upload`, `/upload/bulk`, `/items` | Safety checks run before storage; each item gets a stable integer `wardrobe_items.id` | `test_wardrobe_upload_safety_order.py` (5) |
| 2. Vision metadata | `POST /wardrobe/items/{id}/analyze`, auto-tag | Served model id stored in `analysis_source` (0047); manual edits → `manual`; failures never fabricate tags | `test_watsonx_stylist.py` Scenario A–D |
| 3. Category correctness | `wardrobe_taxonomy.normalize_category` | Category is user-correctable and is the **only** source of outfit role | role-correction test + `test_wardrobe_saved_outfits.py::test_role_comes_from_stored_category…` |
| 4. Context | `OutfitRecommendationRequest` | occasion, time_of_day, season, location, activity, dress code, style/colour prefs, **`excluded_colors` (new 2026-10-27)**, comfort, exclusions, language. Unknown fields (e.g. `count`) → 422, never silently dropped | panel test "sends the user's context…"; `test_stylist_colour_constraints_eval.py` |
| 5. Generate from real wardrobe | `POST /wardrobe/outfit-recommendation` | Closet sent to the model contains only the caller's ready, un-binned items; model may only reference `wardrobe_item_id`s from that list | Scenario E/H; `test_cross_user_items_are_not_styled` |
| 6. Correct photos | service resolves `image_url` from the DB row per id — never from model text | Scenario H |
| 7. Refine / exclude / regenerate | `excluded_item_ids`, `previous_item_ids`, "Swap out", "Another outfit" | exclusions honoured server-side; excluded ids returned by the model are rejected and listed in `limitations` | Scenario I; panel tests "Another outfit"/"Swap out" |
| 7b. Colour constraints (new 2026-10-27) | `color_preferences`, `excluded_colors`, negated colour words in `exclusions` ("no black", "بدون أسود") | Preferred colours go to the prompt + fallback scorer. **Excluded colours are enforced on the way back**: any item whose stored `color_name` normalises (EN or AR alias) to a banned family is dropped from the model's answer and from the fallback candidates, and a limitation names the colour and the count. Unrecognised entries are reported, never guessed (the taxonomy's "Black" default is not applied to ban lists). | `test_stylist_colour_constraints_eval.py` (23) |
| 7c. Outfit quantity | — | **NOT SUPPORTED as a parameter.** The endpoint returns exactly one outfit per call; "three distinct outfits" is achieved by the client calling again with `previous_item_ids` (the UI's "Another outfit"). A `count` field is rejected with 422 so the gap is visible, not silent. Multi-outfit generation would need a prompt/schema/UI change and multiplies model latency per request — product decision, not a bug fix. | `test_unknown_fields_such_as_count_are_rejected_not_ignored` |
| 8. Honest failures | error codes `FEATURE_NOT_CONFIGURED`, `PROVIDER_ERROR`, 422, 429 | fallback labelled `source=deterministic_fallback, ai_generated=false`; UI never shows "Styled by <model>" for it | Scenario F/G/J; panel test (fallback badge) |
| 9. **Save / revisit (new)** | `POST/GET/DELETE /wardrobe/outfits`, "Save this look", *Looks* tab → "Saved wardrobe looks" | see below | `test_wardrobe_saved_outfits.py` (7), `wardrobeStylistPanel.test.tsx` (+4), `savedWardrobeLooks.test.tsx` (5) |

## Persistence design (migration 0048)

* `wardrobe_outfits` (user_id, title, occasion, summary, notes/limitations/
  missing JSON, context JSON, is_complete, **source, ai_generated, model_id,
  prompt_version**, created_at) and `wardrobe_outfit_items` (outfit_id,
  wardrobe_item_id FK → `wardrobe_items` **ON DELETE CASCADE**, role, reason,
  sort_order). Grants to `confit_app_rw` are in the migration (same pattern as 0046).
* Catalog `outfits`/`outfit_items` are **untouched** (they require `product_id`
  and drive price/cart/share).
* Save-time rules: ids must be the caller's, `ready`, not binned → otherwise
  rejected and returned in `rejected_references`; a look with **zero** valid
  ids is refused (422), never saved empty; role derived from stored category;
  `ai_generated/model_id` forced false/null when `source != watsonx`;
  **when `source == watsonx`, `model_id` must be the configured reasoning model
  (or reasoning deployment) id — any other value is refused (422), so a
  client cannot label a look as a Granite answer from a model this deployment
  never called** (added 2026-10-26 after the PostgreSQL negative-test run
  persisted `gpt-4o`); 201 only after commit.
* Read-time rules: binned garments are omitted and counted in
  `dropped_item_count`; `is_complete` turns false when something was dropped;
  cross-user GET/DELETE → 404 (no existence oracle).
* UI: "Save this look" has four states (idle/saving/saved/error) — a success is
  only shown after a 201 with an id; the *Looks* tab lists saved wardrobe looks
  with stored photos, per-look provenance badge ("Made by ibm/…" vs
  "Rule-based (no AI)"), dropped-item caveat, delete.

## Acceptance tests mapped to the master prompt

| Requirement | Test | Status |
|---|---|---|
| Cross-user item ids rejected | `test_foreign_and_unknown_ids_are_rejected_not_stored`, `test_look_made_only_of_foreign_ids_is_refused`, `test_cross_user_items_are_not_styled` | VERIFIED (unit, sqlite) |
| Exclusions honoured | `test_watsonx_stylist.py` Scenario I | VERIFIED (unit) |
| Excluded colours enforced (model path + fallback, EN + AR), preferred colours in prompt, unknown words never ban "Black", `count` → 422 | `test_stylist_colour_constraints_eval.py` | VERIFIED (unit, mocked model; 2026-10-27) |
| Requested outfit count honoured | — | **FAIL / NOT IMPLEMENTED** — one outfit per call by design; see row 7c |
| Incomplete wardrobes | `missing_categories` scenarios; `test_binned_item_is_rejected_at_save_and_hidden_afterwards` | VERIFIED (unit) |
| Save → retrieve | `test_save_then_list_and_get_round_trip`, `test_other_user_cannot_read_or_delete_a_saved_look` | VERIFIED (unit) |
| AI vs fallback labelling | `test_role_comes_from_stored_category_and_fallback_is_never_ai`; panel + saved-looks provenance tests | VERIFIED (unit) |
| Live Granite recommendation | `scripts/watsonx_smoke.py` | VERIFIED LIVE (session 1, granite-4-h-small); re-run in P5 live probe |
| Provenance cannot be forged at save time | `test_watsonx_look_cannot_claim_a_foreign_model_id` | PASS — VERIFIED (unit) |
| Negative battery over HTTP on **PostgreSQL** (2 workers): unauthenticated 401 ×4, cross-tenant read/delete 404, tenant list isolation, foreign/unknown ids 422, empty items 422, oversized title 422, foreign `source` 422, non-integer id 422, unsupported language 422, empty wardrobe → 422 not 5xx, garment delete → look still readable (`items=[]`) | `docs/qa/load/style_list_negative_tests_postgres.json` (21 checks) | 20 PASS; the single FAIL (`model_id=gpt-4o` accepted) is the defect fixed above — re-run after the fix is recorded in the same file |
| Existing conversational StyleList (chat) regression | `test_stylist_wardrobe_influence.py`, `test_stylist_*` in the full backend run | PASS — AUTOMATED (full suite, this pass) |
