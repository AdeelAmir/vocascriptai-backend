"""Make every published pricing plan available to the public catalog."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260802_03"
down_revision = "20260802_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE pricings SET is_active = TRUE, is_public = TRUE "
            "WHERE lifecycle_status = 'published'"
        )
    )


def downgrade() -> None:
    # Published plans remain active/public on downgrade; this migration only
    # normalizes catalog visibility and has no safe inverse for prior values.
    pass
