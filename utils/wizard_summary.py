"""
User-facing generation summary built from wizard FSM data (no Telegram imports).
"""
from __future__ import annotations

import html

from utils.i18n import Lang, surprise_me_phrases, t
from utils.prompts import IMAGE_STYLE_LABELS, OCCASION_LABELS, TEXT_STYLE_LABELS
from utils.wizard_input import validate_holiday, validate_image_description


def _label(pair: tuple[str, str], lang: Lang) -> str:
    return pair[1] if lang == "en" else pair[0]


def is_auto_image_idea(image_description: str, lang: Lang) -> bool:
    low = (image_description or "").strip().lower()
    if not low:
        return True
    return low in surprise_me_phrases(lang)


def image_idea_summary_label(image_description: str, lang: Lang) -> str:
    if is_auto_image_idea(image_description, lang):
        return t("summary_image_idea_auto", lang)
    if not validate_image_description(image_description, lang):
        return t("summary_image_idea_auto", lang)
    return html.escape(image_description.strip())


def holiday_summary_label(holiday: str, lang: Lang) -> str:
    raw = (holiday or "").strip()
    if not raw or not validate_holiday(raw, lang):
        return "—" if lang == "ru" else "—"
    return html.escape(raw)


def build_generation_summary(
    *,
    lang: Lang,
    occasion: str,
    image_description: str,
    holiday: str,
    image_style: str,
    text_style: str,
) -> str:
    occasion_label = _label(OCCASION_LABELS.get(occasion, ("—", "—")), lang)
    image_idea_label = image_idea_summary_label(image_description, lang)
    holiday_label = holiday_summary_label(holiday, lang)
    image_style_label = _label(IMAGE_STYLE_LABELS.get(image_style, ("—", "—")), lang)
    text_style_label = _label(TEXT_STYLE_LABELS.get(text_style, ("—", "—")), lang)

    return t(
        "generation_summary",
        lang,
        occasion=occasion_label,
        image_idea=image_idea_label,
        holiday=holiday_label,
        image_style=image_style_label,
        text_style=text_style_label,
    )
