"""
Persistent reply keyboard for the main menu (Weather Teller style).
"""
from __future__ import annotations

from typing import Literal, Optional

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from utils.i18n import Lang, t

MainMenuAction = Literal["create_card", "profile", "help"]


def main_menu_reply_keyboard(lang: Lang) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("btn_create_card", lang)),
                KeyboardButton(text=t("btn_profile_settings", lang)),
            ],
            [KeyboardButton(text=t("btn_help_short", lang))],
        ],
        resize_keyboard=True,
        is_persistent=True,
        one_time_keyboard=False,
    )


def _all_menu_button_texts() -> frozenset[str]:
    keys = ("btn_create_card", "btn_profile_settings", "btn_help_short")
    return frozenset(t(key, lang) for key in keys for lang in ("ru", "en"))


MAIN_MENU_BUTTON_TEXTS = _all_menu_button_texts()


def main_menu_action_for_text(text: str | None) -> Optional[MainMenuAction]:
    stripped = (text or "").strip()
    if not stripped:
        return None
    if stripped in (t("btn_create_card", "ru"), t("btn_create_card", "en")):
        return "create_card"
    if stripped in (t("btn_profile_settings", "ru"), t("btn_profile_settings", "en")):
        return "profile"
    if stripped in (t("btn_help_short", "ru"), t("btn_help_short", "en")):
        return "help"
    return None
