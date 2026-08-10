"""Add guest_visitors table for dual-key cookie and IP anonymous tracking.

Revision ID: 20260806_01
Revises: 20260803_02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260806_01"
down_revision = "20260803_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guest_visitors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("visitor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ip_address", sa.String(length=255), nullable=False),
        sa.Column("video_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("visitor_id", name="uq_guest_visitors_visitor_id"),
    )
    op.create_index("ix_guest_visitors_visitor_id", "guest_visitors", ["visitor_id"])
    op.create_index("ix_guest_visitors_ip_address", "guest_visitors", ["ip_address"])


def downgrade() -> None:
    op.drop_index("ix_guest_visitors_ip_address", table_name="guest_visitors")
    op.drop_index("ix_guest_visitors_visitor_id", table_name="guest_visitors")
    op.drop_table("guest_visitors")
