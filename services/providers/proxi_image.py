"""
ProxyAPI.ru image provider — thin adapter over services.proxi.
"""
from __future__ import annotations

from config import Settings
from services.proxi import generate_image


class ProxiImageProvider:
    """ImageProvider backed by ProxyAPI.ru (OpenAI-compatible images API)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def generate_image(self, prompt: str) -> bytes:
        return await generate_image(
            prompt,
            api_key=self._settings.PROXI_API_KEY,
            base_url=self._settings.PROXI_BASE_URL,
            model=self._settings.PROXI_IMAGE_MODEL,
            timeout=self._settings.PROXI_IMAGE_TIMEOUT,
        )
