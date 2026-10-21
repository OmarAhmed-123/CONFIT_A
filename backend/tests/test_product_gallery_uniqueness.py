"""The product gallery must show one frame per photograph, not one per file.

MEASURED DEFECT (2026-10-20, production, read-only)
---------------------------------------------------
``GET /api/v1/catalog/products/silk-slip-column-maxi-dress`` returned eight
entries in ``images``::

    /api/v1/media/products/5/5-4x5.jpg
    /api/v1/media/products/5/5-4x5.webp     <- same photograph
    /api/v1/media/products/5/5-1x1.jpg
    /api/v1/media/products/5/5-1x1.webp     <- same photograph
    ...

The PDP renders ``images`` as a thumbnail rail and as a swipeable hero gallery,
so a four-photograph product advertised **eight** frames and every photograph
appeared twice in a row. Verified in the deployed bundle: the rail exposes
``View image 1`` … ``View image 8`` for four registered ratios.

WHY IT HAPPENED
---------------
``product_media_service.gallery_images`` documents itself as "one URL per
ratio, no master" and de-duplicates on the URL string. Since the media
materialization pass registers BOTH formats per ratio (``jpg`` for the
compatibility list and ``webp`` for a ``<picture>`` element — see
``FORMAT_ORDER``), two different URLs exist per ratio and neither is a string
duplicate of the other. The de-duplication therefore never fired.

The invariant these tests pin:

  A. ``gallery_images`` returns ONE URL per ratio, in ladder order, master
     excluded;
  B. the preferred format wins (``jpg`` before ``webp``), because the JPEG is
     the format the ``<img src>`` fallback needs;
  C. a ratio registered in a single format is still returned;
  D. ``media[]`` keeps BOTH formats — the ``<picture>`` path must not lose the
     webp that this change removes from ``images``;
  E. the number of gallery frames equals the number of distinct ratios for a
     real seeder-shaped product.
"""
from __future__ import annotations

import pytest

from backend.app.models.catalog import ProductImage
from backend.app.services.product_media_service import gallery_images, media_payload


def _row(ratio: str, fmt: str, *, primary: bool = False, pid: int = 1) -> ProductImage:
    return ProductImage(
        id=hash((ratio, fmt)) % 10_000,
        product_id=pid,
        storage_key=f"products/{pid}/{pid}-{ratio}.{fmt}",
        public_url=f"/api/v1/media/products/{pid}/{pid}-{ratio}.{fmt}",
        ratio=ratio,
        format=fmt,
        width=1200,
        height=1500,
        bytes=1000,
        role="hero" if primary else "gallery",
        is_primary=primary,
        source_type="stock",
        provider="unsplash",
        attribution="Photo: Unsplash",
    )


def _ladder(pid: int = 1) -> list[ProductImage]:
    """The registry shape the materializer actually writes: 4 ratios × 2 formats."""
    rows: list[ProductImage] = []
    for ratio in ("4x5", "1x1", "3x2", "16x9"):
        for fmt in ("jpg", "webp"):
            rows.append(_row(ratio, fmt, primary=(ratio == "4x5" and fmt == "jpg"), pid=pid))
    for fmt in ("jpg", "webp"):
        rows.append(_row("master", fmt, pid=pid))
    return rows


def test_gallery_returns_one_frame_per_ratio():
    """A. Eight registered files, four photographs -> four frames."""
    frames = gallery_images(_ladder())

    assert len(frames) == 4, f"expected one frame per ratio, got {len(frames)}: {frames}"

    suffixes = [f.rsplit("/", 1)[-1] for f in frames]
    assert suffixes == [
        "1-4x5.jpg",
        "1-1x1.jpg",
        "1-3x2.jpg",
        "1-16x9.jpg",
    ], f"unexpected ladder order/format: {suffixes}"


def test_gallery_prefers_the_compatibility_format():
    """B. jpg is the fallback a plain <img src> can always decode."""
    frames = gallery_images(_ladder())

    assert not [f for f in frames if f.endswith(".webp")], (
        f"images[] must carry the universally-decodable format; got {frames}"
    )


def test_gallery_keeps_a_single_format_ratio():
    """C. A ratio that only exists as webp is still a real photograph."""
    rows = [
        _row("4x5", "jpg", primary=True),
        _row("1x1", "jpg"),
        _row("16x9", "webp"),
    ]

    frames = gallery_images(rows)

    assert len(frames) == 3
    assert frames[-1].endswith("1-16x9.webp"), frames


def test_gallery_excludes_the_master():
    """The zoom master is never a card/gallery frame."""
    frames = gallery_images(_ladder())

    assert not [f for f in frames if "master" in f], frames


def test_media_payload_keeps_both_formats():
    """D. Removing the duplicate from ``images`` must not remove it from ``media``."""
    payload = media_payload(_ladder())

    formats = {(item["ratio"], item["format"]) for item in payload}
    assert len(payload) == 10, f"media[] must keep every asset, got {len(payload)}"
    assert ("4x5", "jpg") in formats and ("4x5", "webp") in formats


def test_gallery_is_deduplicated_per_product_in_a_two_product_catalog():
    """E. Two products never contaminate each other's gallery."""
    first = gallery_images([r for r in _ladder(pid=1)])
    second = gallery_images([r for r in _ladder(pid=2)])

    assert len(first) == len(second) == 4
    assert all("/products/1/" in f for f in first)
    assert all("/products/2/" in f for f in second)


def test_empty_registry_yields_no_frames():
    assert gallery_images([]) == []
