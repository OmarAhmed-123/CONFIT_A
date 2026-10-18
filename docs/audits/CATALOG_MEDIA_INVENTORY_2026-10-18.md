# Catalog media: API & data-source inventory, pre-launch

Date: 2026-10-18. Every "measured" cell below was read this session with a
command (curl against production, read-only SQL against the production Neon DB,
or a file read of this repo). Probes were bounded: HEAD/ranged GET, 20–30 s
timeouts, ≤10 URLs touched. No production rows were written.

## 1. The defect this inventory closes (home "New in" + try-on builder grids)

Both screenshots showed the HonestProductImage "Image unavailable" state on
cards that had prices and colours. Chain, each link measured:

| # | Link | Evidence |
|---|------|----------|
| 1 | `products.thumbnail_url` / `products.images` in prod are clean live CDN URLs | SQL: 12 products, 0 media-route-shaped thumbnails; sampled URLs return HTTP 200 `image/jpeg` (ranged GET 206) |
| 2 | `product_images` (the "media pass" registry, migration 0035) has 54 rows, **all** keyed `provider:photo_id:ratio:role` (e.g. `pexels:450212:4x5:hero`), **0** in the `products/<id>/<file>` ingest shape | SQL counts this session |
| 3 | The registry rows' `public_url` holds the real, verified upstream URL (Pexels/Unsplash CDN or same-origin `/product-media/...` for the 4 generated-illustration rows) | SQL dump of rows 223–227 + generated rows; live probe of a sample: all 200/206 image/jpeg |
| 4 | `product_media_service` derived `/api/v1/media/<storage_key>` for **every** row regardless of whether bytes were ever ingested | code read |
| 5 | `media_controller` whitelists only `^products/\d+/file` keys and re-checks the DB — every derived URL answered 404 `RESOURCE_NOT_FOUND` | live curl on prod: all three provider shapes 404, JSON error envelope |
| 6 | `HonestProductImage` onError → localized "Image unavailable" | frontend component read; matches both screenshots pixel-for-pixel |

Root cause class: **canonical-data/contract drift** — a registry pass wrote
rows in a *planning* key shape and a display rewrite then treated "registered"
as "serveable". Neither table, nor the bucket, nor the CDN was the problem;
the single conversion point invented URLs the server could not honour. Local
dev never reproduced it because the local `product_images` table is EMPTY
(measured: 0 rows) — the derivation only breaks where registry rows exist
without bucket ingestion.

CSP was explicitly ruled out as cause: `vercel.json` `img-src` already
allowlists `'self' data: blob: images.unsplash.com images.pexels.com
placehold.co` and the Neon-S3 storage host.

## 2. Fix (commit `1ff5209`, contract tests `118191f`/`6709323`)

One rule in one place (`product_media_service.display_url_for_row`): a client
gets a URL only for a source the server can actually deliver —

1. ingest-shaped registered key → immutable same-origin media route;
2. else the row's verified `public_url` when `https://` or a same-origin
   absolute path (http, protocol-relative, empty → rejected);
3. else **no URL at all** → serializer falls back to the legacy columns;
   `HonestProductImage` keeps its honest unavailable state for genuinely
   missing assets, and never gets fed a dead route.

The serveable-key regex now lives in the service and is imported by the
controller: client-facing URLs and accepted keys cannot drift apart again.
Validated against **all 54 production rows read-only**: 50 resolve to live
CDN https URLs, 4 to same-origin `/product-media/` files (one fetched: 200),
0 unresolvable, 0 dead media-route URLs.

## 3. Endpoint / data-source inventory

| Surface (UI) | Endpoint | Image field origin | Pre-fix prod state | Post-fix state |
|---|---|---|---|---|
| Home "New in" row | `GET /api/v1/catalog/products?sort_by=newest&limit=8` | registry → `thumbnail_url` via `primary_url()` | media-route URL → 404 → placeholder | live CDN URL (measured all resolvable) |
| Home featured / grid | `GET /api/v1/catalog/products` (filters) | same | same | same fix |
| PDP gallery + swatches | `GET /api/v1/catalog/products/{slug}` | `images` via `gallery_images()`, `media[]` via `media_payload()` | 4 dead media-route URLs | live `public_url`s, master/undeliverable rows skipped, attribution travels |
| Try-on outfit builder grid | catalog list via `ProductCard` (`thumbnail_url`) + `image_url` on outfit items (`outfit_controller`, legacy column — was already clean) | mixed | cards 404'd via registry; outfit-item path was unaffected | deliverable URLs everywhere |
| Media route | `GET /api/v1/media/{key}` | `product_images` row (ACL) + Neon-S3 object (`read_media_object`) | 0 registered ingest keys → everything 404 | unchanged by design; becomes primary path only after bucket ingestion (see §5) |
| VTON garment fetch (try-on) | controller fetches the garment URL the catalog hands it | registry-derived URL | server-side fetch of a 404 → `asset_gate` blocked (`garment_fetch_failed`) | fetches live CDN URL (200 verified from this network); asset-gate pressure on catalog data drops |
| Generated-illustration rows | `/product-media/<slug>/*.{jpg}` static files in the Vercel deployment | `public_url` absolute same-origin | registered but unreachable via media route | served via same-origin static (200 measured); **still classified AI illustration, never product photography** (plan rule) |
| Search / discovery | same list endpoint + q filters | same as list | same | same fix |
| Stylist suggestions | `/api/v1/outfits/fill-in-the-blank` (auth) | outfit-item `image_url` = `products.thumbnail_url` (clean column) | OK | OK (untouched) |
| Cart/checkout item rows | commerce endpoints, snapshot of catalog fields | product row columns | clean | clean |

## 4. Versioned pre-launch test dataset (deliverable F)

`backend/tests/data/prelaunch_media_dataset_v1.json` — 15 stable-ID cases
(`plm-001…015`) covering: ingest key registered; prod-exact colon rows for
pexels/unsplash/generated (live at audit time); registered-but-undeliverable
(empty `public_url`); insecure http; protocol-relative; traversal key;
unregistered key; registered-but-object-missing; upstream 404/403/429;
200-but-not-a-decodable-image; no image at all. Each case records the measured
evidence and the expected contract outcome; labels mark URL values as fixture
material, not current third-party inventory claims.

Driven by `backend/tests/test_prelaunch_media_dataset.py` (18 tests) and
`backend/tests/test_prelaunch_journeys.py` (7 API-level journey replays of the
broken screenshots, incl. card↔PDP agreement and the honest 404 envelopes).
The ingestion verifier's refusal classes are tested against the REAL
`fetch_check` (monkeypatched transport) and the real revision guard of
`repair_product_images.py` — a dead/expired/rate-limited/non-image URL cannot
be promoted into canonical product data by a "successful" apply; and the tool
aborts outright on any DB whose alembic head differs from its audited
revision (`0035_product_images`; prod is past that, so any future apply
requires a plan RE-AUDIT first — recorded here as the gate doing its job).

## 5. Open owner decisions (honest blockers, not code)

1. **Bucket ingestion** (makes the media route the primary path and ends
   third-party hotlink dependence): needs approved storage writes + a re-audited
   plan at the current head. The Vercel filesystem is NOT a durable home for
   the 4 generated `/product-media/` files — they survive only in-repo under
   `frontend/public/product-media/`; deployment is the copy. Ingest them into
   the private Neon-S3 bucket under `products/<id>/…` keys and register the
   rows; the derivation already prefers that path when present.
2. **`h=1` anomaly observed in a historical VTON fetch log** (`w=800&h=1`):
   Pexels clamps it to a ~1 KB image rather than erroring — a *valid* status
   hiding an unusable asset. Current prod rows do not carry it; any future
   plan generator must keep the width/height/bytes/md5 equality check in
   `fetch_check` (it is what rejects exactly this class).
3. Production remains the pre-fix state until this PR ships (deploy = merge);
   verified pre-fix symptom and post-fix resolvable-set arithmetic above.

Commands reproducing the measurements are in the PR #358 discussion thread.
