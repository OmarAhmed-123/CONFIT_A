"""Email outbox table — idempotent templated-mail dispatch (spec 15).

WHY
---
The template system gives every transactional/engagement/marketing message
a contract (subject/preheader/html/text, EN+AR). What rendering alone cannot
give is DELIVERY truth: whether a given business event already produced a
send, and what the relay actually did. Without a durable event ledger a
replayed payment webhook or a retried worker would email the customer twice,
and a transport failure would vanish into a log line.

One row per event (``event_key`` UNIQUE = the idempotency guarantee), with
the spec's status contract: pending / sent / failed / bounced / unsubscribed.
Stores envelope facts only — recipient, template id, locale, outcome. Never
the rendered body, never credentials.

Revision: 0032_email_outbox
Revises:  0031_outfit_soft_delete
"""
import sqlalchemy as sa
from alembic import op

revision: str = "0032_email_outbox"
down_revision: str = "0031_outfit_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_key", sa.String(length=255), nullable=False),
        sa.Column("template", sa.String(length=64), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False, server_default="en"),
        sa.Column("recipient", sa.String(length=320), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message_id", sa.String(length=255), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_email_outbox_id", "email_outbox", ["id"])
    op.create_index("ix_email_outbox_event_key", "email_outbox", ["event_key"], unique=True)
    op.create_index("ix_email_outbox_status", "email_outbox", ["status"])


def downgrade() -> None:
    op.drop_index("ix_email_outbox_status", table_name="email_outbox")
    op.drop_index("ix_email_outbox_event_key", table_name="email_outbox")
    op.drop_index("ix_email_outbox_id", table_name="email_outbox")
    op.drop_table("email_outbox")
