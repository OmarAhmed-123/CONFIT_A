"""Public, cacheable product media.

WHY THIS ROUTE HAD TO EXIST
---------------------------
``product_images.public_url`` has advertised ``/api/v1/media/products/{id}/{file}``
since the media pass was seeded, and that path answered HTTP 404 in production
(measured 2026-10-08 on every one of the 12 primary assets) because no router
implemented it. The bucket itself is private — an anonymous GET on the plain
Neon endpoint returns 403 — so the derived set was unreachable from a browser:
the correct assets existed, were registered, and could not be seen.

DESIGN CONSTRAINTS (each one is a defect this file must not reintroduce)
-----------------------------------------------------------------------
1. **Whitelist, never a path join.** A key is served only if a ``product_images``
   row carries it. Traversal, bucket enumeration and "read any object" are all
   impossible by construction — the database is the access-control list.
2. **Immutable and cacheable.** These bytes never change under a fixed key (a
   re-shoot produces a new key), so the response carries
   ``public, max-age=31536000, s-maxage=31536000, immutable`` and an ETag from
   the registered checksum: the CDN absorbs the traffic and a repeat view is a
   304, which is what keeps a media-heavy editorial page fast.
3. **Honest failure.** Unknown key -> 404 in the project's error envelope;
   object missing although registered -> 404 (and the log names the key, because
   that is a data defect the operator must fix); storage unconfigured -> 503 via
   the shared exception, never a blank 200.
4. **Same-origin, CSP-safe.** Serving from our own host keeps ``img-src 'self'``
   intact — no third-party image host has to be added to the policy.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.exceptions import ResourceNotFoundError
from backend.app.core.logging import logger
from backend.app.models.catalog import ProductImage
from backend.app.services.storage_service import read_media_object

router = APIRouter(prefix="/media", tags=["Media"])

#: products/<digits>/<name>.<ext> — the registry's own key shape. Anchored and
#: dot-segment free; anything else is rejected before a query is issued.
_KEY_RE = re.compile(r"^products/\d{1,12}/[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")

_IMMUTABLE = "public, max-age=31536000, s-maxage=31536000, immutable"

_CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "avif": "image/avif",
    "gif": "image/gif",
}


def _content_type(row: ProductImage) -> str:
    fmt = (row.format or "").lower()
    if fmt in _CONTENT_TYPES:
        return _CONTENT_TYPES[fmt]
    ext = row.storage_key.rsplit(".", 1)[-1].lower() if "." in row.storage_key else ""
    return _CONTENT_TYPES.get(ext, "application/octet-stream")


@router.get("/{key:path}")
def get_product_media(key: str, request: Request, db: Session = Depends(get_db)) -> Response:
    """Stream one registered product asset from the object store."""
    if not _KEY_RE.match(key):
        raise ResourceNotFoundError("Media", key)

    row = db.query(ProductImage).filter(ProductImage.storage_key == key).first()
    if row is None:
        # Not registered = not public. This is the whitelist boundary.
        raise ResourceNotFoundError("Media", key)

    etag = f'"{row.checksum}"' if row.checksum else f'W/"{row.id}-{row.bytes}"'
    if request.headers.get("if-none-match") in {etag, etag.strip('"')}:
        return Response(
            status_code=304,
            headers={"ETag": etag, "Cache-Control": _IMMUTABLE, "Vary": "Accept"},
        )

    data = read_media_object(key)  # raises FeatureNotConfiguredError when unset; None = absent
    if data is None:
        # Registered but absent from the bucket: a data defect, not a client
        # error. Logged with the key so it can be repaired, still a 404 to the
        # caller because there is nothing to serve.
        logger.error(f"media object missing for registered key: {key}")
        raise ResourceNotFoundError("Media", key)

    return Response(
        content=data,
        media_type=_content_type(row),
        headers={
            "Cache-Control": _IMMUTABLE,
            "ETag": etag,
            "Content-Length": str(len(data)),
            # Explicit: the bytes are what the registry says they are, and this
            # header is proof rather than a promise.
            "X-Media-Ratio": row.ratio,
            "X-Media-Checksum": (row.checksum or "")[:32],
        },
    )
