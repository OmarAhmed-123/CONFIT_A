"""MFA email codes — the mailbox alternative for the two-factor step.

WHY (2026-10-06): the two-factor dialog offered only authenticator /
recovery codes; a shopper without their phone was locked out of their own
account. This table stores one-time 6-digit codes delivered by email:
hashed at rest (sha256), 10-minute expiry, single-use (atomic claim on
``used_at``), with a per-row failed-attempt counter so a live code cannot
be brute-forced.

Revision ID: 0034_mfa_email_codes
Revises: 0033_email_preferences
"""

from alembic import op
import sqlalchemy as sa

revision = "0034_mfa_email_codes"
down_revision = "0033_email_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mfa_email_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_mfa_email_codes_id", "mfa_email_codes", ["id"])
    op.create_index("ix_mfa_email_codes_user_id", "mfa_email_codes", ["user_id"])
    op.create_index("ix_mfa_email_codes_code_hash", "mfa_email_codes", ["code_hash"])


def downgrade() -> None:
    op.drop_index("ix_mfa_email_codes_code_hash", table_name="mfa_email_codes")
    op.drop_index("ix_mfa_email_codes_user_id", table_name="mfa_email_codes")
    op.drop_index("ix_mfa_email_codes_id", table_name="mfa_email_codes")
    op.drop_table("mfa_email_codes")
