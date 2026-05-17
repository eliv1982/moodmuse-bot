"""
Voice transcription confirmation (FSM helpers and inline keyboard).
"""
from __future__ import annotations

import html
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from handlers.states import CardStates
from utils.i18n import Lang, t

VOICE_FIELD_IMAGE = "image_description"
VOICE_FIELD_HOLIDAY = "holiday"

VOICE_CONFIRM_OK = "voice_confirm_ok"
VOICE_CONFIRM_RETRY = "voice_confirm_retry"
VOICE_CONFIRM_TYPE = "voice_confirm_type"

VOICE_CONFIRM_CALLBACKS = frozenset(
    {
        VOICE_CONFIRM_OK,
        VOICE_CONFIRM_RETRY,
        VOICE_CONFIRM_TYPE,
    }
)

PENDING_VOICE_FIELD_KEY = "pending_voice_field"
PENDING_VOICE_TEXT_KEY = "pending_voice_text"
PENDING_VOICE_CHAT_ID_KEY = "pending_voice_chat_id"
PENDING_VOICE_SOURCE_MESSAGE_ID_KEY = "pending_voice_source_message_id"
PENDING_VOICE_CONFIRM_MESSAGE_ID_KEY = "pending_voice_confirm_message_id"

_STATE_FOR_FIELD: dict[str, str] = {
    VOICE_FIELD_IMAGE: CardStates.image_description.state,
    VOICE_FIELD_HOLIDAY: CardStates.holiday.state,
}

_FIELD_PROMPT: dict[str, tuple[str, str]] = {
    VOICE_FIELD_IMAGE: ("image_idea_custom_prompt", "image_custom"),
    VOICE_FIELD_HOLIDAY: ("step2_holiday", "holiday"),
}


def escape_voice_display(text: str) -> str:
    return html.escape(text.strip())


def format_voice_confirm_prompt(lang: Lang, recognized_text: str) -> str:
    return t("voice_confirm_prompt", lang, text=escape_voice_display(recognized_text))


def voice_confirm_keyboard(lang: Lang) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("btn_voice_confirm_ok", lang), callback_data=VOICE_CONFIRM_OK)],
            [
                InlineKeyboardButton(text=t("btn_voice_confirm_retry", lang), callback_data=VOICE_CONFIRM_RETRY),
                InlineKeyboardButton(text=t("btn_voice_confirm_type", lang), callback_data=VOICE_CONFIRM_TYPE),
            ],
        ]
    )


def voice_confirm_button_labels(lang: Lang) -> dict[str, str]:
    return {
        VOICE_CONFIRM_OK: t("btn_voice_confirm_ok", lang),
        VOICE_CONFIRM_RETRY: t("btn_voice_confirm_retry", lang),
        VOICE_CONFIRM_TYPE: t("btn_voice_confirm_type", lang),
    }


def state_matches_pending_field(current_state: str | None, pending_field: str | None) -> bool:
    if not pending_field:
        return False
    expected = _STATE_FOR_FIELD.get(pending_field)
    return expected is not None and current_state == expected


def field_prompt_for_voice_field(field: str) -> tuple[str, str] | None:
    pair = _FIELD_PROMPT.get(field)
    if not pair:
        return None
    return pair


def pending_voice_payload(
    field: str,
    text: str,
    *,
    chat_id: int,
    source_message_id: int,
    confirm_message_id: int,
) -> dict[str, Any]:
    return {
        PENDING_VOICE_FIELD_KEY: field,
        PENDING_VOICE_TEXT_KEY: text,
        PENDING_VOICE_CHAT_ID_KEY: chat_id,
        PENDING_VOICE_SOURCE_MESSAGE_ID_KEY: source_message_id,
        PENDING_VOICE_CONFIRM_MESSAGE_ID_KEY: confirm_message_id,
    }


def clear_pending_voice_payload() -> dict[str, None]:
    return {
        PENDING_VOICE_FIELD_KEY: None,
        PENDING_VOICE_TEXT_KEY: None,
        PENDING_VOICE_CHAT_ID_KEY: None,
        PENDING_VOICE_SOURCE_MESSAGE_ID_KEY: None,
        PENDING_VOICE_CONFIRM_MESSAGE_ID_KEY: None,
    }


def read_pending_voice_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    return {
        PENDING_VOICE_FIELD_KEY: data.get(PENDING_VOICE_FIELD_KEY),
        PENDING_VOICE_TEXT_KEY: data.get(PENDING_VOICE_TEXT_KEY),
        PENDING_VOICE_CHAT_ID_KEY: data.get(PENDING_VOICE_CHAT_ID_KEY),
        PENDING_VOICE_SOURCE_MESSAGE_ID_KEY: data.get(PENDING_VOICE_SOURCE_MESSAGE_ID_KEY),
        PENDING_VOICE_CONFIRM_MESSAGE_ID_KEY: data.get(PENDING_VOICE_CONFIRM_MESSAGE_ID_KEY),
    }
