"""Baseline: create every current CONFIT table from Base.metadata.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-29 21:00:00.000000

This baseline snapshots the current SQLAlchemy metadata after the Group 1
audit remediation. Deployments that already have a database created by
`Base.metadata.create_all()` should stamp this revision instead of
running it:

    PYTHONPATH=. alembic -c backend/alembic.ini stamp 0001_baseline

Fresh databases run the migration as normal:

    PYTHONPATH=. alembic -c backend/alembic.ini upgrade head

New migrations create/alter columns via explicit `op.*` calls; only this
baseline reflects from the metadata.
"""
from typing import Sequence, Union

from alembic import op

# Import the app metadata — same source of truth the runtime uses.
from backend.app.core.database import Base
import backend.app.models  # noqa: F401


revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
