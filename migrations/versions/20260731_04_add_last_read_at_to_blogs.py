"""add last_read_at to blogs

Revision ID: 20260731_04
Revises: 20260731_03
Create Date: 2026-07-31 15:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260731_04'
down_revision: Union[str, None] = '20260731_03b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'blogs',
        sa.Column('last_read_at', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('blogs', 'last_read_at')
