"""Journal legacy partner-reported counters; not a verified billing ledger."""
from alembic import op
import sqlalchemy as sa
revision='0021_partner_counter_journal'
down_revision='0020_partner_catalog_operations'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('sponsored_placements',sa.Column('spend_day',sa.Date(),nullable=True))
    op.create_table('placement_counter_events',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('placement_id',sa.Integer(),sa.ForeignKey('sponsored_placements.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('brand_id',sa.Integer(),sa.ForeignKey('brand_profiles.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('kind',sa.String(20),nullable=False),
        sa.Column('key_hash',sa.String(64),nullable=False),
        sa.Column('amount',sa.Numeric(12,2),nullable=False),
        sa.Column('event_day',sa.Date(),nullable=False),
        sa.Column('response_json',sa.Text(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('placement_id','kind','key_hash',name='uq_placement_counter_event'),
        sa.CheckConstraint("kind IN ('impression','click')",name='ck_placement_counter_kind'),
        sa.CheckConstraint('amount >= 0',name='ck_placement_counter_amount'))
    op.create_index('ix_placement_counter_events_brand_id','placement_counter_events',['brand_id'])
    if op.get_bind().dialect.name=='postgresql':
        op.execute('CREATE TRIGGER protect_counter_event BEFORE UPDATE OR DELETE ON placement_counter_events FOR EACH ROW EXECUTE FUNCTION confit_protect_partner_audit()')


def downgrade():
    op.drop_table('placement_counter_events')
    with op.batch_alter_table('sponsored_placements') as batch:
        batch.drop_column('spend_day')
