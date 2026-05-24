"""
Profile settings screens: summary text and inline keyboards.
"""
from __future__ import annotations

from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from utils.i18n import Lang, t
from utils.profile_preferences import (
    ADDRESS_FORMAL,
    ADDRESS_INFORMAL,
    CB_PROFILE_ADDRESS,
    CB_PROFILE_BACK,
    CB_PROFILE_DEV_RESET,
    CB_PROFILE_HOME,
    CB_PROFILE_LANG,
    CB_PROFILE_LENGTH,
    CB_PROFILE_NAME,
    CB_PROFILE_NAME_CANCEL,
    CB_PROFILE_TONE,
    TONE_IRONIC,
    LENGTH_BALANCED,
    LENGTH_DETAILED,
    LENGTH_EXPANDED,
    LENGTH_SHORT,
    ProfilePreferences,
    TONE_ELEGANT,
    TONE_INSPIRING,
    TONE_NEUTRAL,
    TONE_PLAYFUL,
    TONE_TENDER,
    TONE_WARM,
    resolve_display_name,
)


def _language_label(lang: Lang) -> str:
    return "English" if lang == "en" else "Русский"


def _label_address(prefs: ProfilePreferences, lang: Lang) -> str:
    key = "pref_address_formal" if prefs.address_style == ADDRESS_FORMAL else "pref_address_informal"
    return t(key, lang)


def _label_tone(prefs: ProfilePreferences, lang: Lang) -> str:
    return t(f"pref_tone_{prefs.text_tone}", lang)


def _label_length(prefs: ProfilePreferences, lang: Lang) -> str:
    return t(f"pref_length_{prefs.text_length}", lang)


def profile_main_text(
    prefs: ProfilePreferences,
    lang: Lang,
    *,
    ui_lang: Lang,
    telegram_first_name: Optional[str] = None,
) -> str:
    name = resolve_display_name(prefs, telegram_first_name)
    name_display = name if name else t("profile_name_not_set", ui_lang)
    return t(
        "profile_settings_title",
        ui_lang,
        name=name_display,
        language=_language_label(lang),
        address=_label_address(prefs, ui_lang),
        tone=_label_tone(prefs, ui_lang),
        length=_label_length(prefs, ui_lang),
    )


def profile_main_keyboard(lang: Lang, *, show_dev_reset: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=t("profile_btn_name", lang), callback_data=CB_PROFILE_NAME)],
        [InlineKeyboardButton(text=t("profile_btn_lang", lang), callback_data=CB_PROFILE_LANG)],
        [
            InlineKeyboardButton(
                text=t("profile_btn_address", lang),
                callback_data=CB_PROFILE_ADDRESS,
            )
        ],
        [InlineKeyboardButton(text=t("profile_btn_tone", lang), callback_data=CB_PROFILE_TONE)],
        [
            InlineKeyboardButton(
                text=t("profile_btn_length", lang),
                callback_data=CB_PROFILE_LENGTH,
            )
        ],
    ]
    if show_dev_reset:
        rows.append(
            [
                InlineKeyboardButton(
                    text=t("profile_btn_dev_reset", lang),
                    callback_data=CB_PROFILE_DEV_RESET,
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=t("btn_back_home", lang), callback_data=CB_PROFILE_HOME)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _back_row(lang: Lang) -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text=t("profile_btn_back", lang), callback_data=CB_PROFILE_BACK)]


def profile_address_keyboard(lang: Lang) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("pref_address_informal", lang),
                    callback_data="profile:set:address:informal",
                ),
                InlineKeyboardButton(
                    text=t("pref_address_formal", lang),
                    callback_data="profile:set:address:formal",
                ),
            ],
            _back_row(lang),
        ]
    )


def profile_tone_keyboard(lang: Lang) -> InlineKeyboardMarkup:
    tones = (
        TONE_WARM,
        TONE_NEUTRAL,
        TONE_PLAYFUL,
        TONE_TENDER,
        TONE_ELEGANT,
        TONE_INSPIRING,
        TONE_IRONIC,
    )
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(tones), 2):
        row = [
            InlineKeyboardButton(
                text=t(f"pref_tone_{tones[i]}", lang),
                callback_data=f"profile:set:tone:{tones[i]}",
            )
        ]
        if i + 1 < len(tones):
            row.append(
                InlineKeyboardButton(
                    text=t(f"pref_tone_{tones[i + 1]}", lang),
                    callback_data=f"profile:set:tone:{tones[i + 1]}",
                )
            )
        rows.append(row)
    rows.append(_back_row(lang))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def profile_length_keyboard(lang: Lang) -> InlineKeyboardMarkup:
    lengths = (LENGTH_SHORT, LENGTH_BALANCED, LENGTH_DETAILED, LENGTH_EXPANDED)
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(lengths), 2):
        row = [
            InlineKeyboardButton(
                text=t(f"pref_length_{lengths[i]}", lang),
                callback_data=f"profile:set:length:{lengths[i]}",
            )
        ]
        if i + 1 < len(lengths):
            row.append(
                InlineKeyboardButton(
                    text=t(f"pref_length_{lengths[i + 1]}", lang),
                    callback_data=f"profile:set:length:{lengths[i + 1]}",
                )
            )
        rows.append(row)
    rows.append(_back_row(lang))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def profile_language_keyboard(lang: Lang) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Русский", callback_data="profile:set:lang:ru"),
                InlineKeyboardButton(text="English", callback_data="profile:set:lang:en"),
            ],
            _back_row(lang),
        ]
    )


def profile_name_cancel_keyboard(lang: Lang) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("profile_name_cancel", lang),
                    callback_data=CB_PROFILE_NAME_CANCEL,
                )
            ],
        ]
    )
