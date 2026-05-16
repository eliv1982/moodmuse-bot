"""
YandexGPT text provider — thin adapter over services.yandex_gpt.
"""
from __future__ import annotations

from config import Settings
from services.yandex_gpt import enhance_image_prompt, generate_greeting_text
from utils.i18n import Lang


class YandexTextProvider:
    """TextProvider backed by Yandex Cloud Foundation Models."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def generate_greeting_text(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        timeout: float,
        max_tokens: int = 400,
        temperature: float = 0.65,
    ) -> str:
        return await generate_greeting_text(
            system_prompt,
            user_prompt,
            api_key=self._settings.YANDEX_API_KEY,
            folder_id=self._settings.YANDEX_FOLDER_ID,
            model_uri=self._settings.model_uri(),
            url=self._settings.YANDEX_COMPLETION_URL,
            timeout=timeout,
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
        return await enhance_image_prompt(
            draft_english_prompt=draft_english_prompt,
            lang=lang,
            api_key=self._settings.YANDEX_API_KEY,
            folder_id=self._settings.YANDEX_FOLDER_ID,
            model_uri=self._settings.model_uri(),
            url=self._settings.YANDEX_COMPLETION_URL,
            timeout=timeout,
        )
