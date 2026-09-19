"""partner leads public request-demo workflow

Revision ID: 0018_partner_leads
Revises: 0017_audit_before_after_request_id
Create Date: 2026-09-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_partner_leads"
down_revision = "0017_audit_before_after_request_id"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "partner_leads" not in existing_tables:
        op.create_table(
        "partner_leads",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("contact_name", sa.String(length=255), nullable=False),
        sa.Column("work_email", sa.String(length=255), nullable=False),
        sa.Column("website", sa.String(length=500), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("monthly_order_volume", sa.String(length=50), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="received"),
        sa.Column("notification_status", sa.String(length=30), nullable=False, server_default="not_configured"),
        sa.Column("duplicate_of_id", sa.Integer(), sa.ForeignKey("partner_leads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_path", sa.String(length=255), nullable=False, server_default="/b2b"),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    existing_indexes = {ix["name"] for ix in inspector.get_indexes("partner_leads")} if "partner_leads" in set(sa.inspect(bind).get_table_names()) else set()
    for name, cols in {
        "ix_partner_leads_company_name": ["company_name"],
        "ix_partner_leads_work_email": ["work_email"],
        "ix_partner_leads_status": ["status"],
        "ix_partner_leads_duplicate_of_id": ["duplicate_of_id"],
        "ix_partner_leads_ip_hash": ["ip_hash"],
        "ix_partner_leads_email_created": ["work_email", "created_at"],
    }.items():
        if name not in existing_indexes:
            op.create_index(name, "partner_leads", cols)


def downgrade():
    bind = op.get_bind()
    if "partner_leads" not in set(sa.inspect(bind).get_table_names()):
        return
    op.drop_index("ix_partner_leads_email_created", table_name="partner_leads")
    op.drop_index("ix_partner_leads_ip_hash", table_name="partner_leads")
    op.drop_index("ix_partner_leads_duplicate_of_id", table_name="partner_leads")
    op.drop_index("ix_partner_leads_status", table_name="partner_leads")
    op.drop_index("ix_partner_leads_work_email", table_name="partner_leads")
    op.drop_index("ix_partner_leads_company_name", table_name="partner_leads")
    op.drop_table("partner_leads")
