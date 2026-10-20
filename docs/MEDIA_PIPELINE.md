# CONFIT — Product media pipeline

**Status:** implemented 2026-10-08. Verified in production by
`backend/scripts/verify_product_media.py` (exit 0 = every registered asset
exists, matches its metadata, and is reachable over HTTP as an image).

## Why this document exists

Before 2026-10-08 the platform had the assets and the metadata, and served
neither. Measured in production that day:

| Observation | Number |
|---|---|
| Registered derived assets in `product_images` | **120** (12 products x 5 ratios x 2 formats) |
| Assets present in the bucket with matching size/pixels | 120 / 120 |
| Registered URLs that answered HTTP 200 | **0 / 120** — the advertised `/api/v1/media/...` route did not exist |
| Rendered images on 8 screen captures that contradicted their own aspect ratio | **52 of 201 (25.9%)**, from 0.20 to 2.17 |
| Products whose storefront image came from a single legacy stock URL | 12 / 12 |

The storefront read `products.images` (one 3:2 stock photo) and cropped it into
seven fixed heights. The five-ratio set — the thing that makes an editorial
layout possible — existed but was invisible to every consumer.

## Architecture (one rule per arrow)

```
        seed / operator                 API                         browser
  ┌───────────────────────┐   ┌───────────────────────┐   ┌────────────────────────┐
  │ derive 5 ratios x 2   │   │ catalog serializer    │   │ <img src="…">          │
  │ formats, upload       │──▶│ reads product_images  │──▶│ same-origin, immutable │
  │ product_images rows   │   │ media route streams   │   │ CDN-cached, 304-able   │
  └───────────────────────┘   └───────────────────────┘   └────────────────────────┘
            │                            │
            ▼                            ▼
   private bucket (S3/Neon/R2)   whitelist = the table itself
```

1. **The bucket is private.** Anonymous GET on the plain endpoint returns 403
   (verified against Neon Object Storage). Nothing is exposed by making the
   bucket public — and nothing needs to be.
2. **The table is the access-control list.** `GET /api/v1/media/{key}` serves a
   key ONLY if a `product_images` row carries it. Traversal, enumeration and
   "read an arbitrary object" are impossible by construction, not by filter.
3. **URLs are derived, never stored twice.** `services/product_media_service.
   media_url_for_key()` is the single conversion point, so the URL the API hands
   out and the URL the route accepts cannot drift — that drift is exactly what
   produced the 404s.
4. **Two audiences, two mechanics.** Public catalogue media is streamed and
   cached immutably (`read_media_object`). Private per-user media (wardrobe,
   mood boards) keeps using presigned URLs (`storage_public_url`), because a
   durable public URL for a personal photo would be an exposure. Same bucket,
   different contract, on purpose.

## The ratio ladder

| ratio | pixels | used for | master? |
|---|---|---|---|
| `4x5` | 1200x1500 | product cards, portrait frames, the primary/hero asset | hero |
| `1x1` | 800x800 | thumbnails, swatch frames, cart lines | gallery |
| `3x2` | 1200x800 | editorial bands | gallery |
| `16x9` | 1280x720 | cinematic bands, open-graph cards | gallery |
| `master` | 1600x1600 | zoom / detail inspection only — never a card, never in `gallery_images()` | zoom source |

These are `RATIO_DIMENSIONS` in `services/media_materialization_service.py`, and
that dict is the authority. This table previously listed 1200x1200 / 1500x1000 /
1600x900 / 2000x2000 — the *earlier* set — and the prose outlived the code.
Measured against production on 2026-10-20, all five ratios carry exactly one
dimension across all 12 products (24 rows each: 12 products x 2 formats), which
is the signature of a single render pass at the values above. If you change
`RATIO_DIMENSIONS`, change this table in the same commit.

`order_media()` puts the primary row first and then walks this ladder, so the
first gallery frame, the card thumbnail and the list endpoint's hero are the
same file by construction.

## Integrity contract

* `checksum` = **first 32 hex characters of the object SHA-256** (recomputed for
  all 120 objects on 2026-10-08: every row matched its object's digest prefix).
  It is exposed as the response `ETag`, so a byte change invalidates every
  cache entry. Verification compares the prefix — see
  `scripts/verify_product_media.py`.
* `bytes`, `width`, `height` are asserted against the object on every
  verification run; a mismatch fails the script.
* `attribution` / `source_type` travel with the asset through the API
  (`media[]`), because a stock editorial photograph must never be presented as
  a boutique's own product shot.

## How to run the verification

```bash
# local (needs DATABASE_URL + storage credentials)
python -m backend.scripts.verify_product_media

# against a deployment
python -m backend.scripts.verify_product_media --api https://confit-a.vercel.app

# registry + bucket only, no HTTP
python -m backend.scripts.verify_product_media --skip-http
```

Exit code 1 means at least one of: a missing object, a size/digest/pixel
mismatch, an API payload that does not expose the registered set, or a media URL
that is not a 200 image. The failure list is printed (first 40).

## Repairing an incomplete ladder

`product_images` is the access-control list AND the completeness record, so a
product whose rows stop at `4x5` and `master` serves two frames and 404s the
other six URLs — even when the bucket holds objects for them. That is the
correct, restrictive behaviour: an unregistered object is invisible.

```bash
# what is missing, read-only
python -m backend.scripts.materialize_catalog_media --verify

# what a repair WOULD do (no writes)
python -m backend.scripts.materialize_catalog_media \
  --complete-ladder --slug <slug> --slug <slug>

# the repair itself — reversible, and refuses without a snapshot
python -m backend.scripts.materialize_catalog_media \
  --complete-ladder --apply --backup /path/snapshot.json --slug <slug>

# undo
python -m backend.scripts.materialize_catalog_media --rollback /path/snapshot.json
```

Three things this tooling learned the hard way, all of them now enforced:

1. **`--slug` repeats.** It used to hold a single value, so `--slug a --slug b`
   repaired only `b` while printing one line and exiting 0.
2. **`--apply` requires a real storage backend.** With `STORAGE_PROVIDER=local`
   the rows describe files on the operator's machine while the deployment reads
   its own bucket — a silent, total mismatch that still reports success. The
   tool refuses unless the provider is `s3`/`r2`, or you pass
   `--allow-local-storage` for a genuinely local database.
3. **A corrected object needs a new key.** Responses carry
   `s-maxage=31536000, immutable`, so the CDN keeps serving the old bytes for
   that URL for up to a year; rewriting the object at the same key changes
   nothing a browser can see. Re-publish under a new key
   (`products/9/9-1x1-20261020.jpg`) and repoint the row. This is the same rule
   the "no transformation at request time" decision implies: the key names a
   *shoot*, not a slot.

**Restore guarantee.** `--backup` writes every `product_images` row (all 16
columns) plus each product's `thumbnail_url`/`images`; `--rollback` restores that
snapshot exactly (pinned by `test_rollback_restores_the_snapshot_exactly`). The
*objects* are reproducible from the first-party sources in
`frontend/public/product-media/<slug>/` — verified on 2026-10-20 by re-rendering
all 8 objects of products 9 and 18 and matching their registered digests 8/8.

## What is deliberately NOT here

* **No image transformation at request time.** Ratios are derived once, at
  ingest, and stored. A resize proxy in the request path is a latency and cost
  trap, and it makes the bytes the customer saw unreproducible.
* **No public bucket.** It would be one misconfiguration away from exposing
  non-catalogue objects in the same bucket.
* **No invented imagery.** The current set is stock photography (`source_type =
  stock`, `provider = unsplash`) carried with attribution. Replacing it with
  real boutique photography is a content operation, and the UI must keep
  labelling what it is until then.
