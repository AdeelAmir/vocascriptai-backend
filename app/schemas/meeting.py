import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class MeetingStatus(StrEnum):
    uploading = "uploading"
    transcribing = "transcribing"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class TranscriptSegment(BaseModel):
    speaker_id: str
    label: str
    text: str
    start_time: float
    end_time: float


class ActionItem(BaseModel):
    type: str
    title: str
    description: str
    prompt: str


class MeetingCreate(BaseModel):
    title: str
    file_name: str
    file_type: str
    file_size: float | None = None
    user_id: uuid.UUID | None = None



class MeetingStatusUpdate(BaseModel):
    status: MeetingStatus
    error_code: str | None = None
    error_message: str | None = None


class MeetingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    file_name: str
    file_type: str
    file_duration: float | None = None
    file_size: float | None = None
    status: MeetingStatus
    transcript: list[TranscriptSegment] | None = None
    summary: str | None = None
    action_items: list[ActionItem] | None = None
    error_code: str | None = None
    share_token: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class MeetingListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    file_type: str
    file_duration: float | None = None
    status: MeetingStatus
    error_code: str | None = None
    error_message: str | None = None
    summary: str | None = None
    action_items: list[ActionItem] | None = None
    share_token: str | None = None
    created_at: datetime


__all__ = [
    "MeetingStatus",
    "TranscriptSegment",
    "ActionItem",
    "MeetingCreate",
    "MeetingStatusUpdate",
    "MeetingResponse",
    "MeetingListResponse",
]
