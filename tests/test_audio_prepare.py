"""Audio preparation for OpenAI STT."""
from pathlib import Path
from unittest.mock import patch

import pytest

from services.audio_prepare import (
    is_telegram_opus_voice,
    needs_openai_conversion,
    prepare_audio_for_openai,
)
from services.speech_to_text import SpeechToTextError


def test_needs_conversion_for_oga_ogg() -> None:
    assert needs_openai_conversion("voice.oga") is True
    assert needs_openai_conversion("voice.ogg") is True


def test_needs_conversion_for_ogg_opus_mime() -> None:
    assert needs_openai_conversion("voice.bin", mime_type="audio/ogg") is True
    assert needs_openai_conversion("voice.bin", mime_type="audio/opus") is True


def test_is_telegram_opus_voice_oga() -> None:
    assert is_telegram_opus_voice("voice.oga") is True
    assert is_telegram_opus_voice("file.oga", "audio/ogg") is True


def test_no_conversion_for_wav_or_webm() -> None:
    assert needs_openai_conversion("audio.wav") is False
    assert needs_openai_conversion("clip.webm") is False


@pytest.mark.asyncio
async def test_oga_is_converted_to_wav(tmp_path: Path) -> None:
    async def fake_ffmpeg(ffmpeg_binary: str, input_path: Path, output_path: Path) -> None:
        assert input_path.suffix == ".oga"
        output_path.write_bytes(b"converted-wav")

    class _TmpCtx:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> str:
            return str(tmp_path)

        def __exit__(self, *args: object) -> None:
            pass

    with patch("services.audio_prepare._run_ffmpeg", side_effect=fake_ffmpeg):
        with patch("services.audio_prepare.tempfile.TemporaryDirectory", _TmpCtx):
            result, name = await prepare_audio_for_openai(
                b"oga-data", "voice.oga", mime_type="audio/ogg"
            )

    assert result == b"converted-wav"
    assert name == "audio.wav"
    assert (tmp_path / "input.oga").read_bytes() == b"oga-data"


@pytest.mark.asyncio
async def test_ogg_is_converted_before_upload(tmp_path: Path) -> None:
    async def fake_ffmpeg(ffmpeg_binary: str, input_path: Path, output_path: Path) -> None:
        output_path.write_bytes(b"converted-wav")

    class _TmpCtx:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> str:
            return str(tmp_path)

        def __exit__(self, *args: object) -> None:
            pass

    with patch("services.audio_prepare._run_ffmpeg", side_effect=fake_ffmpeg):
        with patch("services.audio_prepare.tempfile.TemporaryDirectory", _TmpCtx):
            result, name = await prepare_audio_for_openai(b"ogg-data", "voice.ogg")

    assert result == b"converted-wav"
    assert name == "audio.wav"
    assert (tmp_path / "input.ogg").read_bytes() == b"ogg-data"


@pytest.mark.asyncio
async def test_wav_passes_through_unchanged() -> None:
    data = b"RIFF...."
    result, name = await prepare_audio_for_openai(data, "audio.wav")
    assert result == data
    assert name == "audio.wav"


@pytest.mark.asyncio
async def test_missing_ffmpeg_raises_controlled_error(tmp_path: Path) -> None:
    class _TmpCtx:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> str:
            return str(tmp_path)

        def __exit__(self, *args: object) -> None:
            pass

    with patch(
        "services.audio_prepare._run_ffmpeg",
        side_effect=FileNotFoundError("ffmpeg"),
    ):
        with patch("services.audio_prepare.tempfile.TemporaryDirectory", _TmpCtx):
            with pytest.raises(SpeechToTextError) as exc:
                await prepare_audio_for_openai(b"oga", "voice.oga")
    assert exc.value.reason == "technical"
