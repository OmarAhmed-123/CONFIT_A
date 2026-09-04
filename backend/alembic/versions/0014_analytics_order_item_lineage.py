"""Item-grain attribution lineage: brand_analytics_events.order_item_id

Revision ID: 0014_analytics_order_item_lineage
Revises: 0013_migration_audit_and_quarantine
Create Date: 2026-09-03

Why
---
Purchase events were keyed only by (order_id, product_id, sku_id). Revenue
attribution therefore had to *reconstruct* the OrderItem a purchase event
accounts for, and item-level refunds could not be netted against the exact
item that was returned ("Brand A returned 300 / Brand B keeps 700").

What this migration does
------------------------
1. Adds ``brand_analytics_events.order_item_id``
   (nullable, FK -> order_items.id ON DELETE SET NULL, indexed).
2. Adds the unique index ``uq_brand_analytics_item_event (order_item_id,
   event_type)``: at most ONE purchase event and ONE return event per
   OrderItem. NULL order_item_id rows (views, impressions, clicks) never
   collide because NULLs are distinct in unique indexes on both PostgreSQL and
   SQLite.
3. Data migration — backfills ``order_item_id`` for existing purchase events
   ONLY where the (order_id, product_id, sku_id) triple resolves to exactly one
   OrderItem and that OrderItem has exactly one purchase event. Every event
   that cannot be resolved unambiguously is left NULL and recorded in
   ``migration_audit_log`` (action ``unresolved_lineage``) with the observed
   values, so the gap is visible instead of silently guessed.

Safety
------
* Additive: no column is dropped or narrowed; no row is deleted.
* Idempotent: every step checks for prior existence.
* Downgrade drops the two indexes and the column (batch mode for SQLite).
  Backfilled values are lost on downgrade — the audit rows remain.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision: str = "0014_analytics_order_item_lineage"
down_revision: Union[str, None] = "0013_migration_audit_and_quarantine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "brand_analytics_events"
COLUMN = "order_item_id"
FK_NAME = "fk_brand_analytics_events_order_item_id"
IDX_NAME = "ix_brand_analytics_order_item"
UQ_NAME = "uq_brand_analytics_item_event"


def _tables(bind) -> set:
    return set(inspect(bind).get_table_names())


def _columns(bind, table: str) -> set:
    return {c["name"] for c in inspect(bind).get_columns(table)}


def _indexes(bind, table: str) -> set:
    return {i["name"] for i in inspect(bind).get_indexes(table)}


def _backfill(bind) -> None:
    """Resolve order_item_id for legacy purchase events, unambiguous cases only."""
    events = bind.execute(text(
        f"SELECT id, event_id, order_id, product_id, sku_id, revenue_amount "
        f"FROM {TABLE} WHERE event_type = 'purchase' AND order_id IS NOT NULL AND {COLUMN} IS NULL"
    )).fetchall()
    if not events:
        print("[0014] No legacy purchase events to backfill")
        return

    resolved = 0
    unresolved = 0
    claimed_items: dict = {}
    for ev in events:
        ev_id, event_key, order_id, product_id, sku_id, revenue = ev
        params = {"order_id": order_id, "product_id": product_id}
        sku_clause = "product_sku_id = :sku_id" if sku_id is not None else "product_sku_id IS NULL"
        if sku_id is not None:
            params["sku_id"] = sku_id
        items = bind.execute(text(
            f"SELECT id, subtotal FROM order_items WHERE order_id = :order_id "
            f"AND product_id = :product_id AND {sku_clause}"
        ), params).fetchall()

        reason = None
        if len(items) == 0:
            reason = "no OrderItem matches (order_id, product_id, sku_id)"
        elif len(items) > 1:
            reason = f"{len(items)} OrderItems match (order_id, product_id, sku_id) — ambiguous"
        elif items[0][0] in claimed_items:
            reason = f"OrderItem {items[0][0]} already claimed by event {claimed_items[items[0][0]]}"

        if reason is None:
            item_id = items[0][0]
            bind.execute(text(
                f"UPDATE {TABLE} SET {COLUMN} = :item_id WHERE id = :ev_id"
            ), {"item_id": item_id, "ev_id": ev_id})
            claimed_items[item_id] = event_key
            resolved += 1
        else:
            unresolved += 1
            bind.execute(text(
                "INSERT INTO migration_audit_log (migration_revision, table_name, row_id, field_name, "
                "original_value, remediated_value, action, reason) VALUES "
                "('0014', :table, :row_id, :field, :observed, NULL, 'unresolved_lineage', :reason)"
            ), {
                "table": TABLE,
                "row_id": ev_id,
                "field": COLUMN,
                "observed": f"event_id={event_key} order_id={order_id} product_id={product_id} "
                            f"sku_id={sku_id} revenue_amount={revenue}",
                "reason": reason,
            })
    print(f"[0014] Backfill: resolved={resolved} unresolved={unresolved} (unresolved rows audited)")


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    if TABLE not in tables:
        raise RuntimeError(
            f"[0014] {TABLE} does not exist — chain is broken before 0010; refusing to continue"
        )
    if "migration_audit_log" not in tables:
        raise RuntimeError("[0014] migration_audit_log missing — 0013 did not apply; refusing to continue")

    if COLUMN not in _columns(bind, TABLE):
        with op.batch_alter_table(TABLE) as batch:
            batch.add_column(sa.Column(COLUMN, sa.Integer(), nullable=True))
            batch.create_foreign_key(FK_NAME, "order_items", [COLUMN], ["id"], ondelete="SET NULL")
        print(f"[0014] Added {TABLE}.{COLUMN}")

    _backfill(bind)

    existing = _indexes(bind, TABLE)
    if IDX_NAME not in existing:
        op.create_index(IDX_NAME, TABLE, [COLUMN])
    if UQ_NAME not in existing:
        # Any pre-existing duplicate (order_item_id, event_type) pair would make
        # this fail loudly — that is intended: duplicates mean double-counted
        # revenue and must be investigated, not hidden.
        op.create_index(UQ_NAME, TABLE, [COLUMN, "event_type"], unique=True)
    print("[0014] Indexes ensured")


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
    print(f"[0014] Dropped {TABLE}.{COLUMN} (backfilled lineage lost; audit rows retained)")
