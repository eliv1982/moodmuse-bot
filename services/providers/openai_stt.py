"""
OpenAI Audio Transcriptions API (direct API).
"""
from __future__ import annotations

import logging

import aiohttp

from config import Settings
from services.audio_prepare import needs_openai_conversion, prepare_audio_for_openai
from services.providers.stt_normalize import normalize_transcription
from services.speech_to_text import SpeechToTextError

logger = logging.getLogger(__name__)

_CONTENT_TYPES = {
    ".wav": "audio/wav",
    ".webm": "audio/webm",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".mpeg": "audio/mpeg",
    ".mpga": "audio/mpeg",
}


def _transcriptions_url(settings: Settings) -> str:
    base = (settings.OPENAI_BASE_URL or "https://api.openai.com/v1").rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/audio/transcriptions"
    return f"{base}/v1/audio/transcriptions"


def _upload_content_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    key = f".{ext}"
    return _CONTENT_TYPES.get(key, "application/octet-stream")


async def transcribe_openai_audio(
    audio_bytes: bytes,
    settings: Settings,
    *,
    filename: str = "voice.oga",
    timeout: float = 45.0,
    language: str | None = None,
    mime_type: str | None = None,
) -> str:
    """
    Transcribe audio via OpenAI Audio Transcriptions API.
    Returns normalized text, or an empty string when the model returns no text.
    """
    api_key = (settings.OPENAI_API_KEY or "").strip()
    if not api_key:
        raise SpeechToTextError("OpenAI STT not configured", reason="technical")

    ffmpeg_binary = (settings.FFMPEG_BINARY or "ffmpeg").strip() or "ffmpeg"
    try:
        upload_bytes, upload_name = await prepare_audio_for_openai(
            audio_bytes,
            filename,
            ffmpeg_binary=ffmpeg_binary,
            mime_type=mime_type,
        )
    except SpeechToTextError:
        raise
    if not upload_name.lower().endswith(".wav") and needs_openai_conversion(
        filename, mime_type
    ):
        raise SpeechToTextError(
            "OpenAI STT upload is not WAV after conversion", reason="technical"
        )

    model = (settings.OPENAI_STT_MODEL or "gpt-4o-mini-transcribe").strip()
    url = _transcriptions_url(settings)
    headers = {"Authorization": f"Bearer {api_key}"}

    data = aiohttp.FormData()
    data.add_field(
        "file",
        upload_bytes,
        filename=upload_name,
        content_type=_upload_content_type(upload_name),
    )
    data.add_field("model", model)
    data.add_field("response_format", "text")
    lang = (language or "").strip().lower()
    if lang in ("ru", "en"):
        data.add_field("language", lang)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                data=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                body = await resp.text()
                if resp.status != 200:
                    logger.error(
                        "OpenAI STT failed: status=%s body=%s",
                        resp.status,
                        body[:300],
                    )
                    raise SpeechToTextError(
                        f"OpenAI STT HTTP {resp.status}", reason="technical"
                    )

                result = normalize_transcription(body)
                if result:
                    logger.info("OpenAI STT: recognized %d characters", len(result))
                return result
    except SpeechToTextError:
        raise
    except aiohttp.ClientError as e:
        logger.exception("OpenAI STT request failed: %s", e)
        raise SpeechToTextError(f"OpenAI STT request failed: {e}", reason="technical") from e
