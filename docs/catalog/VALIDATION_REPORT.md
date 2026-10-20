# Validation report — catalog CSV import

Every number below was produced by running the command in this workspace, on this
worktree. Nothing is projected, estimated, or carried over from an earlier run.
Where a run was red, the failure and its fix are shown instead of a green number.

Environment: Linux sandbox, SQLite (per-test temp files), Python 3.13 (`.venv`),
Node 20 + vite 4.1.11, `frontend/node_modules` installed with `npm ci`. No
production database was contacted at any point; `DATABASE_URL` is forced to a
temporary SQLite file by the end-to-end script before FastAPI is imported.

---

## 0. Integration base — read this first

The work started on a local `fix/wizard-reappearing` at `d97f374`. The **remote**
branch had moved on:

```
git fetch origin fix/wizard-reappearing:refs/remotes/origin/fix/wizard-reappearing
git rev-list --left-right --count d97f374...origin/fix/wizard-reappearing   ->  0   5
```

Five commits the local clone did not have (`8dcafff`, `db3248a`, `d1b24c2`,
`c34eab6`, `f1e50c9`) touched files this change also touches:
`product_media_service.py`, `catalog_controller.py`, `models/index.ts`,
`i18n/en.json`, `i18n/ar.json`, `test_catalog_media_materialization.py`.

A `git ls-remote` earlier reported `f1e50c9`, but a plain `git fetch origin <branch>`
writes only `FETCH_HEAD` — the compare against the stale local ref said "0 ahead,
0 behind" and would have been wrong. It was re-fetched with an explicit refspec.

The commit was rebased onto the real tip:

```
git rebase --onto origin/fix/wizard-reappearing d97f374 feat/catalog-csv-import-verified
-> Successfully rebased and updated refs/heads/feat/catalog-csv-import-verified
```

No textual conflicts. One **behavioural** interaction did surface, and it is the
reason the rebase mattered: `f1e50c9` withholds the internal `sku_code` from the
public catalog payload, and the end-to-end script identified branch inventory by
`sku_code`. It went from `46/46` on the old base to `45/46` on the new one. The
script now matches on `sku_id` — the identifying field the endpoint still serves —
and is back to `46/46`. Nothing in the product code was changed to accommodate it.

Every result below is from the **rebased** tree, i.e. `f1e50c9` + this change.

---

## 1. Backend

### Full suite

```
PYTHONPATH=. .venv/bin/python -m pytest backend/tests -q
```

**4270 passed, 24 skipped, 238 warnings in 845.48s — exit 0.**

(Two earlier runs of the same suite in this work are recorded rather than
discarded: `2 failed, 4242 passed` on the original base, then `4245 passed` after
the fixes below but before the rebase; the extra 25 tests come from the five
upstream commits.)

| Failing test | Cause | Fix |
| --- | --- | --- |
| `test_production_parity.py::…::test_localhost_only_in_documented_places` | The guard scans `backend/app/*.py` for loopback literals. `backend/app/core/net_guard.py` is the SSRF blocklist — it *must* name `127.0.0.1`/`localhost` in order to deny them. | Added the file to `ALLOWED_LOCALHOST_FILES` with the same rationale the other blocklist entries carry. Deleting the blocklist lines to satisfy the scan would have removed the protection. |
| `test_catalog_media_materialization.py::test_import_rejects_a_row_whose_image_cannot_resolve` | Asserted the commit-time wording `"no resolvable media"`, but the refusal now happens earlier, at validation, on `thumbnail_url` — with the more precise `"This image host is not an approved stock source"`. | Relaxed to accept either wording; both prove the same property (`rejected_rows == 1`, no product row, `status == "failed"`). |

### Targeted suites

| Command | Result |
| --- | --- |
| `pytest backend/tests/test_catalog_csv_import_contract.py -q` | **35 passed** (34 before this work; one added) |
| `pytest backend/tests/test_net_guard.py -q` | **26 passed** |
| `pytest backend/tests/test_catalog_media_materialization.py -q` | **17 passed** |
| `pytest backend/tests/test_production_parity.py -q` | **38 passed** |

The added contract test is `test_imported_gender_reaches_the_stylist_filter`. It
imports one row with an explicit `gender` and one without, then asserts through
`services/styling/garment_gender.is_compatible` that a men's outfit request cannot
be composed around the imported dress. Asserting `product.gender == "womens"` alone
would not have proved the value the stylist actually filters on.

---

## 2. End-to-end proof against a real database

```
PYTHONPATH=. .venv/bin/python scripts/tooling/verify_catalog_csv_import_e2e.py \
    --csv docs/catalog/confit_ss26_catalog.csv
```

**46/46 checks passed** (rebased tree).

The script builds a real SQLite database, registers a brand through the real auth
flow, uploads the real CSV through the real FastAPI app, and inspects what landed.
No credentials appear in the CSV: the brand identity is created by
`POST /auth/brand/register` and used as a bearer token.

What it proves, in order:

1. Preview reports 28 rows, no rejects, `can_import: true`, and writes nothing.
2. A dry run leaves product/image/SKU counts unchanged (`9 -> 9`, `0 -> 0`, `21 -> 21`).
3. Commit creates 12 products, 28 SKUs, 120 media rows for a brand that had none.
4. `GET /api/v1/media/…` returns real hero bytes (not a redirect, not a 404).
5. The products appear in `/catalog/products`, in `/catalog/search`, and on the PDP,
   which lists the variants and returns prices with a currency.
6. The cart accepts an imported variant at the same unit price the PDP shows.
7. `GET /catalog/stores/{id}/inventory` exposes the branch stock the import wrote
   (`28/28` of the imported SKU ids, matched by `sku_id`).
8. The brand console lists the 12 products and the job; `GET …/imports/{id}` returns
   the stored result.
9. Re-uploading the identical file updates in place: 12 → 12 products, 28 → 28 SKUs,
   120 → 120 media objects, i.e. no duplicate rows and no re-rendered images.

---

## 3. Frontend

The full suite was **red when first run on this work: 5 failing tests in 3 files,
2073 passed**. All five were genuine defects in the new work, not stale tests. Fixes:

| Failing test | What it caught | Fix |
| --- | --- | --- |
| `translatedStringReview.test.ts` ×2 — "every key added after the audit base is in the reviewed set" | Fifteen new `b2b.cat.*` keys reached both locales without going through the string review. | Reviewed each pair (Arabic is a real translation, both locales present, no English left in `ar.json`), then registered all fifteen with the review rationale. `ar.json` was not edited to make a test pass. |
| `BrandCatalog.test.tsx` D3 — inline alert for a non-CSV file | The modal crashed on mount in the test because it calls `brandService.getStores()` and the transport mock returned a non-promise; the crash took the alert with it. | Gave the transport mock a resolved default, so an unmocked call can no longer hand a non-thenable to `.then`. |
| `BrandCatalog.test.tsx` D8 — a non-terminal job is followed to terminal, then the data refreshes | **The real bug**: `BrandCatalogView` had a `followJob` poller that nothing ever called, so a job returned as `processing` was displayed and forgotten. | Polling moved into the modal, where progress is shown: it polls `GET /partner/catalog/imports/{id}` every 2.5 s, bounded to 25 polls, renders the server's own status, and stops on any of the three terminal states. The dead poller was replaced by a ledger refetch that fires while any job in `importJobs` is non-terminal — the "come back later" case the modal cannot cover. |
| `buttonGlyph.contract.test.tsx` — "wired the verbs the brief names into real controls" | Removing the legacy bulk-upload dialog also removed the only `<UploadIcon` in `BrandCatalogView`, silently dropping the screen out of the design system's verb-glyph vocabulary. | The header import CTA now renders `UploadIcon` from `ConfitIcons`; the printed label still carries the meaning, so the glyph stays decorative. |

### Final runs

| Command | Result |
| --- | --- |
| `npx tsc --noEmit` | clean (last run after the rebase) |
| `npx vite build` | exit 0 (pre-existing >1000 kB chunk warning and an `INEFFECTIVE_DYNAMIC_IMPORT` note only) |
| `npx vitest run --maxWorkers=2` | **2133 passed, 150/150 test files, exit 0** |

**About the worker count.** `npx vitest run` at default parallelism reported
`4 failed | 2129 passed` — all four in `src/views/__tests__/homeMerchandising.test.tsx`,
a file this change does not touch, with durations of 8 s and 56 s for tests that
normally take under a second. Each of those tests passes in isolation on this tree
*and* on the base commit `f1e50c9` in a separate worktree, and the whole suite passes
at `--maxWorkers=2`. Conclusion: CPU starvation under a 150-file parallel run, not a
regression — but it is recorded here because "the suite is green" is only true at the
concurrency stated.

Behaviour added to the frontend, each covered by a test:

* One import entry point. The header CTA keeps its established B03 name ("Bulk CSV
  Import") and there is no longer a second button that POSTed straight to the commit
  endpoint, skipping preview. The spec asserts there is exactly one.
* Live job progress: the result screen shows the server's `status` and counts and
  moves to a terminal state on its own.
* `preview_records` read defensively — a preview body without it renders an empty
  table instead of white-screening the modal.
* Notifications default OFF, matching the API contract.
* Server warnings rendered verbatim; `can_import: false` shows the blockers and
  disables confirm; rejected rows download through a real `{blob, filename}` instead
  of opening a POST-only endpoint in a new tab (a guaranteed 405).

---

## 4. Static CSV validation

```
python3 scripts/tooling/validate_csv.py --diagnose docs/catalog/confit_ss26_catalog.csv
```

**0 issues.** The doctor imports the importer's own constants (`REQUIRED_FIELDS`,
`OPTIONAL_FIELDS`, `HEADER_ALIASES`, `LIMITS`) instead of restating the schema, so it
cannot drift. An earlier version *did* restate it and reported a false clean bill of
health; that is why it is imported rather than copied.

---

## 5. What is still unverified

Not failures — work not attempted. None of it may be read as passing:

* **Durable background execution.** `POST /partner/catalog/confirm-import` declares
  `202 Accepted` and then performs the entire import inside the request. The
  `catalog_ingest` Celery route points at `bulk_catalog_import_task`, which is not
  defined. See `PRIORITY_AUDIT.md`.
* **Gallery images beyond the first.** The `images` JSON column is parsed but only
  `parsed[0]` is used; the rest are discarded without a warning.
* **EGP conversion.** Refused at validation by design. No FX source, table, or
  freshness policy exists in the repository.
* **Per-brand image ownership.** The network guard proves a URL is safe to fetch; it
  does not prove the brand owns it.
* **PostgreSQL.** Everything above ran against SQLite; no instance was available, so
  parity is argued from SQLAlchemy/Alembic compatibility, not measured.
* **Browser E2E.** The end-to-end proof drives the real FastAPI app and database via
  `TestClient`. No Playwright/Chromium journey ran, so nothing here is a visual or
  cross-browser verification.
* **CI.** No CI run was observed; nothing has been pushed.
