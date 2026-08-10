import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class CategoryBase(BaseModel):
    name: str = Field(..., max_length=100)
    slug: str | None = Field(None, max_length=100)
    parent_id: uuid.UUID | None = None


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: str | None = Field(None, max_length=100)
    slug: str | None = Field(None, max_length=100)
    parent_id: uuid.UUID | None = None


class CategoryResponse(CategoryBase):
    id: uuid.UUID
    slug: str
    parent_id: uuid.UUID | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TagBase(BaseModel):
    name: str = Field(..., max_length=100)
    slug: str | None = Field(None, max_length=100)


class TagCreate(TagBase):
    pass


class TagResponse(TagBase):
    id: uuid.UUID
    slug: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BlogBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    slug: str | None = Field(None, max_length=255)
    subtitle: str | None = Field(None, max_length=255)
    excerpt: str = Field(..., min_length=5)
    content: str = Field(..., min_length=5)
    quote: str | None = None
    meta_description: str | None = Field(None, max_length=255)
    featured_image: str | None = None
    status: str = Field("published", description="draft or published")
    blog_type: str = Field("free", description="free or premium")
    read_time: str = Field("5 min read", max_length=50)
    author_name: str = Field("BriefRoom Team", max_length=100)
    category_id: uuid.UUID | None = None
    tag_ids: list[uuid.UUID] = []


class BlogCreate(BlogBase):
    pass


class BlogUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    slug: str | None = Field(None, max_length=255)
    subtitle: str | None = Field(None, max_length=255)
    excerpt: str | None = None
    content: str | None = None
    quote: str | None = None
    meta_description: str | None = Field(None, max_length=255)
    featured_image: str | None = None
    status: str | None = None
    blog_type: str | None = None
    read_time: str | None = None
    author_name: str | None = None
    category_id: uuid.UUID | None = None
    tag_ids: list[uuid.UUID] | None = None


class BlogResponse(BaseModel):
    id: uuid.UUID
    title: str
    slug: str
    subtitle: str | None = None
    excerpt: str
    content: str
    quote: str | None = None
    meta_description: str | None = None
    featured_image: str | None = None
    status: str
    blog_type: str
    read_time: str
    author_name: str
    category_id: uuid.UUID | None = None
    category: CategoryResponse | None = None
    tags: list[TagResponse] = []
    last_read_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BlogListResponse(BaseModel):
    total: int
    items: list[BlogResponse]
