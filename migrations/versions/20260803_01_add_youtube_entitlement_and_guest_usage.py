"""Add configurable YouTube access and guest monthly usage tracking."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260803_01"
down_revision = "20260802_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pricings",
        sa.Column("youtube_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(sa.text("UPDATE pricings SET youtube_enabled = (billing_type <> 'free')"))
    op.execute(sa.text("""
        UPDATE pricings
        SET max_file_size_mb = NULL,
            max_file_size_unlimited = TRUE,
            max_duration_minutes = NULL,
            max_duration_unlimited = TRUE
        WHERE slug = 'pro'
    """))

    op.create_table(
        "guest_usage_periods",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ip_address", sa.String(length=255), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("video_count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ip_address", "period_start", name="uq_guest_usage_periods_key"),
    )
    op.create_index(
        "ix_guest_usage_periods_ip_period",
        "guest_usage_periods",
        ["ip_address", "period_start"],
    )


def downgrade() -> None:
    op.drop_index("ix_guest_usage_periods_ip_period", table_name="guest_usage_periods")
    op.drop_table("guest_usage_periods")
    op.drop_column("pricings", "youtube_enabled")
