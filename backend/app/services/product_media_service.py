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
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple

from backend.app.models.catalog import ProductImage

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
    """
    return f"{MEDIA_URL_PREFIX}{storage_key.lstrip('/')}"


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

    ONE FRAME PER PHOTOGRAPH, NOT PER FILE
    --------------------------------------
    The registry stores each ratio twice (``jpg`` for the compatibility list,
    ``webp`` for a ``<picture>``) and ``order_media`` puts the JPEG first, so
    the key to de-duplicate on is the RATIO. De-duplicating on the URL — which
    this did until 2026-10-20 — compares two different strings, so nothing was
    ever removed: a four-photograph product advertised eight gallery frames in
    production and every photograph appeared twice in a row (the PDP rail
    exposed ``View image 1`` … ``View image 8``).

    ``media[]`` still carries both formats; a caller that wants ``<picture>``
    reads it there. This list is the plain ``images`` contract: one decodable
    URL per photograph, in ladder order, master excluded.
    """
    hero = _hero_photo_rows(rows)
    ordered = order_media(hero)
    out: List[str] = []
    seen_ratios: set[str] = set()
    for row in ordered:
        if row.ratio == "master" or row.ratio in seen_ratios:
            continue
        seen_ratios.add(row.ratio)
        out.append(media_url_for_key(row.storage_key))
    return out


def primary_url(rows: Sequence[ProductImage]) -> Optional[str]:
    """Hero URL for cards/OG tags — the registry's own ``is_primary`` row."""
    ordered = order_media(rows)
    for row in ordered:
        if row.is_primary and row.ratio != "master":
            return media_url_for_key(row.storage_key)
    for row in ordered:
        if row.ratio != "master":
            return media_url_for_key(row.storage_key)
    return None


def photo_index_of(row: ProductImage) -> int:
    """Which source photograph a row is a rendition of (0 = hero)."""
    idx = getattr(row, "photo_index", 0)
    return 0 if idx is None else int(idx)


def _hero_photo_rows(rows: Sequence[ProductImage]) -> List[ProductImage]:
    """The rows of the FIRST photograph, and nothing else.

    ``images`` is pinned to "one frame per ratio" by
    ``test_product_gallery_uniqueness.py``, and that contract is about the hero
    photograph's format ladder. With a gallery in the table, de-duplicating on
    ratio across ALL photographs would silently mix frames from different
    pictures into one list. Scoping to photograph 0 keeps the old contract
    exactly true for single-photograph products (every row is 0) and keeps it
    meaningful for multi-photograph products.
    """
    indices = sorted({photo_index_of(r) for r in rows})
    if not indices:
        return []
    hero = indices[0]
    return [r for r in rows if photo_index_of(r) == hero]


def photos_payload(rows: Sequence[ProductImage]) -> List[dict]:
    """The product's photographs, ordered, primary first.

    ONE ENTRY PER SUPPLIED IMAGE — the additive half of the media contract.
    ``images``/``media`` describe renditions of the hero; they cannot describe a
    gallery, because a second photograph has no place in a list that is keyed by
    ratio. This payload is what the product page's thumbnail rail iterates, so
    every photograph a brand supplied is addressable and none is invisible.

    Each entry carries its own attribution: photograph 2 may be the brand's own
    back view while photograph 1 is licensed stock, and a caption about "whose
    picture this is" cannot be borrowed from a sibling.
    """
    by_photo: dict = {}
    for row in rows:
        by_photo.setdefault(photo_index_of(row), []).append(row)

    out: List[dict] = []
    for position in sorted(by_photo):
        group = by_photo[position]
        ordered = order_media(group)
        # jpg before webp per ratio: the plain <img> src needs a decodable format.
        ratios: dict = {}
        for row in ordered:
            if row.ratio == "master":
                continue
            ratios.setdefault(row.ratio, media_url_for_key(row.storage_key))
        lead = next((r for r in ordered if r.ratio != "master"), ordered[0])
        out.append(
            {
                "position": position,
                "is_primary": any(bool(r.is_primary) for r in group) or position == 0,
                "url": media_url_for_key(lead.storage_key),
                "images": ratios,
                "source_ref": lead.source_ref,
                "source_type": lead.source_type,
                "provider": lead.provider,
                "attribution": lead.attribution,
                "frames": media_payload(group),
            }
        )
    return out


def media_payload(rows: Sequence[ProductImage]) -> List[dict]:
    """Metadata for every asset, so the UI can choose by ratio and attribute.

    ``attribution``/``source_type`` travel with the image because honesty about
    whose photograph this is cannot be reconstructed later: a stock editorial
    picture presented as a boutique's own product shot is a trust defect, and
    the label has to come from the same row that holds the file.
    """
    return [
        {
            "url": media_url_for_key(r.storage_key),
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
            "photo_index": photo_index_of(r),
        }
        for r in order_media(rows)
    ]
