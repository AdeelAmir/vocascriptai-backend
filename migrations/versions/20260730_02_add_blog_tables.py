"""Add blog_categories, blog_tags, blog_tag_associations, and blogs tables.

Revision ID: 20260730_02
Revises: 20260729_01
Create Date: 2026-07-30 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260730_02"
down_revision = "20260729_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create blog_categories
    op.create_table(
        "blog_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("slug", sa.String(length=100), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_blog_categories_slug", "blog_categories", ["slug"])

    # 2. Create blog_tags
    op.create_table(
        "blog_tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("slug", sa.String(length=100), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_blog_tags_slug", "blog_tags", ["slug"])

    # 3. Create blogs
    op.create_table(
        "blogs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False, unique=True),
        sa.Column("subtitle", sa.String(length=255), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("meta_description", sa.String(length=255), nullable=True),
        sa.Column("featured_image", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="published", nullable=False),
        sa.Column("blog_type", sa.String(length=20), server_default="free", nullable=False),
        sa.Column("read_time", sa.String(length=50), server_default="5 min read", nullable=False),
        sa.Column("author_name", sa.String(length=100), server_default="BriefRoom Team", nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("blog_categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_blogs_slug", "blogs", ["slug"])

    # 4. Create blog_tag_associations
    op.create_table(
        "blog_tag_associations",
        sa.Column("blog_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("blogs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("blog_tags.id", ondelete="CASCADE"), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("blog_tag_associations")
    op.drop_index("ix_blogs_slug", table_name="blogs")
    op.drop_table("blogs")
    op.drop_index("ix_blog_tags_slug", table_name="blog_tags")
    op.drop_table("blog_tags")
    op.drop_index("ix_blog_categories_slug", table_name="blog_categories")
    op.drop_table("blog_categories")
