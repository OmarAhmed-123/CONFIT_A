# feat(catalog): make the brand CSV import honest, verified and production-safe

**Base:** `fix/wizard-reappearing` (not `main` — the target is 4 commits ahead)
**Branch:** `feat/catalog-csv-import-verified`

## Why

The CSV import feature already existed and was already merged. What it did not do
was tell the truth: the preview approved rows the commit refused, the template
shipped rows its own validator rejected, the error-report download was broken on
both of its code paths, and a row priced in EGP produced one price on the product
page and a different one (≈54× apart) in the cart.

This branch makes the screen and the database agree, and proves the whole path
end to end against a throwaway database and the real network.

## What changed

### Backend — `services/brand_catalog_service.py`

| Fix | Evidence it was broken |
| --- | --- |
| Validation now refuses an image source the media stage cannot materialise (`APPROVED_SOURCE_HOSTS`, reusing the media service's own allowlist) | preview returned `valid_rows_count: 28, can_import: true`, then the commit rejected every row with "no resolvable media" |
| `image_source=own` support (owner flag, default **off**) + an SSRF guard on every fetch and redirect hop | the media service could already store first-party assets (`source_type="own"`), but nothing could reach that branch, so a real boutique's own CDN was impossible to import |
| Prices must be in the price-book denomination (`PRICING_CURRENCY`) | a row entered as `1450.00 EGP` rendered `1 450 EGP` on the PDP and `78 166.03 EGP` in the cart — the same product, two prices |
| `description_ar` no longer falls back to the English copy | imported products claimed an Arabic description they did not have, and the AR page rendered English prose unmarked |
| `gender` column + synonyms + inference via `garment_gender.infer_gender` | every imported product was `unisex`; the repo's own migration 0027 backfilled every existing product with that classifier, so imports were the only rows it never reached |
| Real `warnings` (stock 0, missing Arabic, inferred gender, unknown column) instead of `[]` | `warn…_count` and the `warnings` array were declared in the API and the TS types, and always empty |
| `create`/`update` decided by the same rule the importer uses | re-uploading a file showed "create" for rows that were silently updated |
| A SKU belonging to another product is caught in validation | the preview approved it and the commit refused it |
| Re-import reuses verified media from the same source | a stock-level correction re-rendered 5 ratios × 2 formats per row and deleted the registry rows first |
| Media rejections explain the cause in actionable words | `(materialization_failed)` told the brand owner nothing about their own file |
| `generate_sample_csv` now round-trips through its own validator | two of the four template rows had `original_price == price` |
| `generate_error_report_csv` suggests real category slugs | it offered `shirts`/`trousers`/`knitwear`, none of which exist |

### Backend — `core/net_guard.py` (new)

`assert_public_http_url` / `safe_get`: scheme, port, embedded credentials, every
resolved address, and **each redirect hop re-checked before it is requested**.
Unresolvable names are refused rather than assumed safe; IPv4-mapped IPv6 is
unwrapped before classification. Wired into
`MediaMaterializationService._get_fetch`, which is the one place a string from a
spreadsheet becomes a server-side request.

### Frontend

* Notifications toggle defaults to **off**, matching the API's deliberate
  opt-in (the UI had re-opened the one-click accident the API closed).
* Warnings panel, blocker panel (`blocked_reasons`) and a disabled confirm
  button when nothing would land.
* Import summary shows media rows registered, missing Arabic titles and inferred
  genders, plus the rejected rows and a working error-report download.
* `requestBlobPost` — the error report is a POST that returns `text/csv`;
  `request()` always parsed JSON, so the download always threw, and the fallback
  opened a POST-only URL in a new tab (405). One working path now.
* Template download comes from the API, not a hardcoded string. The hardcoded
  string named the category `shirts`, which does not exist, and priced in EGP.
* The duplicate "Bulk CSV Import" entry point that POSTed straight to the commit
  endpoint — no preview, no dry run, no error report — is removed. One workflow.
* A11y: table `caption`, `scope="col"`, step label says "Importing…" during the
  commit instead of "Validate & Preview".
* EN + AR strings for every new label.

### Tooling / docs

* `scripts/tooling/validate_csv.py` validated against a **fictional** column
  schema (`name`, `subcategory`, `cost_price`, `meta_title`…) that the importer
  has never heard of. It now imports the importer's own constants and resolves
  aliases, so the tool cannot bless a file the API rejects.
* `scripts/tooling/verify_catalog_csv_import_e2e.py` — the missing proof (below).
* `docs/catalog/CATALOG_CSV_IMPORT.md`, `BRAND_OWNER_GUIDE.md` (EN/AR),
  `VALIDATION_REPORT.md`, and a ready-to-import dataset + template.

## Verification

| Check | Command | Result |
| --- | --- | --- |
| End-to-end, real network, real SQLite, real media | `python3 scripts/tooling/verify_catalog_csv_import_e2e.py --csv docs/catalog/confit_ss26_catalog.csv` | **46/46 checks passed** |
| New contract tests | `pytest backend/tests/test_catalog_csv_import_contract.py` | **35 passed** |
| Network-guard tests | `pytest backend/tests/test_net_guard.py` | **26 passed** |
| Backend suite (full) | `PYTHONPATH=. .venv/bin/python -m pytest backend/tests -q` | **4245 passed, 24 skipped, 0 failed** (840s) |
| Frontend typecheck | `npx tsc --noEmit` | clean |
| Frontend build | `npx vite build` | exit 0 |
| Frontend suite (full) | `npx vitest run` | **2108 passed, 145/145 files** (311s) |
| Standalone CSV doctor | `python3 scripts/tooling/validate_csv.py --diagnose docs/catalog/confit_ss26_catalog.csv` | 0 issues |

Two suites were genuinely red earlier in this work and were fixed rather than
reported green: `test_production_parity` flagged the SSRF blocklist for
*documenting* loopback (the file was added to the documented allowlist), and
`test_catalog_media_materialization` asserted commit-time wording for a refusal
that now happens at validation time. Both are recorded in `VALIDATION_REPORT.md`
along with the five frontend failures this change surfaced. See also
`PRIORITY_AUDIT.md` for what is **not** done: durable background execution,
gallery images beyond the first, EGP conversion, and per-brand image ownership.

The e2e run proves, against a real database and real downloads: brand identity
resolved through `POST /auth/brand/register` (no credentials in the file), dry run
writes nothing, 28 rows → 12 products / 28 SKUs / 280 image rows / 120 objects on
disk, `GET /api/v1/media/…` serves the hero bytes, the products appear in
`/catalog/products`, `/catalog/search` and the PDP, the cart accepts an imported
variant **at the same price the PDP shows**, the brand console lists them, and a
second identical upload updates in place with no new products and no
re-rendered images.

## Decisions a reviewer should confirm

1. **Currency is not converted at import.** Rows must price in `PRICING_CURRENCY`
   (USD). Converting at import would make an import succeed or fail on FX
   availability; the alternative is a follow-up.
2. **First-party images are off by default** (`CATALOG_IMPORT_ALLOW_OWN_IMAGES`).
   Enabling it lets the server fetch URLs a third party typed — an owner decision,
   now guarded by `core/net_guard.py`.
3. **Gender is inferred when the column is absent**, using the classifier that
   migration 0027 already used for every existing product. It is reported as
   `rows_gender_inferred` and never overwrites an explicit value.
4. **The duplicate bulk-upload dialog is removed**, superseded by the validating
   modal.

## Follow-ups (not in this PR)

* Run the commit path off-request (worker). At ~10 objects/row, a 1 000-row file
  with cold images can outlive a gateway timeout even though rows commit
  individually. `catalog_import_jobs` already models the state needed.
* Optional import-time FX conversion from EGP when `MARKET_FX_RATES` is set.
* Gallery: `images` accepts a list, only its first entry is materialised.
* `is_featured` / `is_active` / `size_chart_json` are not importable.
