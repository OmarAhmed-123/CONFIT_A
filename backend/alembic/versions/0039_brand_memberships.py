"""0039 · brand_memberships + brand_invitations (BRD-02 · spec 005 · #150 residue).

WHY: the tenant link was 1:1 (``brand_profiles.user_id UNIQUE``); multiple staff
per brand, invitations, and last-owner protection are impossible without real
membership rows. This migration ADDS two tables, keeps ``brand_profiles.user_id``
untouched as the founder anchor/legacy fallback, and back-fills one ``owner``
membership per existing profile so every current single-owner brand keeps its
access unchanged (the service resolves membership first, legacy profile second).

Single-head chain: 0038_vton_job_retention -> 0039_brand_memberships.
Additive only (new tables, new indexes, backfill insert). Safe to apply to
production BEFORE deploy (the documented 2026-09-20 ordering lesson).

Revision ID: 0039_brand_memberships
Revises: 0038_vton_job_retention
Create Date: 2026-10-18
"""

from alembic import op
import sqlalchemy as sa

revision = "0039_brand_memberships"
down_revision = "0038_vton_job_retention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "brand_memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("brand_id", sa.Integer(),
                  sa.ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default="active"),
        sa.Column("granted_by", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("brand_id", "user_id", name="uq_brand_membership_brand_user"),
    )
    op.create_index("ix_brand_memberships_brand_id", "brand_memberships", ["brand_id"])
    op.create_index("ix_brand_memberships_user_id", "brand_memberships", ["user_id"])
    # At most one ACTIVE membership row per (brand, user). The full pair stays
    # unique so a revoked user can be re-granted; this index stops two live
    # rows for the same person/brand under any concurrency.
    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_brand_memberships_active "
        "ON brand_memberships (brand_id, user_id) WHERE status = 'active'"
    ))

    op.create_table(
        "brand_invitations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("brand_id", sa.Integer(),
                  sa.ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        # SHA-256 hex of the raw token; the raw token is never stored.
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default="pending"),
        sa.Column("invited_by", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("accepted_by", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("token_hash", name="uq_brand_invitations_token_hash"),
    )
    op.create_index("ix_brand_invitations_brand_id", "brand_invitations", ["brand_id"])
    op.create_index("ix_brand_invitations_email", "brand_invitations", ["email"])
    op.create_index("ix_brand_invitations_brand_status", "brand_invitations",
                    ["brand_id", "status"])
    # Exactly one PENDING invitation per (brand, email): repeat requests are
    # idempotent reads, not new rows, under any race.
    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_brand_invitations_pending "
        "ON brand_invitations (brand_id, email) WHERE status = 'pending'"
    ))

    # ── Backfill: every existing 1:1 owner becomes an ACTIVE owner member ──
    # Idempotent by the (brand_id, user_id) unique constraint.
    op.execute(sa.text(
        "INSERT INTO brand_memberships (brand_id, user_id, role, status, created_at, updated_at) "
        "SELECT bp.id, bp.user_id, 'owner', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
        "FROM brand_profiles bp WHERE bp.user_id IS NOT NULL "
        "ON CONFLICT (brand_id, user_id) DO NOTHING"
    ))


def downgrade() -> None:
    # Drops the new tables; brand_profiles is untouched, so the pre-migration
    # single-owner model keeps working (owner-fallback path).
    op.drop_index("uq_brand_invitations_pending", table_name="brand_invitations")
    op.drop_index("ix_brand_invitations_brand_status", table_name="brand_invitations")
    op.drop_index("ix_brand_invitations_email", table_name="brand_invitations")
    op.drop_index("ix_brand_invitations_brand_id", table_name="brand_invitations")
    op.drop_table("brand_invitations")
    op.drop_index("uq_brand_memberships_active", table_name="brand_memberships")
    op.drop_index("ix_brand_memberships_user_id", table_name="brand_memberships")
    op.drop_index("ix_brand_memberships_brand_id", table_name="brand_memberships")
    op.drop_table("brand_memberships")
