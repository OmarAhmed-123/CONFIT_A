"""Group 1 remediation delta: OAuth linking columns, refresh-token,
password-reset, email-verification, MFA backup codes, mood boards,
extended consent columns on user_style_profiles.

Revision ID: 0002_group1_remediation
Revises: 0001_baseline
Create Date: 2026-08-29 21:15:00.000000

Idempotent: uses `IF NOT EXISTS` semantics via inspector checks so it
can run against a fresh database created from the baseline OR against
a legacy database created by the pre-Group-1 create_all path (where
some columns already exist).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "0002_group1_remediation"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(bind, table: str, column: str) -> bool:
    insp = inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def _has_table(bind, table: str) -> bool:
    return inspect(bind).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()

    # ---- users: OAuth provider linkage ------------------------------------
    if _has_table(bind, "users"):
        with op.batch_alter_table("users") as batch:
            if not _has_column(bind, "users", "oauth_provider"):
                batch.add_column(sa.Column("oauth_provider", sa.String(50), nullable=True))
            if not _has_column(bind, "users", "oauth_subject"):
                batch.add_column(sa.Column("oauth_subject", sa.String(255), nullable=True))
        # Indexes — separate so batch_alter_table above can stay short
        try:
            op.create_index("ix_users_oauth_provider", "users", ["oauth_provider"])
        except Exception:
            pass
        try:
            op.create_index("ix_users_oauth_subject", "users", ["oauth_subject"])
        except Exception:
            pass

    # ---- user_style_profiles: consent columns -----------------------------
    if _has_table(bind, "user_style_profiles"):
        with op.batch_alter_table("user_style_profiles") as batch:
            for name, coltype, default in (
                ("consent_ai_personalization", sa.Boolean(), True),
                ("consent_marketing_analytics", sa.Boolean(), False),
                ("consent_policy_version", sa.Integer(), 3),
                ("consent_last_agreed_at", sa.DateTime(), None),
            ):
                if not _has_column(bind, "user_style_profiles", name):
                    kwargs = {"nullable": True}
                    if default is not None:
                        # Portable defaults: sa.true()/sa.false() render as
                        # TRUE/FALSE on Postgres and 1/0 on SQLite. Using
                        # sa.text("1") for a Boolean column failed on real
                        # Postgres (DatatypeMismatch: default of type integer)
                        # and blocked the entire migration chain — so Group 4
                        # (0004/0005) could never reach production. Discovered
                        # during Neon deployment verification.
                        if isinstance(coltype, sa.Boolean):
                            kwargs["server_default"] = sa.true() if default is True else sa.false()
                        else:
                            kwargs["server_default"] = sa.text(str(default))
                    batch.add_column(sa.Column(name, coltype, **kwargs))

    # ---- refresh_tokens ---------------------------------------------------
    if not _has_table(bind, "refresh_tokens"):
        op.create_table(
            "refresh_tokens",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("jti", sa.String(64), nullable=False, unique=True, index=True),
            sa.Column("family_id", sa.String(64), nullable=False, index=True),
            sa.Column("issued_at", sa.DateTime(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("last_used_at", sa.DateTime(), nullable=True),
            sa.Column("replaced_by_jti", sa.String(64), nullable=True),
            sa.Column("user_agent", sa.String(500), nullable=True),
            sa.Column("ip_address", sa.String(50), nullable=True),
        )
        op.create_index("ix_refresh_tokens_user_active", "refresh_tokens", ["user_id", "revoked_at"])

    # ---- password_reset_tokens --------------------------------------------
    if not _has_table(bind, "password_reset_tokens"):
        op.create_table(
            "password_reset_tokens",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("token_hash", sa.String(128), nullable=False, unique=True, index=True),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("used_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    # ---- email_verification_tokens ----------------------------------------
    if not _has_table(bind, "email_verification_tokens"):
        op.create_table(
            "email_verification_tokens",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("token_hash", sa.String(128), nullable=False, unique=True, index=True),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("used_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    # ---- mfa_backup_codes -------------------------------------------------
    if not _has_table(bind, "mfa_backup_codes"):
        op.create_table(
            "mfa_backup_codes",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("code_hash", sa.String(255), nullable=False),
            sa.Column("used_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    # ---- mood_boards & items ---------------------------------------------
    if not _has_table(bind, "mood_boards"):
        op.create_table(
            "mood_boards",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("profile_id", sa.Integer(), sa.ForeignKey("user_style_profiles.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    if not _has_table(bind, "mood_board_items"):
        op.create_table(
            "mood_board_items",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("board_id", sa.Integer(), sa.ForeignKey("mood_boards.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("kind", sa.String(30), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    for tbl in ("mood_board_items", "mood_boards", "mfa_backup_codes",
                "email_verification_tokens", "password_reset_tokens", "refresh_tokens"):
        if _has_table(bind, tbl):
            op.drop_table(tbl)
    if _has_table(bind, "user_style_profiles"):
        with op.batch_alter_table("user_style_profiles") as batch:
            for name in ("consent_last_agreed_at", "consent_policy_version",
                         "consent_marketing_analytics", "consent_ai_personalization"):
                if _has_column(bind, "user_style_profiles", name):
                    batch.drop_column(name)
    if _has_table(bind, "users"):
        # SQLite batch-mode drop_column recreates the table and re-applies
        # reflected indexes — an index on a dropped column then fails with
        # "no such column". Drop the OAuth indexes first (Postgres would have
        # cascaded them automatically; SQLite will not).
        existing_indexes = {idx["name"] for idx in inspect(bind).get_indexes("users")}
        for idx_name in ("ix_users_oauth_subject", "ix_users_oauth_provider"):
            if idx_name in existing_indexes:
                op.drop_index(idx_name, table_name="users")
        with op.batch_alter_table("users") as batch:
            for name in ("oauth_subject", "oauth_provider"):
                if _has_column(bind, "users", name):
                    batch.drop_column(name)
