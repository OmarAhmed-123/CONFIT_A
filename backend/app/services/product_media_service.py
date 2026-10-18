"""Product media — ONE place that turns the registry into storefront URLs.

The problem this closes (measured in production 2026-10-08):

* ``products.images`` holds a single legacy stock URL per product; the
  storefront rendered it at seven different fixed heights, so 52 of 201
  rendered images (25.9%) contradicted their own aspect ratio;
* ``product_images`` holds the professional derived set — 5 ratios x 2 formats
  per product, with width/height/bytes/checksum/attribution — and NO code read
  it;
* every ``public_url`` in that table pointed at ``/api/v1/media/...``, a route
  that did not exist, so the advertised URLs answered 404.

This module is the single conversion point. Both the catalogue serializer and
the media route import from here, so the URL a client is given and the URL the
server accepts can never drift — the defect above was exactly that drift.

MEASURED 2026-10-18 (the second defect this file must not reintroduce): the
conversion assumed every registry row was an ingested object. In production the
media pass registered 54 rows whose ``storage_key`` is the plan's key shape
(``provider:photo_id:ratio:role``) and whose bytes live at the upstream
``public_url`` (Pexels/Unsplash CDN, or same-origin files under
``/product-media/`` for generated visuals); nothing was ever uploaded to the
bucket, so not one key matches the ``products/<id>/<file>`` shape the media
route whitelists. Deriving ``/api/v1/media/<colon key>`` anyway served the
client a URL that answers 404 by construction — every product card fell to the
honest "Image unavailable" state while perfectly live images sat unused in the
same rows. Rule now enforced here: **a URL is only emitted for a source the
server can actually deliver** — the media route for a registered ingest key,
the row's own verified URL otherwise, and nothing at all when neither exists
(the caller then falls back to the legacy column, and the placeholder stays
honest for genuinely missing assets).
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional, Sequence, Tuple

from backend.app.models.catalog import ProductImage

#: The ONE key shape the media route can serve: an ingested object registered
#: under ``products/<product id>/<file>``. The media controller whitelists
#: against this same pattern; keeping it here is what stops client-facing URLs
#: and server-accepted keys from drifting apart again (2026-10-18 defect).
SERVEABLE_KEY_RE = re.compile(r"^products/\d{1,12}/[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")


def is_serveable_storage_key(key: Optional[str]) -> bool:
    """True only for keys the media route will actually serve bytes for."""
    return bool(SERVEABLE_KEY_RE.match(key or ""))

#: The design system's official ratio ladder, in the order a gallery shows them:
#: the portrait hero first (what cards render), then square, then landscape,
#: then the cinematic band. ``master`` is the zoom source: it is served LAST and
#: is never a card thumbnail (a 2000x2000 master for a 4:5 card is pure waste).
RATIO_ORDER: Tuple[str, ...] = ("4x5", "1x1", "3x2", "16x9", "master")

#: Same bytes, smaller payload: jpg first for the compatibility list, webp kept
#: available in ``media[]`` so a caller can emit a <picture> element.
FORMAT_ORDER: Tuple[str, ...] = ("jpg", "jpeg", "png", "webp", "avif")

#: Public prefix of the media route (see controllers/media_controller.py).
MEDIA_URL_PREFIX = "/api/v1/media/"


def media_url_for_key(storage_key: str) -> str:
    """Canonical, cacheable URL for a stored object.

    Relative on purpose: the same value is correct on a local dev server, on a
    preview deployment and on the production domain, and it keeps working when
    the domain changes. The storefront and the API are same-origin.

    Only valid for ingested keys — callers rendering a registry row must go
    through ``display_url_for_row``, which is the function that knows whether
    the media route can serve the key at all.
    """
    return f"{MEDIA_URL_PREFIX}{storage_key.lstrip('/')}"


def display_url_for_row(row: ProductImage) -> Optional[str]:
    """The URL a client can actually load for one registry row, or None.

    Preference order is capability, not aesthetics:
    1. an ingested key (``products/<id>/<file>``) -> the immutable same-origin
       media route, the fastest and cache-friendliest path;
    2. otherwise the row's own ``public_url`` when it is an https URL or a
       site-relative path — production's rows carry verified upstream URLs
       there, and the CSP already allowlists those image hosts;
    3. otherwise None: no URL is invented. The caller falls back to the legacy
       column, and HonestProductImage shows its honest unavailable state only
       when genuinely nothing can be served.
    """
    key = (row.storage_key or "").lstrip("/")
    if is_serveable_storage_key(key):
        return media_url_for_key(key)
    public = (row.public_url or "").strip()
    if public.startswith("https://") or (public.startswith("/") and not public.startswith("//")):
        return public
    return None


def order_media(rows: Iterable[ProductImage]) -> List[ProductImage]:
    """Deterministic gallery order: primary first, then the ratio ladder.

    Deterministic matters for two reasons: the first element becomes the
    thumbnail, and a gallery that reshuffles between requests makes a product
    look like it changed.
    """
    return sorted(
        rows,
        key=lambda r: (
            0 if r.is_primary else 1,
            RATIO_ORDER.index(r.ratio) if r.ratio in RATIO_ORDER else len(RATIO_ORDER),
            FORMAT_ORDER.index((r.format or "").lower()) if (r.format or "").lower() in FORMAT_ORDER else len(FORMAT_ORDER),
            r.id,
        ),
    )


def gallery_images(rows: Sequence[ProductImage]) -> List[str]:
    """The ``images`` list a product page renders: one URL per ratio, no master.

    Two ratios never collapse into each other: 4:5 is the portrait card frame,
    1:1 the thumbnail/swatch frame, 3:2 and 16:9 the editorial bands. Serving all
    four lets the UI pick instead of cropping a single 3:2 into seven heights.
    """
    ordered = order_media(rows)
    out: List[str] = []
    seen: set[str] = set()
    for row in ordered:
        if row.ratio == "master":
            continue
        url = display_url_for_row(row)
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def primary_url(rows: Sequence[ProductImage]) -> Optional[str]:
    """Hero URL for cards/OG tags — the registry's own ``is_primary`` row."""
    ordered = order_media(rows)
    for row in ordered:
        if row.is_primary and row.ratio != "master":
            url = display_url_for_row(row)
            if url:
                return url
    for row in ordered:
        if row.ratio != "master":
            url = display_url_for_row(row)
            if url:
                return url
    return None


def media_payload(rows: Sequence[ProductImage]) -> List[dict]:
    """Metadata for every asset, so the UI can choose by ratio and attribute.

    ``attribution``/``source_type`` travel with the image because honesty about
    whose photograph this is cannot be reconstructed later: a stock editorial
    picture presented as a boutique's own product shot is a trust defect, and
    the label has to come from the same row that holds the file.
    """
    out: List[dict] = []
    for r in order_media(rows):
        url = display_url_for_row(r)
        if not url:
            # No deliverable source: the row is metadata-only and must not
            # become a dead <img>. The gallery still shows it with no frame.
            continue
        out.append(
        {
            "url": url,
            "storage_key": r.storage_key,
            "ratio": r.ratio,
            "format": r.format,
            "width": r.width,
            "height": r.height,
            "bytes": r.bytes,
            "role": r.role,
            "is_primary": bool(r.is_primary),
            "source_type": r.source_type,
            "provider": r.provider,
            "attribution": r.attribution,
        }
        )
    return out
