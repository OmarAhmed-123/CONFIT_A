# B03 — Catalog & SKU Management (`/b2b/catalog`) · Teardown & Redesign

Scope row: product & SKU list, stock/price update, CSV import, import-job follow-up
with results, tagging. Backend: `/partner/catalog/*`, `/brand/products`,
`/brand/skus/{id}`, `/brand/products/{id}/auto-tag` (`brand_controller.py:253-410`).

Method: every defect measured at commit `e066d37` against
`frontend/src/views/b2b/BrandCatalogView.tsx` (384 lines).

## Defects

### D1 — i18n bypass (10 debt entries)
`frontend/i18n-baseline.json` registers 10 strings for this file (e.g. "Bulk SKU Catalog
Importer", "Recent Import Jobs", "No products yet", "Upload CSV"); everything else is
hard-coded English too. → all copy to `b2b.cat.*` EN+AR; the 10 entries deleted.

### D2 — AA contrast failures on light surfaces
- `text-slate-400` 2.56:1 — both table headers (lines 150, 232: seven+six `<th>`),
  category label (222), product id note (226), drop-zone footnote (317).
- gold `#B8935A` 2.85:1 as small TEXT — price (225, 12px bold) and the "Edit Stock"
  link (289, 12px).
- `emerald-600` 3.77:1 at 12px bold — accepted counters (168, 241): not large text.
- `amber-600` 3.19:1 at 12px — duplicate counters (169, 243).
→ headers/labels slate-600 (7.58), notes slate-500 (4.76), price+link `#7A5C28`
(5.89 on white), counters emerald-700 (5.48) / amber-700 (4.84 on amber-50 family;
plain amber-700 on white 4.84).

### D3 — `window.alert()` for wrong-type/oversize files (lines 196, 200)
Browser chrome, untranslated, disappears from the DOM (untestable, un-announceable).
→ inline validation line inside the drop-zone (`role="alert"`), i18n.

### D4 — emoji as UI (📦 line 213, 📤 line 314)
→ removed; typography + icon strokes only.

### D5 — touch targets far below the 48px floor
Save/Cancel row buttons `py-1 text-[10px]` ≈ 22px (281-288); "Edit Stock" is a bare
text link ≈16px (289); imports Retry `py-1.5` ≈28px (128); modal Cancel/Browse ≈36px;
Download template ≈24px. → every control `min-h-12` (48px) with focus-visible rings.

### D6 — full-page generic spinner (line 63)
→ geometry shimmer: header bar, jobs block, one product card per expected row.

### D7 — bare `<img>` for product thumbs (line 221)
→ `HonestProductImage` (skeleton-free but honest broken-image fallback).

### D8 — import jobs are fire-and-forget
`useBrandViewModel` exposes `getImportJobStatus` (polls
`/partner/catalog/imports/{id}`) but the view NEVER calls it: a 202 upload whose job is
still `processing` shows the stale jobs list and never follows the job to a terminal
state — the row's own requirement "follow-up of import jobs and their results" is not
met by the UI. → after upload, poll the returned job every 2.5s until terminal
(completed / partially_completed / failed) or a 90s cap, updating the result panel and
refreshing the jobs table; the poll is cancelled on unmount.

### D9 — tagging absent from the partner UI
`POST /brand/products/{id}/auto-tag` (FashionCLIP + GLiNER2, per-tag confidence,
`axes_unresolved` reported instead of guessed, append-only merge, 30/hour) exists and
is audited server-side, but `/b2b/catalog` offers nothing. → per-product Auto-tag
flow: **dry-run preview first** (quality, tags with axis/value/confidence, unresolved
axes with reasons, model list, disclaimer), then an explicit Apply; applied/skipped
reported honestly; 429 → throttled copy, never a silent catch.

### D10 — raw machine strings in user copy
Job `status` rendered verbatim (`partially_completed`), "API import" fallback,
`Errors (first 10)`. → translated status labels + human headings.

### D11 — table accessibility
`<th>` without `scope`, tables without captions; colour swatch + text ok but the stock
input relies on aria-label only (kept, it is the contract). → `scope="col"`,
sr-only captions.

### D12 — monotone surfaces / raw hex / no tokens
Same systemic finding as B01/B02: `bg-white rounded-3xl border-slate-200 shadow-sm`
×5, raw `#1B1F3B/#B8935A/#FAF9F6`. → `Surface` + `--confit-*` tokens; presentation
diversity: editorial header, jobs ledger, product dossiers (media 4:5 + SKU table),
inline tag preview panel.

## Preserved contracts (do not break)
- `BrandPortal.contract.test.tsx`: `getByText('Edit Stock')`, `getByText('Save')`,
  `getByLabelText('Stock for REAL-SKU')`, failed SKU mutation keeps controls.
- `check_brand_portal_browser.py`: button matching /Upload CSV|Bulk/, hidden
  `input[type=file]`, uploaded `E2E-COAT` row, `Save`, rendered `12 units`.
EN i18n values keep these exact strings.

## Verification plan
- `npm run verify` (baseline must shrink 37→27).
- new `BrandCatalog.test.tsx`: alert() never called (spy) with inline error instead;
  job polling reaches terminal and refreshes; auto-tag dry-run shows unresolved axes
  and Apply writes; 429 → throttled copy; skeleton role=status.
- extend goal-E2E `e2e_partner_catalog_goals.py` (loopback-only): real CSV upload →
  product row + job terminal; stock edit persists; auto-tag dry-run renders honest
  panel (local provider may be unavailable → assert the honest error path too).
- PR → CI → merge → prod bundle marker check.
