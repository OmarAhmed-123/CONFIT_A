"""FLOW E lineage: wardrobe_items.source_order_item_id

Revision ID: 0015_wardrobe_purchase_lineage
Revises: 0014_analytics_order_item_lineage
Create Date: 2026-09-04

Why
---
A completed purchase never reached the customer's wardrobe (G5 -> G4 was a
documented contract with zero implementation: no code path, no column, no
test). Adding the synchronisation without a durable idempotency key would make
every retry / webhook re-delivery / backfill insert a *second* copy of the same
piece, and the only existing guard (``uq_wardrobe_items_user_image_hash``) does
not apply because catalogue-derived items carry no uploaded image hash.

What this migration does
------------------------
1. Adds ``wardrobe_items.source_order_item_id``
   (nullable, FK -> order_items.id ON DELETE SET NULL, indexed).
2. Adds the unique index ``uq_wardrobe_items_source_order_item
   (source_order_item_id)``: at most ONE wardrobe item per purchased order
   line, enforced by the database rather than by application discipline.
   NULLs (uploaded / manually added items) are distinct in unique indexes on
   both PostgreSQL and SQLite, so the manual wardrobe paths are unaffected.

Safety
------
* Additive: no column is dropped or narrowed, no row is deleted or rewritten.
* No backfill: historical orders are NOT retro-synchronised here. Backfilling
  would invent wardrobe contents the customer never asked for and would have
  to guess attribution for orders whose items were returned; the service-level
  sync is idempotent, so an explicit operator-triggered backfill can be run
  later against this same key with no risk of duplicates.
* Downgrade drops the unique index, the plain index and the column
  (batch mode for SQLite). Wardrobe items created by the sync survive as
  ordinary items — only their purchase lineage is lost.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "0015_wardrobe_purchase_lineage"
down_revision: Union[str, None] = "0014_analytics_order_item_lineage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "wardrobe_items"
COLUMN = "source_order_item_id"
FK_NAME = "fk_wardrobe_items_source_order_item_id"
IDX_NAME = "ix_wardrobe_items_source_order_item_id"
UQ_NAME = "uq_wardrobe_items_source_order_item"


def _tables(bind) -> set:
    return set(inspect(bind).get_table_names())


def _columns(bind, table: str) -> set:
    return {c["name"] for c in inspect(bind).get_columns(table)}


def _indexes(bind, table: str) -> set:
    insp = inspect(bind)
    names = {i["name"] for i in insp.get_indexes(table)}
    # On PostgreSQL a UniqueConstraint surfaces as a unique index; on SQLite
    # it can surface through get_unique_constraints instead. Accept either so
    # the migration is idempotent on both dialects.
    try:
        names |= {u["name"] for u in insp.get_unique_constraints(table)}
    except Exception:  # pragma: no cover - dialect without the accessor
        pass
    return names


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    if TABLE not in tables:
        raise RuntimeError(
            f"[0015] {TABLE} does not exist — chain is broken before 0004; refusing to continue"
        )
    if "order_items" not in tables:
        raise RuntimeError(
            "[0015] order_items does not exist — chain is broken before 0008; refusing to continue"
        )

    if COLUMN not in _columns(bind, TABLE):
        with op.batch_alter_table(TABLE) as batch:
            batch.add_column(sa.Column(COLUMN, sa.Integer(), nullable=True))
            batch.create_foreign_key(FK_NAME, "order_items", [COLUMN], ["id"], ondelete="SET NULL")
        print(f"[0015] Added {TABLE}.{COLUMN}")
    else:
        print(f"[0015] {TABLE}.{COLUMN} already present — skipping add")

    existing = _indexes(bind, TABLE)
    if IDX_NAME not in existing:
        op.create_index(IDX_NAME, TABLE, [COLUMN])
    if UQ_NAME not in existing:
        # A pre-existing duplicate source_order_item_id would make this fail
        # loudly. That is intended: two wardrobe rows claiming the same
        # purchased line is exactly the defect this constraint exists to make
        # impossible, and it must be investigated rather than hidden.
        op.create_index(UQ_NAME, TABLE, [COLUMN], unique=True)
    print("[0015] Indexes ensured")


def downgrade() -> None:
    bind = op.get_bind()
    if TABLE not in _tables(bind):
        return
    existing = _indexes(bind, TABLE)
    if UQ_NAME in existing:
        op.drop_index(UQ_NAME, table_name=TABLE)
    if IDX_NAME in existing:
        op.drop_index(IDX_NAME, table_name=TABLE)
    if COLUMN in _columns(bind, TABLE):
        with op.batch_alter_table(TABLE) as batch:
            if bind.dialect.name != "sqlite":
                batch.drop_constraint(FK_NAME, type_="foreignkey")
            batch.drop_column(COLUMN)
    print(f"[0015] Dropped {TABLE}.{COLUMN} (purchase lineage lost; wardrobe items retained)")
