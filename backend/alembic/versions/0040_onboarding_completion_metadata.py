"""0040 · onboarding completion metadata (Phase 0.2 · wizard-reappearing fix).

WHY: onboarding completion had no server-side record beyond the boolean
``user_style_profiles.onboarding_completed``. The client decided whether to
re-prompt from ``has_profile`` (the mere existence of a profile row), which is
True the moment the wizard saves *anything* — so a shopper who opened the
wizard and closed it was treated as "onboarded" by the API and as
"not onboarded" by the first-run gate, and the two disagreed on every fresh
session. This migration adds the missing state:

  * ``onboarding_completed_at`` — when the most recent COMPLETED submission
    landed (nullable).
  * ``onboarding_version``      — which wizard revision that submission
    satisfied (nullable).

BACKFILL POLICY (deliberate, and the honest half of this migration):
  * ``onboarding_version = 1`` is backfilled for rows already marked
    ``onboarding_completed``. Only wizard v1 has ever existed in production,
    so this is a recorded fact, not a guess.
  * ``onboarding_completed_at`` is intentionally LEFT NULL. The completion
    instant was never captured for pre-0040 rows; ``updated_at`` is not it
    (any later PATCH moves that), so filling it in would manufacture evidence
    the system does not have. Consumers must treat NULL as "completed, time
    unknown" and must not gate on the timestamp.

Both columns are additive and nullable, so this is safe to apply to production
BEFORE deploy (the documented 2026-09-20 ordering lesson).

Single-head chain: 0039_brand_memberships -> 0040_onboarding_completion_metadata.

Revision ID: 0040_onboarding_completion_metadata
Revises: 0039_brand_memberships
Create Date: 2026-10-19
"""

from alembic import op
import sqlalchemy as sa

revision = "0040_onboarding_completion_metadata"
down_revision = "0039_brand_memberships"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_style_profiles",
        sa.Column("onboarding_completed_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "user_style_profiles",
        sa.Column("onboarding_version", sa.Integer(), nullable=True),
    )

    # Version backfill only — see the BACKFILL POLICY note above for why the
    # timestamp stays NULL on legacy rows.
    op.execute(
        "UPDATE user_style_profiles "
        "SET onboarding_version = 1 "
        "WHERE onboarding_completed AND onboarding_version IS NULL"
    )


def downgrade() -> None:
    # SQLite cannot drop columns in place; batch mode rewrites the table.
    with op.batch_alter_table("user_style_profiles") as batch_op:
        batch_op.drop_column("onboarding_version")
        batch_op.drop_column("onboarding_completed_at")
