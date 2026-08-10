from __future__ import annotations

from typing import Any


ERROR_MESSAGES = {
    "NO_AUDIO_OR_SPEECH": "No audio or speech was detected in this video. Please upload a video with clear spoken audio.",
    "POOR_AUDIO_QUALITY": "The audio quality is too poor to transcribe reliably. Please upload a clearer recording with less background noise.",
    "UNSUPPORTED_OR_CORRUPTED_MEDIA": "This video format is unsupported or the file appears to be corrupted. Please export the video as MP4 or upload a playable file.",
    "INVALID_YOUTUBE_URL": "Please enter a valid YouTube video URL.",
    "YOUTUBE_PRIVATE_OR_UNAVAILABLE": "This YouTube video is private or unavailable. Please check the link and make sure the video is public.",
    "MULTIPLE_OR_UNSUPPORTED_LANGUAGES": "The video's language could not be supported reliably. Please upload a video with one supported spoken language.",
    "NETWORK_OR_PROVIDER_ERROR": "The processing service could not be reached. Please try again in a moment.",
    "PROCESSING_TIMEOUT": "Video processing took too long and timed out. Please try a shorter video or try again later.",
}

HTTP_STATUS_BY_CODE = {
    "INVALID_YOUTUBE_URL": 422,
    "YOUTUBE_PRIVATE_OR_UNAVAILABLE": 422,
    "NO_AUDIO_OR_SPEECH": 422,
    "POOR_AUDIO_QUALITY": 422,
    "UNSUPPORTED_OR_CORRUPTED_MEDIA": 422,
    "MULTIPLE_OR_UNSUPPORTED_LANGUAGES": 422,
    "PROCESSING_TIMEOUT": 504,
    "NETWORK_OR_PROVIDER_ERROR": 502,
}


class ProcessingError(Exception):
    """A safe, categorized failure raised by the media-processing pipeline."""

    def __init__(
        self,
        code: str,
        *,
        detail: str | None = None,
        message: str | None = None,
        retryable: bool = False,
    ) -> None:
        self.code = code
        self.public_message = message or ERROR_MESSAGES.get(code, ERROR_MESSAGES["NETWORK_OR_PROVIDER_ERROR"])
        self.detail = detail or self.public_message
        self.retryable = retryable
        super().__init__(self.detail)

    @property
    def http_status(self) -> int:
        return HTTP_STATUS_BY_CODE.get(self.code, 502)

    def public_payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.public_message,
            "retryable": self.retryable,
        }


def classify_processing_exception(
    error: Exception,
    *,
    default_code: str = "NETWORK_OR_PROVIDER_ERROR",
) -> ProcessingError:
    if isinstance(error, ProcessingError):
        return error

    error_text = str(error).lower()
    if "timeout" in error_text or "timed out" in error_text:
        return ProcessingError("PROCESSING_TIMEOUT", detail=str(error), retryable=True)
    if any(term in error_text for term in ("no speech", "no audio", "silent", "no sound", "audio stream")):
        return ProcessingError("NO_AUDIO_OR_SPEECH", detail=str(error))
    if any(term in error_text for term in ("background noise", "low confidence", "poor audio", "audio quality", "unintelligible")):
        return ProcessingError("POOR_AUDIO_QUALITY", detail=str(error))
    if any(term in error_text for term in ("unsupported", "corrupt", "decode", "codec", "invalid media", "unreadable")):
        return ProcessingError("UNSUPPORTED_OR_CORRUPTED_MEDIA", detail=str(error))
    if any(term in error_text for term in ("private video", "video unavailable", "video not found", "deleted video", "restricted video")):
        return ProcessingError("YOUTUBE_PRIVATE_OR_UNAVAILABLE", detail=str(error))
    if any(term in error_text for term in ("language", "multiple languages", "mixed language", "unsupported language")):
        return ProcessingError("MULTIPLE_OR_UNSUPPORTED_LANGUAGES", detail=str(error))
    return ProcessingError(default_code, detail=str(error), retryable=default_code == "NETWORK_OR_PROVIDER_ERROR")
