"""Text provider factory and defaults."""
import pytest

from config import Settings
from services.providers.factory import (
    UnknownTextProviderError,
    get_text_provider,
    text_provider_configured,
    text_provider_preflight_message_key,
)
from services.providers.openai_text import OpenAITextProvider
from services.providers.yandex_text import YandexTextProvider


def _settings(**kwargs: object) -> Settings:
    base: dict[str, object] = {"BOT_TOKEN": "test-token"}
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def test_settings_default_text_provider_is_yandex() -> None:
    s = _settings()
    assert s.TEXT_PROVIDER == "yandex"


def test_get_text_provider_default_yandex() -> None:
    provider = get_text_provider(_settings())
    assert isinstance(provider, YandexTextProvider)


def test_get_text_provider_explicit_yandex() -> None:
    provider = get_text_provider(_settings(TEXT_PROVIDER="yandex"))
    assert isinstance(provider, YandexTextProvider)


def test_get_text_provider_openai() -> None:
    provider = get_text_provider(_settings(TEXT_PROVIDER="openai"))
    assert isinstance(provider, OpenAITextProvider)


def test_get_text_provider_unknown_raises() -> None:
    with pytest.raises(UnknownTextProviderError, match="Unknown TEXT_PROVIDER"):
        get_text_provider(_settings(TEXT_PROVIDER="anthropic"))


def test_text_provider_configured_yandex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YANDEX_API_KEY", "")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "")
    assert text_provider_configured(
        _settings(YANDEX_API_KEY="k", YANDEX_FOLDER_ID="f")
    )
    assert not text_provider_configured(
        _settings(YANDEX_API_KEY="", YANDEX_FOLDER_ID="")
    )


def test_text_provider_configured_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    assert text_provider_configured(
        _settings(TEXT_PROVIDER="openai", OPENAI_API_KEY="sk-test")
    )
    assert not text_provider_configured(
        _settings(TEXT_PROVIDER="openai", OPENAI_API_KEY="")
    )


def test_preflight_message_key_yandex() -> None:
    assert (
        text_provider_preflight_message_key(_settings())
        == "yandex_env_missing"
    )


def test_preflight_message_key_openai() -> None:
    assert (
        text_provider_preflight_message_key(_settings(TEXT_PROVIDER="openai"))
        == "text_provider_not_configured"
    )


def test_openai_configured_without_yandex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YANDEX_API_KEY", "")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "")
    s = _settings(
        TEXT_PROVIDER="openai",
        OPENAI_API_KEY="sk-test",
        YANDEX_API_KEY="",
        YANDEX_FOLDER_ID="",
    )
    assert text_provider_configured(s)
