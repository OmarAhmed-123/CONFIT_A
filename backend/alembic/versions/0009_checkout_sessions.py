"""Checkout sessions persistence + inventory expiry hardening

Revision ID: 0009_checkout_sessions
Revises: 0008_group5_commerce
Create Date: 2026-09-02

Implements durable checkout session persistence (C2) and ensures inventory_reservations
has proper indexes for expiry cleanup. Previously checkout/sessions endpoints generated
tokens but never persisted them (dead code, always 404). This migration creates the
checkout_sessions table with ownership, cart snapshot, expiry, and authorization.

Idempotent inspector-guarded - fresh SQLite dev DBs via Base.metadata.create_all() already
have the table and will no-op.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "0009_checkout_sessions"
down_revision: Union[str, None] = "0008_group5_commerce"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables(bind) -> set:
    return set(inspect(bind).get_table_names())


def _columns(bind, table: str) -> set:
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def _indexes(bind, table: str) -> set:
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {idx["name"] for idx in insp.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    # Checkout sessions table - C2 Fix: durable persistence
    if "checkout_sessions" not in tables:
        op.create_table(
            "checkout_sessions",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("token", sa.String(length=100), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("guest_email", sa.String(length=255), nullable=True),
            sa.Column("guest_session_token", sa.String(length=100), nullable=True),
            sa.Column("cart_snapshot_json", sa.Text(), nullable=False),
            sa.Column("total_amount", sa.Float(), nullable=False),
            sa.Column("currency", sa.String(length=10), nullable=False),
            sa.Column("promo_code", sa.String(length=50), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="SET NULL"), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("converted_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_checkout_sessions_id", "checkout_sessions", ["id"])
        op.create_index("ix_checkout_sessions_token", "checkout_sessions", ["token"], unique=True)
        op.create_index("ix_checkout_sessions_guest_session_token", "checkout_sessions", ["guest_session_token"])
        op.create_index("ix_checkout_sessions_user", "checkout_sessions", ["user_id"])
        op.create_index("ix_checkout_sessions_expires", "checkout_sessions", ["expires_at"])
        op.create_index("ix_checkout_sessions_status", "checkout_sessions", ["status"])

    # Ensure inventory_reservations has indexes needed for expiry cleanup
    if "inventory_reservations" in tables:
        existing_idx = _indexes(bind, "inventory_reservations")
        if "ix_inventory_reservations_status_created" not in existing_idx:
            try:
                op.create_index(
                    "ix_inventory_reservations_status_created",
                    "inventory_reservations",
                    ["status", "created_at"],
                )
            except Exception:
                pass

    # Ensure carts has index for session_token (used in merge)
    if "carts" in tables:
        existing_idx = _indexes(bind, "carts")
        if "ix_carts_session_token" not in existing_idx and "session_token" in _columns(bind, "carts"):
            try:
                op.create_index("ix_carts_session_token", "carts", ["session_token"])
            except Exception:
                pass


def downgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    if "checkout_sessions" in tables:
        op.drop_table("checkout_sessions")

    # Drop the additional index if exists
    if "inventory_reservations" in tables:
        existing_idx = _indexes(bind, "inventory_reservations")
        if "ix_inventory_reservations_status_created" in existing_idx:
            op.drop_index("ix_inventory_reservations_status_created", table_name="inventory_reservations")
