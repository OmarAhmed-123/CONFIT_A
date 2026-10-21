"""The gallery works on the schema production actually has, not a friendlier one.

THE DEFECT THIS PINS (measured 2026-10-21)
------------------------------------------
Migration 0041 added ``product_images.photo_index`` so a product could hold more
than one photograph. Production still carried the pre-0041 rule::

    uq_product_image_ratio_format  UNIQUE (product_id, ratio, format)

Photograph 1's 4:5 JPEG and photograph 0's 4:5 JPEG are the same
``(product_id, ratio, format)``, so production refused the second photograph::

    photograph 0, 4x5 jpeg: inserted
    photograph 1, 4x5 jpeg: REFUSED -> UNIQUE constraint failed

Every gallery test passed anyway, because tests build their schema from
``Base.metadata`` and the ORM never declared that constraint — ``create_all``
produced a table with no such rule. The suite was green against a schema
production does not have, and the feature was dead on deploy.

So these tests do two things a permissive schema cannot fake:

1. assert the constraint the ORM declares *includes* ``photo_index``;
2. build a table carrying production's OLD constraint, show that a second
   photograph is rejected there, and show that the ORM's current rule accepts
   it — the difference being the migration under review.
"""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import inspect

from backend.app.core.database import Base
from backend.app.models.catalog import ProductImage

TABLE = "product_images"


def _unique_constraints(bind) -> dict[str, tuple[str, ...]]:
    """{constraint name: ordered column tuple} for the real, materialised table."""
    insp = inspect(bind)
    return {
        c["name"]: tuple(c["column_names"])
        for c in insp.get_unique_constraints(TABLE)
    }


@pytest.fixture()
def model_table(tmp_path):
    """A database built from the ORM exactly as the test suite builds it."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{tmp_path / 'model.db'}")
    # Only what this test needs; create_all on all 54 tables is slower and adds
    # nothing to the question being asked.
    Base.metadata.create_all(engine, tables=[ProductImage.__table__])
    yield engine
    engine.dispose()


def test_the_declared_constraint_includes_photo_index(model_table):
    """The rule must permit one row per (photograph, ratio, format) — no fewer."""
    constraints = _unique_constraints(model_table)
    assert "uq_product_image_photo_ratio_format" in constraints, (
        f"the ORM does not declare the photo-aware rule; it declares {constraints}"
    )
    cols = constraints["uq_product_image_photo_ratio_format"]
    assert cols == ("product_id", "photo_index", "ratio", "format"), cols
    # The exact regression: a rule without photo_index cannot express a gallery.
    assert "photo_index" in cols, "a constraint without photo_index blocks a second photograph"


def test_two_photographs_can_share_a_ratio_and_format(model_table):
    """Photograph 0 and photograph 1 both supply 4:5 JPEG. Both must persist."""
    from sqlalchemy.orm import sessionmaker

    db = sessionmaker(bind=model_table)()
    try:
        for photo_index in (0, 1, 2):
            db.add(ProductImage(
                product_id=9, photo_index=photo_index, ratio="4x5", format="jpeg",
                storage_key=f"products/9/9-p{photo_index}-4x5.jpg",
                public_url=f"/api/v1/media/products/9/9-p{photo_index}-4x5.jpg",
                width=1200, height=1500, bytes=1000, role="hero",
                is_primary=(photo_index == 0), source_type="stock",
            ))
        db.commit()
        assert db.query(ProductImage).filter_by(product_id=9, ratio="4x5", format="jpeg").count() == 3
    finally:
        db.close()


def test_a_duplicate_photograph_ratio_format_is_still_refused(model_table):
    """The rule must still prevent the same picture twice — relaxing must be exact."""
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import sessionmaker

    db = sessionmaker(bind=model_table)()
    try:
        common = dict(product_id=9, ratio="4x5", format="jpeg", width=1, height=1, bytes=1,
                      role="hero", is_primary=False, source_type="stock")
        db.add(ProductImage(photo_index=0, storage_key="products/9/a.jpg",
                            public_url="/api/v1/media/products/9/a.jpg", **common))
        db.commit()
        db.add(ProductImage(photo_index=0, storage_key="products/9/b.jpg",
                            public_url="/api/v1/media/products/9/b.jpg", **common))
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()


def test_productions_old_constraint_is_what_broke_the_gallery():
    """Reproduce the deployed rule and show the rejection it caused.

    Deliberately built from SQL, not from the ORM: the point is that the two
    schemas disagreed, and a test that only ever builds the ORM's version can
    never observe the disagreement.
    """
    con = sqlite3.connect(":memory:")
    try:
        con.execute(f"""
            CREATE TABLE {TABLE} (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              product_id INTEGER NOT NULL,
              ratio VARCHAR(20) NOT NULL,
              format VARCHAR(20) NOT NULL,
              photo_index INTEGER NOT NULL DEFAULT 0,
              storage_key VARCHAR(255),
              CONSTRAINT uq_product_image_ratio_format UNIQUE (product_id, ratio, format)
            )""")
        con.execute(f"INSERT INTO {TABLE} (product_id,ratio,format,photo_index,storage_key) "
                    f"VALUES (9,'4x5','jpeg',0,'products/9/9-4x5.jpg')")
        with pytest.raises(sqlite3.IntegrityError) as err:
            con.execute(f"INSERT INTO {TABLE} (product_id,ratio,format,photo_index,storage_key) "
                        f"VALUES (9,'4x5','jpeg',1,'products/9/9-p1-4x5.jpg')")
        assert "UNIQUE constraint failed" in str(err.value)

        # And the rule this release ships accepts exactly that row.
        con.execute(f"ALTER TABLE {TABLE} RENAME TO old_rows")
        con.execute(f"""
            CREATE TABLE {TABLE} (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              product_id INTEGER NOT NULL,
              ratio VARCHAR(20) NOT NULL,
              format VARCHAR(20) NOT NULL,
              photo_index INTEGER NOT NULL DEFAULT 0,
              storage_key VARCHAR(255),
              CONSTRAINT uq_product_image_photo_ratio_format
                UNIQUE (product_id, photo_index, ratio, format)
            )""")
        con.execute(f"INSERT INTO {TABLE} (product_id,ratio,format,photo_index,storage_key) "
                    f"VALUES (9,'4x5','jpeg',0,'products/9/9-4x5.jpg')")
        con.execute(f"INSERT INTO {TABLE} (product_id,ratio,format,photo_index,storage_key) "
                    f"VALUES (9,'4x5','jpeg',1,'products/9/9-p1-4x5.jpg')")
        assert con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0] == 2
    finally:
        con.close()
