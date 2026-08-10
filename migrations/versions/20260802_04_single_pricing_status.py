"""Replace pricing lifecycle/public flags with one active status."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260802_04"
down_revision = "20260802_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Preserve the existing catalog meaning before removing the redundant
    # lifecycle and public columns: only published plans remain active.
    op.execute(sa.text("UPDATE pricings SET is_active = (lifecycle_status = 'published')"))
    op.drop_index("ix_pricings_status_public_order", table_name="pricings")
    op.drop_column("pricings", "lifecycle_status")
    op.drop_column("pricings", "is_public")
    op.create_index("ix_pricings_active_order", "pricings", ["is_active", "sort_order"])


def downgrade() -> None:
    op.drop_index("ix_pricings_active_order", table_name="pricings")
    op.add_column("pricings", sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("pricings", sa.Column("lifecycle_status", sa.String(length=20), nullable=False, server_default="draft"))
    op.execute(sa.text(
        "UPDATE pricings SET lifecycle_status = CASE WHEN is_active THEN 'published' ELSE 'draft' END, "
        "is_public = is_active"
    ))
    op.create_index("ix_pricings_status_public_order", "pricings", ["lifecycle_status", "is_public", "sort_order"])
