"""0042 · the photo-uniqueness constraint must include photo_index.

WHY THIS EXISTS
---------------
0041 added ``product_images.photo_index`` so a product could hold MORE THAN ONE
photograph, and it is correct as far as it goes — but it left the older
constraint in place::

    uq_product_image_ratio_format  UNIQUE (product_id, ratio, format)

Photograph 1's 4:5 JPEG and photograph 0's 4:5 JPEG are the same
``(product_id, ratio, format)``, so that constraint refuses the second
photograph. Measured against production's real constraint set on 2026-10-21::

    photograph 0, 4x5 jpeg: inserted
    photograph 1, 4x5 jpeg: REFUSED -> UNIQUE constraint failed

The consequence is the exact defect 0041 set out to fix: a brand supplies
front/back/detail, the hero registers, the rest are reported as failures, and
the job still reports success. In production the feature cannot work; in the
test suite it appears to work because the tests build their schema from
``Base.metadata`` and **the ORM never declared that constraint**, so
``create_all`` never created it. Green tests, broken feature.

WHAT THIS DOES
--------------
Replaces the constraint with the one the model actually needs::

    uq_product_image_photo_ratio_format
        UNIQUE (product_id, photo_index, ratio, format)

Every existing row has ``photo_index = 0`` (0041's server default), so the new
constraint is strictly weaker than the old one: any set of rows satisfying
``UNIQUE (product_id, ratio, format)`` also satisfies this. It therefore cannot
fail on existing data, and no byte moves.

ORDERING AND SAFETY
-------------------
* Additive-in-effect, non-destructive: no row is read, rewritten or deleted.
* ``DROP CONSTRAINT`` takes an ACCESS EXCLUSIVE lock on ``product_images`` for
  the duration; ``ADD CONSTRAINT`` builds its index while holding SHARE ROW
  EXCLUSIVE, blocking writes. The table holds 120 rows, so both are
  sub-second — but they are lock-taking, so this runs in a maintenance window,
  not opportunistically.
* PostgreSQL 15+ supports ``ADD CONSTRAINT ... NOT VALID`` followed by
  ``VALIDATE CONSTRAINT`` to avoid blocking writes while scanning. Not used
  here: at 120 rows the scan is instantaneous and the simpler statement is
  easier to verify.
* Reversible: ``downgrade`` restores the original constraint, which succeeds
  only while no product holds more than one photograph. That is stated plainly
  in ``downgrade`` rather than assumed.

Revision ID: 0042_photo_unique_with_index
Revises: 0041_photo_index
Create Date: 2026-10-21
"""

from alembic import op
import sqlalchemy as sa

revision = "0042_photo_unique_with_index"
down_revision = "0041_photo_index"
branch_labels = None
depends_on = None

_OLD = "uq_product_image_ratio_format"
_NEW = "uq_product_image_photo_ratio_format"
_TABLE = "product_images"


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def upgrade() -> None:
    if _is_sqlite():
        # SQLite cannot drop a table-level constraint in place; batch mode
        # rebuilds the table, preserving rows. Only relevant to developer
        # databases — CI and production are PostgreSQL.
        with op.batch_alter_table(_TABLE, recreate="always") as batch:
            batch.drop_constraint(_OLD, type_="unique")
            batch.create_unique_constraint(
                _NEW, ["product_id", "photo_index", "ratio", "format"]
            )
        return

    op.drop_constraint(_OLD, _TABLE, type_="unique")
    op.create_unique_constraint(
        _NEW, _TABLE, ["product_id", "photo_index", "ratio", "format"]
    )


def downgrade() -> None:
    """Restore the pre-0041 rule.

    This succeeds only if no product currently holds a second photograph: the
    old constraint cannot express one. Reversing it after such rows exist will
    fail with a duplicate-key error rather than silently dropping photographs —
    which is the correct outcome. Prefer the forward fix.
    """
    if _is_sqlite():
        with op.batch_alter_table(_TABLE, recreate="always") as batch:
            batch.drop_constraint(_NEW, type_="unique")
            batch.create_unique_constraint(
                _OLD, ["product_id", "ratio", "format"]
            )
        return

    op.drop_constraint(_NEW, _TABLE, type_="unique")
    op.create_unique_constraint(_OLD, _TABLE, ["product_id", "ratio", "format"])
