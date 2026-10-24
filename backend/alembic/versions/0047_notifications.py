"""Add notifications table for in-app, serverless-safe polling notifications.

Revision ID: 0047_notifications
Revises: 0046_user_wishlist_items
Create Date: 2026-10-24
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "0047_notifications"
down_revision: Union[str, None] = "0046_user_wishlist_items"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "notifications" not in insp.get_table_names():
        op.create_table(
            "notifications",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column(
                "recipient_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("type", sa.String(length=50), nullable=False, server_default="system"),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("body", sa.Text(), nullable=False, server_default=""),
            sa.Column("link", sa.String(length=500), nullable=True),
            sa.Column("data_json", sa.Text(), nullable=True),
            sa.Column("read_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_notifications_id", "notifications", ["id"])
        op.create_index("ix_notifications_recipient_user_id", "notifications", ["recipient_user_id"])
        op.create_index("ix_notifications_created_at", "notifications", ["created_at"])
        op.create_index(
            "ix_notifications_recipient_read",
            "notifications",
            ["recipient_user_id", "read_at"],
        )
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'confit_app_rw') THEN
                        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE notifications TO confit_app_rw;
                        GRANT USAGE, SELECT, UPDATE ON SEQUENCE notifications_id_seq TO confit_app_rw;
                    END IF;
                END $$;
                """
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "notifications" in insp.get_table_names():
        op.drop_index("ix_notifications_recipient_read", table_name="notifications")
        op.drop_index("ix_notifications_created_at", table_name="notifications")
        op.drop_index("ix_notifications_recipient_user_id", table_name="notifications")
        op.drop_index("ix_notifications_id", table_name="notifications")
        op.drop_table("notifications")
