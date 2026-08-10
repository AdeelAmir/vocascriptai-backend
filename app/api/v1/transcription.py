import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, AsyncSessionLocal
from app.models.meeting import Meeting
from app.services.settings_service import get_setting, get_keys
from app.services.transcription import normalize_language_code, transcribe_with_diarization_async
from app.services.by_youtube import get_audio_transcript, get_video_duration
from app.services.translation import translate_text, translate_list, translate_transcript, get_deepl_keys
from app.core.security import verify_token
from app.models.user import User
from app.services.groq_ai import agent as groq_agent, generate_prompt_items
from app.services.openai_ai import build_ai_agent
from app.services.pricing_entitlements import PricingEntitlementService, entitlement_from_pricing
from app.services.media_metadata import inspect_uploaded_media
from app.services.processing_errors import (
    ProcessingError,
    classify_processing_exception,
)
from app.models.pricing import Pricing

router = APIRouter()
ACCEPTED_FILE_TYPES = {"mp3", "mp4", "wav", "m4a", "mov", "avi", "mkv", "webm", "ogg", "aac"}
PROCESSING_JOB_TTL_SECONDS = 30 * 60


@dataclass
class ProcessingJob:
    id: str
    user_id: uuid.UUID | None
    title: str
    file_name: str
    file_type: str
    file_size: float | None
    file_duration: float | None
    ip_address: str | None
    status: str = "queued"
    error_code: str | None = None
    error_message: str | None = None
    created_at: float = 0.0
    created_at_datetime: datetime | None = None


# Processing state is intentionally ephemeral. A Meeting row is created only
# after the pipeline has produced both a transcript and a summary.
_PROCESSING_JOBS: dict[str, ProcessingJob] = {}


def _cleanup_processing_jobs() -> None:
    now = time.monotonic()
    expired_ids = [
        job_id
        for job_id, job in _PROCESSING_JOBS.items()
        if now - job.created_at > PROCESSING_JOB_TTL_SECONDS
    ]
    for job_id in expired_ids:
        _PROCESSING_JOBS.pop(job_id, None)


def _create_processing_job(**kwargs: Any) -> ProcessingJob:
    _cleanup_processing_jobs()
    job = ProcessingJob(
        id=str(uuid.uuid4()),
        created_at=time.monotonic(),
        created_at_datetime=datetime.now(timezone.utc),
        **kwargs,
    )
    _PROCESSING_JOBS[job.id] = job
    return job


def _set_job_status(job_id: str, status: str) -> None:
    job = _PROCESSING_JOBS.get(job_id)
    if job:
        job.status = status


async def _set_meeting_status(meeting_id: str, status: str) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
        meeting = result.scalar_one_or_none()
        if meeting:
            meeting.status = status
            await db.commit()


def _set_job_failure(job_id: str, error: ProcessingError) -> None:
    job = _PROCESSING_JOBS.get(job_id)
    if job:
        job.status = "failed"
        job.error_code = error.code
        job.error_message = error.public_message


def _has_successful_output(transcript: Any, summary: Any) -> bool:
    return isinstance(transcript, list) and bool(transcript) and isinstance(summary, str) and bool(summary.strip())


def processing_http_exception(error: ProcessingError) -> HTTPException:
    return HTTPException(status_code=error.http_status, detail=error.public_payload())

def chunk_text(text: str, max_chars: int = 6000) -> list[str]:
    lines = text.split("\n")
    chunks = []
    current = []
    size = 0
    for line in lines:
        if size + len(line) > max_chars and current:
            chunks.append("\n".join(current))
            current = []
            size = 0
        current.append(line)
        size += len(line)
    if current:
        chunks.append("\n".join(current))
    return chunks


async def summarize_transcript(
    transcript: list[dict[str, Any]],
    language_code: str,
    generate_prompts: bool,
    is_premium: bool = False,
    status_callback: Callable[[str], Awaitable[None]] | None = None,
) -> tuple[str, list[Any], list[str]]:
    language_code = normalize_language_code(language_code)
    
    def format_segment(seg: dict) -> str:
        if seg.get("speaker"):
            return f"[Speaker {seg['speaker']}] {seg['text']}"
        elif seg.get("start") is not None and seg.get("end") is not None:
            return f"[{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['text']}"
        else:
            return seg["text"]

    formatted_transcript = "\n".join(format_segment(seg) for seg in transcript)
    text_chunks = chunk_text(formatted_transcript)
    generation_errors: list[str] = []

    async def generate_with_groq() -> tuple[str, list[Any], list[str]]:
        """Generate both outputs with Groq, including key/provider failures."""
        groq_keys = await get_keys("GROQ_API_KEY")
        if not groq_keys:
            return "", [], ["Groq API keys are not configured."]

        print("[AI Provider] Groq | Model: llama-3.3-70b-versatile")
        partial_summaries: list[str] = []
        errors: list[str] = []

        try:
            for chunk in text_chunks:
                chunk_result: dict[str, Any] = await asyncio.to_thread(
                    groq_agent.invoke,
                    {
                        "text": chunk,
                        "generate_summary": True,
                        "summary_gen": "",
                        "keys": groq_keys,
                    },
                )
                if chunk_result.get("summary_gen"):
                    partial_summaries.append(chunk_result["summary_gen"])

            if len(text_chunks) == 1:
                summary = partial_summaries[0] if partial_summaries else ""
            else:
                combined_summaries_text = "\n\n".join(partial_summaries)
                merge_result = await asyncio.to_thread(
                    groq_agent.invoke,
                    {
                        "text": combined_summaries_text,
                        "generate_summary": True,
                        "summary_gen": "",
                        "keys": groq_keys,
                    },
                )
                summary = merge_result.get("summary_gen", "")
        except Exception as exc:
            summary = ""
            errors.append(f"Groq summary generation failed: {exc}")

        action_items: list[Any] = []
        if generate_prompts:
            if status_callback:
                await status_callback("generating_prompts")
            try:
                action_items = await asyncio.to_thread(
                    generate_prompt_items, formatted_transcript, groq_keys
                )
            except Exception as exc:
                errors.append(f"Groq action-item generation failed: {exc}")

        if not summary and not any("summary generation failed" in error for error in errors):
            errors.append("Groq returned an empty summary.")
        if generate_prompts and not action_items and not any("action-item generation failed" in error for error in errors):
            errors.append("Groq returned no action items for this transcript.")

        return summary, action_items, errors

    if is_premium:
        openai_key = await get_setting("OPENAI_API_KEY")
        openai_failed = False
        if openai_key:
            try:
                openai_model = await get_setting("OPENAI_MODEL") or "gpt-4o-mini"
                print(f"[AI Provider] OpenAI | Model: {openai_model}")
                openai_agent = build_ai_agent(openai_key, openai_model)

                result = await asyncio.to_thread(
                    openai_agent.invoke,
                    {
                        "text": formatted_transcript,
                        "want_summary": True,
                        "want_prompt": generate_prompts,
                        "generated_summary": "",
                        "generated_prompt": [],
                    }
                )
                summary = result.get("generated_summary", "")
                action_items = result.get("generated_prompt", [])
                if generate_prompts and status_callback:
                    await status_callback("generating_prompts")
                openai_errors = [
                    error for error in [result.get("summary_error"), result.get("prompt_error")]
                    if error
                ]
                openai_failed = (
                    bool(openai_errors)
                    or not summary
                    or (generate_prompts and not action_items)
                )
            except Exception as exc:
                print(f"[AI Provider] OpenAI failed; trying Groq fallback: {exc}")
                openai_failed = True
        else:
            print("[AI Provider] OpenAI key is not configured; trying Groq fallback")
            openai_failed = True

        if openai_failed:
            summary, action_items, generation_errors = await generate_with_groq()

    else:
        summary, action_items, generation_errors = await generate_with_groq()

    if language_code not in {"en", "auto"}:
        deepl_keys = await get_deepl_keys()
        if summary:
            summary = await asyncio.to_thread(translate_text, summary, language_code, deepl_keys)
        if action_items:
            action_items = await asyncio.to_thread(translate_list, action_items, language_code, deepl_keys)

    return summary, action_items, generation_errors


# *********************************** UPLOAD BY SYSTEM ****************************************

@router.post("/process")
async def process_meeting(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile,
    language_code: str = Form(default="auto"),
    generate_prompts: bool = Form(default=True),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    language_code = normalize_language_code(language_code)

    # Resolve the authenticated user. Entitlement and usage rules are centralized
    # in PricingEntitlementService so every plan behaves consistently.
    current_user = None
    is_admin = False
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        payload = verify_token(token)
        if payload:
            if payload.get("type") == "admin":
                is_admin = True
            elif payload.get("type") == "user":
                user_id = payload.get("sub")
                user_result = await db.execute(select(User).where(User.id == user_id))
                current_user = user_result.scalar_one_or_none()
                if current_user is not None and not current_user.is_active:
                    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is inactive")
    extension = (file.filename or "").rsplit(".", 1)[-1].lower()
    if extension not in ACCEPTED_FILE_TYPES:
        error = ProcessingError(
            "UNSUPPORTED_OR_CORRUPTED_MEDIA",
            detail=f"unsupported uploaded extension: {extension or '[missing]'}",
        )
        raise processing_http_exception(error)

    file_content = await file.read()
    file_size_mb = len(file_content) / (1024 * 1024)
    if current_user:
        entitlement = await PricingEntitlementService.can_process_video(
            current_user, {"file_size_mb": file_size_mb}, db
        )
        if language_code not in {"en", "auto"}:
            if entitlement.capabilities.get("transcript_language_mode") != "all":
                raise HTTPException(status_code=403, detail="This plan supports English transcription only.")
            if entitlement.capabilities.get("summary_language_mode") != "all":
                raise HTTPException(status_code=403, detail="This plan supports English summaries only.")
    else:
        starter = (await db.execute(select(Pricing).where(Pricing.slug == "starter"))).scalar_one_or_none()
        entitlement = entitlement_from_pricing(starter) if starter else None
        if entitlement and not entitlement.max_file_size_unlimited and entitlement.max_file_size_mb is not None and file_size_mb > entitlement.max_file_size_mb:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File size exceeds maximum allowed size of {entitlement.max_file_size_mb:g}MB",
            )
    try:
        media = await inspect_uploaded_media(file_content, file.filename)
    except ProcessingError as exc:
        raise processing_http_exception(exc) from exc

    duration_minutes = media.duration_minutes
    if current_user:
        entitlement = await PricingEntitlementService.can_process_video(
            current_user, {"file_size_mb": file_size_mb, "duration_minutes": duration_minutes}, db
        )
    elif entitlement and duration_minutes is not None and not entitlement.max_duration_unlimited and entitlement.max_duration_minutes is not None and duration_minutes > entitlement.max_duration_minutes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Video duration exceeds the {entitlement.max_duration_minutes:g} minute limit.",
        )
    print(f"[1/5] File received: ({file_size_mb:.2f} MB)")

    forwarded = request.headers.get("x-forwarded-for")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    visitor_id_header = request.headers.get("x-visitor-id") or request.cookies.get("briefroom_visitor_id")

    assigned_visitor_id = None
    if is_admin:
        # Administrators have unlimited processing and must not consume the
        # anonymous guest quota when their token is used for uploads.
        pass
    elif current_user and entitlement:
        await PricingEntitlementService.reserve_usage(current_user, entitlement, db)
    else:
        assigned_visitor_id = await PricingEntitlementService.reserve_guest_usage(visitor_id_header, client_ip, entitlement, db)

    # Usage reservations are committed independently of the Meeting. The
    # processing attempt itself must not be persisted before it succeeds.
    await db.commit()
    job = _create_processing_job(
        user_id=current_user.id if current_user else None,
        title=file.filename or "Untitled",
        file_name=file.filename or "unknown",
        file_type=extension,
        file_size=round(file_size_mb, 2),
        file_duration=round(media.duration_minutes * 60, 2) if media.duration_minutes is not None else None,
        ip_address=client_ip,
    )

    background_tasks.add_task(
        run_transcription_pipeline_deferred,
        job.id,
        file_content,
        language_code,
        generate_prompts,
        bool(entitlement and entitlement.capabilities.get("ai_model") == "powerful") or is_admin,
        bool(entitlement and entitlement.capabilities.get("prompts_enabled")) or is_admin,
    )

    res_data = {"success": True, "data": {"meeting_id": job.id}}
    if assigned_visitor_id:
        res_data["data"]["visitor_id"] = str(assigned_visitor_id)
    return res_data


async def _legacy_run_transcription_pipeline(
    meeting_id: str,
    file_content: bytes,
    language_code: str,
    generate_prompts: bool,
    is_premium: bool = False,
    prompts_enabled: bool = False,
) -> None:
    from app.core.database import db_execute

    # Step 1: Fetch meeting with fresh session
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
        meeting = result.scalar_one_or_none()
        if meeting is None:
            print(f"[ERROR] Meeting {meeting_id} not found for background pipeline")
            return

    try:
        # Step 2: Transcribe (long running — no DB session held)
        transcript: list[dict[str, Any]] = await transcribe_with_diarization_async(
            file_content, meeting_id, language_code
        )

        # Step 3: Mark summary generation as active.
        await _set_meeting_status(meeting_id, "generating_summary")


        # effective_generate_prompts = generate_prompts if is_premium else False
        # summary, action_items = await summarize_transcript(transcript, language_code, effective_generate_prompts, is_premium)

        # Step 4: AI summarization (long running — no DB session held)
        effective_generate_prompts = generate_prompts and prompts_enabled

        async def update_meeting_status(next_status: str) -> None:
            await _set_meeting_status(meeting_id, next_status)

        summary, action_items, generation_errors = await summarize_transcript(
            transcript,
            language_code,
            effective_generate_prompts,
            is_premium,
            status_callback=update_meeting_status,
        )

        if language_code not in {"en", "auto"}:
            deepl_keys = await get_deepl_keys()
            transcript = await asyncio.to_thread(translate_transcript, transcript, language_code, deepl_keys)

        file_duration: float | None = None
        if transcript:
            file_duration = round(transcript[-1]["end"] / 60, 2)

        # Step 5: Save results with fresh session
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
            meeting = result.scalar_one_or_none()
            if meeting:
                meeting.status = "completed_with_errors" if generation_errors else "completed"
                meeting.transcript = transcript
                meeting.summary = summary
                meeting.action_items = action_items
                meeting.error_code = "NETWORK_OR_PROVIDER_ERROR" if generation_errors else None
                meeting.error_message = (
                    "The summary service could not complete all AI-generated results. Please try again later."
                    if generation_errors
                    else None
                )
                meeting.file_duration = file_duration
                await db.commit()

        # Usage is reserved atomically when the upload is accepted. Processing
        # completion does not increment a second legacy counter.

    except Exception as e:
        processing_error = classify_processing_exception(e)
        import traceback
        traceback.print_exc()
        print(f"[ERROR] Pipeline failed for meeting {meeting_id}: {e}")
        
        # Mark as error with fresh session
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
            meeting = result.scalar_one_or_none()
            if meeting:
                meeting.status = "error"
                meeting.error_code = processing_error.code
                meeting.error_message = processing_error.public_message
                if "transcript" in locals():
                    meeting.transcript = transcript
                if "summary" in locals():
                    meeting.summary = summary
                if "action_items" in locals():
                    meeting.action_items = action_items
                await db.commit()


# *********************************** UPLOAD BY YOUTUBE_URL ****************************************


async def run_transcription_pipeline_deferred(
    meeting_id: str,
    file_content: bytes,
    language_code: str,
    generate_prompts: bool,
    is_premium: bool = False,
    prompts_enabled: bool = False,
) -> None:
    """Process a job and insert its Meeting row only after complete success."""
    try:
        _set_job_status(meeting_id, "transcribing")
        transcript = await transcribe_with_diarization_async(file_content, meeting_id, language_code)

        _set_job_status(meeting_id, "generating_summary")
        effective_generate_prompts = generate_prompts and prompts_enabled

        async def update_job_status(next_status: str) -> None:
            _set_job_status(meeting_id, next_status)

        summary, action_items, generation_errors = await summarize_transcript(
            transcript,
            language_code,
            effective_generate_prompts,
            is_premium,
            status_callback=update_job_status,
        )

        if language_code not in {"en", "auto"}:
            deepl_keys = await get_deepl_keys()
            transcript = await asyncio.to_thread(translate_transcript, transcript, language_code, deepl_keys)

        if generation_errors or not _has_successful_output(transcript, summary):
            raise ProcessingError(
                "NETWORK_OR_PROVIDER_ERROR",
                detail="Processing did not produce both a transcript and a summary",
            )

        job = _PROCESSING_JOBS.get(meeting_id)
        if job is None:
            return

        file_duration = job.file_duration
        if transcript:
            file_duration = round(transcript[-1]["end"], 2)

        async with AsyncSessionLocal() as db:
            db.add(Meeting(
                id=uuid.UUID(meeting_id),
                title=job.title,
                file_name=job.file_name,
                file_type=job.file_type,
                file_size=job.file_size,
                file_duration=file_duration,
                status="completed",
                ip_address=job.ip_address,
                user_id=job.user_id,
                transcript=transcript,
                summary=summary,
                action_items=action_items,
            ))
            await db.commit()
        _PROCESSING_JOBS.pop(meeting_id, None)
    except Exception as exc:
        processing_error = classify_processing_exception(exc)
        import traceback
        traceback.print_exc()
        print(f"[ERROR] Deferred pipeline failed for {meeting_id}: {exc}")
        _set_job_failure(meeting_id, processing_error)

@router.post("/process_youtube")
async def process_youtube(
    request: Request,
    background_tasks: BackgroundTasks,
    youtube_url: str = Form(...),
    language_code: str = Form(default="auto"),
    generate_prompt: bool = Form(default=True),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    language_code = normalize_language_code(language_code)

    # Only premium users and admins can use YouTube feature
    current_user = None
    is_admin = False
    entitlement = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        payload = verify_token(token)
        if payload:
            if payload.get("type") == "admin":
                is_admin = True
            elif payload.get("type") == "user":
                user_id = payload.get("sub")
                user_result = await db.execute(select(User).where(User.id == user_id))
                current_user = user_result.scalar_one_or_none()
                if current_user is not None and not current_user.is_active:
                    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is inactive")
                if current_user and current_user.is_active:
                    entitlement = await PricingEntitlementService.get_current_entitlement(current_user, db)

    if not is_admin:
        if current_user is None or entitlement is None or not entitlement.capabilities.get("youtube_enabled", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="YouTube transcription is available for paid plans only. Please upgrade to access this feature.",
            )

    try:
        actual_duration_seconds = await get_video_duration(youtube_url)
    except ProcessingError as exc:
        raise processing_http_exception(exc) from exc
    actual_duration_minutes = round(actual_duration_seconds / 60, 2)
    if current_user and entitlement:
        if language_code not in {"en", "auto"}:
            if entitlement.capabilities.get("transcript_language_mode") != "all":
                raise HTTPException(status_code=403, detail="This plan supports English transcription only.")
            if entitlement.capabilities.get("summary_language_mode") != "all":
                raise HTTPException(status_code=403, detail="This plan supports English summaries only.")
        await PricingEntitlementService.can_process_video(
            current_user, {"duration_minutes": actual_duration_minutes}, db
        )
        await PricingEntitlementService.reserve_usage(current_user, entitlement, db)

    forwarded = request.headers.get("x-forwarded-for")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")

    await db.commit()
    job = _create_processing_job(
        user_id=current_user.id if current_user else None,
        title=youtube_url,
        file_name=youtube_url,
        file_type="youtube",
        file_size=0,
        file_duration=actual_duration_seconds,
        ip_address=client_ip,
    )

    background_tasks.add_task(
        run_youtube_pipeline_deferred,
        job.id,
        youtube_url,
        language_code,
        generate_prompt,
        bool(entitlement and entitlement.capabilities.get("ai_model") == "powerful") or is_admin,
        bool(entitlement and entitlement.capabilities.get("prompts_enabled")),
    )

    return {"success": True, "data": {"meeting_id": job.id}}




async def _legacy_run_youtube_pipeline(
    meeting_id: str,
    youtube_url: str,
    language_code: str,
    generate_prompts: bool,
    is_premium: bool = False,
    prompts_enabled: bool = False,
) -> None:
    # Step 1: Fetch meeting with fresh session
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
        meeting = result.scalar_one_or_none()
        if meeting is None:
            print(f"[ERROR] Meeting {meeting_id} not found for background pipeline")
            return

    try:
        # Step 2: Fetch YouTube transcript (long running — no DB session held)
        result_data = await get_audio_transcript(youtube_url)

        if not result_data.get("available"):
            raise ProcessingError(
                "NO_AUDIO_OR_SPEECH",
                message="No captions or spoken transcript were found for this YouTube video. Please use a video with clear spoken audio.",
                detail="YouTube transcript provider returned no content",
            )

        transcript: list[dict[str, Any]] = result_data["transcript"]

        # Step 3: Mark summary generation as active.
        await _set_meeting_status(meeting_id, "generating_summary")


        # if language_code != "en":
        #     deepl_keys = await get_deepl_keys()
        #     transcript = await asyncio.to_thread(translate_transcript, transcript, language_code, deepl_keys)

        # effective_generate_prompts = generate_prompts if is_premium else False
        # summary, action_items = await summarize_transcript(transcript, language_code, effective_generate_prompts, is_premium)


        # Step 4: AI summarization (long running — no DB session held)
        effective_generate_prompts = generate_prompts and prompts_enabled
        summary, action_items, generation_errors = await summarize_transcript(
            transcript,
            language_code,
            effective_generate_prompts,
            is_premium,
            status_callback=lambda next_status: _set_meeting_status(meeting_id, next_status),
        )

        # Step 5: Translate transcript if a manual target language was selected
        if language_code not in {"en", "auto"}:
            deepl_keys = await get_deepl_keys()
            transcript = await asyncio.to_thread(translate_transcript, transcript, language_code, deepl_keys)

        # Step 6: Save results with fresh session
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
            meeting = result.scalar_one_or_none()
            if meeting:
                meeting.status = "completed_with_errors" if generation_errors else "completed"
                meeting.transcript = transcript
                meeting.summary = summary
                meeting.action_items = action_items
                meeting.error_code = "NETWORK_OR_PROVIDER_ERROR" if generation_errors else None
                meeting.error_message = (
                    "The summary service could not complete all AI-generated results. Please try again later."
                    if generation_errors
                    else None
                )
                await db.commit()

    except Exception as e:
        processing_error = classify_processing_exception(e)
        import traceback
        traceback.print_exc()
        print(f"[ERROR] YouTube pipeline failed for meeting {meeting_id}: {e}")
        # Mark as failed with fresh session
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
            meeting = result.scalar_one_or_none()
            if meeting:
                meeting.status = "failed"
                meeting.error_code = processing_error.code
                meeting.error_message = processing_error.public_message
                if "transcript" in locals():
                    meeting.transcript = transcript
                if "summary" in locals():
                    meeting.summary = summary
                if "action_items" in locals():
                    meeting.action_items = action_items
                await db.commit()


# *************************************** GET USER TRANSCRIPTS *****************************************


async def run_youtube_pipeline_deferred(
    meeting_id: str,
    youtube_url: str,
    language_code: str,
    generate_prompts: bool,
    is_premium: bool = False,
    prompts_enabled: bool = False,
) -> None:
    """Process YouTube input without persisting an incomplete Meeting row."""
    try:
        _set_job_status(meeting_id, "transcribing")
        result_data = await get_audio_transcript(youtube_url)
        if not result_data.get("available"):
            raise ProcessingError(
                "NO_AUDIO_OR_SPEECH",
                message="No captions or spoken transcript were found for this YouTube video. Please use a video with clear spoken audio.",
                detail="YouTube transcript provider returned no content",
            )

        transcript = result_data.get("transcript") or []
        _set_job_status(meeting_id, "generating_summary")
        effective_generate_prompts = generate_prompts and prompts_enabled

        async def update_job_status(next_status: str) -> None:
            _set_job_status(meeting_id, next_status)

        summary, action_items, generation_errors = await summarize_transcript(
            transcript,
            language_code,
            effective_generate_prompts,
            is_premium,
            status_callback=update_job_status,
        )

        if language_code not in {"en", "auto"}:
            deepl_keys = await get_deepl_keys()
            transcript = await asyncio.to_thread(translate_transcript, transcript, language_code, deepl_keys)

        if generation_errors or not _has_successful_output(transcript, summary):
            raise ProcessingError(
                "NETWORK_OR_PROVIDER_ERROR",
                detail="Processing did not produce both a transcript and a summary",
            )

        job = _PROCESSING_JOBS.get(meeting_id)
        if job is None:
            return

        file_duration = job.file_duration
        if transcript:
            file_duration = round(transcript[-1]["end"], 2)

        async with AsyncSessionLocal() as db:
            db.add(Meeting(
                id=uuid.UUID(meeting_id),
                title=job.title,
                file_name=job.file_name,
                file_type=job.file_type,
                file_size=job.file_size,
                file_duration=file_duration,
                status="completed",
                ip_address=job.ip_address,
                user_id=job.user_id,
                transcript=transcript,
                summary=summary,
                action_items=action_items,
            ))
            await db.commit()
        _PROCESSING_JOBS.pop(meeting_id, None)
    except Exception as exc:
        processing_error = classify_processing_exception(exc)
        import traceback
        traceback.print_exc()
        print(f"[ERROR] Deferred YouTube pipeline failed for {meeting_id}: {exc}")
        _set_job_failure(meeting_id, processing_error)

@router.get("/my-transcripts")
async def get_my_transcripts(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    payload = verify_token(auth_header.split(" ", 1)[1])
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token.")
    
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User identity missing in token.")
    
    import uuid
    try:
        user_uuid = uuid.UUID(str(user_id_str))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user ID format.")

    is_admin_payload = payload.get("type") == "admin" and payload.get("role") == 1

    _cleanup_processing_jobs()
    meetings_query = (
        select(Meeting, User.email, User.first_name, User.last_name)
        .outerjoin(User, Meeting.user_id == User.id)
        .where(
            Meeting.status == "completed",
            Meeting.summary.is_not(None),
            Meeting.transcript.is_not(None),
        )
        .order_by(Meeting.created_at.desc())
    )
    if not is_admin_payload:
        meetings_query = meetings_query.where(Meeting.user_id == user_uuid)

    result = await db.execute(meetings_query)
    meetings = result.all()

    items = []
    for row in meetings:
        m, owner_email, owner_first_name, owner_last_name = row
        transcript_list = m.transcript if isinstance(m.transcript, list) else []
        action_items_list = m.action_items if isinstance(m.action_items, list) else []
        if not transcript_list or not isinstance(m.summary, str) or not m.summary.strip():
            continue
        items.append({
            "id": str(m.id),
            "title": m.title,
            "file_name": m.file_name,
            "file_type": m.file_type,
            "file_duration": m.file_duration,
            "file_size": m.file_size,
            "status": m.status,
            "error_code": m.error_code,
            "summary": m.summary or "",
            "error_message": m.error_message,
            "transcript_count": len(transcript_list),
            "action_items_count": len(action_items_list),
            "owner_name": (
                f"{owner_first_name or ''} {owner_last_name or ''}".strip() or None
            ),
            "owner_email": owner_email,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "updated_at": m.updated_at.isoformat() if m.updated_at else None,
        })

    active_statuses = {"queued", "transcribing", "summarizing", "generating_summary", "generating_prompts"}
    for job in _PROCESSING_JOBS.values():
        if (not is_admin_payload and job.user_id != user_uuid) or job.status not in active_statuses:
            continue
        created_at = job.created_at_datetime.isoformat() if job.created_at_datetime else None
        items.append({
            "id": job.id,
            "title": job.title,
            "file_name": job.file_name,
            "file_type": job.file_type,
            "file_duration": job.file_duration,
            "file_size": job.file_size,
            "status": job.status,
            "error_code": None,
            "summary": "",
            "error_message": None,
            "transcript_count": 0,
            "action_items_count": 0,
            "owner_name": None,
            "owner_email": None,
            "created_at": created_at,
            "updated_at": created_at,
        })

    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)

    return items


# *************************************** GET STATUS *****************************************

@router.get("/{meeting_id}/status")
async def get_meeting_status(
    meeting_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _cleanup_processing_jobs()
    transient_job = _PROCESSING_JOBS.get(meeting_id)
    if transient_job is not None:
        if transient_job.user_id is not None:
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication is required.")
            payload = verify_token(auth_header.split(" ", 1)[1])
            if payload is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token.")
            is_admin_payload = payload.get("type") == "admin" and payload.get("role") == 1
            is_owner_payload = payload.get("type") == "user" and str(transient_job.user_id) == str(payload.get("sub"))
            if not (is_admin_payload or is_owner_payload):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot access this meeting.")

        response: dict[str, Any] = {
            "status": transient_job.status,
            "error_code": transient_job.error_code,
        }
        if transient_job.status == "failed":
            response["error_message"] = transient_job.error_message
            # The client has received the error; remove the only transient
            # trace so failed attempts do not remain in application state.
            _PROCESSING_JOBS.pop(meeting_id, None)
        return response

    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    meeting = result.scalar_one_or_none()

    if meeting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    if meeting.user_id is not None:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication is required.")
        payload = verify_token(auth_header.split(" ", 1)[1])
        if payload is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token.")
        if payload.get("type") == "admin" and payload.get("role") == 1:
            pass
        elif payload.get("type") == "user" and payload.get("role") == 2:
            if str(meeting.user_id) != str(payload.get("sub")):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot access this meeting.")
        else:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    response: dict[str, Any] = {"status": meeting.status, "error_code": meeting.error_code}

    if meeting.status in {"completed", "completed_with_errors"}:
        response.update({
            "transcript": meeting.transcript,
            "summary": meeting.summary,
            "action_items": meeting.action_items,
        })
        if meeting.status == "completed_with_errors":
            response["error_message"] = meeting.error_message
    elif meeting.status in {"error", "failed"}:
        response["error_message"] = meeting.error_message

    return response


# *************************************** GET PDF *****************************************
