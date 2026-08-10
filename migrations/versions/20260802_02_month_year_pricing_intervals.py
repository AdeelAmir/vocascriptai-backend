"""Restrict recurring pricing intervals to monthly or yearly billing."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260802_02"
down_revision = "20260802_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The initial catalog only used monthly recurring billing. Convert any
    # legacy daily catalog rows before tightening the database constraint.
    op.execute(
        sa.text(
            "UPDATE pricings SET billing_interval = 'month' "
            "WHERE billing_type = 'recurring' AND billing_interval = 'day'"
        )
    )
    op.drop_constraint("ck_pricings_billing_interval", "pricings", type_="check")
    op.create_check_constraint(
        "ck_pricings_billing_interval",
        "pricings",
        "(billing_type IN ('free', 'one_time') AND billing_interval IS NULL) OR "
        "(billing_type = 'recurring' AND billing_interval IN ('month', 'year'))",
    )


def downgrade() -> None:
    op.drop_constraint("ck_pricings_billing_interval", "pricings", type_="check")
    op.create_check_constraint(
        "ck_pricings_billing_interval",
        "pricings",
        "(billing_type IN ('free', 'one_time') AND billing_interval IS NULL) OR "
        "(billing_type = 'recurring' AND billing_interval IN ('day', 'month'))",
    )
