# Catalog CSV import — contract and operations

Status: **implemented and verified** on branch `fix/wizard-reappearing`. Every
rule below is enforced by `backend/app/services/brand_catalog_service.py` and
pinned by `backend/tests/test_catalog_csv_import_contract.py`; the job lifecycle
(§2a) is pinned by `backend/tests/test_catalog_import_background_job.py` and
`backend/tests/test_catalog_import_api_async.py`, and the UI half by
`frontend/src/views/b2b/__tests__/csvImportJobLifecycle.test.tsx`. The
end-to-end path is proven by `scripts/tooling/verify_catalog_csv_import_e2e.py`.

---

## 1. What the feature is

A brand owner uploads one UTF-8 CSV of their clothing catalogue. Each row is one
**variant** (product × size × colour). The importer validates the file, shows a
preview with a per-row create/update verdict, and on confirmation writes
products, SKUs, media and branch inventory into the real database, after which
the items appear in the storefront catalogue, search, product pages and cart.

Identity rules (unchanged from the original design, now documented):

| Entity | Identity |
| --- | --- |
| Product | `(brand_id, title)` — the same title in two rows is one product with two variants |
| Variant (SKU) | `sku_code`, globally unique; generated deterministically from `(brand slug, title, size, colour)` when absent |
| Brand ownership | resolved from the authenticated session. **There is no brand/owner column, and no credential may appear in the file.** |

---

## 2. HTTP surface

All routes are mounted twice for historical reasons (`/partner/…` and `/brand/…`);
they are the same handlers.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/partner/catalog/preview-csv` | **dry run** — parse, validate, resolve categories/stores/skus, write nothing |
| `POST` | `/api/v1/partner/catalog/confirm-import` | **accept** the import: persists the job and dispatches it (§2a). `202` + job id, or `503` if the queue is down |
| `GET` | `/api/v1/partner/catalog/template.csv` | the authoritative template (public; contains no data) |
| `POST` | `/api/v1/partner/catalog/export-errors` | CSV error report, formula-injection escaped server-side |
| `GET` | `/api/v1/partner/catalog/imports` | import history |
| `GET` | `/api/v1/brand/catalog/jobs/{job_id}` | one job, with its stored row errors, live `processed_rows`, `attempts` and `last_error` |
| `POST` | `/api/v1/partner/catalog/imports/{job_id}/retry` | re-dispatch a `failed` job whose file is still stored (`409` for a finished job — retrying it would import twice) |

### 2a. The import is a background job, not a slow request

`confirm-import` used to answer `202 Accepted` and then run the entire import
inside the request. The status was false: nothing had been accepted *for later*,
the work was happening right there, and it died with the connection. The route
order is now:

1. **persist** the job row, with the CSV itself (`payload_text`,
   `payload_sha256`, `target_store_id`, `send_notifications`, `actor_id`) —
   migration `0043_import_job_payload`;
2. **dispatch** `backend.app.workers.tasks.bulk_catalog_import_task` to the
   `catalog_ingest` queue;
3. answer **202** with `job_id`, the current status and `status_url`.

The task that `task_routes` and `docker-compose.yml` had been naming since the
worker was introduced **did not exist**. It does now, so the queue is no longer
decorative.

Failure directions, both tested:

| Situation | What the client gets | What the database says |
| --- | --- | --- |
| queue/broker down at dispatch | `503`, "nothing was imported" | job `failed`, `last_error = dispatch_failed: …`, payload **kept** |
| worker starts, gets killed | nothing (client polls) | job stuck in `processing` until the lease expires, then recovered |
| rows rejected by validation | `202` (the file is valid as a file) | `partially_completed` with per-row errors |
| corrupt/missing payload | — | `failed`, `payload_missing` |

**Lease and recovery.** A claim is an atomic conditional `UPDATE`
(`BrandCatalogService.claim_job`): it only succeeds from `queued`/`failed`, only
while `attempts < 3`, and only when any previous `heartbeat_at` is older than
`JOB_LEASE_SECONDS = 900`. The worker refreshes `heartbeat_at` every
`_PROGRESS_EVERY = 10` rows. `recover_stalled_catalog_imports_task` runs every
**300 s** on the `maintenance` queue and re-dispatches jobs that are `queued`
past their grace period or `processing` with an expired lease. Re-dispatch is
safe because a terminal job cannot be claimed again: a broker redelivery or a
double click imports nothing twice.

**Progress is read from the row, never estimated.** `processed_rows` is written
as the worker goes; the UI shows `processed / total` and only renders a
percentage when the server knows the total. The modal polls at 2 s for the first
10 polls, then 6 s, for a ~7 minute budget; when the budget ends it says it
stopped watching rather than freezing on a stale "processing" — the job is still
running server-side, and the panel says so.

Authorisation: `require_brand_access("catalog:write")` for preview/import;
`brand_auth` for reads. Tenant isolation is enforced on stores
(`StoreLocation.brand_id`) and on SKUs (a SKU cannot be moved between products).

---

## 3. Column contract

Header names are matched case-insensitively after alias resolution. Unknown
columns are **warned about, not fatal** — but they are ignored, so the warning is
the only signal that a value was dropped.

### Required

| Column | Aliases | Target | Rule |
| --- | --- | --- | --- |
| `title` | `product_name`, `product_title`, `name` | `products.title` | ≤ 255 chars |
| `category_slug` | `category` | `products.category_id` | must exist; resolved by slug, English name or Arabic name |
| `base_price` | `price`, `selling_price` | `products.base_price` | > 0, ≤ 2 decimals, finite, ≤ `BrandRepository.MAX_SKU_PRICE` |
| `color_family` | — | `products.color_family` | ≤ 50 chars; derived from `color` when absent |
| `thumbnail_url` | `image_url`, `image` | `products.thumbnail_url` + `product_images` | see §5 |

Valid `category_slug` values are exactly the slugs the seeded catalogue creates
(`BrandCatalogService.SEEDED_CATEGORY_SLUGS`):
`outerwear, tops, bottoms, dresses, footwear, accessories`.

### Optional

| Column | Aliases | Target | Rule |
| --- | --- | --- | --- |
| `sku_code` | `sku` | `product_skus.sku_code` | `[A-Za-z0-9_-]{3,100}`; unique in file and, if it already exists, must belong to this product |
| `size` | — | `product_skus.size` | ≤ 20 chars; default `M` |
| `color` | — | `product_skus.color` | ≤ 50 chars; defaults to `color_family` |
| `color_hex` | — | `product_skus.color_hex` | `#RRGGBB` |
| `stock_level` | `stock_quantity`, `stock`, `quantity` | `product_skus.stock_level` | integer 0–100000; default 0 |
| `price_override` | — | `product_skus.price_override` | same money rules as `base_price` |
| `compare_at_price` | `original_price` | `products.compare_at_price` | **must be strictly greater than `base_price`**; empty clears it |
| `currency` | — | `products.currency` | **must equal `PRICING_CURRENCY`** (see §6) |
| `title_ar` | — | `products.title_ar` | Arabic; empty is honest ("no translation"), never filled with English |
| `description_ar` | — | `products.description_ar` | idem |
| `description` | — | `products.description` | ≤ 2000 chars |
| `material` | — | `products.material` | ≤ 255 chars |
| `care_instructions` | `care`, `wash_care` | `products.care_instructions` | ≤ 500 chars |
| `gender` | `sex`, `audience`, `target_gender` | `products.gender` | `mens` \| `womens` \| `unisex`; synonyms (`men`, `women`, `ladies`, `رجالي`, `نسائي`, `للجنسين`, …) are folded; **inferred from the title when absent** (§7) |
| `style_tags` | — | `products.style_tags` | JSON array or comma-separated; ≤ 100 items |
| `occasion_tags` | — | `products.occasion_tags` | idem |
| `images` | — | `products.images` + `product_images` (photographs 1..n) | JSON array or comma-separated list of **additional photographs**; see §5a |
| `dominant_hex` | — | `products.dominant_hex` | `#RRGGBB` |
| `image_source` | `img_source`, `image_source_type` | provenance | `stock` (default) or `own` (§5) |
| `store_id` / `branch_id` | `branch_id` | store inventory target | must belong to **your** brand |
| `store_name` / `branch_name` | — | store inventory target | matched by name inside your brand |

Not importable today: `is_featured`, `is_active`, `size_chart_json`,
`style_embedding`, `rating`, `review_count`. These are curated elsewhere; the CSV
is a product-data channel, not a merchandising console.

---

## 4. Validation, warnings, blockers

Three separate channels, deliberately distinct:

* **errors** — the row will not import. Reported per row and field with a
  `suggestion` that names an actionable fix. One bad row never aborts the file:
  every accepted row commits independently (partial success is the documented
  contract).
* **warnings** — the row *will* import, and the shopper will notice something:
  stock 0 (the storefront hides unpurchasable products), no `title_ar`, no
  `description_ar`, gender inferred, or a column that is not part of the
  contract and is therefore ignored.
* **blockers** — nothing at all would land (e.g. no object storage configured,
  first-party images disabled). `can_import` is `false` and `blocked_reasons`
  says why before the brand owner can confirm.

The preview **is** the dry run: the same code path validates and resolves, and it
writes nothing (`test_preview_writes_nothing`).

Limits: 10 MB, 1 000 rows, one file per import, UTF-8 (a UTF-8 BOM is tolerated
and is what Excel writes).

---

## 5. Images

Media is not optional. A row whose picture cannot be *materialised and verified*
is refused, because a product whose hero 404s is the defect the media pass exists
to remove. `_materialize_media` therefore:

1. classifies the source: an approved stock host (`images.pexels.com`,
   `images.unsplash.com`) or `image_source=own`;
2. applies the network guard (`backend/app/core/net_guard.py`): scheme, port,
   embedded credentials, and every resolved address are checked, and **each
   redirect hop is re-checked** before it is requested — a public host cannot
   bounce the request into `169.254.169.254` or a private range;
3. downloads, centre-crops and encodes **five ratios × two formats**, uploads all
   ten objects, then verifies bytes-back (a registry row alone is not evidence);
4. only then registers `product_images` and points `products.thumbnail_url` at
   `/api/v1/media/products/{id}/{id}-{ratio}.{ext}`, which is the only key shape
   the media route serves.

Re-importing a row whose product already holds verified media **from the same
source URL** re-uses it: no re-download, no re-render, no delete-then-write. A
stock-level correction is therefore cheap and cannot take a live product's
imagery down.

### 5a. Multiple photographs (gallery)

`image_url` is the **hero** and is always gallery position 0 — it is the picture
product cards render, so it cannot be displaced by a gallery entry. The `images`
column adds the **rest** of the gallery:

```csv
image_url,images
https://images.pexels.com/photos/front.jpeg,"[""https://images.pexels.com/photos/back.jpeg"",""https://images.pexels.com/photos/detail.jpeg""]"
```

Comma-separated works too: `back.jpeg,detail.jpeg`. Rules, all enforced server-side:

* **Order is preserved.** The order in the cell is the order on the page.
* **The hero is never duplicated.** Repeating `image_url` inside `images` collapses.
* **Every entry passes the same host rules as the hero** (§5). An entry from an
  unapproved host is dropped, the rest of the gallery still imports, and the
  brand gets one warning per dropped image. It does **not** reject the row — one
  bad cell must not cost the brand the whole product.
* **Each photograph gets its own storage keys and its own ratio ladder**:
  photograph 0 is `products/{id}/{id}-{ratio}.{ext}` (unchanged since the media
  pass), photograph *n* is `products/{id}/{id}-p{n}-{ratio}.{ext}`. That is what
  stops a second photo overwriting the hero's bytes.
* **Exactly one hero.** Only photograph 0's 4:5 JPEG sets `products.thumbnail_url`.
* **Partial failures are reported, never silent.** `process_csv_import` returns
  `photos_not_imported` (count) and `media_warnings` (one actionable message per
  dropped image) alongside the row counters.
* **Re-import is idempotent across the whole gallery**: if the product already
  holds exactly these photographs, nothing is re-fetched or re-rendered.

**API contract.** `GET /catalog/products/{slug}` gains `photos[]`, one entry per
photograph: `position`, `is_primary`, `url`, `images` (that photograph's own
ratio→URL map), `source_ref`, `source_type`, `provider`, `attribution`, `frames`.
`images` and `media` keep their existing meaning — the **hero's** rendition
ladder, one frame per ratio, which
`backend/tests/test_product_gallery_uniqueness.py` pins. The PDP renders the rail
from `photos[]` and falls back to `images` when the payload has none.

**Owner decision — first-party photography.** `CATALOG_IMPORT_ALLOW_OWN_IMAGES`
defaults to `false`. With it off, a row declaring `image_source=own` is refused
with a message telling the brand owner to upload through the dashboard instead.
Turning it on lets the server fetch arbitrary public hosts, which is why the
network guard above exists and why the decision belongs to the operator.

---

## 6. Prices and currency

`products.base_price` is denominated in exactly one currency,
`settings.PRICING_CURRENCY` (today `USD`). The storefront converts for display
(EGP by default). A row that declares any other currency is **refused**.

This was measured, not assumed: with a row priced `1450.00 EGP`, the product page
rendered `1 450 EGP` (the payload declared EGP, so the presentation layer
correctly declined to convert) while the cart converted the same number from the
USD price book and rendered `78 166.03 EGP`. One product, two prices, a factor of
~54 apart — shown to the shopper at one price and charged at the other.

The alternative — converting at import time from the row's currency — was
rejected for now because conversion depends on a live FX table; making an import
succeed or fail on network availability is a worse failure mode than asking for
the price-book currency. Recorded as a follow-up in the PR.

---

## 7. Gender

`products.gender` (`mens | womens | unisex`) was added in migration `0027`, which
backfilled **every existing product** with `services/styling/garment_gender.infer_gender`
from the garment name. CSV imports did not set it at all, so every imported
product was `unisex` — the one class of product the stylist's gender filter could
not reason about, on the path that produces most new products.

The importer now (a) accepts an explicit `gender` column with synonyms, and
(b) when the column is absent, uses the same classifier the migration used. The
inferred value is written **only on create**, reported as `rows_gender_inferred`,
and warned about per row, so a merchandiser's later correction is never
overwritten by the next stock upload.

---

## 8. Notifications

`send_notifications` defaults to **false**. A bulk catalogue load must not email
the customer base; the API made that change deliberately and the modal now
matches it (it previously defaulted to `true` and re-opened the accident).

---

## 9. Known limitations (honest list)

1. ~~One photo per product.~~ **Fixed:** `images` is now a real gallery (§5a), up
   to 100 references per row. Photographs are imported, ordered, attributed and
   served through `photos[]`.
2. **Currency must be the price-book currency** (§6). Import-time conversion from
   EGP is not implemented.
3. **First-party image ingestion is off by default** (§5).
4. **`is_featured` / `is_active` / `size_chart_json` are not importable.**
5. **1000 rows per file.** ~~The import runs synchronously inside the
   request.~~ **Fixed:** the import is a durable background job (§2a) — the
   request only persists and dispatches it, so a slow image fetch can no longer
   outlive a gateway timeout, and a closed tab no longer cancels the work.
6. **`/partner/catalog/template.csv` is unauthenticated.** It is static and holds
   no tenant data; it is left open so a prospective brand can look at the format.
