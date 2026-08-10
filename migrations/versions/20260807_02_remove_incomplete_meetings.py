"""Remove historical processing attempts that never produced usable output.

Revision ID: 20260807_02
Revises: 20260807_01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260807_02"
down_revision = "20260807_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        """
        DELETE FROM meetings
        WHERE status <> 'completed'
           OR summary IS NULL
           OR btrim(summary) = ''
           OR transcript IS NULL
           OR jsonb_typeof(transcript::jsonb) <> 'array'
           OR jsonb_array_length(
                CASE
                    WHEN jsonb_typeof(transcript::jsonb) = 'array' THEN transcript::jsonb
                    ELSE '[]'::jsonb
                END
              ) = 0
        """
    ))


def downgrade() -> None:
    # Deleted incomplete processing attempts cannot be restored.
    pass
