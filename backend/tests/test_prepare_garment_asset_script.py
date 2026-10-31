"""prepare_garment_asset.py — the write path that makes a product renderable.

The script is the ONLY place that sets garment_assets.tryon_ready = True, so it
is also the easiest place to accidentally defeat the ghost-hands guard. These
tests pin the properties that make it safe:

  1. an image the guard calls "model" writes NOTHING (exit 2);
  2. there is no flag that turns that off;
  3. footwear / accessories are refused by design, not forced;
  4. a passing flat-lay records provenance so a generated demo asset stays
     identifiable and replaceable;
  5. it touches garment_assets only - never price, stock or the catalogue photo.
"""

from __future__ import annotations

import json

import pytest
from PIL import Image, ImageDraw

from backend.app.models.tryon import GarmentAsset


@pytest.fixture()
def db_ctx(monkeypatch, tmp_path):
    """Point the script's SessionLocal at a throwaway FILE database.

    A file (not `sqlite://`) on purpose: in-memory SQLite gives every pooled
    connection its own empty database, so a row written on one connection is
    invisible to the next - which makes fixtures fail in ways that look like
    script bugs.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.app.core.database import Base
    from backend.app.models import catalog as _catalog  # noqa: F401  (register tables)

    engine = create_engine(
        f"sqlite:///{tmp_path / 'fixture.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    import backend.scripts.prepare_garment_asset as mod

    monkeypatch.setattr(mod, "SessionLocal", Session)
    return Session


def _insert(db, table, **values):
    """Insert a row, auto-filling any required column the caller did not give.

    The catalogue ORM has many NOT NULL columns unrelated to this script; asking
    the live schema which ones are required keeps the fixture correct as the
    schema moves, instead of hard-coding a column list that rots.
    """
    from sqlalchemy import inspect as sa_inspect, text

    insp = sa_inspect(db.get_bind())
    required = [
        c["name"] for c in insp.get_columns(table)
        if not c["nullable"] and c.get("default") is None
        and not c.get("autoincrement", False)
    ]
    row = {}
    for name in required:
        if name in values:
            row[name] = values[name]
        elif name in ("id",) or name.endswith("_id"):
            row[name] = values.get("id", 1) if name == "id" else 1
        elif "price" in name or "amount" in name or "rate" in name:
            row[name] = 0
        elif "at" in name and (name.endswith("_at") or "date" in name):
            row[name] = "2026-01-01 00:00:00"
        elif name.startswith("is_") or name in ("active", "enabled"):
            row[name] = 1
        elif "json" in name or name in ("images", "style_tags", "occasion_tags"):
            row[name] = "[]"
        elif "url" in name:
            row[name] = "https://example.invalid/x.jpg"
        elif name.endswith("_ar"):
            row[name] = "x"
        else:
            row[name] = "x"
    row.update(values)
    cols = ", ".join(row)
    params = ", ".join(f":{k}" for k in row)
    db.execute(text(f"INSERT INTO {table} ({cols}) VALUES ({params})"), row)


def _seed_product(Session, *, product_id=1, slug="outerwear"):
    """Insert the minimum catalogue graph the script actually reads."""
    db = Session()
    try:
        _insert(db, "users", id=1, email="t@example.com")
        _insert(db, "brand_profiles", id=1, user_id=1, brand_name="Test Brand", slug="test-brand")
        _insert(db, "categories", id=product_id, name=slug.title(), slug=slug)
        _insert(
            db, "products",
            id=product_id, brand_id=1, category_id=product_id,
            title="Test Blazer", slug=f"test-blazer-{product_id}",
            base_price=2900, currency="EGP",
            thumbnail_url="https://example.invalid/on-model.jpg",
        )
        db.commit()
    finally:
        db.close()


def _flatlay(path):
    """A uniform-backdrop product shot: the shape the guard accepts."""
    im = Image.new("RGB", (600, 800), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([200, 150, 400, 700], fill=(20, 30, 80))  # navy garment
    im.save(path)
    return path


def _on_model(path):
    """Large skin-toned region: what the guard rejects."""
    im = Image.new("RGB", (600, 800), (250, 250, 250))
    d = ImageDraw.Draw(im)
    d.ellipse([220, 100, 380, 320], fill=(214, 168, 130))   # face
    d.rectangle([250, 330, 350, 620], fill=(214, 168, 130))  # neck/arms
    im.save(path)
    return path


def test_rejects_a_worn_photo_and_writes_nothing(db_ctx, tmp_path, monkeypatch):
    import backend.scripts.prepare_garment_asset as mod

    _seed_product(db_ctx)
    uploaded = []
    monkeypatch.setattr(
        mod, "get_storage_backend", lambda: type("S", (), {"store": lambda s, k, b: uploaded.append(k) and "x"})()
    )
    img = _on_model(str(tmp_path / "worn.jpg"))

    code = mod.main(["--product-id", "1", "--image", img])
    assert code == 2, "a worn photo must be refused"
    assert uploaded == [], "nothing may be uploaded for a refused image"

    db = db_ctx()
    try:
        assert db.query(GarmentAsset).count() == 0, "a refused image must not create a row"
    finally:
        db.close()


def test_there_is_no_force_flag():
    """The guard is not optional; a --force escape hatch would defeat it."""
    import inspect

    import backend.scripts.prepare_garment_asset as mod

    src = inspect.getsource(mod)
    # Look at the argparse declarations only: a docstring may legitimately say
    # "there is no --force", and matching the raw text would fail on that.
    declared = [ln.strip() for ln in src.splitlines() if "add_argument(" in ln]
    assert not any("--force" in ln for ln in declared), declared
    assert not any("--skip-guard" in ln or "--allow-model" in ln for ln in declared), declared


def test_accepts_a_flat_lay_and_records_provenance(db_ctx, tmp_path, monkeypatch):
    import backend.scripts.prepare_garment_asset as mod

    _seed_product(db_ctx)
    monkeypatch.setattr(
        mod,
        "get_storage_backend",
        lambda: type("S", (), {"store": lambda s, k, b: f"https://store.example/{k}"})(),
    )
    img = _flatlay(str(tmp_path / "flat.png"))

    code = mod.main(
        [
            "--product-id", "1", "--image", img,
            "--provenance", "generated-demo", "--note", "demo only",
        ]
    )
    assert code == 0

    db = db_ctx()
    try:
        asset = db.query(GarmentAsset).filter(GarmentAsset.product_id == 1).one()
        assert asset.tryon_ready is True
        assert asset.photo_type == "flat-lay"
        assert asset.clean_image_url and asset.clean_image_url.startswith("https://store.example/")
        assert asset.slot_type == "upper_outer"
        rec = json.loads(asset.classification_json)
        assert rec["provenance"] == "generated-demo"
        assert rec["note"] == "demo only"
        # This script prepares a clean SOURCE; it does not run segmentation.
        assert asset.segmented_garment_url is None
        assert asset.garment_mask_url is None
    finally:
        db.close()


def test_refuses_slots_the_registry_does_not_support(db_ctx, tmp_path):
    """Footwear/accessories are 'Fit Check only' - not forced to render."""
    import backend.scripts.prepare_garment_asset as mod

    _seed_product(db_ctx, product_id=7, slug="footwear")
    img = _flatlay(str(tmp_path / "shoe.png"))
    assert mod.main(["--product-id", "7", "--image", img]) == 3

    db = db_ctx()
    try:
        assert db.query(GarmentAsset).count() == 0
    finally:
        db.close()


def test_unknown_product_is_an_error_not_a_crash(db_ctx, tmp_path):
    import backend.scripts.prepare_garment_asset as mod

    _seed_product(db_ctx)
    assert mod.main(["--product-id", "999", "--image", _flatlay(str(tmp_path / "f.png"))]) == 3


def test_dry_run_uploads_nothing(db_ctx, tmp_path, monkeypatch):
    import backend.scripts.prepare_garment_asset as mod

    _seed_product(db_ctx)
    touched = []
    monkeypatch.setattr(mod, "get_storage_backend", lambda: touched.append(1))
    img = _flatlay(str(tmp_path / "flat.png"))

    assert mod.main(["--product-id", "1", "--image", img, "--dry-run"]) == 0
    assert touched == []
    db = db_ctx()
    try:
        assert db.query(GarmentAsset).count() == 0
    finally:
        db.close()


def test_never_touches_catalogue_fields(db_ctx, tmp_path, monkeypatch):
    """Preparing an asset must not alter price, stock or the product photo."""
    import backend.scripts.prepare_garment_asset as mod
    from backend.app.models.catalog import Product

    _seed_product(db_ctx)
    db = db_ctx()
    before = db.query(Product).filter(Product.id == 1).one()
    snapshot = (before.base_price, before.currency, before.thumbnail_url, before.title)
    db.close()

    monkeypatch.setattr(
        mod, "get_storage_backend",
        lambda: type("S", (), {"store": lambda s, k, b: f"https://store.example/{k}"})(),
    )
    assert mod.main(["--product-id", "1", "--image", _flatlay(str(tmp_path / "f.png"))]) == 0

    db = db_ctx()
    try:
        after = db.query(Product).filter(Product.id == 1).one()
        assert (after.base_price, after.currency, after.thumbnail_url, after.title) == snapshot
    finally:
        db.close()


def test_repreparing_updates_the_same_row_instead_of_duplicating(db_ctx, tmp_path, monkeypatch):
    import backend.scripts.prepare_garment_asset as mod

    _seed_product(db_ctx)
    monkeypatch.setattr(
        mod, "get_storage_backend",
        lambda: type("S", (), {"store": lambda s, k, b: f"https://store.example/{k}"})(),
    )
    img = _flatlay(str(tmp_path / "f.png"))
    assert mod.main(["--product-id", "1", "--image", img]) == 0
    assert mod.main(["--product-id", "1", "--image", img]) == 0

    db = db_ctx()
    try:
        assert db.query(GarmentAsset).filter(GarmentAsset.product_id == 1).count() == 1
    finally:
        db.close()
