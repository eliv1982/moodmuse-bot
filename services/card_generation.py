"""
Orchestration: refine image prompt + parallel image (image provider) + card texts (text provider).

One text request returns both the short phrase printed on the image and the expanded Telegram caption.
"""
from __future__ import annotations

import asyncio
import html
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from config import Settings
from services.providers.factory import get_text_provider, text_provider_configured
from services.providers.image_factory import get_image_provider
from services.providers.openai_text import OpenAITextError
from services.yandex_gpt import YandexGPTError
from utils.card_texts import clean_short_text, parse_card_texts
from utils.creative_brief import (
    CAPTION_AI,
    CAPTION_USER,
    CreativeBrief,
    authoritative_constraints,
    has_greeting_context,
    inscription_to_draw,
    mood_prompt,
    resolve_caption_mode,
    text_style_for,
)
from utils.creative_brief import creative_context as brief_creative_context
from utils.i18n import Lang, surprise_me_phrases
from utils.profile_preferences import ProfilePreferences
from utils.prompts import (
    NO_TEXT_IN_IMAGE,
    build_brief_image_prompt,
    build_card_texts_user_prompt,
    build_image_prompt,
    build_text_system_prompt,
    build_text_user_prompt,
    hard_constraints_clause,
    image_variation_suffix,
)
from utils.translate import translate_holiday_to_english, translate_prompt_to_english

logger = logging.getLogger(__name__)

# Room for the JSON wrapper and the short phrase on top of the caption itself.
CARD_TEXTS_MAX_TOKENS = 480


@dataclass(frozen=True)
class CardTexts:
    caption_html: str
    """Expanded Telegram caption (HTML-escaped, length-capped)."""
    short_text: str
    """Plain one-line phrase for the image; empty when the model gave none."""


@dataclass(frozen=True)
class GeneratedCard:
    image_bytes: bytes
    """The clean provider image: no text drawn on it."""
    texts: CardTexts
    image_prompt_en: str


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


def card_texts_from_reply(raw: str, max_caption_len: int) -> CardTexts:
    """Split one model reply into the expanded caption and the short phrase for the image."""
    short, full = parse_card_texts(raw)
    return CardTexts(
        caption_html=caption_for_telegram_html(full, max_caption_len),
        short_text=clean_short_text(short),
    )


async def build_draft_image_prompt(
    *,
    occasion: str,
    image_style: str,
    image_description: str,
    holiday: str,
    lang: Lang,
    occasion_details: Optional[str] = None,
    recipient_address: Optional[str] = None,
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
        occasion_details=occasion_details,
        recipient_address=recipient_address,
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
    recipient_address: Optional[str] = None,
    sender_signature: Optional[str] = None,
    occasion_details: Optional[str] = None,
) -> GeneratedCard:
    """
    Returns the clean image, both card texts and the final English image prompt.
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
            occasion_details=occasion_details,
            recipient_address=recipient_address,
        )

    text_provider = get_text_provider(settings)
    refine_timeout = (
        settings.OPENAI_TIMEOUT
        if (settings.TEXT_PROVIDER or "openai").strip().lower() == "openai"
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
        occasion,
        text_style,
        lang,
        profile_prefs=profile_prefs,
        recipient_address=recipient_address,
        sender_signature=sender_signature,
        holiday=holiday,
        occasion_details=occasion_details,
    )
    user_prompt = build_card_texts_user_prompt(holiday, lang)
    text_timeout = (
        settings.OPENAI_TIMEOUT
        if (settings.TEXT_PROVIDER or "openai").strip().lower() == "openai"
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
            max_tokens=CARD_TEXTS_MAX_TOKENS,
            temperature=0.65,
        )

    image_bytes, raw_text = await asyncio.gather(run_image(), run_text())
    texts = card_texts_from_reply(raw_text, settings.MAX_CAPTION_LENGTH)
    return GeneratedCard(image_bytes=image_bytes, texts=texts, image_prompt_en=final_prompt)


def _text_timeout(settings: Settings) -> float:
    if (settings.TEXT_PROVIDER or "openai").strip().lower() == "openai":
        return settings.OPENAI_TIMEOUT
    return settings.YANDEX_TIMEOUT


def _with_hard_constraints(prompt: str, restrictions: list[str]) -> str:
    """
    The final image prompt always states the user's restrictions in their own words and forbids the model
    from printing text. Refinement may reword the draft, so both are re-appended whenever it dropped them.
    """
    cleaned = [r.strip() for r in restrictions if r and r.strip()]
    if any(r not in prompt for r in cleaned):
        prompt = f"{prompt.rstrip(' .')}. {hard_constraints_clause(cleaned)}."
    if NO_TEXT_IN_IMAGE not in prompt:
        prompt = f"{prompt.rstrip()} {NO_TEXT_IN_IMAGE}"
    return prompt


async def run_brief_generation(
    settings: Settings,
    brief: CreativeBrief,
    *,
    profile_prefs: Optional[ProfilePreferences] = None,
) -> GeneratedCard:
    """
    Generate a card from a confirmed creative brief: the clean image, the exact inscription (never invented
    here), and the extended message when one was chosen.

    The inscription is not produced by the text model: it is whatever the user wrote or approved, handed on
    unchanged as ``texts.short_text`` for the renderer; an empty one means a picture without text. The
    extended message is generated only for ``caption_mode`` "ai", taken verbatim from the user for "user",
    and empty for "none".
    """
    inscription = inscription_to_draw(brief)
    greeting = has_greeting_context(brief) or bool(inscription)
    draft = build_brief_image_prompt(
        concept=brief.concept,
        occasion=brief.occasion,
        recipient=brief.recipient,
        mood=mood_prompt(brief),
        style_key=brief.style_key,
        style_text=brief.style_text,
        restrictions=brief.restrictions,
        greeting_card=greeting,
    )

    text_provider = get_text_provider(settings)
    final_prompt = draft
    if text_provider_configured(settings):
        try:
            final_prompt = await text_provider.enhance_image_prompt(
                draft_english_prompt=draft,
                lang=brief.lang,  # type: ignore[arg-type]
                timeout=_text_timeout(settings),
                artwork=not greeting,
            )
            logger.info("Image prompt refined (len=%d)", len(final_prompt))
        except (YandexGPTError, OpenAITextError) as e:
            logger.warning("Prompt refine failed, using draft: %s", e)
            final_prompt = draft
    # Never entrust the original requirements to either extraction or refinement. This block is added
    # locally after refinement (including fallback), and survives storage for image regeneration.
    constrained = _with_hard_constraints(final_prompt, brief.restrictions).replace(NO_TEXT_IN_IMAGE, "").rstrip()
    final_prompt = (
        f"{constrained}\n"
        f"{authoritative_constraints(brief)}\n{NO_TEXT_IN_IMAGE}"
    )

    image_provider = get_image_provider(settings)
    caption_mode = resolve_caption_mode(brief)

    async def run_image() -> bytes:
        return await image_provider.generate_image(final_prompt)

    async def run_caption() -> str:
        system_prompt = build_text_system_prompt(
            "",
            text_style_for(brief),
            brief.lang,  # type: ignore[arg-type]
            profile_prefs=profile_prefs,
            recipient_address=brief.recipient.strip() or None,
            sender_signature=brief.signature.strip() or None,
            holiday=brief.occasion.strip() or None,
            creative_context=brief_creative_context(brief),
        )
        raw = await text_provider.generate_greeting_text(
            system_prompt,
            build_text_user_prompt(brief.occasion.strip() or None, brief.lang),  # type: ignore[arg-type]
            timeout=_text_timeout(settings),
            max_tokens=CARD_TEXTS_MAX_TOKENS,
            temperature=0.65,
        )
        return card_texts_from_reply(raw, settings.MAX_CAPTION_LENGTH).caption_html

    if caption_mode == CAPTION_AI:
        # gather() alone returns on the first failure while its sibling keeps running. Do not release
        # the per-user generation lock and offer retry with an image request still in flight.
        tasks = [asyncio.create_task(run_image()), asyncio.create_task(run_caption())]
        try:
            image_bytes, caption_html = await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
    else:
        image_bytes = await run_image()
        caption_html = (
            caption_for_telegram_html(brief.caption_text, settings.MAX_CAPTION_LENGTH)
            if caption_mode == CAPTION_USER
            else ""
        )
    return GeneratedCard(
        image_bytes=image_bytes,
        texts=CardTexts(caption_html=caption_html, short_text=inscription),
        image_prompt_en=final_prompt,
    )


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
    recipient_address: Optional[str] = None,
    sender_signature: Optional[str] = None,
    occasion_details: Optional[str] = None,
    creative_context: Optional[str] = None,
    caption_only: bool = False,
) -> CardTexts:
    """
    One text request: new short phrase and expanded caption for an existing card image.

    ``caption_only`` asks for the caption alone (the card keeps an inscription the user fixed, so a new
    phrase would only be thrown away); ``creative_context`` carries a brief's idea, mood and restrictions.
    """
    text_provider = get_text_provider(settings)
    text_timeout = (
        settings.OPENAI_TIMEOUT
        if (settings.TEXT_PROVIDER or "openai").strip().lower() == "openai"
        else settings.YANDEX_TIMEOUT
    )
    ra = recipient_address.strip() if recipient_address else None
    ss = sender_signature.strip() if sender_signature else None
    od = occasion_details.strip() if occasion_details else None
    logger.info(
        "run_text_only",
        extra={
            "event": "run_text_only",
            "card_lang": lang,
            "occasion": occasion,
            "text_style": text_style,
            "sender_signature_present": bool(ss),
        },
    )
    raw = await text_provider.generate_greeting_text(
        build_text_system_prompt(
            occasion,
            text_style,
            lang,
            profile_prefs=profile_prefs,
            recipient_address=ra,
            sender_signature=ss,
            holiday=holiday,
            occasion_details=od,
            creative_context=creative_context,
        ),
        (build_text_user_prompt if caption_only else build_card_texts_user_prompt)(holiday, lang),
        timeout=text_timeout,
        max_tokens=CARD_TEXTS_MAX_TOKENS,
        temperature=0.7,
    )
    return card_texts_from_reply(raw, settings.MAX_CAPTION_LENGTH)
