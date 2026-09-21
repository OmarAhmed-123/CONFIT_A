"""Brand memberships and tenant-scoped atomic audit; additive rollout.

Apply with the migration role BEFORE deploying code that reads memberships.
Existing BrandProfile.user_id remains authoritative legacy owner linkage.
Downgrade retains audit content but removes its tenant index/column; invitations
and secondary memberships are lost, so export them before an intentional revert.
"""
from alembic import op
import sqlalchemy as sa

revision = '0019_brand_membership_atomic_audit'
down_revision = '0018_outfit_share_lifecycle'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('brand_memberships',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('brand_id', sa.Integer(), sa.ForeignKey('brand_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('role', sa.String(30), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('brand_id', 'user_id', name='uq_brand_membership_pair'),
        sa.UniqueConstraint('user_id', name='uq_brand_membership_user'),
        sa.CheckConstraint("role IN ('owner','manager','staff','analyst','catalog_editor')", name='ck_brand_membership_role'))
    op.create_index('ix_brand_membership_brand_id', 'brand_memberships', ['brand_id', 'id'])
    op.create_table('brand_invitations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('brand_id', sa.Integer(), sa.ForeignKey('brand_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('role', sa.String(30), nullable=False),
        sa.Column('token_hash', sa.String(64), unique=True, nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('invited_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('owner','manager','staff','analyst','catalog_editor')", name='ck_brand_invitation_role'),
        sa.CheckConstraint("status IN ('pending','accepted','revoked','expired')", name='ck_brand_invitation_status'))
    op.create_index('ix_brand_invitation_brand_id', 'brand_invitations', ['brand_id', 'id'])
    # Timestamp is copied, not generated: repeat rehearsals have deterministic data.
    op.execute("INSERT INTO brand_memberships (brand_id,user_id,role,created_at) SELECT id,user_id,'owner',created_at FROM brand_profiles ORDER BY id")
    op.add_column('audit_logs', sa.Column('brand_id', sa.Integer(), nullable=True))
    op.create_index('ix_audit_logs_brand_id', 'audit_logs', ['brand_id'])
    # Only newly tenant-scoped partner events are covered. Do not pretend this
    # retroactively makes all historic/admin audit paths immutable or atomic.
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("""CREATE FUNCTION confit_provision_brand_owner() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          INSERT INTO brand_memberships (brand_id,user_id,role,created_at)
          VALUES (NEW.id,NEW.user_id,'owner',NEW.created_at)
          ON CONFLICT (brand_id,user_id) DO NOTHING;
          RETURN NEW;
        END; $$""")
        op.execute('CREATE TRIGGER provision_brand_owner AFTER INSERT ON brand_profiles FOR EACH ROW EXECUTE FUNCTION confit_provision_brand_owner()')
        op.execute("""CREATE FUNCTION confit_protect_partner_audit() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.brand_id IS NOT NULL THEN RAISE EXCEPTION 'partner audit events are append-only'; END IF;
          IF TG_OP = 'UPDATE' THEN RETURN NEW; END IF;
          RETURN OLD;
        END; $$""")
        op.execute("CREATE TRIGGER protect_partner_audit BEFORE UPDATE OR DELETE ON audit_logs FOR EACH ROW EXECUTE FUNCTION confit_protect_partner_audit()")


def downgrade():
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('DROP TRIGGER provision_brand_owner ON brand_profiles')
        op.execute('DROP FUNCTION confit_provision_brand_owner()')
        op.execute('DROP TRIGGER protect_partner_audit ON audit_logs')
        op.execute('DROP FUNCTION confit_protect_partner_audit()')
    op.drop_index('ix_audit_logs_brand_id', table_name='audit_logs')
    with op.batch_alter_table('audit_logs') as batch:
        batch.drop_column('brand_id')
    op.drop_table('brand_invitations')
    op.drop_table('brand_memberships')
