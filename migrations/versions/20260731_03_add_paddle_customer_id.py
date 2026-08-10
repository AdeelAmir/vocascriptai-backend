"""Add paddle_customer_id to users table.

Revision ID: 20260731_03
Revises: 20260730_02
Create Date: 2026-07-31 13:50:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260731_03"
down_revision = "20260730_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("paddle_customer_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "paddle_customer_id")
