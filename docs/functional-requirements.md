# Functional requirements — FR-01 … FR-14 mapped to tests

The authoritative, longer requirement register (FR-01…FR-26, with evidence per
session) is `IBM_WATSONX_STYLIST_ACCEPTANCE.md`. This file is the short, test-mapped
view requested for release review; numbering **matches** the acceptance register so
the two never disagree. Status as of 2026-10-29 on the current checkout.

| FR | Requirement (short) | Automated tests (file :: test) | Other evidence | Status |
|---|---|---|---|---|
| FR-01 | Upload wardrobe photos (JPEG/PNG/WebP ≤15 MB, server decode, MIME check, sha256 dedupe) | `test_wardrobe*.py` (48); `test_watsonx_stylist.py::test_prepare_image_downscales_and_rejects_garbage` | live E2E 2026-10-26 | VERIFIED |
| FR-02 | Vision analysis with structured output via watsonx.ai | `test_watsonx_stylist.py::test_parse_vision_json_tolerates_fences_and_prose`, `::test_parse_vision_json_rejects_non_objects` | live rows (`analysis_source=meta-llama/…`) | VERIFIED (non-Granite model, labelled — see `vision-integration-decision.md`) |
| FR-03 | Persist analysis provenance (`analysis_source`, `analysis_description`) | migration tests; `docs/qa/MIGRATION_0047_0048_CHECKLIST.md`; clean PG17 up/down 2026-10-29 | — | VERIFIED |
| FR-04 | Unknown category → `null`, never guessed | `test_watsonx_stylist.py` (unknown-category case) | smoke 2026-10-26 | VERIFIED |
| FR-05 | User correction wins; provenance becomes `manual (was …)` | `test_watsonx_stylist.py::test_manual_correction_changes_provenance`, `::test_recommendation_scenario_h_edited_category_drives_selection` | — | VERIFIED |
| FR-06 | Context inputs: occasion, time of day, season, location, preferences, exclusions | `test_watsonx_stylist.py::test_request_schema_bounds`, `::test_recommendation_respects_exclusions_and_previous` | API probe 2026-10-29: bad season → 422, short occasion → 422 | VERIFIED |
| FR-07 | Granite reasoning via watsonx.ai with versioned system prompt (`wx-stylist-1.1`) | `test_watsonx_stylist.py::test_recommendation_scenario_a_valid_model_output` | live eval 22 calls 2026-10-28 | VERIFIED (live) |
| FR-08 | Structured recommendation contract incl. provenance, `fit_status`, `is_complete`, `selected_by` | schema tests; `test_stylist_explanation_consistency.py` (18) | browser E2E 2026-10-29 | VERIFIED |
| FR-09 | Item references validated by **id** against the caller's wardrobe | `test_watsonx_stylist.py::test_recommendation_scenario_g_rejects_invalid_reference`, `::test_cross_user_items_are_not_styled` | eval: invented ids 0/16 | VERIFIED |
| FR-10 | Role derived from stored category, not model claim | `test_recommendation_scenario_h_edited_category_drives_selection`; `test_d12_role_collision_is_explained` | live log `role_corrected` | VERIFIED |
| FR-11 | Missing categories reported, never fabricated; core positions rule-completed **with disclosure** | `test_recommendation_scenario_d_missing_shoes_is_reported_not_invented`; `test_d12_*` (5) | live: 3 rule-completed, all disclosed | VERIFIED |
| FR-12 | Malformed model output handled honestly (502 strict / labelled fallback auto) | `test_recommendation_scenario_c_malformed_json_falls_back_labelled` | — | VERIFIED (mocked) |
| FR-13 | Timeout/429/5xx/404 `model_not_supported`/IAM → distinct codes, retry/backoff | `test_recommendation_scenario_f_timeout_strict_mode_is_502`; client tests | live 404 probe (granite-vision) | VERIFIED |
| FR-14 | No credentials → `501 FEATURE_NOT_CONFIGURED` (strict) or **labelled** deterministic fallback (auto); never a silent provider swap; fallback items never attributed to a model | `test_recommendation_scenario_e_unconfigured_strict_is_501_with_hint`, `test_recommendation_unconfigured_auto_uses_labelled_fallback`, `test_d11_deterministic_fallback_marks_unsuitable_too`, **`test_d13_deterministic_fallback_never_attributes_items_to_the_model`** (new) | browser E2E 2026-10-29 badge "Rule-based match — not AI" EN/AR | VERIFIED |

Counts on current checkout (2026-10-29): stylist suites **76 passed** (SQLite),
**49 passed** on PostgreSQL (`scripts/dev/test_backend_pg.sh`); wardrobe/colour
sweep **231 passed** (incl. new `test_d14_common_colours_do_not_collapse_to_black` ×6).

Beyond FR-14, the acceptance register also tracks FR-15…FR-26 (config-only model
ids, rate limiting, secret hygiene, UI/i18n/a11y, docs, saved looks, D10/D11/D12
consistency rules, colour exclusions); all are VERIFIED there except the human
reviews, which are PENDING.
