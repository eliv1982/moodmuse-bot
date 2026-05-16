"""
OpenAI Chat Completions text provider (direct API).
"""
from __future__ import annotations

import json
import logging
from typing import Any

import aiohttp

from config import Settings
from utils.i18n import Lang

logger = logging.getLogger(__name__)


class OpenAITextError(Exception):
    """OpenAI Chat Completions API error."""

    pass


class OpenAITextProvider:
    """TextProvider backed by OpenAI Chat Completions."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _chat_completions_url(self) -> str:
        base = (self._settings.OPENAI_BASE_URL or "https://api.openai.com/v1").rstrip("/")
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    async def _completion(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        timeout: float,
        max_tokens: int,
        temperature: float,
    ) -> str:
        api_key = (self._settings.OPENAI_API_KEY or "").strip()
        if not api_key:
            raise OpenAITextError(
                "OpenAI is not configured: set OPENAI_API_KEY in .env"
            )

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self._settings.OPENAI_TEXT_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        url = self._chat_completions_url()

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
                            "OpenAI completion failed: status=%s body=%s",
                            resp.status,
                            text[:800],
                        )
                        raise OpenAITextError(
                            f"OpenAI API {resp.status}: {text[:400]}"
                        )
                    data = json.loads(text)
        except aiohttp.ClientError as e:
            logger.exception("OpenAI request failed: %s", e)
            raise OpenAITextError(f"Request failed: {e}") from e

        choices = data.get("choices")
        if not choices or not isinstance(choices, list):
            raise OpenAITextError("OpenAI response has no choices")

        first = choices[0]
        message = first.get("message") or {}
        content = message.get("content")
        if not content or not str(content).strip():
            raise OpenAITextError("OpenAI response has empty text")

        return str(content).strip()

    async def generate_greeting_text(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        timeout: float,
        max_tokens: int = 400,
        temperature: float = 0.65,
    ) -> str:
        effective_timeout = timeout or self._settings.OPENAI_TIMEOUT
        return await self._completion(
            system_prompt,
            user_prompt,
            timeout=effective_timeout,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def enhance_image_prompt(
        self,
        *,
        draft_english_prompt: str,
        lang: Lang,
        timeout: float,
    ) -> str:
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
                "Улучши черновик на английском в один цельный промпт для картинки. "
                "Выведи ТОЛЬКО финальный промпт на английском: без кавычек, без пояснений, без markdown. "
                "Не больше 700 символов. "
                "Добавь композицию, свет, настроение, стиль. "
                "Это дизайн поздравительной открытки, без читаемого текста на изображении."
            )
            user = f"Черновик промпта (English):\n{draft_english_prompt}\n\nВерни только улучшенный промпт."

        effective_timeout = timeout or self._settings.OPENAI_TIMEOUT
        refined = await self._completion(
            system,
            user,
            timeout=effective_timeout,
            max_tokens=500,
            temperature=0.35,
        )
        line = refined.replace("\n", " ").strip()
        if len(line) > 900:
            line = line[:897] + "..."
        return line
