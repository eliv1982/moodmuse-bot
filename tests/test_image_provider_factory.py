"""Image provider factory and defaults."""
import pytest

from config import Settings
from services.providers.image_factory import (
    UnknownImageProviderError,
    get_image_provider,
    image_provider_configured,
    image_provider_preflight_message_key,
)
from services.providers.openai_image import OpenAIImageProvider
from services.providers.proxi_image import ProxiImageProvider


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "BOT_TOKEN": "test-token",
        "IMAGE_PROVIDER": "proxi",
        "TEXT_PROVIDER": "yandex",
        "PROXI_API_KEY": "",
        "PROXI_BASE_URL": "https://openai.api.proxyapi.ru",
        "OPENAI_API_KEY": "",
        "YANDEX_API_KEY": "",
        "YANDEX_FOLDER_ID": "",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_settings_default_image_provider_is_proxi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("IMAGE_PROVIDER", raising=False)
    s = Settings(BOT_TOKEN="test-token", _env_file=None)  # type: ignore[call-arg]
    assert s.IMAGE_PROVIDER == "proxi"


def test_get_image_provider_default_proxi() -> None:
    provider = get_image_provider(_settings())
    assert isinstance(provider, ProxiImageProvider)


def test_get_image_provider_explicit_proxi() -> None:
    provider = get_image_provider(_settings(IMAGE_PROVIDER="proxi"))
    assert isinstance(provider, ProxiImageProvider)


def test_get_image_provider_openai() -> None:
    provider = get_image_provider(
        _settings(IMAGE_PROVIDER="openai", OPENAI_API_KEY="test-key")
    )
    assert isinstance(provider, OpenAIImageProvider)


def test_get_image_provider_unknown_raises() -> None:
    with pytest.raises(UnknownImageProviderError, match="Unknown IMAGE_PROVIDER"):
        get_image_provider(_settings(IMAGE_PROVIDER="midjourney"))


def test_image_provider_configured_proxi() -> None:
    assert image_provider_configured(
        _settings(IMAGE_PROVIDER="proxi", PROXI_API_KEY="pk")
    )
    assert not image_provider_configured(
        _settings(IMAGE_PROVIDER="proxi", PROXI_API_KEY="")
    )


def test_image_provider_configured_openai() -> None:
    assert image_provider_configured(
        _settings(IMAGE_PROVIDER="openai", OPENAI_API_KEY="test-key")
    )
    assert not image_provider_configured(
        _settings(IMAGE_PROVIDER="openai", OPENAI_API_KEY="")
    )


def test_preflight_message_key_proxi() -> None:
    assert (
        image_provider_preflight_message_key(_settings(IMAGE_PROVIDER="proxi"))
        == "image_proxi_not_configured"
    )


def test_preflight_message_key_openai() -> None:
    assert (
        image_provider_preflight_message_key(_settings(IMAGE_PROVIDER="openai"))
        == "image_provider_not_configured"
    )


def test_openai_image_without_proxi_key() -> None:
    s = _settings(
        IMAGE_PROVIDER="openai",
        OPENAI_API_KEY="test-key",
        PROXI_API_KEY="",
    )
    assert image_provider_configured(s)


def test_image_provider_configured_typo_returns_false() -> None:
    assert not image_provider_configured(
        _settings(IMAGE_PROVIDER="typo", PROXI_API_KEY="k")
    )


def test_get_image_provider_typo_raises() -> None:
    with pytest.raises(UnknownImageProviderError, match="Unknown IMAGE_PROVIDER"):
        get_image_provider(_settings(IMAGE_PROVIDER="typo", PROXI_API_KEY="k"))


def test_preflight_message_key_typo() -> None:
    assert (
        image_provider_preflight_message_key(_settings(IMAGE_PROVIDER="typo"))
        == "image_provider_not_configured"
    )
