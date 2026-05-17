"""STT provider factory and configuration."""
from unittest.mock import AsyncMock, patch

import pytest

from config import Settings
from services.providers.stt_factory import (
    UnknownSTTProviderError,
    normalize_stt_provider_name,
    stt_configured,
    transcribe_audio,
)
from services.speech_to_text import SpeechToTextError


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "BOT_TOKEN": "test-token",
        "PROXI_API_KEY": "",
        "PROXI_BASE_URL": "https://openai.api.proxyapi.ru",
        "OPENAI_API_KEY": "",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_settings_default_stt_provider_is_openai() -> None:
    s = Settings(BOT_TOKEN="test-token", _env_file=None)  # type: ignore[call-arg]
    assert s.STT_PROVIDER == "openai"


def test_normalize_stt_provider_defaults_to_openai() -> None:
    assert normalize_stt_provider_name(None) == "openai"
    assert normalize_stt_provider_name("openai") == "openai"
    assert normalize_stt_provider_name("OPENAI") == "openai"


def test_normalize_stt_provider_legacy_proxi_aliases() -> None:
    assert normalize_stt_provider_name("proxi") == "proxiapi"
    assert normalize_stt_provider_name("proxiapi") == "proxiapi"
    assert normalize_stt_provider_name("PROXIAPI") == "proxiapi"


def test_stt_configured_openai() -> None:
    assert stt_configured(_settings(OPENAI_API_KEY="sk-test"))
    assert not stt_configured(_settings(OPENAI_API_KEY=""))


def test_stt_configured_proxiapi() -> None:
    assert stt_configured(
        _settings(
            STT_PROVIDER="proxiapi",
            PROXI_API_KEY="k",
            PROXI_BASE_URL="https://example.com",
        )
    )
    assert not stt_configured(
        _settings(STT_PROVIDER="proxiapi", PROXI_API_KEY="", PROXI_BASE_URL="https://x")
    )


def test_stt_configured_proxi_alias() -> None:
    assert stt_configured(
        _settings(
            STT_PROVIDER="proxi",
            PROXI_API_KEY="k",
            PROXI_BASE_URL="https://example.com",
        )
    )


def test_stt_configured_unknown_provider() -> None:
    assert not stt_configured(_settings(STT_PROVIDER="yandex"))


@pytest.mark.asyncio
async def test_transcribe_default_routes_to_openai() -> None:
    settings = _settings(OPENAI_API_KEY="sk-test")
    with patch(
        "services.providers.stt_factory.transcribe_openai_audio",
        new_callable=AsyncMock,
        return_value="hello",
    ) as mock_openai:
        result = await transcribe_audio(b"audio", settings, filename="voice.ogg", timeout=30.0)

    assert result == "hello"
    mock_openai.assert_awaited_once_with(
        b"audio",
        settings,
        filename="voice.ogg",
        timeout=30.0,
        language=None,
        mime_type=None,
    )


@pytest.mark.asyncio
async def test_transcribe_routes_to_openai_explicit() -> None:
    settings = _settings(STT_PROVIDER="openai", OPENAI_API_KEY="sk-test")
    with patch(
        "services.providers.stt_factory.transcribe_openai_audio",
        new_callable=AsyncMock,
        return_value="hello",
    ) as mock_openai:
        result = await transcribe_audio(b"audio", settings)

    assert result == "hello"
    mock_openai.assert_awaited_once()


@pytest.mark.asyncio
async def test_transcribe_routes_to_proxiapi_legacy() -> None:
    settings = _settings(
        STT_PROVIDER="proxiapi",
        PROXI_API_KEY="k",
        PROXI_BASE_URL="https://proxy.example",
    )
    with patch(
        "services.providers.stt_factory.transcribe_proxi_audio",
        new_callable=AsyncMock,
        return_value="legacy text",
    ) as mock_proxi:
        result = await transcribe_audio(b"audio", settings)

    assert result == "legacy text"
    mock_proxi.assert_awaited_once()
    call_kwargs = mock_proxi.call_args.kwargs
    assert call_kwargs["api_key"] == "k"
    assert call_kwargs["base_url"] == "https://proxy.example"


@pytest.mark.asyncio
async def test_transcribe_proxi_alias_routes_to_legacy() -> None:
    settings = _settings(
        STT_PROVIDER="proxi",
        PROXI_API_KEY="k",
        PROXI_BASE_URL="https://proxy.example",
    )
    with patch(
        "services.providers.stt_factory.transcribe_proxi_audio",
        new_callable=AsyncMock,
        return_value="alias ok",
    ) as mock_proxi:
        result = await transcribe_audio(b"audio", settings)

    assert result == "alias ok"
    mock_proxi.assert_awaited_once()


@pytest.mark.asyncio
async def test_transcribe_unknown_provider_raises() -> None:
    with pytest.raises(UnknownSTTProviderError, match="Unknown STT_PROVIDER"):
        await transcribe_audio(b"audio", _settings(STT_PROVIDER="invalid"))


@pytest.mark.asyncio
async def test_proxi_legacy_empty_still_raises() -> None:
    """Proxy STT path keeps raising on empty responses (unchanged behavior)."""
    settings = _settings(
        STT_PROVIDER="proxiapi",
        PROXI_API_KEY="k",
        PROXI_BASE_URL="https://proxy.example",
    )
    with patch(
        "services.providers.stt_factory.transcribe_proxi_audio",
        new_callable=AsyncMock,
        side_effect=SpeechToTextError("empty proxy STT response", reason="empty"),
    ):
        with pytest.raises(SpeechToTextError) as exc:
            await transcribe_audio(b"audio", settings)
        assert exc.value.reason == "empty"
