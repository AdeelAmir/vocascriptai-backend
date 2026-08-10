"""Add dynamic pricing, pricing snapshots, and atomic usage periods.

Revision ID: 20260802_01
Revises: 20260801_04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260802_01"
down_revision = "20260801_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pricings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("price_amount_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency_code", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("billing_type", sa.String(length=20), nullable=False, server_default="free"),
        sa.Column("billing_interval", sa.String(length=10), nullable=True),
        sa.Column("billing_frequency", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("daily_video_limit", sa.Integer(), nullable=True),
        sa.Column("daily_video_quota_unlimited", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("monthly_video_limit", sa.Integer(), nullable=True),
        sa.Column("monthly_video_quota_unlimited", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("max_file_size_mb", sa.Numeric(10, 2), nullable=True),
        sa.Column("max_file_size_unlimited", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("max_duration_minutes", sa.Numeric(10, 2), nullable=True),
        sa.Column("max_duration_unlimited", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("transcript_language_mode", sa.String(length=20), nullable=False, server_default="english"),
        sa.Column("summary_language_mode", sa.String(length=20), nullable=False, server_default="english"),
        sa.Column("prompts_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ai_model", sa.String(length=20), nullable=False, server_default="standard"),
        sa.Column("pdf_download_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("priority_support_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("paddle_product_id", sa.String(), nullable=True),
        sa.Column("paddle_price_id", sa.String(), nullable=True),
        sa.Column("lifecycle_status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_highlighted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("billing_type IN ('free', 'recurring', 'one_time')", name="ck_pricings_billing_type"),
        sa.CheckConstraint(
            "(billing_type IN ('free', 'one_time') AND billing_interval IS NULL) OR "
            "(billing_type = 'recurring' AND billing_interval IN ('day', 'month'))",
            name="ck_pricings_billing_interval",
        ),
        sa.CheckConstraint("price_amount_minor >= 0", name="ck_pricings_price_nonnegative"),
        sa.CheckConstraint("billing_frequency > 0", name="ck_pricings_billing_frequency_positive"),
        sa.CheckConstraint("daily_video_quota_unlimited OR (daily_video_limit IS NOT NULL AND daily_video_limit > 0)", name="ck_pricings_daily_limit"),
        sa.CheckConstraint("monthly_video_quota_unlimited OR (monthly_video_limit IS NOT NULL AND monthly_video_limit > 0)", name="ck_pricings_monthly_limit"),
        sa.CheckConstraint("max_file_size_unlimited OR (max_file_size_mb IS NOT NULL AND max_file_size_mb > 0)", name="ck_pricings_file_size"),
        sa.CheckConstraint("max_duration_unlimited OR (max_duration_minutes IS NOT NULL AND max_duration_minutes > 0)", name="ck_pricings_duration"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_pricings_slug"),
    )
    op.create_index("ix_pricings_status_public_order", "pricings", ["lifecycle_status", "is_public", "sort_order"])

    op.create_table(
        "pricing_features",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pricing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feature_key", sa.String(length=80), nullable=True),
        sa.Column("label", sa.String(length=250), nullable=False),
        sa.Column("included", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["pricing_id"], ["pricings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pricing_features_pricing_order", "pricing_features", ["pricing_id", "sort_order"])

    op.add_column("subscriptions", sa.Column("pricing_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("subscriptions", sa.Column("paddle_transaction_id", sa.String(), nullable=True))
    op.add_column("subscriptions", sa.Column("billing_type", sa.String(), nullable=False, server_default="recurring"))
    op.add_column("subscriptions", sa.Column("pricing_slug_snapshot", sa.String(), nullable=True))
    op.add_column("subscriptions", sa.Column("pricing_name_snapshot", sa.String(), nullable=True))
    op.add_column("subscriptions", sa.Column("price_amount_minor_snapshot", sa.Integer(), nullable=True))
    op.add_column("subscriptions", sa.Column("currency_code_snapshot", sa.String(length=3), nullable=True))
    op.add_column("subscriptions", sa.Column("billing_type_snapshot", sa.String(), nullable=True))
    op.add_column("subscriptions", sa.Column("billing_interval_snapshot", sa.String(), nullable=True))
    op.add_column("subscriptions", sa.Column("paddle_price_id_snapshot", sa.String(), nullable=True))
    op.add_column("subscriptions", sa.Column("entitlements_snapshot", sa.JSON(), nullable=True))
    op.add_column("subscriptions", sa.Column("quota_snapshot", sa.JSON(), nullable=True))
    op.create_foreign_key("fk_subscriptions_pricing_id", "subscriptions", "pricings", ["pricing_id"], ["id"], ondelete="SET NULL")
    op.create_unique_constraint("uq_subscriptions_paddle_transaction_id", "subscriptions", ["paddle_transaction_id"])
    op.create_index(
        "uq_subscriptions_free_user",
        "subscriptions",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("billing_type = 'free'"),
    )

    op.create_table(
        "usage_periods",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entitlement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_type", sa.String(length=10), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("video_count", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["entitlement_id"], ["subscriptions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "entitlement_id", "period_type", "period_start", name="uq_usage_periods_key"),
        sa.CheckConstraint("period_type IN ('daily', 'monthly')", name="ck_usage_periods_type"),
    )
    op.create_index("ix_usage_periods_user_period", "usage_periods", ["user_id", "period_type", "period_start"])

    op.execute(
        sa.text(
            """
            INSERT INTO pricings (
                id, slug, name, description, price_amount_minor, currency_code,
                billing_type, billing_interval, billing_frequency,
                daily_video_limit, daily_video_quota_unlimited,
                monthly_video_limit, monthly_video_quota_unlimited,
                max_file_size_mb, max_file_size_unlimited,
                max_duration_minutes, max_duration_unlimited,
                transcript_language_mode, summary_language_mode, prompts_enabled,
                ai_model, pdf_download_enabled, priority_support_enabled,
                lifecycle_status, is_active, is_public, is_highlighted, sort_order
            ) VALUES
            (
                gen_random_uuid(), 'starter', 'Starter', 'For individuals who want to try BriefRoom for free.',
                0, 'USD', 'free', NULL, 1,
                NULL, TRUE, 5, FALSE,
                COALESCE((SELECT NULLIF(value, '')::numeric FROM settings WHERE key = 'MAX_FILE_SIZE_MB'), 200), FALSE,
                COALESCE((SELECT NULLIF(value, '')::numeric FROM settings WHERE key = 'MAX_VIDEO_DURATION_MINUTES'), 30), FALSE,
                'english', 'english', FALSE, 'standard', TRUE, FALSE,
                'published', TRUE, TRUE, FALSE, 1
            ),
            (
                gen_random_uuid(), 'pro', 'Pro', 'For professionals who need full power and no limits.',
                999, 'USD', 'recurring', 'month', 1,
                NULL, TRUE, NULL, TRUE,
                COALESCE((SELECT NULLIF(value, '')::numeric FROM settings WHERE key = 'PREMIUM_MAX_FILE_SIZE_MB'), 1000), FALSE,
                COALESCE((SELECT NULLIF(value, '')::numeric FROM settings WHERE key = 'PREMIUM_MAX_VIDEO_DURATION_MINUTES'), 120), FALSE,
                'all', 'all', TRUE, 'powerful', TRUE, TRUE,
                'published', TRUE, TRUE, TRUE, 2
            ),
            (
                gen_random_uuid(), 'lifetime', '$2 Lifetime', 'One-time lifetime access plan. Configure limits and features before publishing.',
                200, 'USD', 'one_time', NULL, 1,
                NULL, TRUE, NULL, TRUE,
                NULL, TRUE, NULL, TRUE,
                'english', 'english', FALSE, 'standard', TRUE, FALSE,
                'draft', FALSE, FALSE, FALSE, 3
            )
            """
        )
    )

    feature_rows = {
        "starter": [
            ("transcript_english", "Full transcript — English only"),
            ("summary_english", "Full summary — English only"),
            ("pdf_download", "PDF download"),
            ("standard_processing", "Standard processing speed"),
            ("video_quota", "Up to 5 videos per month"),
        ],
        "pro": [
            ("unlimited_videos", "Unlimited videos"),
            ("unlimited_duration_size", "Unlimited duration & file size"),
            ("transcript_languages", "Transcript in 110+ languages"),
            ("summary_languages", "Summary in your own language"),
            ("actionable_prompts", "Actionable prompts in your own language"),
            ("powerful_ai", "Powerful AI model"),
            ("pdf_download", "PDF download"),
            ("priority_support", "Priority support"),
        ],
    }
    for slug, rows in feature_rows.items():
        for index, (feature_key, label) in enumerate(rows):
            op.get_bind().execute(
                sa.text(
                    """
                    INSERT INTO pricing_features (id, pricing_id, feature_key, label, included, sort_order)
                    SELECT gen_random_uuid(), id, :feature_key, :label, TRUE, :sort_order
                    FROM pricings WHERE slug = :slug
                    """
                ),
                {"slug": slug, "feature_key": feature_key, "label": label, "sort_order": index},
            )

    op.execute(
        sa.text(
            """
            UPDATE subscriptions s
            SET pricing_id = p.id,
                pricing_slug_snapshot = p.slug,
                pricing_name_snapshot = p.name,
                price_amount_minor_snapshot = p.price_amount_minor,
                currency_code_snapshot = p.currency_code,
                billing_type_snapshot = p.billing_type,
                billing_interval_snapshot = p.billing_interval,
                billing_type = p.billing_type,
                entitlements_snapshot = json_build_object(
                    'transcript_language_mode', p.transcript_language_mode,
                    'summary_language_mode', p.summary_language_mode,
                    'prompts_enabled', p.prompts_enabled,
                    'ai_model', p.ai_model,
                    'pdf_download_enabled', p.pdf_download_enabled,
                    'priority_support_enabled', p.priority_support_enabled
                ),
                quota_snapshot = json_build_object(
                    'daily_video_limit', p.daily_video_limit,
                    'daily_video_quota_unlimited', p.daily_video_quota_unlimited,
                    'monthly_video_limit', p.monthly_video_limit,
                    'monthly_video_quota_unlimited', p.monthly_video_quota_unlimited,
                    'max_file_size_mb', p.max_file_size_mb,
                    'max_file_size_unlimited', p.max_file_size_unlimited,
                    'max_duration_minutes', p.max_duration_minutes,
                    'max_duration_unlimited', p.max_duration_unlimited
                )
            FROM pricings p
            WHERE p.slug = 'pro'
              AND (s.plan = 'premium' OR s.plan = 'pro')
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_usage_periods_user_period", table_name="usage_periods")
    op.drop_table("usage_periods")
    op.drop_constraint("uq_subscriptions_paddle_transaction_id", "subscriptions", type_="unique")
    op.drop_index("uq_subscriptions_free_user", table_name="subscriptions")
    op.drop_constraint("fk_subscriptions_pricing_id", "subscriptions", type_="foreignkey")
    for column in (
        "quota_snapshot", "entitlements_snapshot", "paddle_price_id_snapshot",
        "billing_interval_snapshot", "billing_type_snapshot", "currency_code_snapshot",
        "price_amount_minor_snapshot", "pricing_name_snapshot", "pricing_slug_snapshot",
        "billing_type", "paddle_transaction_id", "pricing_id",
    ):
        op.drop_column("subscriptions", column)
    op.drop_index("ix_pricing_features_pricing_order", table_name="pricing_features")
    op.drop_table("pricing_features")
    op.drop_index("ix_pricings_status_public_order", table_name="pricings")
    op.drop_table("pricings")
