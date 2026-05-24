"""
Orchestration: refine image prompt + parallel image (image provider) + caption (text provider).
"""
from __future__ import annotations

import asyncio
import html
import logging
from typing import Optional, Tuple

from config import Settings
from services.providers.factory import get_text_provider, text_provider_configured
from services.providers.image_factory import get_image_provider
from services.providers.openai_text import OpenAITextError
from services.yandex_gpt import YandexGPTError
from utils.i18n import Lang, surprise_me_phrases
from utils.profile_preferences import ProfilePreferences
from utils.prompts import (
    build_image_prompt,
    build_text_system_prompt,
    build_text_user_prompt,
    image_variation_suffix,
)
from utils.translate import translate_holiday_to_english, translate_prompt_to_english

logger = logging.getLogger(__name__)


def truncate_caption(text: str, max_len: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    if max_len <= 1:
        return "…"
    return text[: max_len - 1].rstrip() + "…"


def caption_for_telegram_html(text: str, max_len: int) -> str:
    """Telegram HTML caption: escape and enforce length."""
    return html.escape(truncate_caption(text, max_len))


async def build_draft_image_prompt(
    *,
    occasion: str,
    image_style: str,
    image_description: str,
    holiday: str,
    lang: Lang,
) -> Tuple[str, Optional[str]]:
    """
    Returns (draft_english_prompt, holiday_en_or_none).
    """
    phrases = surprise_me_phrases(lang)
    desc_lower = (image_description or "").strip().lower()
    desc_en: Optional[str] = None
    if image_description and desc_lower not in phrases:
        desc_en = translate_prompt_to_english(image_description, lang) or image_description
    holiday_en = translate_holiday_to_english(holiday, lang) if holiday else None
    draft = build_image_prompt(
        occasion,
        image_style,
        desc_en,
        holiday_en or holiday,
        surprise_phrases=phrases,
    )
    return draft, holiday_en


async def run_card_generation(
    settings: Settings,
    *,
    occasion: str,
    image_description: str,
    holiday: str,
    image_style: str,
    text_style: str,
    lang: Lang,
    image_prompt_override: Optional[str] = None,
    refine_prompt: bool = True,
    profile_prefs: Optional[ProfilePreferences] = None,
) -> Tuple[bytes, str, str]:
    """
    Returns (image_bytes, caption_html, final_image_prompt_en).
    """
    if image_prompt_override is not None:
        draft = image_prompt_override
    else:
        draft, _ = await build_draft_image_prompt(
            occasion=occasion,
            image_style=image_style,
            image_description=image_description,
            holiday=holiday,
            lang=lang,
        )

    text_provider = get_text_provider(settings)
    refine_timeout = (
        settings.OPENAI_TIMEOUT
        if (settings.TEXT_PROVIDER or "yandex").strip().lower() == "openai"
        else settings.YANDEX_PROMPT_REFINE_TIMEOUT
    )

    final_prompt = draft
    if refine_prompt and text_provider_configured(settings):
        try:
            final_prompt = await text_provider.enhance_image_prompt(
                draft_english_prompt=draft,
                lang=lang,
                timeout=refine_timeout,
            )
            logger.info("Image prompt refined (len=%d)", len(final_prompt))
        except (YandexGPTError, OpenAITextError) as e:
            logger.warning("Prompt refine failed, using draft: %s", e)
            final_prompt = draft
    elif not refine_prompt:
        logger.info("Prompt refine skipped (override path)")
    else:
        logger.info("Prompt refine skipped (text provider not configured)")

    system_prompt = build_text_system_prompt(
        occasion, text_style, lang, profile_prefs=profile_prefs
    )
    user_prompt = build_text_user_prompt(holiday, lang)
    text_timeout = (
        settings.OPENAI_TIMEOUT
        if (settings.TEXT_PROVIDER or "yandex").strip().lower() == "openai"
        else settings.YANDEX_TIMEOUT
    )

    image_provider = get_image_provider(settings)

    async def run_image() -> bytes:
        return await image_provider.generate_image(final_prompt)

    async def run_text() -> str:
        return await text_provider.generate_greeting_text(
            system_prompt,
            user_prompt,
            timeout=text_timeout,
            max_tokens=380,
            temperature=0.65,
        )

    image_bytes, raw_text = await asyncio.gather(run_image(), run_text())
    cap = caption_for_telegram_html(raw_text, settings.MAX_CAPTION_LENGTH)
    return image_bytes, cap, final_prompt


async def run_image_only(
    settings: Settings,
    image_prompt_en: str,
) -> Tuple[bytes, str]:
    image_provider = get_image_provider(settings)
    image_bytes = await image_provider.generate_image(image_prompt_en)
    return image_bytes, image_prompt_en


async def run_text_only(
    settings: Settings,
    *,
    occasion: str,
    holiday: str,
    text_style: str,
    lang: Lang,
    profile_prefs: Optional[ProfilePreferences] = None,
) -> str:
    text_provider = get_text_provider(settings)
    text_timeout = (
        settings.OPENAI_TIMEOUT
        if (settings.TEXT_PROVIDER or "yandex").strip().lower() == "openai"
        else settings.YANDEX_TIMEOUT
    )
    raw = await text_provider.generate_greeting_text(
        build_text_system_prompt(occasion, text_style, lang, profile_prefs=profile_prefs),
        build_text_user_prompt(holiday, lang),
        timeout=text_timeout,
        max_tokens=380,
        temperature=0.7,
    )
    return caption_for_telegram_html(raw, settings.MAX_CAPTION_LENGTH)
