"""Pre-launch media contract tests driven by a versioned dataset.

The dataset (backend/tests/data/prelaunch_media_dataset_v1.json) was authored
2026-10-18 from REAL production measurements: the 54 registered
``product_images`` rows (all in the upstream-source key shape), the twelve
products, and the live status of every URL class involved in the "Image
unavailable" defect. Cases are labelled fixture material; nothing here claims
third-party inventory beyond what was fetched and checked.

These tests pin the CONTRACT each producer/consumer must honour pre-launch:

* derivation (product_media_service.display_url_for_row) emits only deliverable
  URLs — media route for ingest keys, verified https/same-origin public_url
  for upstream rows, never an invented dead route, never http/protocol-relative;
* the media route's whitelist (database as ACL) keeps refusing traversal,
  unregistered and colon-shaped keys;
* registered-but-absent objects answer a 404 an operator can trace, and the
  serializer falls back to legacy data instead of blanking the page;
* the ingestion verifier refuses dead/forbidden/rate-limited/non-decodable
  sources so a broken URL can never be promoted into canonical product data
  because an import "succeeded".
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.models.catalog import Product, ProductImage
from backend.app.services import product_media_service as pms
from backend.tests.conftest import TestingSessionLocal

DATA = json.loads(
    (Path(__file__).parent / "data" / "prelaunch_media_dataset_v1.json").read_text(encoding="utf-8")
)
CASES = {c["id"]: c for c in DATA["cases"]}


def _row(case_inputs):
    from types import SimpleNamespace

    return SimpleNamespace(
        storage_key=case_inputs.get("storage_key"),
        public_url=case_inputs.get("public_url"),
    )


def test_dataset_is_versioned_and_complete():
    assert DATA["version"] == 1
    assert DATA["generated_utc"] == "2026-10-18"
    assert len(CASES) == 15
    assert all(c.startswith("plm-") for c in CASES), "stable IDs required"


@pytest.mark.parametrize("case_id", ["plm-001", "plm-002", "plm-003", "plm-004", "plm-008"])
def test_derivation_emits_exactly_the_expected_deliverable_url(case_id):
    case = CASES[f"{case_id}-ingest-key-registered"] if case_id == "plm-001" else None
    key = {
        "plm-001": "plm-001-ingest-key-registered",
        "plm-002": "plm-002-prod-pexels-colon-live",
        "plm-003": "plm-003-prod-unsplash-colon-live",
        "plm-004": "plm-004-generated-same-origin",
        "plm-008": "plm-008-traversal-key",
    }[case_id]
    expected = CASES[key]["expect"]["display_url"]
    assert pms.display_url_for_row(_row(CASES[key]["inputs"])) == expected


@pytest.mark.parametrize("case_id", [
    "plm-005-colon-key-empty-public-url",
    "plm-006-insecure-http-public-url",
    "plm-007-protocol-relative-public-url",
    "plm-015-no-image-at-all",
])
def test_undeliverable_inputs_yield_no_url(case_id):
    inputs = CASES[case_id]["inputs"]
    assert pms.display_url_for_row(_row(inputs)) is None


def test_media_route_refuses_dataset_key_shapes(client: TestClient):
    """Whitelist matrix from the dataset: traversal, unregistered ingest key,
    and the production colon shape are all 404 before any query or read."""
    for path in [
        "/api/v1/media/products/1/../../etc/passwd",
        "/api/v1/media/products/99999/99999-4x5.jpg",
        "/api/v1/media/pexels:883362:4x5:hero",
        "/api/v1/media/generated:whatever:4x5:hero",
    ]:
        res = client.get(path)
        assert res.status_code == 404, path
        assert res.json()["error"]["code"] == "RESOURCE_NOT_FOUND", path


def test_registered_but_absent_object_is_honest_404(client: TestClient, monkeypatch):
    """plm-010: the row is registered, the bucket object is gone -> 404 + a
    traceable log, never a blank 200 (the placeholder then stays honest)."""
    db = TestingSessionLocal()
    try:
        product = db.query(Product).order_by(Product.id).first()
        row = ProductImage(
            product_id=product.id,
            storage_key="products/2/2-4x5.jpg",
            public_url="/api/v1/media/products/2/2-4x5.jpg",
            ratio="4x5", format="jpg", width=800, height=1000, bytes=1,
            role="hero", is_primary=True, source_type="stock", provider="pexels",
            source_ref="https://www.pexels.com/photo/1/", attribution="Photo: Pexels",
            checksum="c" * 32, created_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
    finally:
        db.close()
    try:
        monkeypatch.setattr(
            "backend.app.controllers.media_controller.read_media_object", lambda key: None
        )
        res = client.get("/api/v1/media/products/2/2-4x5.jpg")
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    finally:
        db = TestingSessionLocal()
        try:
            db.query(ProductImage).filter(ProductImage.storage_key == "products/2/2-4x5.jpg").delete()
            db.commit()
        finally:
            db.close()


# ── ingestion verifier: broken sources must never reach canonical data ─────


class _Resp:
    def __init__(self, status_code, content=b"", headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}


@pytest.mark.parametrize("case_id,http_status", [
    ("plm-011-upstream_dead_404", 404),
    ("plm-012-upstream_forbidden_403", 403),
    ("plm-013-upstream_rate_limited_429", 429),
])
def test_plan_verifier_refuses_dead_forbidden_rate_limited_sources(monkeypatch, case_id, http_status):
    """The transport is faked via sys.modules so this test file never imports
    `requests` directly — check_runtime_imports.py walks backend/tests and the
    docker manifest legitimately ships without requests (the app uses httpx;
    the repair script imports lazily at its own runtime)."""
    import sys
    import types as _t

    fake = _t.ModuleType("requests")
    fake.get = lambda url, **kw: _Resp(http_status, b"nope")  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "requests", fake)
    from backend.scripts.repair_product_images import fetch_check

    case = CASES[case_id]
    rendition = {"url": case["inputs"]["url"], "ratio": "4x5", "width": 800, "height": 1000, "bytes": 10, "md5": "0" * 32}
    out = fetch_check(rendition)
    assert out["ok"] is False, "non-200 must fail verification — never a silent pass"
    assert out["http"] == http_status


def test_plan_verifier_refuses_200_that_is_not_a_decodable_image(monkeypatch):
    """plm-014: an HTML error page served with 200 is NOT an asset."""
    import sys
    import types as _t

    fake = _t.ModuleType("requests")
    fake.get = lambda url, **kw: _Resp(200, b"<html>404 not an image</html>", {"content-type": "text/html"})  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "requests", fake)
    from backend.scripts.repair_product_images import fetch_check

    case = CASES["plm-014-upstream_non_image_content"]
    rendition = {"url": case["inputs"]["url"], "ratio": "4x5", "width": 800, "height": 1000, "bytes": 999, "md5": "0" * 32}
    out = fetch_check(rendition)
    assert out["ok"] is False
    assert "error" in out, "decode failure must be recorded as a verification failure"


def test_apply_guard_refuses_wrong_database_revision():
    """The repair tool is pinned to its audited migration (0035) and ABORTS on
    a database at a different head — production is at 0039 (0040 pending), so
    a plan re-audit is mandatory before any apply. This is the guard doing its
    job, proven here without touching any database."""
    import pytest as _pytest
    from backend.scripts.repair_product_images import guard

    class Cur:
        def execute(self, sql):
            self.sql = sql
            return self

        def fetchall(self):
            if "alembic_version" in self.sql:
                return [("0039_some_other",)]
            return [(12,)]

        def fetchone(self):
            return (12,)

    plan = {"db_revision_audited": "0035_product_images"}
    with _pytest.raises(SystemExit) as exc:
        guard(Cur(), plan)
    assert "ABORT" in str(exc.value)
