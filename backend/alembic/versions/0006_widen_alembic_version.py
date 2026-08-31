"""widen alembic_version.version_num for descriptive revision ids

Revision ID: 0006_widen_alembic_version
Revises: 0005_group4_wardrobe_dedup_integrity
Create Date: 2026-08-31

Alembic auto-creates the ``alembic_version`` table with
``version_num VARCHAR(32)`` by default. Descriptive revision ids like
``0005_group4_wardrobe_dedup_integrity`` (36 chars) do not fit and cause
``StringDataRightTruncation`` errors when Alembic tries to record the
current head after applying that migration on PostgreSQL.

Fresh SQLite dev databases were unaffected because Alembic's SQLite
compat layer stores VARCHAR without a length limit — the failure only
surfaced on the real Postgres deployment.

This migration widens the column to VARCHAR(255) so it can hold the
longer names going forward. It is a no-op on databases where the column
is already at that width (idempotent).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_widen_alembic_version"
down_revision: Union[str, None] = "0005_group4_wardrobe_dedup_integrity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _current_length(bind) -> int | None:
    """Return current character_maximum_length of alembic_version.version_num,
    or None if the column doesn't exist (should never happen at this point)."""
    dialect = bind.dialect.name
    if dialect == "sqlite":
        return None  # SQLite ignores VARCHAR length; nothing to do
    row = bind.execute(
        sa.text(
            "SELECT character_maximum_length FROM information_schema.columns "
            "WHERE table_name='alembic_version' AND column_name='version_num'"
        )
    ).fetchone()
    return row[0] if row else None


def upgrade() -> None:
    bind = op.get_bind()
    current = _current_length(bind)
    if current is None:
        return  # SQLite — VARCHAR length is a no-op
    if current >= 255:
        return  # already wide enough (idempotent)
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=current or 32),
        type_=sa.String(length=255),
        existing_nullable=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    # Narrowing is safe only if no existing revision id exceeds 32 chars,
    # otherwise it would break Alembic's own head tracking. Guard against
    # data loss: refuse to narrow when the current head no longer fits.
    row = bind.execute(sa.text("SELECT version_num FROM alembic_version")).fetchone()
    if row and len(row[0]) > 32:
        raise RuntimeError(
            f"Cannot downgrade alembic_version.version_num back to VARCHAR(32): "
            f"current head '{row[0]}' ({len(row[0])} chars) would not fit. "
            f"Downgrade the schema past this revision first."
        )
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=255),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
