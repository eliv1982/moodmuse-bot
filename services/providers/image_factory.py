"""
Factory for image generation providers (ProxyAPI or OpenAI).
"""
from __future__ import annotations

from config import Settings
from services.providers.image_base import ImageProvider
from services.providers.openai_image import OpenAIImageProvider
from services.providers.proxi_image import ProxiImageProvider


class UnknownImageProviderError(ValueError):
    """Raised when IMAGE_PROVIDER is not supported."""

    pass


def _normalized_image_provider(settings: Settings) -> str:
    return (settings.IMAGE_PROVIDER or "proxi").strip().lower()


def _is_known_image_provider(name: str) -> bool:
    return name in ("proxi", "openai")


def get_image_provider(settings: Settings) -> ImageProvider:
    """
    Return image provider from settings.
    Default: proxi (backward compatible).
    """
    name = _normalized_image_provider(settings)
    if name == "proxi":
        return ProxiImageProvider(settings)
    if name == "openai":
        return OpenAIImageProvider(settings)
    raise UnknownImageProviderError(
        f"Unknown IMAGE_PROVIDER={settings.IMAGE_PROVIDER!r}; use 'proxi' or 'openai'"
    )


def image_provider_configured(settings: Settings) -> bool:
    """True if the active image provider has required credentials."""
    name = _normalized_image_provider(settings)
    if not _is_known_image_provider(name):
        return False
    if name == "openai":
        return bool((settings.OPENAI_API_KEY or "").strip())
    return bool((settings.PROXI_API_KEY or "").strip())


def image_provider_preflight_message_key(settings: Settings) -> str:
    """i18n key shown when image_provider_configured is False."""
    name = _normalized_image_provider(settings)
    if name == "proxi":
        return "image_proxi_not_configured"
    return "image_provider_not_configured"
