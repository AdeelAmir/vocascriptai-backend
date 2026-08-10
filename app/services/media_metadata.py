from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass

from app.services.processing_errors import ProcessingError


@dataclass(frozen=True)
class MediaInspection:
    duration_minutes: float | None
    has_audio: bool
    format_name: str | None = None
    audio_codec: str | None = None


def _probe_media(path: str) -> MediaInspection:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration,format_name:stream=codec_type,codec_name",
                "-of",
                "json",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ProcessingError(
            "NETWORK_OR_PROVIDER_ERROR",
            detail="ffprobe is not installed on the processing server",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ProcessingError("PROCESSING_TIMEOUT", detail="ffprobe timed out while inspecting the upload") from exc
    except OSError as exc:
        raise ProcessingError("NETWORK_OR_PROVIDER_ERROR", detail=f"media probe failed: {exc}") from exc

    if result.returncode != 0:
        raise ProcessingError(
            "UNSUPPORTED_OR_CORRUPTED_MEDIA",
            detail=result.stderr.strip() or "ffprobe could not decode the uploaded media",
        )

    try:
        payload = json.loads(result.stdout)
        streams = payload.get("streams") or []
        format_data = payload.get("format") or {}
        duration = float(format_data["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ProcessingError(
            "UNSUPPORTED_OR_CORRUPTED_MEDIA",
            detail="media probe returned incomplete metadata",
        ) from exc

    if duration <= 0 or not streams:
        raise ProcessingError("UNSUPPORTED_OR_CORRUPTED_MEDIA", detail="media has no playable streams")

    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    return MediaInspection(
        duration_minutes=duration / 60,
        has_audio=bool(audio_streams),
        format_name=format_data.get("format_name"),
        audio_codec=audio_streams[0].get("codec_name") if audio_streams else None,
    )


async def inspect_uploaded_media(content: bytes, filename: str | None) -> MediaInspection:
    suffix = os.path.splitext(filename or "upload.bin")[1] or ".bin"

    def run() -> MediaInspection:
        temporary_path = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temporary:
                temporary.write(content)
                temporary_path = temporary.name
            inspection = _probe_media(temporary_path)
            if not inspection.has_audio:
                raise ProcessingError(
                    "NO_AUDIO_OR_SPEECH",
                    detail="uploaded media does not contain an audio stream",
                )
            return inspection
        finally:
            if temporary_path:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass

    return await asyncio.to_thread(run)


async def get_uploaded_duration_minutes(content: bytes, filename: str | None) -> float | None:
    inspection = await inspect_uploaded_media(content, filename)
    return inspection.duration_minutes
