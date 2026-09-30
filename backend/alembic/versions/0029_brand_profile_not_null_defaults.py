"""Stop the database holding a brand profile the API cannot serialise.

THE DEFECT (found by live role testing on production, 2026-09-30)
-----------------------------------------------------------------
``GET /brand/profile`` (and its ``/partner/profile`` alias) returned
**HTTP 500** for a brand manager whose profile row had NULLs in
``commission_rate``, ``return_rate_benchmark``, ``current_return_rate`` or
``is_verified``. That is the brand's own portal landing call — the first
request the B2B dashboard makes.

Root cause is a mismatch between two contracts:

* ``BrandProfileOut`` declares ``commission_rate: int``,
  ``return_rate_benchmark: int``, ``current_return_rate: int`` and
  ``is_verified: bool`` — all NON-optional.
* ``models/user.BrandProfile`` declares them with ``default=15`` / ``28`` /
  ``11`` / ``True``, which are **Python-side ORM defaults with no
  ``nullable=False`` and no ``server_default``**.

A Python-side default only fires when the row is created through the ORM. Any
other writer — a catalogue/partner import, a migration backfill, an ops fix
applied in SQL, a bulk onboarding script — produces a perfectly valid database
row that the response model then refuses, and FastAPI turns the
ValidationError into a 500. The brand cannot open their portal, and the error
message names nothing they or support could act on.

Notably ``/brand/analytics`` kept returning 200 on the same row, because it
consumes the profile internally and never serialises it. So the failure was
endpoint-shaped, not data-shaped, which is what made it look like a fluke.

THE FIX
-------
Make the database enforce what the API contract already promises: backfill the
existing NULLs with the same values the ORM would have written, add
``server_default`` so every future writer gets them regardless of how the row
is created, then mark the columns ``NOT NULL``.

Order matters: backfill BEFORE the NOT NULL, or the ALTER fails on existing
rows. The defaults are copied from the model rather than re-invented, so the
database and the application cannot disagree about what a new brand starts on.

This is a constraint, not a behaviour change: no existing non-NULL value is
touched, and the ORM path keeps working exactly as before.

Revision: 0029_brand_profile_not_null_defaults
Revises:  0028_order_fx_lock
"""
import sqlalchemy as sa
from alembic import op

revision: str = "0029_brand_profile_not_null_defaults"
down_revision: str = "0028_order_fx_lock"
branch_labels = None
depends_on = None

#: Copied from models/user.BrandProfile so the two cannot drift.
_DEFAULTS = (
    ("commission_rate", "15", sa.Integer()),
    ("return_rate_benchmark", "28", sa.Integer()),
    ("current_return_rate", "11", sa.Integer()),
    ("is_verified", "true", sa.Boolean()),
)


def upgrade() -> None:
    # 1. Backfill FIRST — a NOT NULL added before this would fail on any
    #    existing row that was written outside the ORM.
    for column, default, _type in _DEFAULTS:
        op.execute(
            f"UPDATE brand_profiles SET {column} = {default} WHERE {column} IS NULL"
        )

    # 2. `batch_alter_table`, not a bare `alter_column`. PostgreSQL (the
    #    deployment engine) supports ALTER COLUMN directly, but SQLite — which
    #    the test suite migrates end-to-end — does not, and a bare alter_column
    #    fails there with `near "ALTER": syntax error`. Batch mode emits the
    #    native ALTER on PostgreSQL and the table-rebuild recipe on SQLite, so
    #    one migration is correct on both engines. Measured: 8 failures and 6
    #    errors in the audit-guard and schema-drift suites before this change.
    with op.batch_alter_table("brand_profiles") as batch:
        for column, default, type_ in _DEFAULTS:
            # server_default so EVERY writer gets the value, not just the ORM;
            # NOT NULL so the database can no longer hold a row the API
            # contract declares impossible.
            batch.alter_column(
                column,
                existing_type=type_,
                server_default=sa.text(default),
                nullable=False,
            )


def downgrade() -> None:
    with op.batch_alter_table("brand_profiles") as batch:
        for column, _default, type_ in _DEFAULTS:
            batch.alter_column(
                column,
                existing_type=type_,
                server_default=None,
                nullable=True,
            )
