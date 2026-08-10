"""Move subscription state from users into subscription history.

Revision ID: 20260801_04
Revises: 20260731_04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260801_04"
down_revision = "20260731_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("email_snapshot", sa.String(), nullable=False),
        sa.Column("paddle_subscription_id", sa.String(), nullable=True),
        sa.Column("paddle_customer_id", sa.String(), nullable=True),
        sa.Column("plan", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_webhook_occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_webhook_event_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("paddle_subscription_id", name="uq_subscriptions_paddle_subscription_id"),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])
    op.create_index("ix_subscriptions_created_at", "subscriptions", ["created_at"])

    op.execute(
        sa.text(
            """
            INSERT INTO subscriptions (
                id, user_id, email_snapshot, paddle_subscription_id,
                paddle_customer_id, plan, status, started_at, ends_at
            )
            SELECT
                gen_random_uuid(),
                id,
                email,
                NULLIF(BTRIM(paddle_subscription_id), ''),
                NULLIF(BTRIM(paddle_customer_id), ''),
                CASE
                    WHEN NULLIF(BTRIM(subscription_tier), '') IS NULL
                         OR subscription_tier = 'free' THEN 'premium'
                    ELSE subscription_tier
                END,
                CASE
                    WHEN NULLIF(BTRIM(subscription_status), '') IS NULL
                         OR (subscription_status = 'free' AND NULLIF(BTRIM(paddle_subscription_id), '') IS NOT NULL)
                        THEN CASE
                            WHEN NULLIF(BTRIM(paddle_subscription_id), '') IS NOT NULL THEN 'active'
                            ELSE 'canceled'
                        END
                    ELSE subscription_status
                END,
                NULL,
                subscription_ends_at
            FROM users
            WHERE NULLIF(BTRIM(paddle_subscription_id), '') IS NOT NULL
               OR COALESCE(subscription_tier, 'free') <> 'free'
               OR COALESCE(subscription_status, 'free') <> 'free'
            """
        )
    )

    for column in (
        "subscription_tier",
        "subscription_status",
        "subscription_ends_at",
        "paddle_subscription_id",
        "paddle_customer_id",
    ):
        op.drop_column("users", column)


def downgrade() -> None:
    raise RuntimeError("Downgrade is not supported after subscription data normalization.")
