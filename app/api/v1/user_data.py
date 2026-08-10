from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_admin
from app.models.meeting import Meeting

router = APIRouter()


@router.get("/userdata")
async def user_data(
    _: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    search: str = Query("", max_length=200),
):
    query = select(
        Meeting.id,
        Meeting.title,
        Meeting.file_name,
        Meeting.ip_address,
        Meeting.status,
        Meeting.error_code,
        Meeting.error_message,
        Meeting.created_at,
    )

    # Server-side search filter
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            Meeting.title.ilike(search_pattern)
            | Meeting.file_name.ilike(search_pattern)
            | Meeting.ip_address.ilike(search_pattern)
        )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Apply pagination
    offset = (page - 1) * limit
    query = query.order_by(Meeting.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    rows = result.all()

    total_pages = max(1, (total + limit - 1) // limit)

    return {
        "data": [
            {
                "id": str(row.id),
                "title": row.title,
                "file_name": row.file_name,
                "ip_address": row.ip_address,
                "status": row.status,
                "error_code": row.error_code,
                "error_message": row.error_message,
                "created_at": row.created_at,
            }
            for row in rows
        ],
        "page": page,
        "limit": limit,
        "total": total,
        "total_pages": total_pages,
    }


@router.get("/userdata/{meeting_id}")
async def user_data_detail(
    meeting_id: str,
    _: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    meeting = result.scalar_one_or_none()

    if meeting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    return {
        "id": str(meeting.id),
        "ip_address": meeting.ip_address,
        "title": meeting.title,
        "file_name": meeting.file_name,
        "file_type": meeting.file_type,
        "file_duration": meeting.file_duration,
        "file_size": meeting.file_size,
        "status": meeting.status,
        "transcript": meeting.transcript,
        "summary": meeting.summary,
        "action_items": meeting.action_items,
        "error_code": meeting.error_code,
        "error_message": meeting.error_message,
        "created_at": meeting.created_at,
        "updated_at": meeting.updated_at,
    }
