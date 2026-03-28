"""
Orchestration: refine image prompt (Yandex), parallel image (Proxi) + caption (Yandex).
"""
from __future__ import annotations

import asyncio
import html
import logging
from typing import Optional, Tuple

from config import Settings
from services.proxi import generate_image
from services.yandex_gpt import YandexGPTError, enhance_image_prompt, generate_greeting_text
from utils.i18n import Lang, surprise_me_phrases
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

    final_prompt = draft
    if refine_prompt and settings.YANDEX_API_KEY and settings.YANDEX_FOLDER_ID:
        try:
            final_prompt = await enhance_image_prompt(
                draft_english_prompt=draft,
                lang=lang,
                api_key=settings.YANDEX_API_KEY,
                folder_id=settings.YANDEX_FOLDER_ID,
                model_uri=settings.model_uri(),
                url=settings.YANDEX_COMPLETION_URL,
                timeout=settings.YANDEX_PROMPT_REFINE_TIMEOUT,
            )
            logger.info("Image prompt refined via Yandex (len=%d)", len(final_prompt))
        except YandexGPTError as e:
            logger.warning("Prompt refine failed, using draft: %s", e)
            final_prompt = draft
    elif not refine_prompt:
        logger.info("Prompt refine skipped (override path)")
    else:
        logger.info("Prompt refine skipped (no Yandex config)")

    system_prompt = build_text_system_prompt(occasion, text_style, lang)
    user_prompt = build_text_user_prompt(holiday, lang)

    async def run_image() -> bytes:
        return await generate_image(
            final_prompt,
            api_key=settings.PROXI_API_KEY,
            base_url=settings.PROXI_BASE_URL,
            model=settings.PROXI_IMAGE_MODEL,
            timeout=settings.PROXI_IMAGE_TIMEOUT,
        )

    async def run_text() -> str:
        return await generate_greeting_text(
            system_prompt,
            user_prompt,
            api_key=settings.YANDEX_API_KEY,
            folder_id=settings.YANDEX_FOLDER_ID,
            model_uri=settings.model_uri(),
            url=settings.YANDEX_COMPLETION_URL,
            timeout=settings.YANDEX_TIMEOUT,
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
    image_bytes = await generate_image(
        image_prompt_en,
        api_key=settings.PROXI_API_KEY,
        base_url=settings.PROXI_BASE_URL,
        model=settings.PROXI_IMAGE_MODEL,
        timeout=settings.PROXI_IMAGE_TIMEOUT,
    )
    return image_bytes, image_prompt_en


async def run_text_only(
    settings: Settings,
    *,
    occasion: str,
    holiday: str,
    text_style: str,
    lang: Lang,
) -> str:
    raw = await generate_greeting_text(
        build_text_system_prompt(occasion, text_style, lang),
        build_text_user_prompt(holiday, lang),
        api_key=settings.YANDEX_API_KEY,
        folder_id=settings.YANDEX_FOLDER_ID,
        model_uri=settings.model_uri(),
        url=settings.YANDEX_COMPLETION_URL,
        timeout=settings.YANDEX_TIMEOUT,
        max_tokens=380,
        temperature=0.7,
    )
    return caption_for_telegram_html(raw, settings.MAX_CAPTION_LENGTH)
