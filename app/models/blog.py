import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, Table, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


blog_tag_association = Table(
    "blog_tag_associations",
    Base.metadata,
    Column("blog_id", ForeignKey("blogs.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("blog_tags.id", ondelete="CASCADE"), primary_key=True),
)


class BlogCategory(Base):
    __tablename__ = "blog_categories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("blog_categories.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    parent: Mapped["BlogCategory | None"] = relationship(
        "BlogCategory", remote_side=[id], back_populates="children"
    )
    children: Mapped[list["BlogCategory"]] = relationship("BlogCategory", back_populates="parent")
    blogs: Mapped[list["Blog"]] = relationship("Blog", back_populates="category")


class BlogTag(Base):
    __tablename__ = "blog_tags"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    blogs: Mapped[list["Blog"]] = relationship(
        "Blog", secondary=blog_tag_association, back_populates="tags"
    )


class Blog(Base):
    __tablename__ = "blogs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    subtitle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    featured_image: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="published", server_default="published", nullable=False)
    blog_type: Mapped[str] = mapped_column(String(20), default="free", server_default="free", nullable=False)
    read_time: Mapped[str] = mapped_column(String(50), default="5 min read", server_default="5 min read", nullable=False)
    author_name: Mapped[str] = mapped_column(String(100), default="BriefRoom Team", server_default="BriefRoom Team", nullable=False)
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("blog_categories.id", ondelete="SET NULL"), nullable=True
    )
    category: Mapped[BlogCategory | None] = relationship("BlogCategory", back_populates="blogs")
    tags: Mapped[list[BlogTag]] = relationship("BlogTag", secondary=blog_tag_association, back_populates="blogs")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
