"""Add one configurable daily, monthly, yearly, or lifetime video quota."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260802_05"
down_revision = "20260802_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pricings", sa.Column("video_quota_period", sa.String(length=10), nullable=True))
    op.add_column("pricings", sa.Column("video_quota_limit", sa.Integer(), nullable=True))
    op.add_column("pricings", sa.Column("video_quota_unlimited", sa.Boolean(), nullable=True))
    op.execute(sa.text("""
        UPDATE pricings
        SET
            video_quota_period = CASE
                WHEN NOT daily_video_quota_unlimited THEN 'daily'
                WHEN NOT monthly_video_quota_unlimited THEN 'monthly'
                ELSE 'lifetime'
            END,
            video_quota_limit = CASE
                WHEN NOT daily_video_quota_unlimited THEN daily_video_limit
                WHEN NOT monthly_video_quota_unlimited THEN monthly_video_limit
                ELSE NULL
            END,
            video_quota_unlimited = CASE
                WHEN NOT daily_video_quota_unlimited OR NOT monthly_video_quota_unlimited THEN FALSE
                ELSE TRUE
            END
    """))
    op.alter_column("pricings", "video_quota_period", nullable=False, server_default="monthly")
    op.alter_column("pricings", "video_quota_unlimited", nullable=False, server_default=sa.true())
    op.create_check_constraint(
        "ck_pricings_video_quota_period",
        "pricings",
        "video_quota_period IN ('daily', 'monthly', 'yearly', 'lifetime')",
    )
    op.create_check_constraint(
        "ck_pricings_video_quota_limit",
        "pricings",
        "video_quota_unlimited OR (video_quota_limit IS NOT NULL AND video_quota_limit > 0)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_pricings_video_quota_limit", "pricings", type_="check")
    op.drop_constraint("ck_pricings_video_quota_period", "pricings", type_="check")
    op.drop_column("pricings", "video_quota_unlimited")
    op.drop_column("pricings", "video_quota_limit")
    op.drop_column("pricings", "video_quota_period")
