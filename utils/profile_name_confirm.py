"""
Profile display-name confirmation (typed or voice) — separate from wizard field confirm.
"""
from __future__ import annotations

import html
from typing import Any, Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from utils.i18n import Lang, t

CB_PROFILE_NAME_OK = "profile:name:ok"
CB_PROFILE_NAME_CHANGE = "profile:name:change"

PROFILE_NAME_CONFIRM_CALLBACKS = frozenset({CB_PROFILE_NAME_OK, CB_PROFILE_NAME_CHANGE})

PENDING_PROFILE_NAME_KEY = "pending_profile_name"
PENDING_PROFILE_NAME_MODE_KEY = "pending_profile_name_mode"
PENDING_PROFILE_NAME_CHAT_ID_KEY = "pending_profile_name_chat_id"
PENDING_PROFILE_NAME_SOURCE_MSG_ID_KEY = "pending_profile_name_source_msg_id"
PENDING_PROFILE_NAME_CONFIRM_MSG_ID_KEY = "pending_profile_name_confirm_msg_id"

NameConfirmMode = Literal["onboarding", "editing"]


def escape_name_display(text: str) -> str:
    return html.escape(text.strip())


def format_profile_name_confirm_prompt(lang: Lang, name: str) -> str:
    return t("profile_name_confirm", lang, name=escape_name_display(name))


def profile_name_confirm_keyboard(lang: Lang) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_profile_name_ok", lang),
                    callback_data=CB_PROFILE_NAME_OK,
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("btn_profile_name_change", lang),
                    callback_data=CB_PROFILE_NAME_CHANGE,
                )
            ],
        ]
    )


def pending_profile_name_payload(
    name: str,
    mode: NameConfirmMode,
    *,
    chat_id: int,
    source_message_id: int,
    confirm_message_id: int,
) -> dict[str, Any]:
    return {
        PENDING_PROFILE_NAME_KEY: name,
        PENDING_PROFILE_NAME_MODE_KEY: mode,
        PENDING_PROFILE_NAME_CHAT_ID_KEY: chat_id,
        PENDING_PROFILE_NAME_SOURCE_MSG_ID_KEY: source_message_id,
        PENDING_PROFILE_NAME_CONFIRM_MSG_ID_KEY: confirm_message_id,
    }


def clear_pending_profile_name_payload() -> dict[str, None]:
    return {
        PENDING_PROFILE_NAME_KEY: None,
        PENDING_PROFILE_NAME_MODE_KEY: None,
        PENDING_PROFILE_NAME_CHAT_ID_KEY: None,
        PENDING_PROFILE_NAME_SOURCE_MSG_ID_KEY: None,
        PENDING_PROFILE_NAME_CONFIRM_MSG_ID_KEY: None,
    }


def read_pending_profile_name_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    return {
        PENDING_PROFILE_NAME_KEY: data.get(PENDING_PROFILE_NAME_KEY),
        PENDING_PROFILE_NAME_MODE_KEY: data.get(PENDING_PROFILE_NAME_MODE_KEY),
        PENDING_PROFILE_NAME_CHAT_ID_KEY: data.get(PENDING_PROFILE_NAME_CHAT_ID_KEY),
        PENDING_PROFILE_NAME_SOURCE_MSG_ID_KEY: data.get(PENDING_PROFILE_NAME_SOURCE_MSG_ID_KEY),
        PENDING_PROFILE_NAME_CONFIRM_MSG_ID_KEY: data.get(PENDING_PROFILE_NAME_CONFIRM_MSG_ID_KEY),
    }
