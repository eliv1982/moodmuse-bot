"""
Yandex Cloud Foundation Models — chat completion (text, prompt refine, small talk).
Docs: https://yandex.cloud/en/docs/foundation-models/text-generation/api-ref/
"""
from __future__ import annotations

import json
import logging
from typing import Any, List, Optional

import aiohttp

from utils.i18n import Lang

logger = logging.getLogger(__name__)


class YandexGPTError(Exception):
    """Yandex Cloud completion API error."""

    pass


def _message_list(system: str, user: str) -> List[dict[str, str]]:
    return [
        {"role": "system", "text": system},
        {"role": "user", "text": user},
    ]


async def completion(
    messages: List[dict[str, str]],
    *,
    api_key: str,
    folder_id: str,
    model_uri: str,
    url: str,
    timeout: float = 60.0,
    temperature: float = 0.6,
    max_tokens: int = 1024,
) -> str:
    if not api_key or not folder_id:
        raise YandexGPTError(
            "Yandex Cloud is not configured: set YANDEX_API_KEY and YANDEX_FOLDER_ID in .env"
        )

    headers = {
        "Authorization": f"Api-Key {api_key.strip()}",
        "x-folder-id": folder_id.strip(),
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "modelUri": model_uri,
        "completionOptions": {
            "stream": False,
            "temperature": temperature,
            "maxTokens": max_tokens,
        },
        "messages": messages,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url.rstrip("/"),
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                text = await resp.text()
                if resp.status != 200:
                    logger.error(
                        "Yandex completion failed: status=%s body=%s",
                        resp.status,
                        text[:800],
                    )
                    raise YandexGPTError(f"Yandex API {resp.status}: {text[:400]}")
                data = json.loads(text)
    except aiohttp.ClientError as e:
        logger.exception("Yandex request failed: %s", e)
        raise YandexGPTError(f"Request failed: {e}") from e

    result = data.get("result") or {}
    alts = result.get("alternatives")
    if not alts or not isinstance(alts, list):
        raise YandexGPTError("Yandex response has no alternatives")

    first = alts[0]
    msg = first.get("message") or {}
    content = msg.get("text")
    if not content:
        content = first.get("text")
    if not content or not str(content).strip():
        raise YandexGPTError("Yandex response has empty text")

    return str(content).strip()


async def generate_greeting_text(
    system_prompt: str,
    user_prompt: str,
    *,
    api_key: str,
    folder_id: str,
    model_uri: str,
    url: str,
    timeout: float = 90.0,
    max_tokens: int = 400,
    temperature: float = 0.65,
) -> str:
    return await completion(
        _message_list(system_prompt, user_prompt),
        api_key=api_key,
        folder_id=folder_id,
        model_uri=model_uri,
        url=url,
        timeout=timeout,
        temperature=temperature,
        max_tokens=max_tokens,
    )


async def enhance_image_prompt(
    *,
    draft_english_prompt: str,
    lang: Lang,
    api_key: str,
    folder_id: str,
    model_uri: str,
    url: str,
    timeout: float = 45.0,
) -> str:
    """
    Refine the English image prompt for diffusion / image models.
    Returns improved prompt or raises; caller may fall back to draft.
    """
    if lang == "en":
        system = (
            "You are an expert prompt engineer for image generation models. "
            "Improve the user's draft into one clear English prompt. "
            "Output ONLY the final prompt text: no quotes, no explanations, no markdown. "
            "Keep it under 700 characters. "
            "Emphasize composition, lighting, mood, and art direction. "
            "The image must stay a greeting-card style illustration or design, no readable text on the image."
        )
        user = f"Draft prompt:\n{draft_english_prompt}\n\nReturn the improved prompt only."
    else:
        system = (
            "Ты — инженер промптов для моделей генерации изображений. "
            "Улучни черновик на английском в один цельный промпт для картинки. "
            "Выведи ТОЛЬКО финальный промпт на английском: без кавычек, без пояснений, без markdown. "
            "Не больше 700 символов. "
            "Добавь композицию, свет, настроение, стиль. "
            "Это дизайн поздравительной открытки, без читаемого текста на изображении."
        )
        user = f"Черновик промпта (English):\n{draft_english_prompt}\n\nВерни только улучшенный промпт."

    refined = await completion(
        _message_list(system, user),
        api_key=api_key,
        folder_id=folder_id,
        model_uri=model_uri,
        url=url,
        timeout=timeout,
        temperature=0.35,
        max_tokens=500,
    )
    line = refined.replace("\n", " ").strip()
    if len(line) > 900:
        line = line[:897] + "..."
    return line


SMALL_TALK_SYSTEM_RU = (
    "Ты — бот хорошего настроения. Помогаешь создавать поздравительные открытки. "
    "Отвечай кратко (1–2 предложения), дружелюбно. В каждом ответе мягко напомни про /start для создания открытки."
)

SMALL_TALK_SYSTEM_EN = (
    "You are a feel-good greeting-card bot. Reply in 1–2 short friendly sentences. "
    "Gently remind the user they can send /start to create a card."
)


async def small_talk_reply(
    user_message: str,
    *,
    lang: Lang,
    api_key: str,
    folder_id: str,
    model_uri: str,
    url: str,
    timeout: float = 30.0,
) -> str:
    system = SMALL_TALK_SYSTEM_EN if lang == "en" else SMALL_TALK_SYSTEM_RU
    return await generate_greeting_text(
        system,
        user_message or ("Hello" if lang == "en" else "Привет"),
        api_key=api_key,
        folder_id=folder_id,
        model_uri=model_uri,
        url=url,
        timeout=timeout,
        max_tokens=200,
        temperature=0.5,
    )
