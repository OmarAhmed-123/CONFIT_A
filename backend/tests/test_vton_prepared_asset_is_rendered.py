"""The prepared garment asset must actually be the image that gets rendered.

BUG FOUND ON THE LIVE PIPELINE (2026-10-25)
  `_build_garments_payload` fetched the garment as:

      b64 = await self._fetch_image_as_base64(p.thumbnail_url)

  and never looked at `GarmentAsset.clean_image_url` again. A prepared asset
  therefore only did ONE thing: `if not (asset and asset.tryon_ready)` SKIPPED
  the ghost-hands gate. The bytes sent to the segmentation-free engine were
  still the catalogue photo.

  Two consequences, both reproduced end to end:

  1. WRONG GARMENT RENDERED. Product 3 ("Relaxed Organic Poplin Oxford Shirt",
     white) rendered as a PURPLE JACKET, because its catalogue thumbnail is a
     stock photo of THREE shirts on a table and the engine composited the
     burgundy one. Two runs 1 minute apart, with a different prepared asset
     between them, returned a byte-identical image (md5 a33a6271...) - proof
     the new asset was never read.

  2. THE GUARD WAS BYPASSED, NOT SATISFIED. Marking a product `tryon_ready`
     let an ON-MODEL catalogue photo reach an engine that cannot distinguish a
     worn garment from a flat-lay - exactly the ghost-hands incident the gate
     exists to prevent. Preparing an asset made the product LESS safe.

  These tests pin the corrected contract: a ready asset's clean image is what
  ships to the worker; if it cannot be fetched, the request FAILS CLOSED rather
  than silently falling back to the on-model catalogue photo.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json

import pytest
from PIL import Image, ImageDraw


def _png_bytes(colour=(20, 30, 80)) -> bytes:
    im = Image.new("RGB", (64, 96), (255, 255, 255))
    ImageDraw.Draw(im).rectangle([16, 16, 48, 80], fill=colour)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


CLEAN_BYTES = _png_bytes((20, 30, 80))     # the prepared asset
THUMB_BYTES = _png_bytes((200, 30, 30))    # the catalogue photo


class _Product:
    def __init__(self, pid=3, thumbnail="https://cdn.example/on-model.jpg"):
        self.id = pid
        self.title = "Relaxed Organic Poplin Oxford Shirt"
        self.thumbnail_url = thumbnail
        self.base_price = 95
        self.currency = "EGP"
        self.color_family = "Optic White"
        self.color_hex = "#FAF9F6"
        self.material = "100% Organic Cotton"
        self.image_url = thumbnail
        self.skus = []

        class _Cat:
            slug = "tops"
            name = "Tops & Shirts"

        class _Brand:
            brand_name = "Casa Lumen"

        self.category = _Cat()
        self.brand = _Brand()


class _FakeService:
    """Minimal stand-in exposing only what _build_garments_payload touches."""

    def __init__(self, asset, fetch_map, db=None):
        self._asset = asset
        self._fetch_map = fetch_map
        self.db = db or _FakeDB(asset)
        self.catalog_repo = None
        self.tryon_repo = None
        self.profile_repo = None
        from backend.app.services.tryon_service import TryOnService

        self._real = TryOnService

    async def _fetch_image_as_base64(self, url):
        return self._fetch_map.get(url)

    def __getattr__(self, name):
        raise AttributeError(name)


class _FakeDB:
    def __init__(self, asset):
        self._asset = asset

    def query(self, model):
        return self

    def filter(self, *a, **k):
        return self

    def first(self):
        return self._asset


class _Asset:
    def __init__(self, ready=True, clean="https://store.example/clean.png"):
        self.tryon_ready = ready
        self.clean_image_url = clean
        self.segmented_garment_url = None
        self.product_id = 3


def _build(service, products):
    """Call the real method with the fake's collaborators patched in."""
    from backend.app.services.tryon_service import TryOnService

    payload = asyncio.run(
        TryOnService._build_garments_payload.__get__(service, TryOnService)(products)
    )
    return payload


def _b64_of(payload_entry) -> bytes:
    raw = payload_entry["image_base64"]
    if raw.startswith("data:"):
        raw = raw.split(",", 1)[1]
    return base64.b64decode(raw)


def test_a_ready_asset_sends_the_prepared_clean_image_not_the_thumbnail():
    """The regression. Before the fix this sent THUMB_BYTES."""
    clean_url = "https://store.example/clean.png"
    svc = _FakeService(
        asset=_Asset(ready=True, clean=clean_url),
        fetch_map={
            "https://cdn.example/on-model.jpg": "data:image/png;base64,"
            + base64.b64encode(THUMB_BYTES).decode(),
            clean_url: "data:image/png;base64," + base64.b64encode(CLEAN_BYTES).decode(),
        },
    )
    payload = _build(svc, [_Product()])
    assert len(payload) == 1
    assert _b64_of(payload[0]) == CLEAN_BYTES, (
        "the prepared garment asset must be the image rendered"
    )


def test_fails_closed_when_the_prepared_asset_cannot_be_fetched():
    """Never silently fall back to the on-model catalogue photo."""
    svc = _FakeService(
        asset=_Asset(ready=True, clean="https://store.example/gone.png"),
        fetch_map={
            "https://cdn.example/on-model.jpg": "data:image/png;base64,"
            + base64.b64encode(THUMB_BYTES).decode(),
            # clean url deliberately absent -> fetch returns None
        },
    )
    with pytest.raises(Exception) as exc:
        _build(svc, [_Product()])
    assert "VTON_GARMENT_ASSET_INVALID" in str(exc.value)
    assert THUMB_BYTES not in str(exc.value).encode()


def test_an_unprepared_product_still_goes_through_the_ghost_hands_gate():
    """No ready asset -> the catalogue photo is classified and refused if worn."""
    # A figure the REAL guard classifies as `model` (skin-ratio, 0.158):
    # head + torso + two arms in skin tone. Verified against the shipped
    # classifier, not assumed - a fixture the guard accepts would make this
    # test assert nothing.
    worn = io.BytesIO()
    im = Image.new("RGB", (600, 900), (140, 150, 160))
    d = ImageDraw.Draw(im)
    d.ellipse([230, 80, 370, 260], fill=(214, 168, 130))
    d.rectangle([250, 260, 350, 420], fill=(214, 168, 130))
    d.rectangle([140, 300, 200, 620], fill=(214, 168, 130))
    d.rectangle([400, 300, 460, 620], fill=(214, 168, 130))
    im.save(worn, format="PNG")
    worn_b64 = "data:image/png;base64," + base64.b64encode(worn.getvalue()).decode()

    svc = _FakeService(
        asset=None,
        fetch_map={"https://cdn.example/on-model.jpg": worn_b64},
    )
    with pytest.raises(Exception) as exc:
        _build(svc, [_Product()])
    assert "VTON_GARMENT_ASSET_INVALID" in str(exc.value)


def test_a_disabled_gate_still_prefers_the_prepared_asset():
    """The asset path is not a gate feature; it is the correct input."""
    clean_url = "https://store.example/clean.png"
    svc = _FakeService(
        asset=_Asset(ready=True, clean=clean_url),
        fetch_map={
            "https://cdn.example/on-model.jpg": "data:image/png;base64,"
            + base64.b64encode(THUMB_BYTES).decode(),
            clean_url: "data:image/png;base64," + base64.b64encode(CLEAN_BYTES).decode(),
        },
    )
    import os

    old = os.environ.get("VTON_ASSET_GATE_ENABLED")
    os.environ["VTON_ASSET_GATE_ENABLED"] = "false"
    try:
        payload = _build(svc, [_Product()])
    finally:
        if old is None:
            os.environ.pop("VTON_ASSET_GATE_ENABLED", None)
        else:
            os.environ["VTON_ASSET_GATE_ENABLED"] = old
    assert _b64_of(payload[0]) == CLEAN_BYTES


def test_a_private_bucket_asset_is_signed_before_fetching(monkeypatch):
    """Neon buckets are private; the stored canonical URL returns 403.

    The row therefore holds the right object and the fetch still fails unless
    the URL is presigned at read time - which is what the API does at every
    response boundary. Pinned here because the failure mode is silent: a
    prepared asset that exists but cannot be read looks identical to an
    unprepared product until a render is attempted.
    """
    from backend.app.services import storage_service

    clean_url = "https://store.example/confit-a-media/garment-assets/3/clean.png"
    signed_url = clean_url + "?X-Amz-Signature=deadbeef"

    class _Store:
        def key_for_url(self, url):
            return "garment-assets/3/clean.png" if url == clean_url else None

        def presign_url(self, key, expires_in=None):
            assert key == "garment-assets/3/clean.png"
            return signed_url

    monkeypatch.setattr(storage_service, "get_storage_backend", lambda: _Store())

    svc = _FakeService(
        asset=_Asset(ready=True, clean=clean_url),
        fetch_map={
            clean_url: None,  # unsigned: 403 in reality, None here
            signed_url: "data:image/png;base64," + base64.b64encode(CLEAN_BYTES).decode(),
        },
    )
    payload = _build(svc, [_Product()])
    assert _b64_of(payload[0]) == CLEAN_BYTES
