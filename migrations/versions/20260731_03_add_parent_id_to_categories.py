"""Add parent_id to blog_categories table.

Revision ID: 20260731_03b
Revises: 20260731_03
Create Date: 2026-07-31 13:40:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260731_03b"
down_revision = "20260731_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "blog_categories",
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("blog_categories.id", ondelete="SET NULL"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("blog_categories", "parent_id")
