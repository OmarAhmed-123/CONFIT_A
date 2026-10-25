"""The try-on studio must be able to SAY when a garment asset is a demo.

Products 1-4 render from ``generated-demo`` assets: an AI-generated flat-lay
stands in for the real product so the engine can be exercised at all. The
customer is shown a garment that is not the thing they are buying, and until now
nothing in the response told the UI so — the product page carries the catalogue
photo, the try-on renders a different garment, and the shopper has no way to
know which one they are looking at.

The avatar path already discloses this ("Demo models are AI-generated full-body
figures, not customers"). This pins the same honesty for garments: the
capability entry for a product carries the asset's provenance, and it is
read-only — asking about a product must never create an asset row.
"""
from __future__ import annotations

import json

import pytest


def _fake_db_with_asset(classification: dict | None, *, exists: bool = True):
    """Minimal stand-in for the SQLAlchemy session used by the lookup."""
    class _Asset:
        product_id = 3
        classification_json = json.dumps(classification) if classification else None

    class _Query:
        def filter(self, *a, **k):
            return self

        def first(self):
            return _Asset() if exists else None

    class _DB:
        def query(self, *a, **k):
            return _Query()

    return _DB()


def test_a_generated_demo_asset_is_reported_as_such():
    from backend.app.services.tryon_service import TryOnService

    service = TryOnService(db=_fake_db_with_asset(
        {"provenance": "generated-demo", "note": "DEMO asset"}))
    assert service.garment_asset_provenance(3) == "generated-demo"


def test_a_real_photograph_is_reported_as_such():
    from backend.app.services.tryon_service import TryOnService

    service = TryOnService(db=_fake_db_with_asset({"provenance": "real-photo"}))
    assert service.garment_asset_provenance(3) == "real-photo"


def test_no_asset_is_reported_as_none_not_guessed():
    """Absent provenance must not be presented as real photography."""
    from backend.app.services.tryon_service import TryOnService

    service = TryOnService(db=_fake_db_with_asset(None, exists=False))
    assert service.garment_asset_provenance(3) is None


def test_unparseable_classification_json_does_not_raise():
    from backend.app.services.tryon_service import TryOnService

    class _Asset:
        product_id = 3
        classification_json = "{not json"

    class _Query:
        def filter(self, *a, **k):
            return self

        def first(self):
            return _Asset()

    class _DB:
        def query(self, *a, **k):
            return _Query()

    service = TryOnService(db=_DB())
    assert service.garment_asset_provenance(3) is None


def test_the_capability_payload_carries_the_provenance(client):
    """End to end through the endpoint the studio actually calls."""
    res = client.get("/api/v1/try-on/capabilities?product_ids=3")
    assert res.status_code == 200, res.text
    body = res.json()
    entries = body.get("products") or []
    assert entries, body
    entry = entries[0]
    assert entry["product_id"] == 3
    assert "garment_asset_provenance" in entry, (
        "the studio cannot disclose a demo garment asset it is never told about"
    )
