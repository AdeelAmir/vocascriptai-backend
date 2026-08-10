import asyncio
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from dotenv import load_dotenv
from sqlalchemy import select
from supadata import Supadata, SupadataError

from app.core.database import AsyncSessionLocal
from app.core.encryption import decrypt
from app.models.settings import Setting
from app.services.processing_errors import ProcessingError, classify_processing_exception


load_dotenv()
env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=env_path)
api_key = os.environ.get("YOUTUBE_API_KEY")

PLAIN_KEYS = ("MAX_FILE_SIZE_MB", "MAX_VIDEO_DURATION_MINUTES")


async def get_setting(key: str) -> str | None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()
        if not setting:
            return None
        return setting.value if key in PLAIN_KEYS else decrypt(setting.value)


async def get_keys(prefix: str) -> list[str]:
    keys = []
    for i in range(1, 6):
        value = await get_setting(f"{prefix}_{i}")
        if value:
            keys.append(value)
    return keys


CURRENT_KEY_INDEX = 0


def is_quota_error(error: Exception) -> bool:
    error_text = str(error).lower()
    return any(phrase in error_text for phrase in (
        "rate limit",
        "quota",
        "limit exceeded",
        "429",
        "credits",
    ))


def _fetch(youtube_url: str, keys: list[str]) -> dict:
    global CURRENT_KEY_INDEX

    for attempt in range(len(keys)):
        key_index = (CURRENT_KEY_INDEX + attempt) % len(keys)
        try:
            supadata = Supadata(api_key=keys[key_index])
            transcript = supadata.transcript(url=youtube_url, text=True, mode="native")
            content = getattr(transcript, "content", None)
            if not content:
                raise ProcessingError(
                    "NO_AUDIO_OR_SPEECH",
                    message="No captions or spoken transcript were found for this YouTube video. Please use a video with clear spoken audio.",
                    detail="Supadata returned no transcript content",
                )

            CURRENT_KEY_INDEX = key_index
            return {"available": True, "text": content}
        except ProcessingError:
            raise
        except SupadataError as error:
            print(f"[DEBUG] Supadata error on key {key_index + 1}: {error!r}")
            if is_quota_error(error):
                CURRENT_KEY_INDEX = (key_index + 1) % len(keys)
                continue
            raise classify_processing_exception(error) from error
        except Exception as error:
            raise classify_processing_exception(error) from error

    raise ProcessingError(
        "NETWORK_OR_PROVIDER_ERROR",
        detail="All Supadata API keys have reached their limits",
        retryable=True,
    )


async def get_audio_transcript(youtube_url: str) -> dict:
    keys = await get_keys("SUPADATA_API_KEY")
    if not keys:
        raise ProcessingError("NETWORK_OR_PROVIDER_ERROR", detail="Supadata API keys are not configured")

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_fetch, youtube_url, keys),
            timeout=900,
        )
    except asyncio.TimeoutError as error:
        raise ProcessingError(
            "PROCESSING_TIMEOUT",
            detail="YouTube transcript request exceeded 15 minutes",
            retryable=True,
        ) from error
    return {
        "available": True,
        "transcript": [
            {
                "speaker": "A",
                "start": 0,
                "end": 0,
                "text": result["text"],
            }
        ],
    }


def extract_video_id(url: str) -> str:
    candidate = url.strip()
    if not candidate:
        raise ProcessingError("INVALID_YOUTUBE_URL", detail="YouTube URL is empty")
    if not re.match(r"^https?://", candidate, re.IGNORECASE):
        candidate = f"https://{candidate}"

    parsed = urlparse(candidate)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    video_id = ""
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0]
    elif host in {"youtube.com", "m.youtube.com"}:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        else:
            for prefix in ("/shorts/", "/embed/"):
                if parsed.path.startswith(prefix):
                    video_id = parsed.path.removeprefix(prefix).split("/")[0]
                    break

    if not re.fullmatch(r"[0-9A-Za-z_-]{11}", video_id):
        raise ProcessingError("INVALID_YOUTUBE_URL", detail=f"Could not extract a valid YouTube ID from {url}")
    return video_id


async def get_video_duration(youtube_url: str) -> int:
    video_id = extract_video_id(youtube_url)
    if not api_key:
        raise ProcessingError("NETWORK_OR_PROVIDER_ERROR", detail="YouTube API key is not configured")

    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {"part": "contentDetails", "id": video_id, "key": api_key}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(url, params=params)
    except httpx.TimeoutException as error:
        raise ProcessingError("PROCESSING_TIMEOUT", detail="YouTube duration request timed out", retryable=True) from error
    except httpx.RequestError as error:
        raise ProcessingError("NETWORK_OR_PROVIDER_ERROR", detail=f"YouTube request failed: {error}", retryable=True) from error

    try:
        data = response.json()
    except ValueError as error:
        raise ProcessingError("NETWORK_OR_PROVIDER_ERROR", detail="YouTube returned invalid JSON") from error

    if response.status_code != 200:
        reasons = (data.get("error") or {}).get("errors") or []
        reason = str(reasons[0].get("reason", "") if reasons else "").lower()
        if response.status_code == 400 or reason in {"videoidinvalid", "badrequest"}:
            raise ProcessingError("INVALID_YOUTUBE_URL", detail=f"YouTube rejected video ID {video_id}")
        if response.status_code == 403 and any(term in reason for term in ("quota", "dailylimit", "ratelimit")):
            raise ProcessingError("NETWORK_OR_PROVIDER_ERROR", detail=f"YouTube API quota error: {reason}", retryable=True)
        if response.status_code in {403, 404}:
            raise ProcessingError("YOUTUBE_PRIVATE_OR_UNAVAILABLE", detail=f"YouTube returned HTTP {response.status_code}")
        raise ProcessingError("NETWORK_OR_PROVIDER_ERROR", detail=f"YouTube returned HTTP {response.status_code}")

    if not data.get("items"):
        raise ProcessingError("YOUTUBE_PRIVATE_OR_UNAVAILABLE", detail="YouTube returned no public video for this ID")

    iso_duration = data["items"][0].get("contentDetails", {}).get("duration", "")
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_duration)
    if not match:
        raise ProcessingError("NETWORK_OR_PROVIDER_ERROR", detail=f"Unexpected YouTube duration format: {iso_duration}")
    hours, minutes, seconds = (int(value) if value else 0 for value in match.groups())
    return hours * 3600 + minutes * 60 + seconds
