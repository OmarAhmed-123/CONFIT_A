"""0018: partner onboarding, invitations & transactional-email lifecycle.

Additive-only migration for the 2026-09-19 authentication/registration/
onboarding/email work:

  * ``users.registration_intent``  — what the registrant asked for. Data, never
    an authorization input; the role column remains the only privilege source
    and is still written exclusively by trusted server-side paths.
  * ``partner_applications``       — BRD G6 §2.2 "partner onboarding
    approvals": a consumer requests brand access, an admin decides.
  * ``invitations``                — BRD G6 §2.1 "user invitations": a brand
    owner/admin invites a colleague; role + brand are recorded server-side.
  * ``email_change_requests``      — two-step email change (verify ownership of
    the new address before it becomes the account address).
  * ``email_deliveries``           — the delivery ledger. There is no code path
    that reports "email sent" without a row here recording what the provider
    actually accepted (task §15/§33 honesty rule).

Idempotent (inspector-guarded, safe to replay) and reversible. No existing
column is altered and no row is rewritten, so old code keeps working against
the new schema and this migration is safe to run before the code deploy.

Revision: 0018_partner_onboarding_email_lifecycle
Revises:  0017_audit_before_after_request_id
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0018_partner_onboarding_email_lifecycle"
down_revision: str = "0017_audit_before_after_request_id"
branch_labels = None
depends_on = None

_TABLES = (
    "brand_members",
    "partner_applications",
    "invitations",
    "email_change_requests",
    "email_deliveries",
)

_INDEXES = (
    "uq_partner_applications_user_pending",
    "uq_invitations_pending_email_brand",
    "uq_email_change_open_user",
    "ix_partner_applications_status",
    "ix_partner_applications_user_id",
    "ix_invitations_status",
    "ix_invitations_email",
    "ix_invitations_brand_id",
    "ix_email_change_requests_user_id",
    "ix_email_deliveries_purpose",
    "ix_email_deliveries_status",
    "ix_email_deliveries_user_id",
)


def _has_table(bind, name: str) -> bool:
    from sqlalchemy import inspect
    return name in set(inspect(bind).get_table_names())


def _has_column(bind, table: str, column: str) -> bool:
    from sqlalchemy import inspect
    return column in {c["name"] for c in inspect(bind).get_columns(table)}


def _has_index(bind, table: str, name: str) -> bool:
    from sqlalchemy import inspect
    try:
        return name in {i["name"] for i in inspect(bind).get_indexes(table)}
    except Exception:  # pragma: no cover - dialect without index introspection
        return False


def upgrade() -> None:
    bind = op.get_bind()

    # --- users.registration_intent -----------------------------------------
    if not _has_column(bind, "users", "registration_intent"):
        with op.batch_alter_table("users") as batch:
            batch.add_column(sa.Column(
                "registration_intent",
                sa.String(length=40),
                nullable=False,
                server_default="consumer",
            ))
        print("[0018] Added users.registration_intent (default 'consumer')")
    else:
        print("[0018] users.registration_intent already present — skipping")

    # --- partner_applications ----------------------------------------------
    if not _has_table(bind, "partner_applications"):
        op.create_table(
            "partner_applications",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
            sa.Column("brand_name", sa.String(length=255), nullable=False),
            sa.Column("legal_name", sa.String(length=255), nullable=True),
            sa.Column("website", sa.String(length=500), nullable=True),
            sa.Column("market", sa.String(length=8), nullable=False, server_default="EG"),
            sa.Column("category", sa.String(length=120), nullable=True),
            sa.Column("catalogue_size", sa.String(length=40), nullable=True),
            sa.Column("contact_name", sa.String(length=255), nullable=False),
            sa.Column("contact_email", sa.String(length=255), nullable=False),
            sa.Column("contact_phone", sa.String(length=50), nullable=True),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("submitted_at", sa.DateTime(), nullable=False),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("reviewed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("decision_note", sa.Text(), nullable=True),
            sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brand_profiles.id", ondelete="SET NULL"), nullable=True),
            sa.Column("request_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        print("[0018] Created partner_applications")
    else:
        print("[0018] partner_applications already present — skipping")

    # --- invitations --------------------------------------------------------
    if not _has_table(bind, "invitations"):
        op.create_table(
            "invitations",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("token_hash", sa.String(length=128), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("role", sa.String(length=50), nullable=False),
            sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=False),
            sa.Column("invited_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("accepted_at", sa.DateTime(), nullable=True),
            sa.Column("accepted_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("request_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        print("[0018] Created invitations")
    else:
        print("[0018] invitations already present — skipping")

    # --- brand_members ------------------------------------------------------
    if not _has_table(bind, "brand_members"):
        op.create_table(
            "brand_members",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=False),
            sa.Column("role", sa.String(length=50), nullable=False),
            sa.Column("invited_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("invitation_id", sa.Integer(), sa.ForeignKey("invitations.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        print("[0018] Created brand_members")
    else:
        print("[0018] brand_members already present — skipping")

    # --- email_change_requests ---------------------------------------------
    if not _has_table(bind, "email_change_requests"):
        op.create_table(
            "email_change_requests",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("new_email", sa.String(length=255), nullable=False),
            sa.Column("token_hash", sa.String(length=128), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("used_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        print("[0018] Created email_change_requests")
    else:
        print("[0018] email_change_requests already present — skipping")

    # --- email_deliveries ---------------------------------------------------
    if not _has_table(bind, "email_deliveries"):
        op.create_table(
            "email_deliveries",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("purpose", sa.String(length=40), nullable=False),
            sa.Column("idempotency_key", sa.String(length=160), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("provider", sa.String(length=40), nullable=True),
            sa.Column("provider_message_id", sa.String(length=255), nullable=True),
            sa.Column("error_class", sa.String(length=120), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("recipient_hash", sa.String(length=64), nullable=True),
            sa.Column("request_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        print("[0018] Created email_deliveries")
    else:
        print("[0018] email_deliveries already present — skipping")

    # --- indexes (regular + race-guarding partial uniques) ------------------
    def _idx(name, table, cols, unique=False, where=None):
        if _has_index(bind, table, name):
            print(f"[0018] index {name} already present — skipping")
            return
        kwargs = {"unique": unique}
        if where is not None:
            kwargs["sqlite_where"] = sa.text(where)
            kwargs["postgresql_where"] = sa.text(where)
        op.create_index(name, table, cols, **kwargs)
        print(f"[0018] Created index {name}")

    _idx("uq_partner_applications_user_pending", "partner_applications", ["user_id"], unique=True, where="status = 'pending'")
    _idx("uq_invitations_pending_email_brand", "invitations", ["email", "brand_id"], unique=True, where="status = 'pending'")
    _idx("uq_email_change_open_user", "email_change_requests", ["user_id"], unique=True, where="used_at IS NULL")
    _idx("uq_brand_members_user_brand", "brand_members", ["user_id", "brand_id"], unique=True)
    _idx("ix_brand_members_user_id", "brand_members", ["user_id"])
    _idx("ix_brand_members_brand_id", "brand_members", ["brand_id"])
    _idx("ix_partner_applications_status", "partner_applications", ["status"])
    _idx("ix_partner_applications_user_id", "partner_applications", ["user_id"])
    _idx("ix_invitations_status", "invitations", ["status"])
    _idx("ix_invitations_email", "invitations", ["email"])
    _idx("ix_invitations_brand_id", "invitations", ["brand_id"])
    _idx("ix_email_change_requests_user_id", "email_change_requests", ["user_id"])
    _idx("ix_email_deliveries_purpose", "email_deliveries", ["purpose"])
    _idx("ix_email_deliveries_status", "email_deliveries", ["status"])
    _idx("ix_email_deliveries_user_id", "email_deliveries", ["user_id"])
    # unique token lookups
    _idx("ix_invitations_token_hash", "invitations", ["token_hash"], unique=True)
    _idx("ix_email_change_requests_token_hash", "email_change_requests", ["token_hash"], unique=True)
    _idx("ix_email_deliveries_idempotency_key", "email_deliveries", ["idempotency_key"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    for name, table in (
        ("uq_partner_applications_user_pending", "partner_applications"),
        ("uq_invitations_pending_email_brand", "invitations"),
        ("uq_email_change_open_user", "email_change_requests"),
        ("uq_brand_members_user_brand", "brand_members"),
        ("ix_brand_members_user_id", "brand_members"),
        ("ix_brand_members_brand_id", "brand_members"),
        ("ix_partner_applications_status", "partner_applications"),
        ("ix_partner_applications_user_id", "partner_applications"),
        ("ix_invitations_status", "invitations"),
        ("ix_invitations_email", "invitations"),
        ("ix_invitations_brand_id", "invitations"),
        ("ix_email_change_requests_user_id", "email_change_requests"),
        ("ix_email_deliveries_purpose", "email_deliveries"),
        ("ix_email_deliveries_status", "email_deliveries"),
        ("ix_email_deliveries_user_id", "email_deliveries"),
        ("ix_invitations_token_hash", "invitations"),
        ("ix_email_change_requests_token_hash", "email_change_requests"),
        ("ix_email_deliveries_idempotency_key", "email_deliveries"),
    ):
        if _has_table(bind, table) and _has_index(bind, table, name):
            op.drop_index(name, table_name=table)
            print(f"[0018] Dropped index {name}")

    for table in _TABLES:
        if _has_table(bind, table):
            op.drop_table(table)
            print(f"[0018] Dropped table {table}")

    if _has_column(bind, "users", "registration_intent"):
        with op.batch_alter_table("users") as batch:
            batch.drop_column("registration_intent")
        print("[0018] Dropped users.registration_intent")
