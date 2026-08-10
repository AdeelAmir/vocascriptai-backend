"""Bootstrap schema and replace startup auth migration with Alembic.

Revision ID: 20260729_01
Revises:
Create Date: 2026-07-29 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260729_01"
down_revision = None
branch_labels = None
depends_on = None


def _inspect(bind: sa.Connection) -> sa.Inspector:
    return sa.inspect(bind)


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _has_constraint(bind: sa.Connection, table_name: str, constraint_name: str) -> bool:
    result = bind.execute(
        text(
            """
            SELECT 1
            FROM pg_constraint
            WHERE conname = :constraint_name
              AND conrelid = to_regclass(:table_name)
            """
        ),
        {"constraint_name": constraint_name, "table_name": table_name},
    )
    return result.scalar_one_or_none() is not None


def _drop_email_unique_constraints(inspector: sa.Inspector) -> None:
    for unique_constraint in inspector.get_unique_constraints("users"):
        column_names = unique_constraint.get("column_names") or []
        constraint_name = unique_constraint.get("name")
        if column_names == ["email"] and constraint_name:
            op.drop_constraint(constraint_name, "users", type_="unique")


def _drop_foreign_keys_referencing_admins(bind: sa.Connection) -> None:
    bind.execute(
        text(
            """
            DO $$
            DECLARE constraint_record RECORD;
            BEGIN
                FOR constraint_record IN
                    SELECT conname, conrelid::regclass AS table_name
                    FROM pg_constraint
                    WHERE confrelid = 'admins'::regclass
                      AND contype = 'f'
                LOOP
                    EXECUTE format(
                        'ALTER TABLE %s DROP CONSTRAINT %I',
                        constraint_record.table_name,
                        constraint_record.conname
                    );
                END LOOP;
            END $$;
            """
        )
    )


def _create_settings_table() -> None:
    op.create_table(
        "settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_settings_key", "settings", ["key"], unique=True)


def _create_users_table() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("first_name", sa.String(), nullable=False),
        sa.Column("last_name", sa.String(), nullable=False),
        sa.Column("password", sa.String(), nullable=False),
        sa.Column("role", sa.Integer(), server_default="2", nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("subscription_tier", sa.String(), nullable=False),
        sa.Column("subscription_status", sa.String(), nullable=False),
        sa.Column("subscription_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("monthly_video_count", sa.Integer(), nullable=False),
        sa.Column("usage_reset_date", sa.Date(), nullable=False),
        sa.Column("paddle_subscription_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("role IN (1, 2)", name="ck_users_role"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True)


def _create_meetings_table() -> None:
    op.create_table(
        "meetings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ip_address", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("file_name", sa.String(), nullable=False),
        sa.Column("file_type", sa.String(), nullable=False),
        sa.Column("file_duration", sa.Float(), nullable=True),
        sa.Column("file_size", sa.Float(), nullable=True),
        sa.Column("b2_file_key", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("transcript", sa.JSON(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("action_items", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def _create_email_verification_tokens_table() -> None:
    op.create_table(
        "email_verification_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )


def _create_password_reset_tokens_table() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )


def _create_user_refresh_tokens_table() -> None:
    op.create_table(
        "user_refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )


def _create_final_schema(inspector: sa.Inspector) -> None:
    if not _has_table(inspector, "settings"):
        _create_settings_table()
        inspector = _inspect(op.get_bind())
    if not _has_table(inspector, "users"):
        _create_users_table()
        inspector = _inspect(op.get_bind())
    if not _has_table(inspector, "meetings"):
        _create_meetings_table()
        inspector = _inspect(op.get_bind())
    if not _has_table(inspector, "email_verification_tokens"):
        _create_email_verification_tokens_table()
        inspector = _inspect(op.get_bind())
    if not _has_table(inspector, "password_reset_tokens"):
        _create_password_reset_tokens_table()
        inspector = _inspect(op.get_bind())
    if not _has_table(inspector, "user_refresh_tokens"):
        _create_user_refresh_tokens_table()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = _inspect(bind)
    _create_final_schema(inspector)
    inspector = _inspect(bind)

    if _has_table(inspector, "users"):
        if not _has_column(inspector, "users", "password") and _has_column(inspector, "users", "hashed_password"):
            op.execute("ALTER TABLE users RENAME COLUMN hashed_password TO password")
        elif _has_column(inspector, "users", "password") and _has_column(inspector, "users", "hashed_password"):
            op.execute("UPDATE users SET password = hashed_password WHERE password IS NULL")
            op.execute("ALTER TABLE users DROP COLUMN hashed_password")

        inspector = _inspect(bind)

        if not _has_column(inspector, "users", "role"):
            op.execute("ALTER TABLE users ADD COLUMN role INTEGER NOT NULL DEFAULT 2")
        else:
            op.execute("UPDATE users SET role = 2 WHERE role IS NULL")

        op.execute("UPDATE users SET role = 2 WHERE role NOT IN (1, 2)")
        op.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 2")
        op.execute("ALTER TABLE users ALTER COLUMN role SET NOT NULL")
        op.execute("ALTER TABLE users ALTER COLUMN password SET NOT NULL")

        duplicate_email = bind.execute(
            text(
                """
                SELECT lower(email)
                FROM users
                GROUP BY lower(email)
                HAVING COUNT(*) > 1
                """
            )
        ).scalar_one_or_none()
        if duplicate_email is not None:
            raise RuntimeError(
                f"Duplicate user email found during migration: '{duplicate_email}'"
            )

        if not _has_constraint(bind, "users", "ck_users_role"):
            op.execute("ALTER TABLE users ADD CONSTRAINT ck_users_role CHECK (role IN (1, 2))")

        inspector = _inspect(bind)
        _drop_email_unique_constraints(inspector)

        inspector = _inspect(bind)
        if not _has_index(inspector, "users", "uq_users_email_lower"):
            op.execute("CREATE UNIQUE INDEX uq_users_email_lower ON users (lower(email))")

    inspector = _inspect(bind)
    if _has_table(inspector, "refresh_tokens"):
        op.execute("DROP TABLE refresh_tokens")

    inspector = _inspect(bind)
    if _has_table(inspector, "admins"):
        _drop_foreign_keys_referencing_admins(bind)
        op.execute("DROP TABLE admins")

    inspector = _inspect(bind)
    if _has_table(inspector, "schema_migrations"):
        op.execute("DROP TABLE schema_migrations")


def downgrade() -> None:
    raise RuntimeError(
        "Downgrade is not supported for the bootstrap migration because it consolidates legacy auth tables."
    )
