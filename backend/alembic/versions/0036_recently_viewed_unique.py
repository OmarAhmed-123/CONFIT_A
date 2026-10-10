"""Recently-viewed dedup: unique (user_id, product_id) + upsert semantics.

WHY (DB-01 / CUS-14): recently_viewed had no uniqueness constraint, so
concurrent or repeated views created duplicate rows per (user, product),
causing UI jitter and wasted rows. The repository already implements
upsert in Python (query then update), but without a DB constraint a race
can still insert duplicates. This migration:

1. Deduplicates existing rows, keeping the most-recent viewed_at (and
   highest id as tie-breaker) per (user_id, product_id).
2. Adds a unique constraint uq_recently_viewed_user_product.

Revision ID: 0036_recently_viewed_unique
Revises: 0035_product_images

Reconciliation history:
- Originally authored as 0035_recently_viewed_unique (commit 46e9fc8) when
  prod 0035_product_images was UNVERIFIED and not found in any remote branch.
- On 2026-10-10, evidence from backend/scripts/repair_product_images.py
  (AUDITED_REVISION = 0035_product_images, snapshot of product_images table
  with 120 rows, audited on production 2026-10-09) confirmed prod DOES have
  product_images table. Per PROD_ALEMBIC_HEAD_CHECK_PROCEDURE.md Case B,
  the missing migration is now imported as 0035_product_images (idempotent,
  creates table if not exists, with uq_product_image_ratio_format), and this
  migration is renumbered to 0036 with down_revision 0035_product_images,
  preserving single-head linear history.
- Chain: 0034_mfa_email_codes -> 0035_product_images -> 0036_recently_viewed_unique

Money columns: untouched (DB-19 preserved).
"""

from alembic import op
import sqlalchemy as sa

revision = "0036_recently_viewed_unique"
down_revision = "0035_product_images"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Deduplicate: keep most-recent viewed_at per (user_id, product_id)
    # Use window function ROW_NUMBER which works on both PostgreSQL and
    # modern SQLite (>=3.25). Fallback to MAX(id) grouping if window not
    # supported (defensive).
    try:
        # Identify duplicate ids to delete (rn > 1)
        # First, find ids that are NOT the chosen keeper per group
        conn.execute(
            sa.text(
                """
                DELETE FROM recently_viewed
                WHERE id NOT IN (
                    SELECT keeper_id FROM (
                        SELECT id AS keeper_id,
                               ROW_NUMBER() OVER (
                                   PARTITION BY user_id, product_id
                                   ORDER BY viewed_at DESC, id DESC
                               ) AS rn
                        FROM recently_viewed
                    ) WHERE rn = 1
                )
                """
            )
        )
    except Exception:
        # Fallback: keep MAX(id) per group (deterministic, no window)
        conn.execute(
            sa.text(
                """
                DELETE FROM recently_viewed
                WHERE id NOT IN (
                    SELECT MAX(id) FROM recently_viewed GROUP BY user_id, product_id
                )
                """
            )
        )

    # 2. Add unique constraint. Use batch mode for SQLite compatibility.
    # SQLite does not support ADD CONSTRAINT directly; batch creates new table.
    with op.batch_alter_table("recently_viewed") as batch:
        batch.create_unique_constraint(
            "uq_recently_viewed_user_product", ["user_id", "product_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("recently_viewed") as batch:
        batch.drop_constraint(
            "uq_recently_viewed_user_product", type_="unique"
        )
