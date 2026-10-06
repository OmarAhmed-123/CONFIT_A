"""Email preferences table — the consent store the outbox was waiting for.

WHY
---
Spec 15 §8 ("respect consent and unsubscribe") shipped half-done: the outbox
records 'unsubscribed' and the templates demand an unsubscribe_url for every
engagement/marketing message, but there was NO user-level store answering
"may I send this person this category?" — the documented gap in
``email_outbox.dispatch``. This table closes it.

One row per user (lazy-created), two booleans: engagement and marketing.
Transactional mail has no switch by design — order receipts, payment
failures and shipping notices are facts about the user's money, not
promotions. Unsubscribe links carry a signed, expiring token (HMAC, derived
key with a dedicated label) so one click works without a session and cannot
be forged for another user.

Revision: 0033_email_preferences
Revises:  0032_email_outbox
"""
import sqlalchemy as sa
from alembic import op

revision: str = "0033_email_preferences"
down_revision: str = "0032_email_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("engagement", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("marketing", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_email_preferences_id", "email_preferences", ["id"])
    op.create_index(
        "ix_email_preferences_user_id", "email_preferences", ["user_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_email_preferences_user_id", table_name="email_preferences")
    op.drop_index("ix_email_preferences_id", table_name="email_preferences")
    op.drop_table("email_preferences")
