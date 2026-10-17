"""Garment-asset gate metadata — ghost-hands remediation P0/P1.

WHY (2026-10-10): the production "ghost hands" render happened because an
on-model catalog photo was fed to the segmentation-free engine as a flat-lay.
The P0 gate blocks on-model products until a validated clean asset exists,
and the P1 prep pipeline records HOW each asset was classified
(photo_type + evidence) and whether it is tryon_ready. Existing rows
default to tryon_ready=False: an asset that was never validated must never
count as ready (fail closed).

Revision ID: 0035_garment_asset_gate
Revises: 0034_mfa_email_codes
"""

from alembic import op
import sqlalchemy as sa

revision = "0035_garment_asset_gate"
down_revision = "0034_mfa_email_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("garment_assets", sa.Column("photo_type", sa.String(length=24), nullable=True))
    op.add_column(
        "garment_assets",
        sa.Column("tryon_ready", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.add_column("garment_assets", sa.Column("clean_image_url", sa.Text(), nullable=True))
    op.add_column("garment_assets", sa.Column("classification_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("garment_assets", "classification_json")
    op.drop_column("garment_assets", "clean_image_url")
    op.drop_column("garment_assets", "tryon_ready")
    op.drop_column("garment_assets", "photo_type")
