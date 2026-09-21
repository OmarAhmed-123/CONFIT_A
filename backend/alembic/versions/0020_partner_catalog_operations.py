"""Product archive, durable import work and private asset metadata.

No binary media is stored in the database. Payload_json holds bounded catalog
business rows and a durable cursor, not an in-memory background task.
"""
from alembic import op
import sqlalchemy as sa
revision = '0020_partner_catalog_operations'
down_revision = '0019_brand_membership_atomic_audit'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('brand_profiles', sa.Column('is_test', sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table('products') as batch:
        batch.add_column(sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))
        batch.create_check_constraint('ck_product_archive_hidden', 'archived_at IS NULL OR is_active = false')
        batch.create_index('ix_product_brand_cursor', ['brand_id', 'id'])
    op.create_table('product_assets',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('brand_id', sa.Integer(), sa.ForeignKey('brand_profiles.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('object_key', sa.String(500), unique=True, nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False),
        sa.Column('byte_size', sa.Integer(), nullable=False),
        sa.Column('state', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("state IN ('upload_pending','active','delete_pending','deleted')", name='ck_product_asset_state'))
    op.create_index('ix_product_asset_brand_state','product_assets',['brand_id','state'])
    op.create_table('catalog_import_work',
        sa.Column('job_id',sa.Integer(),sa.ForeignKey('catalog_import_jobs.id',ondelete='CASCADE'),primary_key=True),
        sa.Column('brand_id',sa.Integer(),sa.ForeignKey('brand_profiles.id',ondelete='CASCADE'),nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='SET NULL'),nullable=True),
        sa.Column('idempotency_key',sa.String(100),nullable=False),
        sa.Column('payload_hash',sa.String(64),nullable=False),
        sa.Column('payload_json',sa.Text(),nullable=False),
        sa.Column('cursor',sa.Integer(),nullable=False),
        sa.Column('attempts',sa.Integer(),nullable=False),
        sa.Column('next_attempt_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('brand_id','idempotency_key',name='uq_catalog_work_idempotency'),
        sa.CheckConstraint('cursor >= 0 AND attempts >= 0',name='ck_catalog_work_progress'))
    op.create_index('ix_catalog_work_retry','catalog_import_work',['next_attempt_at','job_id'])


def downgrade():
    with op.batch_alter_table('brand_profiles') as batch:
        batch.drop_column('is_test')
    # Hidden products stay hidden when archive metadata is removed.
    op.drop_table('catalog_import_work')
    op.drop_table('product_assets')
    with op.batch_alter_table('products') as batch:
        batch.drop_index('ix_product_brand_cursor')
        batch.drop_constraint('ck_product_archive_hidden',type_='check')
        batch.drop_column('archived_at')
