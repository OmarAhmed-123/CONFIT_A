"""Materialise product media: fetch an approved source image, store derived
renditions, and register them so the URL the catalogue serves IS the object key.

WHY THIS MODULE EXISTS
----------------------
Measured on the live store 2026-10-20: every product card rendered
"Image unavailable". The registry was NOT empty — 54 ``product_images`` rows
existed — and the bucket was not empty either (120 derived objects). The two
disagreed, three ways:

  * ``media_controller._KEY_RE`` accepts only ``products/{id}/{file}``;
  * the bucket holds ``products/{product_id}/{product_id}-{ratio}.{ext}``;
  * the registry rows carried ``{provider}:{photo_id}:{ratio}:{role}`` — a
    *label* produced by the 2026-10-09 repair pass, never an object key, with
    ``public_url`` pointing at the upstream Pexels/Unsplash hotlink because that
    pass assumed the media route would serve ``public_url``. It does not: it
    serves ``storage_key``.

So the URL streamed to the browser named an object that could not exist under
that name, and every request was rejected by the whitelist regex before the
database was even queried. Zero of the 54 rows' byte counts matched any object
in the bucket, which is the proof that those files were never uploaded — the
registry recorded *intent*, not storage.

The rule this module enforces, and the reason it is the only writer:

    a ``product_images`` row is created ONLY after the exact bytes it describes
    have been uploaded, and its ``storage_key`` is the key they were uploaded to.

Everything recorded (bytes, width, height, checksum) is measured from the bytes
that were actually stored, never copied from a plan or a remote URL. That makes
the registry a statement about the bucket rather than a hope about it.

Provenance is mandatory: ``source_type`` is ``stock`` for licensed photography
and ``generated`` for illustrations, and ``provider``/``attribution`` travel with
the row so the UI can say whose picture it is. A stock photo presented as a
boutique's own product shot is a trust defect, not a cosmetic one.
"""
from __future__ import annotations

import hashlib
import io
import os
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, NamedTuple

from backend.app.core.logging import logger
from backend.app.models.catalog import ProductImage

#: The ratio ladder the design system renders. ``master`` is the zoom source and
#: is never a card thumbnail.
RATIO_DIMENSIONS: Dict[str, Tuple[int, int]] = {
    "4x5": (1200, 1500),
    "1x1": (800, 800),
    "3x2": (1200, 800),
    "16x9": (1280, 720),
    "master": (1600, 1600),
}

#: ``hero`` is the card/first frame; everything else is gallery.
ROLE_BY_RATIO: Dict[str, str] = {"4x5": "hero"}

#: Hosts whose licences permit commercial storefront use and which are already
#: allowed by the site's CSP ``img-src``. A source outside this list is refused
#: rather than uploaded: widening the policy is an owner decision.
APPROVED_SOURCE_HOSTS: Tuple[str, ...] = (
    "images.unsplash.com",
    "images.pexels.com",
)

_PROVIDER_BY_HOST: Sequence[Tuple[str, str]] = (
    ("images.unsplash.com", "unsplash"),
    ("images.pexels.com", "pexels"),
)

_EXT_BY_FORMAT = {"jpeg": "jpg", "jpg": "jpg", "png": "png", "webp": "webp", "avif": "avif"}
_FORMAT_BY_EXT = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "avif": "avif"}

#: The object key contract. Must stay identical to
#: ``controllers.media_controller._KEY_RE`` — that identity is the whole point.
CANONICAL_KEY_RE = re.compile(r"^products/\d{1,12}/[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")


def _per_photo_failures() -> tuple:
    """Exceptions that drop ONE photograph instead of aborting the gallery.

    A refused ownership check is a per-image verdict — the rest of the gallery
    is still importable and must still be reported. Imported lazily because
    `brand_catalog_service` imports this module.
    """
    from backend.app.services.brand_catalog_service import MediaOwnershipRefused

    return (MediaMaterializationError, MediaSourceNotApproved, MediaOwnershipRefused)


class MediaSourceNotApproved(ValueError):
    """The image host is not on the commercial-use allowlist."""


class MediaMaterializationError(RuntimeError):
    """Nothing was registered; the caller must not claim an image exists."""


def canonical_storage_key(product_id: int, ratio: str, fmt: str, photo_index: int = 0) -> str:
    """``products/{id}/{id}-{ratio}.{ext}`` — the ONE object-key shape.

    The product id doubles as the row prefix, which is what the bucket already
    contains and what the media route's whitelist accepts.

    PHOTOGRAPH n > 0 gets ``{id}-p{n}-{ratio}.{ext}``. The suffix is what makes
    a second photograph possible at all: without it, photograph 1 would be
    written to photograph 0's exact keys and silently replace the hero the
    storefront is already serving. Photograph 0 keeps the historical shape
    unchanged, so no existing object, row, cached URL or test moves.
    """
    ext = _EXT_BY_FORMAT.get((fmt or "").lower())
    if not ext:
        raise MediaMaterializationError(f"unsupported image format: {fmt!r}")
    idx = int(photo_index or 0)
    if idx < 0:
        raise MediaMaterializationError(f"photo index must be >= 0, got {idx}")
    stem = f"{int(product_id)}" if idx == 0 else f"{int(product_id)}-p{idx}"
    key = f"products/{int(product_id)}/{stem}-{ratio}.{ext}"
    if not CANONICAL_KEY_RE.match(key):
        raise MediaMaterializationError(f"derived key violates the media contract: {key}")
    return key


def photo_index_of(row) -> int:
    """The photograph a registry row belongs to, defaulting to the hero.

    Rows written before migration 0041 carry the server default; a row object
    that has not been refreshed from the database yet may present ``None``, and
    treating that as "not the hero" would drop it from ``images``.
    """
    idx = getattr(row, "photo_index", 0)
    return 0 if idx is None else int(idx)


def provider_for_url(url: str) -> str:
    """Map a source URL to its provider, or raise if the host is not approved."""
    host = (url or "").split("://", 1)[-1].split("/", 1)[0].lower().split(":")[0]
    for allowed in APPROVED_SOURCE_HOSTS:
        if host == allowed or host.endswith("." + allowed):
            for known, provider in _PROVIDER_BY_HOST:
                if allowed == known:
                    return provider
    raise MediaSourceNotApproved(
        f"{host or 'unknown host'} is not an approved image source; "
        f"allowed: {', '.join(APPROVED_SOURCE_HOSTS)}"
    )


def _render(img, width: int, height: int):
    """Centre-crop to the target aspect, then resize. Never stretches."""
    from PIL import Image

    target_ratio = width / height
    src_ratio = img.width / img.height
    if src_ratio > target_ratio:          # too wide → trim the sides
        new_w = int(round(img.height * target_ratio))
        left = (img.width - new_w) // 2
        img = img.crop((left, 0, left + new_w, img.height))
    elif src_ratio < target_ratio:        # too tall → trim top/bottom
        new_h = int(round(img.width / target_ratio))
        top = (img.height - new_h) // 2
        img = img.crop((0, top, img.width, top + new_h))
    return img.resize((width, height), Image.LANCZOS)


def render_renditions(data: bytes, ratios: Iterable[str] = tuple(RATIO_DIMENSIONS)) -> Dict[str, "object"]:
    """Decode once, produce one PIL image per requested ratio."""
    from PIL import Image

    img = Image.open(io.BytesIO(data))
    img.load()
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    out = {}
    for ratio in ratios:
        dims = RATIO_DIMENSIONS.get(ratio)
        if not dims:
            raise MediaMaterializationError(f"unknown ratio: {ratio}")
        out[ratio] = _render(img, *dims)
    return out


def encode(img, fmt: str, quality: int = 86) -> bytes:
    buf = io.BytesIO()
    fmt = (fmt or "").lower()
    if fmt in ("jpg", "jpeg"):
        img.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
    elif fmt == "webp":
        img.save(buf, format="WEBP", quality=quality, method=4)
    elif fmt == "png":
        img.save(buf, format="PNG", optimize=True)
    else:
        raise MediaMaterializationError(f"unsupported output format: {fmt}")
    return buf.getvalue()


def checksum_of(data: bytes) -> str:
    """The 32-char SHA-256 prefix the schema and the ETag both expect."""
    return hashlib.sha256(data).hexdigest()[:32]


def storage_key_for_row(row: ProductImage) -> Optional[str]:
    """The key a row claims, or ``None`` when it is a legacy label.

    Used by the repair path to identify rows that predate this module. A label
    never satisfies the media route's whitelist, so serving one is impossible.
    """
    key = (row.storage_key or "").strip()
    return key if CANONICAL_KEY_RE.match(key) else None


class MediaResolvability(NamedTuple):
    """The honest answer to "will this product's hero actually render?".

    A row in ``product_images`` is NOT the answer. The original defect was
    exactly that: 54 rows existed and every one of them 404'd, because the row
    named a key that had never been written to the bucket. So ``resolvable``
    requires all three of:
      1. at least one registered row,
      2. whose ``storage_key`` is a canonical key (i.e. what the media route
         will accept rather than reject at parse time),
      3. whose backing object is actually present in the store.
    ``reason`` says which of those failed, so an import can report something
    specific instead of a shrug.
    """

    rows: int
    resolvable: bool
    reason: str


def verify_resolvable(db, product_id: int, storage=None) -> MediaResolvability:
    """Measure — never assume — whether a product has servable media."""
    rows = db.query(ProductImage).filter(ProductImage.product_id == product_id).all()
    canonical = [r for r in rows if r.storage_key and CANONICAL_KEY_RE.match(r.storage_key)]
    if not canonical:
        return MediaResolvability(len(rows), False, "no_source" if not rows else "legacy_label_key")
    if storage is None:
        try:
            storage = MediaMaterializationService(db)._get_storage()
        except Exception:
            return MediaResolvability(len(rows), False, "storage_unavailable")
    for row in canonical:
        key = row.storage_key
        try:
            exists = getattr(storage, "exists", None)
            present = exists(key) if callable(exists) else storage.read(key) is not None
        except Exception:
            continue
        if present:
            return MediaResolvability(len(rows), True, "ok")
    return MediaResolvability(len(rows), False, "object_missing")


class MediaMaterializationService:
    """Fetch → derive → store → register. The only writer of ``product_images``."""

    def __init__(self, db, storage=None, fetch=None):
        self.db = db
        self._storage = storage
        self._fetch = fetch

    # -- collaborators (overridable so tests never touch the network) --------
    def _get_storage(self):
        if self._storage is not None:
            return self._storage
        from backend.app.services.storage_service import get_storage
        return get_storage()

    #: Per-call ownership gate for the duration of one `materialize()`. Read by
    #: the default transport so the check reaches EVERY redirect hop without
    #: changing `_get_fetch`'s zero-argument shape — that shape is the seam the
    #: test suite replaces with an offline double, and a double has no redirect
    #: chain to authorize (it would also silently skip the gate).
    _hop_gate = None

    def _get_fetch(self):
        if self._fetch is not None:
            return self._fetch
        from backend.app.core.net_guard import safe_get

        def fetch(url: str) -> bytes:
            # `safe_get` validates the URL and EVERY redirect hop before it is
            # requested. Stock hosts were safe by construction; first-party
            # URLs typed into a CSV are not, and this is the one place in the
            # catalogue that turns such a string into a server-side request.
            #
            # `allow_hop` adds the ownership check to the SAME hops, because a
            # verified domain redirecting to an unowned host must not be
            # followed: net_guard would see a perfectly public destination and
            # allow it, and the brand would import someone else's image.
            return safe_get(url, timeout=30, allow_hop=self._hop_gate)

        return fetch

    # -- the single public operation -----------------------------------------
    def materialize(
        self,
        product,
        source_url: str,
        *,
        source_type: str = "stock",
        provider: Optional[str] = None,
        source_ref: Optional[str] = None,
        attribution: Optional[str] = None,
        ratios: Sequence[str] = tuple(RATIO_DIMENSIONS),
        formats: Sequence[str] = ("jpeg", "webp"),
        commit: bool = True,
        photo_index: int = 0,
        replace_existing: bool = True,
        ownership_gate=None,
    ) -> List[ProductImage]:
        """Upload every rendition and register a row per (ratio, format).

        All-or-nothing PER PHOTOGRAPH: if any rendition of THIS photograph fails
        to store, none of its rows are registered — a partial ladder would
        advertise frames that 404. Other photographs already registered are
        untouched, which is what makes a partially failed gallery reportable
        instead of fatal.

        ``photo_index`` selects the photograph (0 = the hero, preserving the
        historical keys). ``replace_existing=False`` keeps the product's existing
        rows, so a gallery can be built photograph by photograph; the caller is
        then responsible for clearing the set before the first photograph.
        """
        if source_type not in ("stock", "own", "partner", "generated"):
            raise MediaMaterializationError(f"invalid source_type: {source_type!r}")

        if source_type == "stock":
            # Licensed photography MUST come from an approved commercial host,
            # even when the caller asserts a provider: a caller-supplied string
            # is not evidence of a licence.
            provider = provider_for_url(source_url)
        else:
            # First-party assets (our own generated illustrations, a partner's
            # own photography) are not third-party stock and have no external
            # licence to check.
            provider = provider or source_type

        # Defence in depth on the SECOND question. `_validate_image_source`
        # already refused unauthorized URLs during validation, but this method
        # is also reachable from the dashboard and from any future caller — and
        # a check that only runs in the importer is a check an importer-shaped
        # bug can skip. `ownership_gate(url)` raises on an unauthorized hop.
        if ownership_gate is not None:
            ownership_gate(source_url)

        previous_gate = self._hop_gate
        self._hop_gate = ownership_gate
        try:
            source_bytes = self._get_fetch()(source_url)
        except MediaSourceNotApproved:
            raise
        except Exception as exc:  # network/decode failure: nothing was stored
            raise MediaMaterializationError(
                f"could not read source image for product {getattr(product, 'id', '?')}: {type(exc).__name__}: {exc}"
            ) from exc
        finally:
            # Never leak one import's authorization into the next photograph:
            # a stale gate would authorize a URL for the wrong brand.
            self._hop_gate = previous_gate

        rendered = render_renditions(source_bytes, ratios)
        storage = self._get_storage()

        written: List[Tuple[str, str, str, int, int, int, str]] = []
        try:
            for ratio, img in rendered.items():
                for fmt in formats:
                    data = encode(img, fmt)
                    key = canonical_storage_key(product.id, ratio, fmt, photo_index)
                    returned = storage.store(key, data) or key

                    # Backends differ: the local one returns the relative path,
                    # the S3/R2 one returns a full public URL. What must hold in
                    # both cases is that the object ended up UNDER THE KEY WE
                    # REGISTER — otherwise the row would name a file that is not
                    # there, which is the exact defect this module exists to
                    # prevent.
                    if not (returned == key or str(returned).endswith("/" + key)):
                        raise MediaMaterializationError(
                            f"storage placed {key} somewhere else ({returned}); refusing to register"
                        )
                    exists = getattr(storage, "exists", None)
                    if callable(exists) and not exists(key):
                        raise MediaMaterializationError(
                            f"storage reported success but holds no object at {key}"
                        )
                    written.append((key, ratio, fmt, img.width, img.height, len(data), checksum_of(data)))
        except Exception as exc:
            self._unregister(product)
            raise MediaMaterializationError(
                f"media upload failed for product {getattr(product, 'id', '?')}: {exc}"
            ) from exc

        # Every byte is in place; only now does the registry learn about it.
        if replace_existing:
            self._unregister(product, flush=True)
        rows: List[ProductImage] = []
        for key, ratio, fmt, width, height, nbytes, checksum in written:
            row = ProductImage(
                product_id=product.id,
                storage_key=key,
                public_url=f"/api/v1/media/{key}",
                ratio=ratio,
                format=fmt,
                width=width,
                height=height,
                bytes=nbytes,
                role=ROLE_BY_RATIO.get(ratio, "gallery"),
                # Exactly one hero across the whole gallery: the first
                # photograph's 4:5 JPEG. A second photograph that also claimed
                # ``is_primary`` would make ``primary_url`` depend on row order.
                is_primary=(int(photo_index or 0) == 0 and ratio == "4x5"
                            and _EXT_BY_FORMAT.get(fmt) == "jpg"),
                photo_index=int(photo_index or 0),
                source_type=source_type,
                provider=provider,
                source_ref=source_ref or source_url,
                attribution=attribution,
                checksum=checksum,
            )
            self.db.add(row)
            rows.append(row)

        # The legacy column must agree with the registry, otherwise a caller
        # that still reads it shows a different picture than the card. Only
        # photograph 0 may write it: a later photograph must not move the hero.
        if int(photo_index or 0) == 0:
            hero = next((r for r in rows if r.is_primary), rows[0])
            product.thumbnail_url = hero.public_url

        try:
            if commit:
                self.db.commit()
            else:
                self.db.flush()
        except Exception as exc:
            self.db.rollback()
            raise MediaMaterializationError(f"registry write failed for product {product.id}: {exc}") from exc

        logger.info(
            "product_media_materialized",
            product_id=product.id,
            rows=len(rows),
            provider=provider,
            source_type=source_type,
        )
        return rows

    def materialize_photos(
        self,
        product,
        photos: Sequence[dict],
        *,
        commit: bool = True,
        ownership_gate=None,
    ) -> Tuple[List[ProductImage], List[dict]]:
        """Register EVERY supplied photograph, reporting the ones that failed.

        ``photos`` is an ordered sequence of
        ``{"url", "source_type", "provider", "attribution", "source_ref"}``.
        Position in the sequence IS the photograph's index, so the gallery keeps
        the order the brand submitted instead of the order the network happened
        to answer in.

        Returns ``(rows, failures)``. A failure is
        ``{"position", "url", "reason"}`` and does NOT abort the remaining
        photographs — a brand whose third image 404s must still get the other
        two, and must be told which one was dropped. The caller is required to
        surface ``failures``: silently importing "some of" a gallery while
        reporting success is the defect this method exists to end.
        """
        rows: List[ProductImage] = []
        failures: List[dict] = []
        if not photos:
            return rows, failures

        # Clear once, then append: each photograph registers into the set that
        # the previous one built.
        self._unregister(product, flush=True)

        for position, photo in enumerate(photos):
            url = (photo.get("url") or "").strip()
            if not url:
                failures.append({"position": position, "url": url, "reason": "empty_url"})
                continue
            try:
                rows.extend(
                    self.materialize(
                        product,
                        url,
                        source_type=photo.get("source_type") or "stock",
                        provider=photo.get("provider"),
                        source_ref=photo.get("source_ref") or url,
                        attribution=photo.get("attribution"),
                        commit=False,
                        photo_index=position,
                        replace_existing=False,
                        ownership_gate=ownership_gate,
                    )
                )
            except _per_photo_failures() as exc:
                failures.append({"position": position, "url": url, "reason": str(exc)[:200]})
                logger.warning(
                    "photo_materialization_failed",
                    product_id=getattr(product, "id", None),
                    position=position,
                    reason=type(exc).__name__,
                )
            except Exception as exc:  # network/decode: one photo, not the gallery
                failures.append({"position": position, "url": url, "reason": f"{type(exc).__name__}"})
                logger.warning(
                    "photo_materialization_error",
                    product_id=getattr(product, "id", None),
                    position=position,
                    reason=type(exc).__name__,
                )

        try:
            if commit:
                self.db.commit()
            else:
                self.db.flush()
        except Exception as exc:
            self.db.rollback()
            raise MediaMaterializationError(f"gallery write failed for product {product.id}: {exc}") from exc
        return rows, failures

    def _unregister(self, product, flush: bool = False) -> None:
        """Drop this product's registered rows (used before a re-registration)."""
        existing = self.db.query(ProductImage).filter(ProductImage.product_id == product.id).all()
        for row in existing:
            self.db.delete(row)
        if flush:
            self.db.flush()
