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
    """Intentionally a no-op: the column stays VARCHAR(255).

    The previous downgrade narrowed ``version_num`` back to VARCHAR(32). Its
    guard checked the CURRENT head (``0006_widen_alembic_version``, 26 chars),
    passed, narrowed the column — and Alembic then immediately wrote the new
    head ``0005_group4_wardrobe_dedup_integrity`` (36 chars) into it, failing
    with StringDataRightTruncation. So on PostgreSQL the chain could never be
    downgraded below 0006 (found 2026-09-03 rehearsing ``downgrade base`` on
    PostgreSQL 17). A wider bookkeeping column is harmless; keeping it is the
    only downgrade that leaves Alembic able to track its own state.
    """
    return
