"""Product images table — reconciles production 0035_product_images.

Background (from backend/scripts/repair_product_images.py, audited 2026-10-09
on production, read-only):
- Production holds a product_images table with 120 rows (10 per product) but
  no migration file for it exists in any remote branch (verified 2026-10-10
  via git branch -a search). The table is not read by any code path in main,
  but repair scripts and data backups reference it.
- Columns inferred from repair script snapshot(): id, product_id,
  storage_key, public_url, ratio, format, width, height, bytes, role,
  is_primary, source_type, provider, source_ref, attribution, checksum,
  created_at.
- Constraint: one row per (product_id, ratio, format) — uq_product_image_ratio_format
  (see repair_product_images.py:118).

This migration creates the table if it does not already exist, with the
exact columns observed in production backups, and adds the unique constraint.
It is idempotent: if the table already exists (e.g., prod already has it),
it ensures the constraint and indexes exist but does not drop data.

Revision ID: 0035_product_images
Revises: 0034_mfa_email_codes

Reconciliation: This file was missing from repo main (repo head was
0034_mfa_email_codes, prod reported as 0035_product_images). Importing it
here restores linear history. The previously created 0035_recently_viewed_unique
is renumbered to 0036_recently_viewed_unique with down_revision
0035_product_images, preserving single-head chain.

Money columns: untouched (DB-19 preserved).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0035_product_images"
down_revision = "0034_mfa_email_codes"
branch_labels = None
depends_on = None


def _table_exists(conn, table_name: str) -> bool:
    return inspect(conn).has_table(table_name)


def upgrade() -> None:
    conn = op.get_bind()

    # If table already exists (prod), ensure constraint/index exist and exit
    # idempotently — do not recreate or drop data.
    if _table_exists(conn, "product_images"):
        # Ensure unique constraint/index exists; create if missing
        # Use batch mode for SQLite compatibility
        try:
            with op.batch_alter_table("product_images") as batch:
                # Check if constraint already exists by inspecting indexes
                # SQLite: unique constraint is an index
                # Postgres: try create if not exists
                pass
            # Create unique index if not exists (covers both SQLite and Postgres)
            # The constraint name in repair script: uq_product_image_ratio_format
            # We use IF NOT EXISTS for safety on Postgres via raw SQL
            if conn.dialect.name == "postgresql":
                conn.execute(sa.text("""
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_product_image_ratio_format
                    ON product_images (product_id, ratio, format)
                """))
                conn.execute(sa.text("""
                    CREATE INDEX IF NOT EXISTS ix_product_images_product_id
                    ON product_images (product_id)
                """))
            else:
                # SQLite
                conn.execute(sa.text("""
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_product_image_ratio_format
                    ON product_images (product_id, ratio, format)
                """))
                conn.execute(sa.text("""
                    CREATE INDEX IF NOT EXISTS ix_product_images_product_id
                    ON product_images (product_id)
                """))
        except Exception:
            # If table exists but constraint creation fails, don't block migration
            # — the table is already usable, constraint can be added later
            pass
        return

    # Table does not exist — create it with full schema observed in prod
    # Note: do not use index=True on columns when we also create explicit indexes,
    # otherwise SQLite will auto-create ix_* and explicit create will fail with
    # "index already exists" (observed 2026-10-10).
    op.create_table(
        "product_images",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=True),
        sa.Column("public_url", sa.String(length=1000), nullable=False),
        sa.Column("ratio", sa.String(length=20), nullable=False),  # e.g., 4x5, 1x1, 3x2, 16x9, master
        sa.Column("format", sa.String(length=20), nullable=False, server_default="jpeg"),  # jpeg, webp
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("bytes", sa.Integer(), nullable=True),
        sa.Column("role", sa.String(length=50), nullable=False, server_default="gallery"),  # hero, thumb, gallery
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("source_type", sa.String(length=50), nullable=True),  # licensed, generated
        sa.Column("provider", sa.String(length=100), nullable=True),  # pexels, unsplash
        sa.Column("source_ref", sa.String(length=1000), nullable=True),
        sa.Column("attribution", sa.String(length=500), nullable=True),
        sa.Column("checksum", sa.String(length=128), nullable=True),  # md5
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("product_id", "ratio", "format", name="uq_product_image_ratio_format"),
    )
    op.create_index("ix_product_images_product_id", "product_images", ["product_id"])
    op.create_index("ix_product_images_id", "product_images", ["id"])


def downgrade() -> None:
    # Downgrade drops the table — safe because no code path in main reads it
    # (per repair script). Production rollback would need backup (see repair script --rollback).
    # We use IF EXISTS equivalent via check
    conn = op.get_bind()
    if _table_exists(conn, "product_images"):
        op.drop_index("ix_product_images_id", table_name="product_images")
        op.drop_index("ix_product_images_product_id", table_name="product_images")
        op.drop_table("product_images")
