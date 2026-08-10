import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Query
from sqlalchemy import select, func, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.blog import Blog, BlogCategory, BlogTag, blog_tag_association
from app.schemas.blog import (
    BlogCreate,
    BlogUpdate,
    BlogResponse,
    BlogListResponse,
    CategoryCreate,
    CategoryUpdate,
    CategoryResponse,
    TagCreate,
    TagResponse,
)

router = APIRouter()

UPLOAD_DIR = os.path.join(os.getcwd(), "uploads", "blogs")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


# ==================== IMAGE UPLOAD ====================

@router.post("/admin/blogs/upload-image")
async def upload_blog_image(file: UploadFile = File(...)) -> dict[str, str]:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are allowed.")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image file size cannot exceed 10MB.")

    ext = os.path.splitext(file.filename or "")[1] or ".jpg"
    filename = f"{uuid.uuid4()}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    with open(filepath, "wb") as f:
        f.write(content)

    return {"url": f"/uploads/blogs/{filename}"}


# ==================== CATEGORIES & TAGS ====================

@router.get("/admin/categories", response_model=list[CategoryResponse])
async def get_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(BlogCategory).order_by(BlogCategory.name))
    return result.scalars().all()


@router.post("/admin/categories", response_model=CategoryResponse)
async def create_category(payload: CategoryCreate, db: AsyncSession = Depends(get_db)):
    if not payload.name or not payload.name.strip():
        raise HTTPException(status_code=400, detail="Category name cannot be empty.")

    slug = slugify(payload.slug or payload.name)
    existing = await db.execute(select(BlogCategory).where(BlogCategory.slug == slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Category with this name already exists.")

    category = BlogCategory(name=payload.name.strip(), slug=slug, parent_id=payload.parent_id)
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


@router.put("/admin/categories/{category_id}", response_model=CategoryResponse)
async def update_category(category_id: uuid.UUID, payload: CategoryUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(BlogCategory).where(BlogCategory.id == category_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found.")

    if payload.parent_id and payload.parent_id == category_id:
        raise HTTPException(status_code=400, detail="A category cannot be its own parent.")

    if payload.name is not None and payload.name.strip():
        new_slug = slugify(payload.slug or payload.name)
        existing = await db.execute(
            select(BlogCategory).where(BlogCategory.slug == new_slug, BlogCategory.id != category_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Another category with this name already exists.")
        cat.name = payload.name.strip()
        cat.slug = new_slug

    if payload.parent_id is not None:
        cat.parent_id = payload.parent_id

    await db.commit()
    await db.refresh(cat)
    return cat


@router.delete("/admin/categories/{category_id}")
async def delete_category(category_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(BlogCategory).where(BlogCategory.id == category_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found.")
    await db.delete(cat)
    await db.commit()
    return {"message": "Category deleted successfully"}


@router.get("/admin/tags", response_model=list[TagResponse])
async def get_tags(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(BlogTag).order_by(BlogTag.name))
    return result.scalars().all()


@router.post("/admin/tags", response_model=TagResponse)
async def create_tag(payload: TagCreate, db: AsyncSession = Depends(get_db)):
    if not payload.name or not payload.name.strip():
        raise HTTPException(status_code=400, detail="Tag name cannot be empty.")

    slug = slugify(payload.slug or payload.name)
    existing = await db.execute(select(BlogTag).where(BlogTag.slug == slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Tag with this name already exists.")

    tag = BlogTag(name=payload.name.strip(), slug=slug)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return tag


@router.put("/admin/tags/{tag_id}", response_model=TagResponse)
async def update_tag(tag_id: uuid.UUID, payload: TagCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(BlogTag).where(BlogTag.id == tag_id))
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found.")

    if not payload.name or not payload.name.strip():
        raise HTTPException(status_code=400, detail="Tag name cannot be empty.")

    new_slug = slugify(payload.slug or payload.name)
    existing = await db.execute(
        select(BlogTag).where(BlogTag.slug == new_slug, BlogTag.id != tag_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Another tag with this name already exists.")

    tag.name = payload.name.strip()
    tag.slug = new_slug

    await db.commit()
    await db.refresh(tag)
    return tag


@router.delete("/admin/tags/{tag_id}")
async def delete_tag(tag_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(BlogTag).where(BlogTag.id == tag_id))
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found.")
    await db.delete(tag)
    await db.commit()
    return {"message": "Tag deleted successfully"}


# ==================== PUBLIC BLOG ROUTES ====================

@router.get("/blogs", response_model=BlogListResponse)
async def get_public_blogs(
    search: str | None = None,
    category_slug: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Blog)
        .options(selectinload(Blog.category), selectinload(Blog.tags))
        .where(Blog.status == "published")
    )

    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                Blog.title.ilike(search_pattern),
                Blog.excerpt.ilike(search_pattern),
                Blog.content.ilike(search_pattern),
            )
        )

    if category_slug:
        query = query.join(Blog.category).where(BlogCategory.slug == category_slug)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar_one()

    query = query.order_by(Blog.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    blogs = result.scalars().all()

    return BlogListResponse(total=total, items=[BlogResponse.model_validate(b) for b in blogs])


@router.get("/blogs/{slug}", response_model=BlogResponse)
async def get_public_blog_by_slug(slug: str, db: AsyncSession = Depends(get_db)):
    conditions = [Blog.slug == slug]
    try:
        val_uuid = uuid.UUID(slug)
        conditions.append(Blog.id == val_uuid)
    except ValueError:
        pass

    result = await db.execute(
        select(Blog)
        .options(selectinload(Blog.category), selectinload(Blog.tags))
        .where(or_(*conditions), Blog.status == "published")
    )
    blog = result.scalar_one_or_none()
    if not blog:
        raise HTTPException(status_code=404, detail="Blog post not found.")

    blog.last_read_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(blog)

    return BlogResponse.model_validate(blog)


@router.post("/blogs/{slug}/read", response_model=BlogResponse)
async def mark_blog_as_read(slug: str, db: AsyncSession = Depends(get_db)):
    conditions = [Blog.slug == slug]
    try:
        val_uuid = uuid.UUID(slug)
        conditions.append(Blog.id == val_uuid)
    except ValueError:
        pass

    result = await db.execute(
        select(Blog)
        .options(selectinload(Blog.category), selectinload(Blog.tags))
        .where(or_(*conditions), Blog.status == "published")
    )
    blog = result.scalar_one_or_none()
    if not blog:
        raise HTTPException(status_code=404, detail="Blog post not found.")

    blog.last_read_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(blog)

    return BlogResponse.model_validate(blog)


# ==================== ADMIN BLOG CRUD ====================

@router.get("/admin/blogs", response_model=BlogListResponse)
async def get_admin_blogs(
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Blog).options(selectinload(Blog.category), selectinload(Blog.tags))

    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                Blog.title.ilike(search_pattern),
                Blog.excerpt.ilike(search_pattern),
            )
        )

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar_one()

    query = query.order_by(Blog.created_at.desc())
    result = await db.execute(query)
    blogs = result.scalars().all()

    return BlogListResponse(total=total, items=[BlogResponse.model_validate(b) for b in blogs])


@router.get("/admin/blogs/{blog_id}", response_model=BlogResponse)
async def get_admin_blog_by_id(blog_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Blog)
        .options(selectinload(Blog.category), selectinload(Blog.tags))
        .where(Blog.id == blog_id)
    )
    blog = result.scalar_one_or_none()
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found.")
    return BlogResponse.model_validate(blog)


@router.post("/admin/blogs", response_model=BlogResponse)
async def create_blog(payload: BlogCreate, db: AsyncSession = Depends(get_db)):
    if not payload.featured_image or not payload.featured_image.strip():
        raise HTTPException(status_code=400, detail="Featured image is required.")

    slug = slugify(payload.slug or payload.title)
    existing = await db.execute(select(Blog).where(Blog.slug == slug))
    if existing.scalar_one_or_none():
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    blog = Blog(
        title=payload.title,
        slug=slug,
        subtitle=payload.subtitle,
        excerpt=payload.excerpt,
        content=payload.content,
        quote=payload.quote,
        meta_description=payload.meta_description,
        featured_image=payload.featured_image,
        status=payload.status,
        blog_type=payload.blog_type,
        read_time=payload.read_time,
        author_name=payload.author_name,
        category_id=payload.category_id,
    )

    if payload.tag_ids:
        tags_result = await db.execute(select(BlogTag).where(BlogTag.id.in_(payload.tag_ids)))
        blog.tags = list(tags_result.scalars().all())

    db.add(blog)
    await db.commit()

    # Re-fetch with relationships loaded
    result = await db.execute(
        select(Blog)
        .options(selectinload(Blog.category), selectinload(Blog.tags))
        .where(Blog.id == blog.id)
    )
    saved_blog = result.scalar_one()
    return BlogResponse.model_validate(saved_blog)


@router.put("/admin/blogs/{blog_id}", response_model=BlogResponse)
async def update_blog(blog_id: uuid.UUID, payload: BlogUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Blog)
        .options(selectinload(Blog.category), selectinload(Blog.tags))
        .where(Blog.id == blog_id)
    )
    blog = result.scalar_one_or_none()
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found.")

    data = payload.model_dump(exclude_unset=True)

    if "slug" in data and data["slug"]:
        new_slug = slugify(data["slug"])
        if new_slug != blog.slug:
            existing = await db.execute(select(Blog).where(Blog.slug == new_slug, Blog.id != blog_id))
            if existing.scalar_one_or_none():
                new_slug = f"{new_slug}-{uuid.uuid4().hex[:6]}"
            blog.slug = new_slug
        del data["slug"]

    tag_ids = data.pop("tag_ids", None)
    if tag_ids is not None:
        tags_result = await db.execute(select(BlogTag).where(BlogTag.id.in_(tag_ids)))
        blog.tags = list(tags_result.scalars().all())

    for key, value in data.items():
        setattr(blog, key, value)

    await db.commit()

    # Re-fetch with relationships loaded
    refreshed = await db.execute(
        select(Blog)
        .options(selectinload(Blog.category), selectinload(Blog.tags))
        .where(Blog.id == blog_id)
    )
    return BlogResponse.model_validate(refreshed.scalar_one())


@router.delete("/admin/blogs/{blog_id}")
async def delete_blog(blog_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Blog).where(Blog.id == blog_id))
    blog = result.scalar_one_or_none()
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found.")

    await db.delete(blog)
    await db.commit()
    return {"message": "Blog deleted successfully"}
