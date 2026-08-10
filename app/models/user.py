import uuid
from datetime import datetime, date

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, func, Integer, Date, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN (1, 2)", name="ck_users_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String, nullable=False)
    first_name: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[str] = mapped_column(String, nullable=False)
    # The value is bcrypt-hashed; only the column name is intentionally generic.
    password: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[int] = mapped_column(Integer, default=2, server_default="2", nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    monthly_video_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    usage_reset_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


Index("uq_users_email_lower", func.lower(User.email), unique=True)
