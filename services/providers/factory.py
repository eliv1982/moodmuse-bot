"""
Factory for text generation providers (YandexGPT or OpenAI).
"""
from __future__ import annotations

from config import Settings
from services.providers.base import TextProvider
from services.providers.openai_text import OpenAITextProvider
from services.providers.yandex_text import YandexTextProvider


class UnknownTextProviderError(ValueError):
    """Raised when TEXT_PROVIDER is not supported."""

    pass


def get_text_provider(settings: Settings) -> TextProvider:
    """
    Return text provider from settings.
    Default: yandex (backward compatible).
    """
    name = (settings.TEXT_PROVIDER or "yandex").strip().lower()
    if name == "yandex":
        return YandexTextProvider(settings)
    if name == "openai":
        return OpenAITextProvider(settings)
    raise UnknownTextProviderError(
        f"Unknown TEXT_PROVIDER={settings.TEXT_PROVIDER!r}; use 'yandex' or 'openai'"
    )


def text_provider_configured(settings: Settings) -> bool:
    """True if the active text provider has required credentials."""
    name = (settings.TEXT_PROVIDER or "yandex").strip().lower()
    if name == "openai":
        return bool((settings.OPENAI_API_KEY or "").strip())
    return bool(
        (settings.YANDEX_API_KEY or "").strip()
        and (settings.YANDEX_FOLDER_ID or "").strip()
    )
