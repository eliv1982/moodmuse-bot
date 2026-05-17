"""OpenAI STT provider with mocked aiohttp (no network)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import Settings
from services.providers.openai_stt import transcribe_openai_audio
from services.speech_to_text import SpeechToTextError


def _settings(**kwargs: object) -> Settings:
    base: dict[str, object] = {
        "BOT_TOKEN": "test-token",
        "STT_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-test",
        "OPENAI_STT_MODEL": "gpt-4o-mini-transcribe",
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def _mock_session_response(body: str, *, status: int = 200) -> MagicMock:
    resp = AsyncMock()
    resp.status = status
    resp.text = AsyncMock(return_value=body)

    post_cm = AsyncMock()
    post_cm.__aenter__ = AsyncMock(return_value=resp)
    post_cm.__aexit__ = AsyncMock(return_value=None)

    session = MagicMock()
    session.post = MagicMock(return_value=post_cm)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


@pytest.mark.asyncio
async def test_openai_stt_returns_clean_text() -> None:
    session = _mock_session_response("  Happy birthday!  ")

    with (
        patch(
            "services.providers.openai_stt.prepare_audio_for_openai",
            new_callable=AsyncMock,
            return_value=(b"wav", "audio.wav"),
        ),
        patch(
            "services.providers.openai_stt.aiohttp.ClientSession",
            return_value=session,
        ),
    ):
        result = await transcribe_openai_audio(
            b"audio", _settings(), filename="voice.ogg", language="en"
        )

    assert result == "Happy birthday!"
    url = session.post.call_args[0][0]
    assert "audio/transcriptions" in url


@pytest.mark.asyncio
async def test_openai_stt_converts_ogg_via_prepare() -> None:
    session = _mock_session_response("hello")
    mock_prepare = AsyncMock(return_value=(b"converted", "audio.wav"))

    with (
        patch(
            "services.providers.openai_stt.prepare_audio_for_openai",
            mock_prepare,
        ),
        patch(
            "services.providers.openai_stt.aiohttp.ClientSession",
            return_value=session,
        ),
    ):
        await transcribe_openai_audio(b"ogg-bytes", _settings(), filename="voice.ogg")

    mock_prepare.assert_awaited_once()
    assert mock_prepare.await_args.kwargs["ffmpeg_binary"] == "ffmpeg"


@pytest.mark.asyncio
async def test_openai_stt_uploads_wav_not_oga() -> None:
    session = _mock_session_response("привет")
    mock_prepare = AsyncMock(return_value=(b"wav-bytes", "audio.wav"))

    with (
        patch(
            "services.providers.openai_stt.prepare_audio_for_openai",
            mock_prepare,
        ),
        patch(
            "services.providers.openai_stt.aiohttp.ClientSession",
            return_value=session,
        ),
    ):
        await transcribe_openai_audio(
            b"oga-bytes",
            _settings(),
            filename="voice.oga",
            mime_type="audio/ogg",
        )

    mock_prepare.assert_awaited_once_with(
        b"oga-bytes",
        "voice.oga",
        ffmpeg_binary="ffmpeg",
        mime_type="audio/ogg",
    )
    form = session.post.call_args.kwargs["data"]
    file_field = next(f for f in form._fields if f[0]["name"] == "file")
    assert file_field[0]["filename"] == "audio.wav"
    assert file_field[2] == b"wav-bytes"
    assert "oga" not in file_field[0]["filename"].lower()


@pytest.mark.asyncio
async def test_openai_stt_parses_json_response() -> None:
    session = _mock_session_response('{"text": "  Привет  "}')

    with (
        patch(
            "services.providers.openai_stt.prepare_audio_for_openai",
            new_callable=AsyncMock,
            return_value=(b"wav", "audio.wav"),
        ),
        patch(
            "services.providers.openai_stt.aiohttp.ClientSession",
            return_value=session,
        ),
    ):
        result = await transcribe_openai_audio(b"audio", _settings(), language="ru")

    assert result == "Привет"


@pytest.mark.asyncio
async def test_openai_stt_empty_returns_empty_string() -> None:
    session = _mock_session_response("   ")

    with (
        patch(
            "services.providers.openai_stt.prepare_audio_for_openai",
            new_callable=AsyncMock,
            return_value=(b"wav", "audio.wav"),
        ),
        patch(
            "services.providers.openai_stt.aiohttp.ClientSession",
            return_value=session,
        ),
    ):
        result = await transcribe_openai_audio(b"audio", _settings())

    assert result == ""


@pytest.mark.asyncio
async def test_openai_stt_api_error_raises_technical_reason() -> None:
    session = _mock_session_response('{"error": "bad"}', status=500)

    with (
        patch(
            "services.providers.openai_stt.prepare_audio_for_openai",
            new_callable=AsyncMock,
            return_value=(b"wav", "audio.wav"),
        ),
        patch(
            "services.providers.openai_stt.aiohttp.ClientSession",
            return_value=session,
        ),
    ):
        with pytest.raises(SpeechToTextError) as exc:
            await transcribe_openai_audio(b"audio", _settings())
    assert exc.value.reason == "technical"


@pytest.mark.asyncio
async def test_openai_stt_missing_api_key() -> None:
    with pytest.raises(SpeechToTextError) as exc:
        await transcribe_openai_audio(b"audio", _settings(OPENAI_API_KEY=""))
    assert exc.value.reason == "technical"
