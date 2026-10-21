"""0045 · brand_domains — prove a brand owns the host it imports images from.

WHY: the importer has two independent questions to answer about an image URL,
and it only answered one of them.

  * **Is it safe to fetch?** ``core/net_guard.py`` answers this: scheme, port,
    credentials, private/loopback/link-local/metadata addresses, and every
    redirect hop.
  * **Is this brand allowed to use it?** Nothing answered this. The only
    ownership control was a single deployment-wide boolean,
    ``CATALOG_IMPORT_ALLOW_OWN_IMAGES``, which says "first-party URLs may be
    fetched on this server" — not "THIS BRAND owns THAT host". With that flag
    on, any brand could point an import at any public host, including a
    competitor's CDN, and the platform would copy the competitor's photography
    into its own catalogue under the wrong brand.

Those are separate controls and this table is the second one. Passing one never
implies the other: a verified domain still goes through every net_guard check,
and a safe destination still has to belong to the brand.

WHAT A VERIFIED DOMAIN IS
-------------------------
An operator-verified claim that ``brand_id`` controls ``hostname``, proven by
publishing a random token in DNS (``confit-verify=<token>`` TXT). The token is
generated server-side and is not a secret the brand has to keep — it is a claim
in public DNS that only the domain's controller can make.

    brand_id        the owning brand (tenant isolation key)
    hostname        normalized ASCII hostname, no scheme, no port, no path
    status          pending | verified | revoked
    token           the DNS TXT value that proves control
    method          dns_txt (the only method implemented)
    last_checked_at   when verification was last attempted
    verified_at     when it succeeded
    revoked_at      when it stopped authorizing imports

CONSTRAINTS
-----------
``uq_brand_domain_hostname`` makes a hostname claimable by exactly ONE brand. Two
brands claiming the same host would make "who owns this image" undecidable, and
a shared-CDN situation is precisely when that question must have one answer.

No backfill: no brand holds a verified domain today, and inventing one from
``brand_profiles.website`` would be a fabricated ownership claim. Brands import
from the platform's licensed stock hosts until they verify their own.

Additive and reversible: one new table, nothing existing is touched. SQLite-safe
and PostgreSQL-safe (standard CREATE TABLE).

Revision ID: 0045_brand_verified_domains
Revises: 0044_product_price_provenance
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0045_brand_verified_domains"
down_revision: str = "0044_product_price_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "brand_domains",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "brand_id",
            sa.Integer(),
            sa.ForeignKey("brand_profiles.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("hostname", sa.String(length=253), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False, server_default="dns_txt"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("hostname", name="uq_brand_domain_hostname"),
        sa.CheckConstraint(
            "status IN ('pending', 'verified', 'revoked')",
            name="ck_brand_domain_status",
        ),
    )
    # The hot lookup is "is this hostname verified for this brand", so index the
    # pair rather than either column alone.
    op.create_index(
        "ix_brand_domain_brand_status", "brand_domains", ["brand_id", "status"],
        unique=False,
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'confit_app_rw') THEN
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE brand_domains TO confit_app_rw;
                    GRANT USAGE, SELECT, UPDATE ON SEQUENCE brand_domains_id_seq TO confit_app_rw;
                END IF;
            END $$;
        """))


def downgrade() -> None:
    op.drop_index("ix_brand_domain_brand_status", table_name="brand_domains")
    op.drop_table("brand_domains")
