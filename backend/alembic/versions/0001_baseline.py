"""Baseline schema — Group 1 §7.

Creates every CONFIT table via explicit portable Alembic ops. Does NOT call
`Base.metadata.create_all()`; every table, column, index, foreign key and
default is materialised through explicit `op.create_table` / `op.create_index`
calls so the migration is a faithful, reviewable description of the schema
and behaves identically on sqlite (dev/test, render_as_batch) and postgresql
(production).

Databases previously created by `create_all()` should stamp this revision:

    PYTHONPATH=. alembic -c backend/alembic.ini stamp 0001_baseline

Fresh databases run the migrations normally:

    PYTHONPATH=. alembic -c backend/alembic.ini upgrade head
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "audit_logs"):
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("action", sa.String(length=255), nullable=False),
            sa.Column("resource_type", sa.String(length=100), nullable=False),
            sa.Column("resource_id", sa.String(length=100), nullable=True),
            sa.Column("ip_address", sa.String(length=50), nullable=True),
            sa.Column("details_json", sa.Text(), nullable=True),
            sa.Column("timestamp", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_audit_logs_id", "audit_logs", ["id"])
        op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
        op.create_index("ix_audit_logs_action", "audit_logs", ["action"])

    if not _table_exists(bind, "categories"):
        op.create_table(
            "categories",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("name_ar", sa.String(length=100), nullable=False),
            sa.Column("slug", sa.String(length=100), nullable=False, unique=True),
            sa.Column("parent_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete='SET NULL'), nullable=True),
            sa.Column("icon_name", sa.String(length=50), nullable=True),
        )
        op.create_index("ix_categories_slug", "categories", ["slug"], unique=True)
        op.create_index("ix_categories_id", "categories", ["id"])

    if not _table_exists(bind, "person_scan_cache"):
        op.create_table(
            "person_scan_cache",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("image_hash", sa.String(length=64), nullable=False, unique=True),
            sa.Column("segmentation_mask_url", sa.Text(), nullable=True),
            sa.Column("pose_keypoints_json", sa.Text(), nullable=False),
            sa.Column("body_shape_detected", sa.String(length=50), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_person_scan_cache_id", "person_scan_cache", ["id"])
        op.create_index("ix_person_scan_cache_image_hash", "person_scan_cache", ["image_hash"], unique=True)

    if not _table_exists(bind, "style_heatmap_aggregates"):
        op.create_table(
            "style_heatmap_aggregates",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("period", sa.String(length=50), nullable=False),
            sa.Column("region", sa.String(length=100), nullable=False),
            sa.Column("top_aesthetics_json", sa.Text(), nullable=False),
            sa.Column("top_colors_json", sa.Text(), nullable=False),
            sa.Column("top_occasions_json", sa.Text(), nullable=False),
            sa.Column("sample_size", sa.Integer(), nullable=False),
            sa.Column("calculated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_style_heatmap_aggregates_id", "style_heatmap_aggregates", ["id"])

    if not _table_exists(bind, "users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False, unique=True),
            sa.Column("hashed_password", sa.String(length=255), nullable=False),
            sa.Column("full_name", sa.String(length=255), nullable=False),
            sa.Column("role", sa.String(length=50), nullable=False),
            sa.Column("phone", sa.String(length=50), nullable=True),
            sa.Column("preferred_language", sa.String(length=10), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("is_verified", sa.Boolean(), nullable=False),
            sa.Column("mfa_enabled", sa.Boolean(), nullable=False),
            sa.Column("mfa_secret", sa.String(length=255), nullable=True),
            sa.Column("oauth_provider", sa.String(length=50), nullable=True),
            sa.Column("oauth_subject", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)
        op.create_index("ix_users_id", "users", ["id"])
        op.create_index("ix_users_oauth_subject", "users", ["oauth_subject"])
        op.create_index("ix_users_oauth_provider", "users", ["oauth_provider"])

    if not _table_exists(bind, "brand_profiles"):
        op.create_table(
            "brand_profiles",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete='CASCADE'), nullable=False, unique=True),
            sa.Column("brand_name", sa.String(length=255), nullable=False, unique=True),
            sa.Column("slug", sa.String(length=255), nullable=False, unique=True),
            sa.Column("logo_url", sa.String(length=1000), nullable=True),
            sa.Column("banner_url", sa.String(length=1000), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("description_ar", sa.Text(), nullable=True),
            sa.Column("website", sa.String(length=500), nullable=True),
            sa.Column("commission_rate", sa.Integer(), nullable=True),
            sa.Column("return_rate_benchmark", sa.Integer(), nullable=True),
            sa.Column("current_return_rate", sa.Integer(), nullable=True),
            sa.Column("is_verified", sa.Boolean(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_brand_profiles_slug", "brand_profiles", ["slug"], unique=True)
        op.create_index("ix_brand_profiles_brand_name", "brand_profiles", ["brand_name"], unique=True)
        op.create_index("ix_brand_profiles_id", "brand_profiles", ["id"])

    if not _table_exists(bind, "carts"):
        op.create_table(
            "carts",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete='CASCADE'), nullable=True),
            sa.Column("session_token", sa.String(length=100), nullable=False, unique=True),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_carts_session_token", "carts", ["session_token"], unique=True)
        op.create_index("ix_carts_id", "carts", ["id"])

    if not _table_exists(bind, "email_verification_tokens"):
        op.create_table(
            "email_verification_tokens",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete='CASCADE'), nullable=False),
            sa.Column("token_hash", sa.String(length=128), nullable=False, unique=True),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("used_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_email_verification_tokens_token_hash", "email_verification_tokens", ["token_hash"], unique=True)
        op.create_index("ix_email_verification_tokens_id", "email_verification_tokens", ["id"])
        op.create_index("ix_email_verification_tokens_user_id", "email_verification_tokens", ["user_id"])

    if not _table_exists(bind, "measurement_sessions"):
        op.create_table(
            "measurement_sessions",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete='SET NULL'), nullable=True),
            sa.Column("guest_session_token", sa.String(length=100), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("capture_mode", sa.String(length=30), nullable=False),
            sa.Column("consent_granted", sa.Boolean(), nullable=False),
            sa.Column("save_to_profile", sa.Boolean(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_measurement_sessions_id", "measurement_sessions", ["id"])
        op.create_index("ix_measurement_sessions_guest_session_token", "measurement_sessions", ["guest_session_token"])

    if not _table_exists(bind, "mfa_backup_codes"):
        op.create_table(
            "mfa_backup_codes",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete='CASCADE'), nullable=False),
            sa.Column("code_hash", sa.String(length=255), nullable=False),
            sa.Column("used_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_mfa_backup_codes_id", "mfa_backup_codes", ["id"])
        op.create_index("ix_mfa_backup_codes_user_id", "mfa_backup_codes", ["user_id"])

    if not _table_exists(bind, "outfits"):
        op.create_table(
            "outfits",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete='CASCADE'), nullable=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("occasion", sa.String(length=100), nullable=False),
            sa.Column("total_price", sa.Float(), nullable=False),
            sa.Column("compatibility_score", sa.Integer(), nullable=False),
            sa.Column("color_palette", sa.Text(), nullable=False),
            sa.Column("style_tags", sa.Text(), nullable=False),
            sa.Column("is_saved", sa.Boolean(), nullable=False),
            sa.Column("is_system_curated", sa.Boolean(), nullable=False),
            sa.Column("share_token", sa.String(length=100), nullable=True, unique=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_outfits_share_token", "outfits", ["share_token"], unique=True)
        op.create_index("ix_outfits_id", "outfits", ["id"])

    if not _table_exists(bind, "password_reset_tokens"):
        op.create_table(
            "password_reset_tokens",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete='CASCADE'), nullable=False),
            sa.Column("token_hash", sa.String(length=128), nullable=False, unique=True),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("used_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])
        op.create_index("ix_password_reset_tokens_id", "password_reset_tokens", ["id"])
        op.create_index("ix_password_reset_tokens_token_hash", "password_reset_tokens", ["token_hash"], unique=True)

    if not _table_exists(bind, "refresh_tokens"):
        op.create_table(
            "refresh_tokens",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete='CASCADE'), nullable=False),
            sa.Column("jti", sa.String(length=64), nullable=False, unique=True),
            sa.Column("family_id", sa.String(length=64), nullable=False),
            sa.Column("issued_at", sa.DateTime(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("last_used_at", sa.DateTime(), nullable=True),
            sa.Column("replaced_by_jti", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.String(length=500), nullable=True),
            sa.Column("ip_address", sa.String(length=50), nullable=True),
        )
        op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])
        op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
        op.create_index("ix_refresh_tokens_user_active", "refresh_tokens", ["user_id", "revoked_at"])
        op.create_index("ix_refresh_tokens_jti", "refresh_tokens", ["jti"], unique=True)
        op.create_index("ix_refresh_tokens_id", "refresh_tokens", ["id"])

    if not _table_exists(bind, "stylist_sessions"):
        op.create_table(
            "stylist_sessions",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete='CASCADE'), nullable=True),
            sa.Column("session_title", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_stylist_sessions_id", "stylist_sessions", ["id"])

    if not _table_exists(bind, "user_style_profiles"):
        op.create_table(
            "user_style_profiles",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete='CASCADE'), nullable=False, unique=True),
            sa.Column("style_archetypes", sa.Text(), nullable=False),
            sa.Column("preferred_colors", sa.Text(), nullable=False),
            sa.Column("avoided_colors", sa.Text(), nullable=False),
            sa.Column("fashion_aesthetics", sa.Text(), nullable=False),
            sa.Column("moodboard_urls", sa.Text(), nullable=False),
            sa.Column("encrypted_body_data", sa.Text(), nullable=True),
            sa.Column("body_shape_tag", sa.String(length=50), nullable=True),
            sa.Column("budget_monthly_min", sa.Float(), nullable=True),
            sa.Column("budget_monthly_max", sa.Float(), nullable=True),
            sa.Column("budget_per_outfit_max", sa.Float(), nullable=True),
            sa.Column("preferred_brands", sa.Text(), nullable=False),
            sa.Column("blacklisted_brands", sa.Text(), nullable=False),
            sa.Column("occasion_weights", sa.Text(), nullable=False),
            sa.Column("size_tops", sa.String(length=20), nullable=True),
            sa.Column("size_bottoms", sa.String(length=20), nullable=True),
            sa.Column("size_shoes", sa.String(length=20), nullable=True),
            sa.Column("fit_preference", sa.String(length=30), nullable=True),
            sa.Column("onboarding_completed", sa.Boolean(), nullable=False),
            sa.Column("privacy_consent_tryon_storage", sa.Boolean(), nullable=False),
            sa.Column("privacy_consent_share_with_brands", sa.Boolean(), nullable=False),
            sa.Column("consent_ai_personalization", sa.Boolean(), nullable=False),
            sa.Column("consent_marketing_analytics", sa.Boolean(), nullable=False),
            sa.Column("consent_policy_version", sa.Integer(), nullable=False),
            sa.Column("consent_last_agreed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_user_style_profiles_user_id", "user_style_profiles", ["user_id"], unique=True)
        op.create_index("ix_user_style_profiles_id", "user_style_profiles", ["id"])

    if not _table_exists(bind, "visual_search_queries"):
        op.create_table(
            "visual_search_queries",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete='SET NULL'), nullable=True),
            sa.Column("input_image_url", sa.Text(), nullable=False),
            sa.Column("detected_category", sa.String(length=100), nullable=True),
            sa.Column("detected_color", sa.String(length=50), nullable=True),
            sa.Column("detected_pattern", sa.String(length=50), nullable=True),
            sa.Column("detected_style", sa.String(length=100), nullable=True),
            sa.Column("detected_attributes_json", sa.Text(), nullable=False),
            sa.Column("matches_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_visual_search_queries_id", "visual_search_queries", ["id"])

    if not _table_exists(bind, "wardrobe_gap_analyses"):
        op.create_table(
            "wardrobe_gap_analyses",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete='CASCADE'), nullable=False),
            sa.Column("missing_category", sa.String(length=100), nullable=False),
            sa.Column("missing_subcategory", sa.String(length=100), nullable=False),
            sa.Column("suggested_colors", sa.Text(), nullable=False),
            sa.Column("rationale", sa.Text(), nullable=False),
            sa.Column("unlocks_outfit_count", sa.Integer(), nullable=False),
            sa.Column("recommended_products_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_wardrobe_gap_analyses_id", "wardrobe_gap_analyses", ["id"])

    if not _table_exists(bind, "wardrobe_items"):
        op.create_table(
            "wardrobe_items",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete='CASCADE'), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("category", sa.String(length=50), nullable=False),
            sa.Column("subcategory", sa.String(length=100), nullable=True),
            sa.Column("color_name", sa.String(length=50), nullable=False),
            sa.Column("color_hex", sa.String(length=20), nullable=False),
            sa.Column("pattern", sa.String(length=50), nullable=False),
            sa.Column("brand_name", sa.String(length=100), nullable=False),
            sa.Column("image_url", sa.String(length=1000), nullable=False),
            sa.Column("ai_tags", sa.Text(), nullable=False),
            sa.Column("occasions", sa.Text(), nullable=False),
            sa.Column("wear_frequency", sa.String(length=30), nullable=False),
            sa.Column("wear_count", sa.Integer(), nullable=False),
            sa.Column("last_worn_date", sa.DateTime(), nullable=True),
            sa.Column("purchase_price", sa.Float(), nullable=True),
            sa.Column("is_favorite", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_wardrobe_items_id", "wardrobe_items", ["id"])

    if not _table_exists(bind, "measurement_results"):
        op.create_table(
            "measurement_results",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("session_id", sa.Integer(), sa.ForeignKey("measurement_sessions.id", ondelete='CASCADE'), nullable=False),
            sa.Column("height_cm", sa.Float(), nullable=False),
            sa.Column("shoulder_width_cm", sa.Float(), nullable=True),
            sa.Column("chest_cm", sa.Float(), nullable=True),
            sa.Column("waist_cm", sa.Float(), nullable=True),
            sa.Column("hip_cm", sa.Float(), nullable=True),
            sa.Column("inseam_cm", sa.Float(), nullable=True),
            sa.Column("body_shape_detected", sa.String(length=50), nullable=True),
            sa.Column("body_shape", sa.String(length=50), nullable=True),
            sa.Column("confidence_score", sa.Integer(), nullable=False),
            sa.Column("calibration_reference_used", sa.String(length=100), nullable=False),
            sa.Column("calibration_method", sa.String(length=100), nullable=True),
            sa.Column("source", sa.String(length=50), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_measurement_results_id", "measurement_results", ["id"])

    if not _table_exists(bind, "mood_boards"):
        op.create_table(
            "mood_boards",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("profile_id", sa.Integer(), sa.ForeignKey("user_style_profiles.id", ondelete='CASCADE'), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_mood_boards_profile_id", "mood_boards", ["profile_id"])
        op.create_index("ix_mood_boards_id", "mood_boards", ["id"])

    if not _table_exists(bind, "products"):
        op.create_table(
            "products",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brand_profiles.id", ondelete='CASCADE'), nullable=False),
            sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("title_ar", sa.String(length=255), nullable=False),
            sa.Column("slug", sa.String(length=255), nullable=False, unique=True),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("description_ar", sa.Text(), nullable=False),
            sa.Column("base_price", sa.Float(), nullable=False),
            sa.Column("currency", sa.String(length=10), nullable=False),
            sa.Column("material", sa.String(length=255), nullable=True),
            sa.Column("care_instructions", sa.String(length=500), nullable=True),
            sa.Column("style_tags", sa.Text(), nullable=False),
            sa.Column("occasion_tags", sa.Text(), nullable=False),
            sa.Column("color_family", sa.String(length=50), nullable=False),
            sa.Column("dominant_hex", sa.String(length=20), nullable=True),
            sa.Column("thumbnail_url", sa.String(length=1000), nullable=False),
            sa.Column("images", sa.Text(), nullable=False),
            sa.Column("size_chart_json", sa.Text(), nullable=False),
            sa.Column("rating", sa.Float(), nullable=True),
            sa.Column("review_count", sa.Integer(), nullable=True),
            sa.Column("style_compatibility_base", sa.Integer(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("is_featured", sa.Boolean(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_products_title", "products", ["title"])
        op.create_index("ix_products_id", "products", ["id"])
        op.create_index("ix_products_slug", "products", ["slug"], unique=True)

    if not _table_exists(bind, "store_locations"):
        op.create_table(
            "store_locations",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brand_profiles.id", ondelete='CASCADE'), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("name_ar", sa.String(length=255), nullable=False),
            sa.Column("address", sa.String(length=500), nullable=False),
            sa.Column("city", sa.String(length=100), nullable=False),
            sa.Column("country", sa.String(length=100), nullable=False),
            sa.Column("latitude", sa.Float(), nullable=False),
            sa.Column("longitude", sa.Float(), nullable=False),
            sa.Column("phone", sa.String(length=50), nullable=True),
            sa.Column("pickup_instructions", sa.Text(), nullable=True),
            sa.Column("is_bopis_enabled", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_store_locations_id", "store_locations", ["id"])

    if not _table_exists(bind, "stylist_messages"):
        op.create_table(
            "stylist_messages",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("session_id", sa.Integer(), sa.ForeignKey("stylist_sessions.id", ondelete='CASCADE'), nullable=False),
            sa.Column("sender", sa.String(length=20), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("audio_url", sa.String(length=1000), nullable=True),
            sa.Column("intent_json", sa.Text(), nullable=False),
            sa.Column("recommendations_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_stylist_messages_id", "stylist_messages", ["id"])

    if not _table_exists(bind, "garment_assets"):
        op.create_table(
            "garment_assets",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete='CASCADE'), nullable=False),
            sa.Column("slot_type", sa.String(length=50), nullable=False),
            sa.Column("flat_image_url", sa.Text(), nullable=False),
            sa.Column("segmented_garment_url", sa.Text(), nullable=True),
            sa.Column("garment_mask_url", sa.Text(), nullable=True),
            sa.Column("bounding_box_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_garment_assets_id", "garment_assets", ["id"])

    if not _table_exists(bind, "mood_board_items"):
        op.create_table(
            "mood_board_items",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("board_id", sa.Integer(), sa.ForeignKey("mood_boards.id", ondelete='CASCADE'), nullable=False),
            sa.Column("kind", sa.String(length=30), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_mood_board_items_id", "mood_board_items", ["id"])
        op.create_index("ix_mood_board_items_board_id", "mood_board_items", ["board_id"])

    if not _table_exists(bind, "orders"):
        op.create_table(
            "orders",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("order_number", sa.String(length=50), nullable=False, unique=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete='SET NULL'), nullable=True),
            sa.Column("total_amount", sa.Float(), nullable=False),
            sa.Column("subtotal_amount", sa.Float(), nullable=False),
            sa.Column("discount_amount", sa.Float(), nullable=False),
            sa.Column("tax_amount", sa.Float(), nullable=False),
            sa.Column("shipping_amount", sa.Float(), nullable=False),
            sa.Column("currency", sa.String(length=10), nullable=False),
            sa.Column("payment_method", sa.String(length=50), nullable=False),
            sa.Column("payment_status", sa.String(length=30), nullable=False),
            sa.Column("payment_installments", sa.Integer(), nullable=False),
            sa.Column("fulfillment_type", sa.String(length=30), nullable=False),
            sa.Column("bopis_store_id", sa.Integer(), sa.ForeignKey("store_locations.id"), nullable=True),
            sa.Column("bopis_pickup_code", sa.String(length=20), nullable=True),
            sa.Column("ready_for_pickup_at", sa.DateTime(), nullable=True),
            sa.Column("shipping_recipient_name", sa.String(length=255), nullable=True),
            sa.Column("shipping_address_line", sa.String(length=500), nullable=True),
            sa.Column("shipping_city", sa.String(length=100), nullable=True),
            sa.Column("shipping_country", sa.String(length=100), nullable=True),
            sa.Column("shipping_phone", sa.String(length=50), nullable=True),
            sa.Column("tracking_number", sa.String(length=100), nullable=True),
            sa.Column("estimated_delivery_date", sa.DateTime(), nullable=True),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("try_on_assisted", sa.Boolean(), nullable=False),
            sa.Column("stylist_assisted", sa.Boolean(), nullable=False),
            sa.Column("idempotency_key", sa.String(length=100), nullable=True, unique=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_orders_idempotency_key", "orders", ["idempotency_key"], unique=True)
        op.create_index("ix_orders_order_number", "orders", ["order_number"], unique=True)
        op.create_index("ix_orders_id", "orders", ["id"])

    if not _table_exists(bind, "product_skus"):
        op.create_table(
            "product_skus",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete='CASCADE'), nullable=False),
            sa.Column("sku_code", sa.String(length=100), nullable=False, unique=True),
            sa.Column("size", sa.String(length=20), nullable=False),
            sa.Column("color", sa.String(length=50), nullable=False),
            sa.Column("color_hex", sa.String(length=20), nullable=True),
            sa.Column("price_override", sa.Float(), nullable=True),
            sa.Column("stock_level", sa.Integer(), nullable=False),
            sa.Column("is_in_stock", sa.Boolean(), nullable=False),
        )
        op.create_index("ix_product_skus_id", "product_skus", ["id"])
        op.create_index("ix_product_skus_sku_code", "product_skus", ["sku_code"], unique=True)

    if not _table_exists(bind, "sponsored_placements"):
        op.create_table(
            "sponsored_placements",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brand_profiles.id", ondelete='CASCADE'), nullable=False),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete='CASCADE'), nullable=False),
            sa.Column("placement_type", sa.String(length=50), nullable=False),
            sa.Column("bid_amount_per_click", sa.Float(), nullable=False),
            sa.Column("daily_budget", sa.Float(), nullable=False),
            sa.Column("spent_today", sa.Float(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("impressions", sa.Integer(), nullable=False),
            sa.Column("clicks", sa.Integer(), nullable=False),
            sa.Column("conversions", sa.Integer(), nullable=False),
            sa.Column("revenue_generated", sa.Float(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_sponsored_placements_id", "sponsored_placements", ["id"])

    if not _table_exists(bind, "tryon_sessions"):
        op.create_table(
            "tryon_sessions",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete='CASCADE'), nullable=True),
            sa.Column("guest_session_token", sa.String(length=100), nullable=True),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete='CASCADE'), nullable=True),
            sa.Column("outfit_id", sa.Integer(), sa.ForeignKey("outfits.id", ondelete='SET NULL'), nullable=True),
            sa.Column("user_image_url", sa.Text(), nullable=True),
            sa.Column("input_user_image_url", sa.Text(), nullable=True),
            sa.Column("garment_image_url", sa.Text(), nullable=True),
            sa.Column("rendered_image_url", sa.Text(), nullable=True),
            sa.Column("rendered_result_url", sa.Text(), nullable=True),
            sa.Column("rendered_animation_url", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("fit_verdict", sa.String(length=50), nullable=False),
            sa.Column("fit_confidence_score", sa.Integer(), nullable=False),
            sa.Column("body_fit_verdict", sa.String(length=100), nullable=True),
            sa.Column("body_scaling_factor", sa.Float(), nullable=False),
            sa.Column("ai_disclosure_text", sa.String(length=500), nullable=True),
            sa.Column("ai_disclosure", sa.String(length=500), nullable=True),
            sa.Column("applied_items_json", sa.Text(), nullable=False),
            sa.Column("slot_mapping_json", sa.Text(), nullable=True),
            sa.Column("layering_order_json", sa.Text(), nullable=True),
            sa.Column("render_metadata_json", sa.Text(), nullable=False),
            sa.Column("traceability_hash", sa.String(length=100), nullable=True),
            sa.Column("consent_retained", sa.Boolean(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_tryon_sessions_guest_session_token", "tryon_sessions", ["guest_session_token"])
        op.create_index("ix_tryon_sessions_id", "tryon_sessions", ["id"])

    if not _table_exists(bind, "cart_items"):
        op.create_table(
            "cart_items",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("cart_id", sa.Integer(), sa.ForeignKey("carts.id", ondelete='CASCADE'), nullable=False),
            sa.Column("product_sku_id", sa.Integer(), sa.ForeignKey("product_skus.id", ondelete='CASCADE'), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("outfit_id", sa.Integer(), sa.ForeignKey("outfits.id", ondelete='SET NULL'), nullable=True),
            sa.Column("added_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_cart_items_id", "cart_items", ["id"])

    if not _table_exists(bind, "order_items"):
        op.create_table(
            "order_items",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete='CASCADE'), nullable=False),
            sa.Column("product_sku_id", sa.Integer(), sa.ForeignKey("product_skus.id", ondelete='SET NULL'), nullable=True),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
            sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brand_profiles.id"), nullable=False),
            sa.Column("product_title", sa.String(length=255), nullable=False),
            sa.Column("brand_name", sa.String(length=255), nullable=False),
            sa.Column("size", sa.String(length=20), nullable=False),
            sa.Column("color", sa.String(length=50), nullable=False),
            sa.Column("unit_price", sa.Float(), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("subtotal", sa.Float(), nullable=False),
            sa.Column("is_returned", sa.Boolean(), nullable=False),
        )
        op.create_index("ix_order_items_id", "order_items", ["id"])

    if not _table_exists(bind, "outfit_items"):
        op.create_table(
            "outfit_items",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("outfit_id", sa.Integer(), sa.ForeignKey("outfits.id", ondelete='CASCADE'), nullable=False),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete='CASCADE'), nullable=False),
            sa.Column("product_sku_id", sa.Integer(), sa.ForeignKey("product_skus.id", ondelete='SET NULL'), nullable=True),
            sa.Column("position", sa.String(length=50), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False),
        )
        op.create_index("ix_outfit_items_id", "outfit_items", ["id"])

    if not _table_exists(bind, "return_requests"):
        op.create_table(
            "return_requests",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("return_number", sa.String(length=50), nullable=False, unique=True),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete='CASCADE'), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete='CASCADE'), nullable=False),
            sa.Column("reason", sa.String(length=100), nullable=False),
            sa.Column("details", sa.Text(), nullable=True),
            sa.Column("refund_amount", sa.Float(), nullable=False),
            sa.Column("return_label_url", sa.String(length=1000), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("try_on_used_for_item", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_return_requests_return_number", "return_requests", ["return_number"], unique=True)
        op.create_index("ix_return_requests_id", "return_requests", ["id"])

    if not _table_exists(bind, "store_inventories"):
        op.create_table(
            "store_inventories",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("store_id", sa.Integer(), sa.ForeignKey("store_locations.id", ondelete='CASCADE'), nullable=False),
            sa.Column("sku_id", sa.Integer(), sa.ForeignKey("product_skus.id", ondelete='CASCADE'), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("reserved_quantity", sa.Integer(), nullable=False),
        )
        op.create_index("ix_store_inventories_id", "store_inventories", ["id"])

    if not _table_exists(bind, "tryon_jobs"):
        op.create_table(
            "tryon_jobs",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("job_id", sa.String(length=64), nullable=False, unique=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete='SET NULL'), nullable=True),
            sa.Column("session_id", sa.Integer(), sa.ForeignKey("tryon_sessions.id", ondelete='SET NULL'), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("progress_pct", sa.Integer(), nullable=False),
            sa.Column("current_stage", sa.String(length=50), nullable=False),
            sa.Column("input_person_image_url", sa.Text(), nullable=False),
            sa.Column("garment_ids_json", sa.Text(), nullable=False),
            sa.Column("garment_layers_json", sa.Text(), nullable=False),
            sa.Column("model_used", sa.String(length=50), nullable=False),
            sa.Column("output_image_url", sa.Text(), nullable=True),
            sa.Column("metrics_json", sa.Text(), nullable=False),
            sa.Column("error_code", sa.String(length=50), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_tryon_jobs_job_id", "tryon_jobs", ["job_id"], unique=True)
        op.create_index("ix_tryon_jobs_id", "tryon_jobs", ["id"])


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "tryon_jobs"):
        op.drop_table("tryon_jobs")
    if _table_exists(bind, "store_inventories"):
        op.drop_table("store_inventories")
    if _table_exists(bind, "return_requests"):
        op.drop_table("return_requests")
    if _table_exists(bind, "outfit_items"):
        op.drop_table("outfit_items")
    if _table_exists(bind, "order_items"):
        op.drop_table("order_items")
    if _table_exists(bind, "cart_items"):
        op.drop_table("cart_items")
    if _table_exists(bind, "tryon_sessions"):
        op.drop_table("tryon_sessions")
    if _table_exists(bind, "sponsored_placements"):
        op.drop_table("sponsored_placements")
    if _table_exists(bind, "product_skus"):
        op.drop_table("product_skus")
    if _table_exists(bind, "orders"):
        op.drop_table("orders")
    if _table_exists(bind, "mood_board_items"):
        op.drop_table("mood_board_items")
    if _table_exists(bind, "garment_assets"):
        op.drop_table("garment_assets")
    if _table_exists(bind, "stylist_messages"):
        op.drop_table("stylist_messages")
    if _table_exists(bind, "store_locations"):
        op.drop_table("store_locations")
    if _table_exists(bind, "products"):
        op.drop_table("products")
    if _table_exists(bind, "mood_boards"):
        op.drop_table("mood_boards")
    if _table_exists(bind, "measurement_results"):
        op.drop_table("measurement_results")
    if _table_exists(bind, "wardrobe_items"):
        op.drop_table("wardrobe_items")
    if _table_exists(bind, "wardrobe_gap_analyses"):
        op.drop_table("wardrobe_gap_analyses")
    if _table_exists(bind, "visual_search_queries"):
        op.drop_table("visual_search_queries")
    if _table_exists(bind, "user_style_profiles"):
        op.drop_table("user_style_profiles")
    if _table_exists(bind, "stylist_sessions"):
        op.drop_table("stylist_sessions")
    if _table_exists(bind, "refresh_tokens"):
        op.drop_table("refresh_tokens")
    if _table_exists(bind, "password_reset_tokens"):
        op.drop_table("password_reset_tokens")
    if _table_exists(bind, "outfits"):
        op.drop_table("outfits")
    if _table_exists(bind, "mfa_backup_codes"):
        op.drop_table("mfa_backup_codes")
    if _table_exists(bind, "measurement_sessions"):
        op.drop_table("measurement_sessions")
    if _table_exists(bind, "email_verification_tokens"):
        op.drop_table("email_verification_tokens")
    if _table_exists(bind, "carts"):
        op.drop_table("carts")
    if _table_exists(bind, "brand_profiles"):
        op.drop_table("brand_profiles")
    if _table_exists(bind, "users"):
        op.drop_table("users")
    if _table_exists(bind, "style_heatmap_aggregates"):
        op.drop_table("style_heatmap_aggregates")
    if _table_exists(bind, "person_scan_cache"):
        op.drop_table("person_scan_cache")
    if _table_exists(bind, "categories"):
        op.drop_table("categories")
    if _table_exists(bind, "audit_logs"):
        op.drop_table("audit_logs")
