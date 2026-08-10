"""Add categorized processing error codes to meetings.

Revision ID: 20260807_01
Revises: 20260806_01
"""

from alembic import op
import sqlalchemy as sa


revision = "20260807_01"
down_revision = "20260806_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("meetings", sa.Column("error_code", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("meetings", "error_code")
