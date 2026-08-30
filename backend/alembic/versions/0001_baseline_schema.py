"""baseline schema — full CONFIT metadata

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-30

Baseline strategy (G2-S1): the schema was historically created via
``Base.metadata.create_all`` at application startup, so existing databases
already hold these tables. To adopt Alembic WITHOUT destroying data:

  * Fresh database  -> ``alembic upgrade head`` creates everything.
  * Existing database -> ``alembic stamp 0001_baseline`` once (records the
    baseline as applied without re-creating tables), then ``alembic upgrade
    head`` applies subsequent revisions only.

``upgrade()`` creates only tables/indexes that do not already exist, so it is
safe to run against either state; ``downgrade()`` drops the full schema and
must never run against a populated production database.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from backend.app.core.database import Base

# Import all model modules so every table is registered on the metadata.
from backend.app.models import (  # noqa: F401
    user,
    profile,
    catalog,
    stylist,
    tryon,
    wardrobe,
    commerce,
    brand_analytics,
)

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            table.create(bind=bind)


def downgrade() -> None:
    # Destructive by definition: drops every application table. Intended for
    # clean test databases and rollback verification only.
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in existing:
            table.drop(bind=bind)
