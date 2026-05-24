"""
Conditional occasion details (age/date/period) for birthday-like holidays.
"""
from __future__ import annotations

import re
from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from utils.i18n import Lang, t

OCCASION_DETAILS_MAX_LEN = 80

WIZARD_OCCASION_DETAILS_YES = "wizard:occasion_details:yes"
WIZARD_OCCASION_DETAILS_NO = "wizard:occasion_details:no"

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
_JSONISH_RE = re.compile(r"[\{\}\[\]]|\"[\w]+\":")

_SUBSTRING_MARKERS: tuple[str, ...] = (
    "день рождения",
    "юбилей",
    "годовщина",
    "лет брака",
    "месяц знакомства",
    "годовщина знакомства",
    "годовщина свадьбы",
    "birthday",
    "anniversary",
    "jubilee",
    "wedding anniversary",
    "years together",
    "years married",
)


def _normalize_holiday(holiday: str) -> str:
    return re.sub(r"\s+", " ", (holiday or "").strip().lower()).replace("ё", "е")


def occasion_needs_details(holiday: str) -> bool:
    """True when the user may optionally specify age, date, or period."""
    normalized = _normalize_holiday(holiday)
    if not normalized:
        return False
    for marker in _SUBSTRING_MARKERS:
        if marker in normalized:
            return True
    return bool(re.search(r"\bдр\b", normalized))


def _normalize_one_line(raw: str) -> str:
    return re.sub(r"\s+", " ", (raw or "").strip())


def validate_occasion_details(raw: str) -> Optional[str]:
    if "\n" in (raw or "") or "\r" in (raw or ""):
        return None
    text = _normalize_one_line(raw)
    if not text or len(text) > OCCASION_DETAILS_MAX_LEN:
        return None
    if _CONTROL_CHARS_RE.search(text):
        return None
    if _URL_RE.search(text) or _JSONISH_RE.search(text):
        return None
    if not any(c.isalnum() for c in text):
        return None
    weird = sum(
        1
        for c in text
        if not c.isalnum() and not c.isspace() and c not in ",'-.!?«»\"—–:/"
    )
    if weird > 10:
        return None
    return text


def build_occasion_details_text_suffix(
    holiday: str | None,
    occasion_details: str | None,
    lang: Lang,
) -> str:
    if occasion_details and occasion_details.strip():
        detail = occasion_details.strip()
        if lang == "en":
            return (
                f"REQUIRED occasion detail — include it naturally in the caption: {detail}. "
                "Do not invent a different age, number, date, or period. "
                "If the detail mentions an age or milestone, reflect it accurately."
            )
        return (
            f"ОБЯЗАТЕЛЬНОЕ уточнение — включи его естественно в текст открытки: {detail}. "
            "Не придумывай другой возраст, число, дату или период. "
            "Если указан возраст или юбилей — отрази его точно."
        )
    if holiday and occasion_needs_details(holiday):
        if lang == "en":
            return (
                "Do not invent ages, numbers, dates, anniversary years, or time periods. "
                "Do not guess candle counts or milestone numbers."
            )
        return (
            "Не придумывай возраст, числа, даты, годы юбилея или периоды. "
            "Не угадывай количество свечей и «круглые» цифры."
        )
    return ""


def build_occasion_details_image_suffix(
    holiday: str | None,
    occasion_details: str | None,
) -> str:
    if occasion_details and occasion_details.strip():
        detail = occasion_details.strip()
        return (
            f", if showing birthday cake, candles, balloons, or numeric visuals, "
            f"they must match this detail and must not contradict it: {detail}. "
            "Do not show conflicting numbers. Avoid readable text or inscriptions on the image"
        )
    if holiday and occasion_needs_details(holiday):
        return (
            ", avoid visible age numbers, anniversary numbers, candle counts, date text, "
            "or numeric inscriptions unless explicitly provided by the user"
        )
    return ""


def occasion_details_toggle_keyboard(lang: Lang) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_wizard_yes", lang),
                    callback_data=WIZARD_OCCASION_DETAILS_YES,
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("btn_wizard_no", lang),
                    callback_data=WIZARD_OCCASION_DETAILS_NO,
                )
            ],
        ]
    )
