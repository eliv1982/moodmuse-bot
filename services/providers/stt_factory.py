"""
Factory for speech-to-text (OpenAI transcriptions or legacy ProxyAPI Whisper).
"""
from __future__ import annotations

from config import Settings
from services.providers.openai_stt import transcribe_openai_audio
from services.speech_to_text import SpeechToTextError, transcribe_audio as transcribe_proxi_audio

__all__ = ["SpeechToTextError", "UnknownSTTProviderError", "stt_configured", "transcribe_audio"]


class UnknownSTTProviderError(ValueError):
    """Raised when STT_PROVIDER is not supported."""

    pass


def normalize_stt_provider_name(raw: str | None) -> str:
    """
    Canonical STT provider id (default: openai).
    Legacy ProxyAPI Whisper: `proxi` and `proxiapi` normalize to `proxiapi`.
    """
    name = (raw or "openai").strip().lower()
    if name in ("proxi", "proxiapi"):
        return "proxiapi"
    return name


def _stt_provider_name(settings: Settings) -> str:
    return normalize_stt_provider_name(settings.STT_PROVIDER)


def stt_configured(settings: Settings) -> bool:
    """True if the active STT provider has required credentials."""
    name = _stt_provider_name(settings)
    if name == "openai":
        return bool((settings.OPENAI_API_KEY or "").strip())
    if name == "proxiapi":
        return bool(
            (settings.PROXI_API_KEY or "").strip()
            and (settings.PROXI_BASE_URL or "").strip()
        )
    return False


async def transcribe_audio(
    audio_bytes: bytes,
    settings: Settings,
    *,
    filename: str = "audio.ogg",
    timeout: float = 45.0,
    language: str | None = None,
    mime_type: str | None = None,
) -> str:
    """
    Transcribe audio using the configured STT provider.
    """
    name = _stt_provider_name(settings)
    if name == "openai":
        return await transcribe_openai_audio(
            audio_bytes,
            settings,
            filename=filename,
            timeout=timeout,
            language=language,
            mime_type=mime_type,
        )
    if name == "proxiapi":
        return await transcribe_proxi_audio(
            audio_bytes,
            api_key=settings.PROXI_API_KEY,
            base_url=settings.PROXI_BASE_URL,
            filename=filename,
            timeout=timeout,
        )
    raise UnknownSTTProviderError(
        f"Unknown STT_PROVIDER={settings.STT_PROVIDER!r}; use 'openai' or legacy 'proxi'/'proxiapi'"
    )
