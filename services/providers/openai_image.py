"""
OpenAI Images API provider (direct API).
"""
from __future__ import annotations

import base64
import json
import logging

import aiohttp

from config import Settings

logger = logging.getLogger(__name__)


class OpenAIImageError(Exception):
    """OpenAI Images API error."""

    pass


class OpenAIImageProvider:
    """ImageProvider backed by OpenAI /v1/images/generations."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _images_generations_url(self) -> str:
        base = (self._settings.OPENAI_BASE_URL or "https://api.openai.com/v1").rstrip("/")
        if base.endswith("/v1"):
            return f"{base}/images/generations"
        return f"{base}/v1/images/generations"

    async def generate_image(self, prompt: str) -> bytes:
        api_key = (self._settings.OPENAI_API_KEY or "").strip()
        if not api_key:
            raise OpenAIImageError(
                "OpenAI is not configured: set OPENAI_API_KEY in .env"
            )

        model = self._settings.OPENAI_IMAGE_MODEL
        size = self._settings.OPENAI_IMAGE_SIZE
        timeout = self._settings.OPENAI_IMAGE_TIMEOUT

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "prompt": prompt,
            "size": size,
            "n": 1,
        }
        url = self._images_generations_url()
        logger.info(
            "OpenAI images: generating (model=%s, prompt_len=%d)",
            model,
            len(prompt),
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as resp:
                    text = await resp.text()
                    if resp.status != 200:
                        logger.error(
                            "OpenAI images failed: status=%s body=%s",
                            resp.status,
                            text[:800],
                        )
                        raise OpenAIImageError(
                            f"OpenAI API {resp.status}: {text[:400]}"
                        )
                    data = json.loads(text)
        except aiohttp.ClientError as e:
            logger.exception("OpenAI images request failed: %s", e)
            raise OpenAIImageError(f"Request failed: {e}") from e

        items = data.get("data")
        if not items or not isinstance(items, list):
            raise OpenAIImageError("OpenAI response has no data array")

        first = items[0]
        b64 = first.get("b64_json")
        if b64:
            try:
                out = base64.b64decode(b64)
                logger.info("OpenAI images: generated %d bytes", len(out))
                return out
            except Exception as e:
                raise OpenAIImageError(f"Failed to decode b64_json: {e}") from e

        url_ref = first.get("url")
        if url_ref:
            logger.info("OpenAI images: downloading from URL")
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url_ref,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as r:
                    if r.status != 200:
                        raise OpenAIImageError(
                            f"Failed to download image: {r.status}"
                        )
                    out = await r.read()
            logger.info("OpenAI images: downloaded %d bytes", len(out))
            return out

        raise OpenAIImageError("OpenAI response has no b64_json or url")
