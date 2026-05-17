"""
Speech-to-text via ProxyAPI.ru (OpenAI transcriptions API).
Используется для голосовых сообщений при описании картинки и праздника.
"""
import json
import logging

import aiohttp

logger = logging.getLogger(__name__)

# Модель для транскрипции (поддерживает русский)
DEFAULT_MODEL = "whisper-1"


class SpeechToTextError(Exception):
    """Speech recognition failed (internal message; map to i18n in handlers)."""

    def __init__(self, message: str = "", *, reason: str = "technical") -> None:
        self.reason = reason
        super().__init__(message)


async def transcribe_audio(
    audio_bytes: bytes,
    *,
    api_key: str,
    base_url: str,
    model: str = DEFAULT_MODEL,
    filename: str = "audio.ogg",
    timeout: float = 30.0,
) -> str:
    """
    Транскрибирует аудио в текст через ProxyAPI.ru (OpenAI transcriptions).
    Поддерживаются форматы: mp3, mp4, mpeg, mpga, m4a, wav, webm.
    """
    url = base_url.rstrip("/") + "/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {api_key}"}

    data = aiohttp.FormData()
    data.add_field("file", audio_bytes, filename=filename, content_type="audio/ogg")
    data.add_field("model", model)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                data=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                text = await resp.text()
                if resp.status != 200:
                    logger.error("STT error status=%s body=%s", resp.status, text[:300])
                    raise SpeechToTextError(
                        f"Proxy STT HTTP {resp.status}", reason="technical"
                    )

                result = text.strip()
                if not result:
                    raise SpeechToTextError("empty proxy STT response", reason="empty")
                try:
                    parsed = json.loads(result)
                    if isinstance(parsed, dict) and "text" in parsed and parsed["text"]:
                        result = str(parsed["text"]).strip()
                except (json.JSONDecodeError, TypeError):
                    pass
                if not result:
                    raise SpeechToTextError("empty proxy STT response", reason="empty")
                logger.info("STT: распознано %d символов", len(result))
                return result
    except SpeechToTextError:
        raise
    except aiohttp.ClientError as e:
        logger.exception("STT request failed: %s", e)
        raise SpeechToTextError(f"Proxy STT request failed: {e}", reason="technical") from e
