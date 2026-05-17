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


def _settings(**overrides: object) -> Settings:
    """Isolated Settings: no .env; explicit fields override external env."""
    values: dict[str, object] = {
        "BOT_TOKEN": "test-token",
        "TEXT_PROVIDER": "yandex",
        "YANDEX_API_KEY": "",
        "YANDEX_FOLDER_ID": "",
        "OPENAI_API_KEY": "",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def _clear_yandex_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Runtime merge_yandex_from_os_environ can fill empty keys from os.environ."""
    monkeypatch.delenv("YANDEX_API_KEY", raising=False)
    monkeypatch.delenv("YANDEX_FOLDER_ID", raising=False)


def test_settings_default_text_provider_is_yandex(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TEXT_PROVIDER", raising=False)
    s = Settings(BOT_TOKEN="test-token", _env_file=None)  # type: ignore[call-arg]
    assert s.TEXT_PROVIDER == "yandex"


def test_get_text_provider_default_yandex() -> None:
    provider = get_text_provider(_settings())
    assert isinstance(provider, YandexTextProvider)


def test_get_text_provider_explicit_yandex() -> None:
    provider = get_text_provider(_settings(TEXT_PROVIDER="yandex"))
    assert isinstance(provider, YandexTextProvider)


def test_get_text_provider_openai() -> None:
    provider = get_text_provider(
        _settings(TEXT_PROVIDER="openai", OPENAI_API_KEY="test-key")
    )
    assert isinstance(provider, OpenAITextProvider)


def test_get_text_provider_unknown_raises() -> None:
    with pytest.raises(UnknownTextProviderError, match="Unknown TEXT_PROVIDER"):
        get_text_provider(_settings(TEXT_PROVIDER="anthropic"))


def test_text_provider_configured_yandex(monkeypatch: pytest.MonkeyPatch) -> None:
    assert text_provider_configured(
        _settings(
            TEXT_PROVIDER="yandex",
            YANDEX_API_KEY="k",
            YANDEX_FOLDER_ID="f",
        )
    )
    _clear_yandex_env(monkeypatch)
    assert not text_provider_configured(
        _settings(
            TEXT_PROVIDER="yandex",
            YANDEX_API_KEY="",
            YANDEX_FOLDER_ID="",
        )
    )


def test_text_provider_configured_openai() -> None:
    assert text_provider_configured(
        _settings(TEXT_PROVIDER="openai", OPENAI_API_KEY="test-key")
    )
    assert not text_provider_configured(
        _settings(TEXT_PROVIDER="openai", OPENAI_API_KEY="")
    )


def test_preflight_message_key_yandex() -> None:
    assert (
        text_provider_preflight_message_key(_settings(TEXT_PROVIDER="yandex"))
        == "yandex_env_missing"
    )


def test_preflight_message_key_openai() -> None:
    assert (
        text_provider_preflight_message_key(_settings(TEXT_PROVIDER="openai"))
        == "text_provider_not_configured"
    )


def test_openai_configured_without_yandex(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_yandex_env(monkeypatch)
    s = _settings(
        TEXT_PROVIDER="openai",
        OPENAI_API_KEY="test-key",
        YANDEX_API_KEY="",
        YANDEX_FOLDER_ID="",
    )
    assert text_provider_configured(s)
