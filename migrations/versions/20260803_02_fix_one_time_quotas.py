"""Make one-time pricing quotas non-resetting lifetime allowances."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260803_02"
down_revision = "20260803_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing one-time catalog rows may have been created with the old
    # periodic quota selector. Preserve their configured count, but stop the
    # allowance from resetting every month/day/year.
    op.execute(sa.text("""
        UPDATE pricings
        SET
            video_quota_period = 'lifetime',
            daily_video_limit = NULL,
            daily_video_quota_unlimited = TRUE,
            monthly_video_limit = NULL,
            monthly_video_quota_unlimited = TRUE
        WHERE billing_type = 'one_time'
    """))


def downgrade() -> None:
    # The original period cannot be reconstructed safely after normalization.
    pass
