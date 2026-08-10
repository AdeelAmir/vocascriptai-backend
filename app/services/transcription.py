import asyncio
import time

import assemblyai as aai
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker

from app.core.database import AsyncSessionLocal, get_sync_database_url
from app.models.settings import Setting
from app.models.meeting import Meeting
from sqlalchemy.pool import NullPool
from app.core.encryption import decrypt
from app.services.processing_errors import ProcessingError, classify_processing_exception

sync_db_url = get_sync_database_url()
sync_engine = create_engine(
    sync_db_url,
    connect_args={"sslmode": "require"},
    poolclass=NullPool,
)
SyncSessionLocal = sessionmaker(bind=sync_engine)

aai.settings.http_timeout = 1800.0  # 30 minutes

CURRENT_KEY_INDEX = 0

PLAIN_KEYS = ("MAX_FILE_SIZE_MB", "MAX_VIDEO_DURATION_MINUTES")


def normalize_language_code(language_code: str | None) -> str:
    """Return the ISO-639-1 code used consistently by all providers.

    The web client stores most language values as uppercase (for example,
    ``UR`` and ``FR``), while English is stored as ``en``.  Treating those
    values as different caused English to go through the translation path and
    made provider behaviour depend on the selected casing.
    """
    normalized = (language_code or "auto").strip().lower()
    return normalized.split("-", 1)[0] or "auto"

async def get_setting(key: str) -> str | None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()
        if not setting:
            return None
        return setting.value if key in PLAIN_KEYS else decrypt(setting.value)


async def get_keys(prefix: str) -> list[str]:
    keys = []
    for i in range(1, 4):
        value = await get_setting(f"{prefix}_{i}")
        if value:
            keys.append(value)
    return keys


def is_rate_limit_error(e: Exception) -> bool:
    error_text = str(e).lower()
    return any(phrase in error_text for phrase in [
        "rate limit",
        "rate_limit",
        "too many requests",
        "429",
        "quota exceeded",
    ])


def _raise_quality_or_language_error(transcript: object) -> None:
    detected_language = getattr(transcript, "language_code", None)
    language_confidence = getattr(transcript, "language_confidence", None)
    if isinstance(detected_language, str) and any(separator in detected_language for separator in (",", "/", "|")):
        raise ProcessingError(
            "MULTIPLE_OR_UNSUPPORTED_LANGUAGES",
            detail=f"provider detected multiple languages: {detected_language}",
        )
    if isinstance(language_confidence, (int, float)) and language_confidence < 0.35:
        raise ProcessingError(
            "MULTIPLE_OR_UNSUPPORTED_LANGUAGES",
            detail=f"provider language confidence was too low: {language_confidence}",
        )

    text = (getattr(transcript, "text", None) or "").strip()
    confidence = getattr(transcript, "confidence", None)
    words = getattr(transcript, "words", None) or []
    word_confidences = []
    for word in words:
        word_confidence = word.get("confidence") if isinstance(word, dict) else getattr(word, "confidence", None)
        if isinstance(word_confidence, (int, float)):
            word_confidences.append(float(word_confidence))
    if word_confidences:
        confidence = sum(word_confidences) / len(word_confidences)
    if isinstance(confidence, (int, float)) and confidence < 0.40 and len(text) >= 20:
        raise ProcessingError(
            "POOR_AUDIO_QUALITY",
            detail=f"provider confidence was too low: {confidence}",
        )


def update_meeting_status_sync(meeting_id: str, status: str) -> None:
    for attempt in range(3):
        try:
            with SyncSessionLocal() as db:
                db.execute(
                    update(Meeting).where(Meeting.id == meeting_id).values(status=status)
                )
                db.commit()
            return
        except Exception as e:
            print(f"[WARN] Status update attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                time.sleep(2)
            else:
                print(f"[ERROR] Failed to update meeting status after 3 attempts: {e}")


def transcribe_with_diarization(
    file_content: bytes,
    keys: list[str],
    meeting_id: str,
    _output_language_code: str = "en",
) -> list[dict]:
    global CURRENT_KEY_INDEX

    config = aai.TranscriptionConfig(
        speech_models=["universal-2"],
        speaker_labels=True,
        # The selected web language is the output/translation language, not
        # necessarily the language spoken in the recording.  Auto-detect the
        # source language so changing the output language cannot change the
        # source transcript and therefore cannot change prompt grouping.
        language_detection=True,
    )

    for attempt in range(len(keys)):
        key_index = (CURRENT_KEY_INDEX + attempt) % len(keys)

        try:
            aai.settings.api_key = keys[key_index]
            transcriber = aai.Transcriber()

            transcript = transcriber.submit(file_content, config=config)
            print(f"Submitted, id={transcript.id}, status={transcript.status}")
            update_meeting_status_sync(meeting_id, transcript.status.value)

            deadline = time.monotonic() + 1800
            while transcript.status not in (aai.TranscriptStatus.completed, aai.TranscriptStatus.error):
                if time.monotonic() >= deadline:
                    raise ProcessingError(
                        "PROCESSING_TIMEOUT",
                        detail="AssemblyAI transcription polling exceeded 30 minutes",
                        retryable=True,
                    )
                time.sleep(3)
                transcript = aai.Transcript.get_by_id(transcript.id)
                print(f"Polling... status={transcript.status}")
                update_meeting_status_sync(meeting_id, transcript.status.value)

            if transcript.status == aai.TranscriptStatus.error:
                error_msg = str(transcript.error or "").lower()
                if any(kw in error_msg for kw in ["no speech", "audio", "silent", "sound"]):
                    raise ProcessingError("NO_AUDIO_OR_SPEECH", detail=str(transcript.error))
                raise classify_processing_exception(
                    RuntimeError(str(transcript.error or "AssemblyAI transcription failed"))
                )

            if not transcript.utterances or not (transcript.text or "").strip():
                raise ProcessingError(
                    "NO_AUDIO_OR_SPEECH",
                    detail="AssemblyAI returned no usable speech segments",
                )

            _raise_quality_or_language_error(transcript)

            results = []
            for utterance in transcript.utterances:
                results.append({
                    "speaker": utterance.speaker,
                    "start": utterance.start / 1000,
                    "end": utterance.end / 1000,
                    "text": utterance.text,
                })

            CURRENT_KEY_INDEX = key_index
            return results

        except Exception as e:
            print(f"[DEBUG] Actual error: {repr(e)}")
            if is_rate_limit_error(e):
                CURRENT_KEY_INDEX = (key_index + 1) % len(keys)
                continue
            raise classify_processing_exception(e) from e

    raise ProcessingError(
        "NETWORK_OR_PROVIDER_ERROR",
        detail="All AssemblyAI API keys have reached their rate limits",
        retryable=True,
    )


async def transcribe_with_diarization_async(
    file_content: bytes,
    meeting_id: str,
    output_language_code: str = "en",
) -> list[dict]:
    keys = await get_keys("ASSEMBLYAI_API_KEY")
    if not keys:
        raise ProcessingError("NETWORK_OR_PROVIDER_ERROR", detail="AssemblyAI API keys are not configured")
    return await asyncio.to_thread(
        transcribe_with_diarization, file_content, keys, meeting_id, output_language_code
    )
