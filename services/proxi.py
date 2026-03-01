"""
ProxyAPI.ru client for image generation (OpenAI-compatible: gpt-image-1).
Документация: https://proxyapi.ru/docs/openai-image-generation
"""
import base64
import json
import logging
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# Модель GPT-Image 1 в ProxyAPI.ru
DEFAULT_MODEL = "gpt-image-1"


class ProxiAPIError(Exception):
    """ProxyAPI.ru request or response error."""

    pass


async def generate_image(
    prompt: str,
    *,
    api_key: str,
    base_url: str,
    model: str = DEFAULT_MODEL,
    size: str = "1024x1024",
    timeout: float = 120.0,
) -> bytes:
    """
    Генерация изображения через ProxyAPI.ru (OpenAI Images API).
    Универсальный API: base_url = https://openai.api.proxyapi.ru → /v1/images/generations
    Оригинальный OpenAI: base_url = https://api.proxyapi.ru/openai → /v1/images/generations
    """
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        url = base + "/images/generations"
    else:
        url = base + "/v1/images/generations"
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
    logger.info("ProxyAPI.ru: generating image (model=%s, prompt_len=%d)", model, len(prompt))
    logger.debug("ProxyAPI.ru: POST %s", url)

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
                    logger.error("ProxyAPI.ru error status=%s body=%s", resp.status, text[:500])
                    raise ProxiAPIError(f"ProxyAPI.ru вернул {resp.status}: {text[:500]}")

                data = json.loads(text)
    except aiohttp.ClientError as e:
        logger.exception("ProxyAPI.ru request failed: %s", e)
        raise ProxiAPIError(f"Ошибка запроса: {e}") from e

    # Формат OpenAI: data[].b64_json (gpt-image-1) или data[].url (dall-e)
    items = data.get("data")
    if not items or not isinstance(items, list):
        logger.error("ProxyAPI.ru: в ответе нет data[], keys=%s", list(data.keys()))
        raise ProxiAPIError("В ответе ProxyAPI.ru нет массива data")

    first = items[0]
    b64 = first.get("b64_json")
    if b64:
        try:
            out = base64.b64decode(b64)
            logger.info("ProxyAPI.ru: изображение сгенерировано, %d bytes", len(out))
            return out
        except Exception as e:
            logger.exception("ProxyAPI.ru: ошибка декодирования base64")
            raise ProxiAPIError(f"Ошибка декодирования изображения: {e}") from e

    url_ref = first.get("url")
    if url_ref:
        # DALL-E возвращает URL — скачиваем изображение
        logger.info("ProxyAPI.ru: скачивание изображения по URL")
        async with aiohttp.ClientSession() as session:
            async with session.get(url_ref, timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                if r.status != 200:
                    raise ProxiAPIError(f"Не удалось скачать изображение: {r.status}")
                out = await r.read()
        logger.info("ProxyAPI.ru: изображение загружено, %d bytes", len(out))
        return out

    logger.error("ProxyAPI.ru: в data[0] нет b64_json и url, keys=%s", list(first.keys()))
    raise ProxiAPIError("В ответе нет изображения (b64_json или url)")
