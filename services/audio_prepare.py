"""
Prepare Telegram voice/audio bytes for OpenAI Audio Transcriptions upload.
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from services.speech_to_text import SpeechToTextError

logger = logging.getLogger(__name__)

# OpenAI transcriptions accept these extensions without conversion.
OPENAI_SUPPORTED_EXTENSIONS = frozenset({".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"})

# Telegram voice messages are OGG Opus, commonly stored as .oga or .ogg.
TELEGRAM_OPUS_EXTENSIONS = frozenset({".oga", ".ogg", ".opus"})

_OGG_OPUS_MIME_MARKERS = ("audio/ogg", "audio/opus", "application/ogg")


def is_telegram_opus_voice(filename: str, mime_type: str | None = None) -> bool:
    """True for Telegram voice containers (.oga/.ogg) or OGG/Opus MIME types."""
    ext = Path(filename).suffix.lower()
    if ext in TELEGRAM_OPUS_EXTENSIONS:
        return True
    mime = (mime_type or "").strip().lower()
    if not mime:
        return False
    return any(marker in mime for marker in _OGG_OPUS_MIME_MARKERS)


def needs_openai_conversion(filename: str, mime_type: str | None = None) -> bool:
    if is_telegram_opus_voice(filename, mime_type):
        return True
    ext = Path(filename).suffix.lower()
    if not ext:
        return True
    return ext not in OPENAI_SUPPORTED_EXTENSIONS


def _input_suffix_for_conversion(filename: str, mime_type: str | None = None) -> str:
    ext = Path(filename).suffix.lower()
    if ext in TELEGRAM_OPUS_EXTENSIONS:
        return ext
    if is_telegram_opus_voice(filename, mime_type):
        return ".oga"
    return ext or ".oga"


async def _run_ffmpeg(ffmpeg_binary: str, input_path: Path, output_path: Path) -> None:
    proc = await asyncio.create_subprocess_exec(
        ffmpeg_binary,
        "-y",
        "-i",
        str(input_path),
        "-ar",
        "16000",
        "-ac",
        "1",
        str(output_path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        err_text = (stderr or b"").decode(errors="replace")[:500]
        logger.error("ffmpeg conversion failed: %s", err_text)
        raise SpeechToTextError(f"ffmpeg failed: {err_text}", reason="technical")


async def prepare_audio_for_openai(
    audio_bytes: bytes,
    filename: str,
    *,
    ffmpeg_binary: str = "ffmpeg",
    mime_type: str | None = None,
) -> tuple[bytes, str]:
    """
    Return (bytes, upload_filename) suitable for OpenAI transcriptions.
    Converts Telegram OGG Opus (.oga/.ogg) to 16 kHz mono WAV when needed.
    """
    if not needs_openai_conversion(filename, mime_type):
        ext = Path(filename).suffix.lower() or ".wav"
        return audio_bytes, f"audio{ext}"

    input_suffix = _input_suffix_for_conversion(filename, mime_type)
    try:
        with tempfile.TemporaryDirectory(prefix="moodmuse_stt_") as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / f"input{input_suffix}"
            output_path = tmp_path / "output.wav"
            input_path.write_bytes(audio_bytes)
            await _run_ffmpeg(ffmpeg_binary, input_path, output_path)
            if not output_path.is_file() or output_path.stat().st_size == 0:
                raise SpeechToTextError("ffmpeg produced empty output", reason="technical")
            logger.info(
                "Converted %s (%s) to WAV for OpenAI STT",
                filename,
                mime_type or "unknown mime",
            )
            return output_path.read_bytes(), "audio.wav"
    except SpeechToTextError:
        raise
    except FileNotFoundError:
        logger.error("ffmpeg binary not found: %s", ffmpeg_binary)
        raise SpeechToTextError("ffmpeg not found", reason="technical") from None
    except OSError as e:
        logger.exception("audio conversion failed: %s", e)
        raise SpeechToTextError(f"audio conversion failed: {e}", reason="technical") from e
