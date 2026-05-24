"""
Wizard free-text confirmation (typed and voice) — FSM-backed, no text in callbacks.
"""
from __future__ import annotations

import html
from typing import Any, Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from handlers.states import CardStates
from utils.i18n import Lang, t

FIELD_IMAGE = "image_description"
FIELD_HOLIDAY = "holiday"
FIELD_OCCASION_DETAILS = "occasion_details"
FIELD_RECIPIENT_ADDRESS = "recipient_address"
FIELD_SENDER_SIGNATURE = "sender_signature"

# Legacy aliases (voice_confirm module name in imports)
VOICE_FIELD_IMAGE = FIELD_IMAGE
VOICE_FIELD_HOLIDAY = FIELD_HOLIDAY

TEXT_CONFIRM_OK = "field_confirm_ok"
TEXT_CONFIRM_CHANGE = "field_confirm_change"
TEXT_CONFIRM_SUGGEST = "field_confirm_suggest"

FIELD_CONFIRM_CALLBACKS = frozenset(
    {
        TEXT_CONFIRM_OK,
        TEXT_CONFIRM_CHANGE,
        TEXT_CONFIRM_SUGGEST,
    }
)

# Legacy callback names (same data values)
VOICE_CONFIRM_OK = TEXT_CONFIRM_OK
VOICE_CONFIRM_RETRY = TEXT_CONFIRM_CHANGE
VOICE_CONFIRM_TYPE = TEXT_CONFIRM_CHANGE
VOICE_CONFIRM_CALLBACKS = FIELD_CONFIRM_CALLBACKS

TEXT_SOURCE_TYPED = "typed"
TEXT_SOURCE_VOICE = "voice"
TextSource = Literal["typed", "voice"]

PENDING_TEXT_FIELD_KEY = "pending_text_field"
PENDING_TEXT_VALUE_KEY = "pending_text_value"
PENDING_TEXT_CHAT_ID_KEY = "pending_text_chat_id"
PENDING_TEXT_SOURCE_MESSAGE_ID_KEY = "pending_text_source_message_id"
PENDING_TEXT_CONFIRM_MESSAGE_ID_KEY = "pending_text_confirm_message_id"
PENDING_TEXT_SOURCE_KEY = "pending_text_source"

# Legacy key aliases
PENDING_VOICE_FIELD_KEY = PENDING_TEXT_FIELD_KEY
PENDING_VOICE_TEXT_KEY = PENDING_TEXT_VALUE_KEY
PENDING_VOICE_CHAT_ID_KEY = PENDING_TEXT_CHAT_ID_KEY
PENDING_VOICE_SOURCE_MESSAGE_ID_KEY = PENDING_TEXT_SOURCE_MESSAGE_ID_KEY
PENDING_VOICE_CONFIRM_MESSAGE_ID_KEY = PENDING_TEXT_CONFIRM_MESSAGE_ID_KEY

_STATE_FOR_FIELD: dict[str, str] = {
    FIELD_IMAGE: CardStates.image_description.state,
    FIELD_HOLIDAY: CardStates.holiday.state,
    FIELD_OCCASION_DETAILS: CardStates.occasion_details.state,
    FIELD_RECIPIENT_ADDRESS: CardStates.recipient_address.state,
    FIELD_SENDER_SIGNATURE: CardStates.sender_signature.state,
}

_FIELD_PROMPT: dict[str, tuple[str, str]] = {
    FIELD_IMAGE: ("image_idea_custom_prompt", "image_custom"),
    FIELD_HOLIDAY: ("step2_holiday", "holiday"),
    FIELD_OCCASION_DETAILS: ("wizard_occasion_details_ask", "occasion_details"),
    FIELD_RECIPIENT_ADDRESS: ("wizard_recipient_address_ask", "recipient_address"),
    FIELD_SENDER_SIGNATURE: ("wizard_signature_ask", "sender_signature"),
}

_FIELD_REPROMPT: dict[str, str] = {
    FIELD_OCCASION_DETAILS: "wizard_occasion_details_retry",
    FIELD_RECIPIENT_ADDRESS: "wizard_recipient_address_retry",
    FIELD_SENDER_SIGNATURE: "wizard_signature_retry",
}


def escape_field_display(text: str) -> str:
    return html.escape(text.strip())


def format_field_confirm_prompt(
    lang: Lang,
    recognized_text: str,
    *,
    source: TextSource,
    field: str | None = None,
) -> str:
    if field == FIELD_OCCASION_DETAILS:
        return t("occasion_details_confirm", lang, value=escape_field_display(recognized_text))
    if field == FIELD_RECIPIENT_ADDRESS:
        return t("recipient_address_confirm", lang, value=escape_field_display(recognized_text))
    if field == FIELD_SENDER_SIGNATURE:
        return t("signature_confirm", lang, signature=escape_field_display(recognized_text))
    if source == TEXT_SOURCE_VOICE:
        return t("voice_confirm_prompt", lang, text=escape_field_display(recognized_text))
    return t("text_confirm_prompt", lang, text=escape_field_display(recognized_text))


def field_reprompt_key(field: str) -> str | None:
    return _FIELD_REPROMPT.get(field)


def field_confirm_button_labels(lang: Lang, field: str) -> dict[str, str]:
    labels = {
        TEXT_CONFIRM_OK: t("btn_field_confirm_ok", lang),
        TEXT_CONFIRM_CHANGE: t("btn_field_confirm_change", lang),
    }
    if field in (FIELD_IMAGE, FIELD_HOLIDAY):
        labels[TEXT_CONFIRM_SUGGEST] = t("btn_field_confirm_suggest", lang)
    return labels


def voice_confirm_button_labels(lang: Lang) -> dict[str, str]:
    return field_confirm_button_labels(lang, FIELD_IMAGE)


def field_confirm_keyboard(lang: Lang, field: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=t("btn_field_confirm_ok", lang), callback_data=TEXT_CONFIRM_OK)],
        [InlineKeyboardButton(text=t("btn_field_confirm_change", lang), callback_data=TEXT_CONFIRM_CHANGE)],
    ]
    if field in (FIELD_IMAGE, FIELD_HOLIDAY):
        rows.append(
            [
                InlineKeyboardButton(
                    text=t("btn_field_confirm_suggest", lang),
                    callback_data=TEXT_CONFIRM_SUGGEST,
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def state_matches_pending_field(current_state: str | None, pending_field: str | None) -> bool:
    if not pending_field:
        return False
    expected = _STATE_FOR_FIELD.get(pending_field)
    return expected is not None and current_state == expected


def field_prompt_for_field(field: str) -> tuple[str, str] | None:
    pair = _FIELD_PROMPT.get(field)
    if not pair:
        return None
    return pair


def field_prompt_i18n_key(field: str, *, reprompt: bool = False) -> str | None:
    if reprompt:
        return field_reprompt_key(field)
    pair = field_prompt_for_field(field)
    return pair[0] if pair else None


def pending_text_payload(
    field: str,
    text: str,
    *,
    chat_id: int,
    source_message_id: int,
    confirm_message_id: int,
    source: TextSource = TEXT_SOURCE_VOICE,
) -> dict[str, Any]:
    return {
        PENDING_TEXT_FIELD_KEY: field,
        PENDING_TEXT_VALUE_KEY: text,
        PENDING_TEXT_CHAT_ID_KEY: chat_id,
        PENDING_TEXT_SOURCE_MESSAGE_ID_KEY: source_message_id,
        PENDING_TEXT_CONFIRM_MESSAGE_ID_KEY: confirm_message_id,
        PENDING_TEXT_SOURCE_KEY: source,
    }


def clear_pending_text_payload() -> dict[str, None]:
    return {
        PENDING_TEXT_FIELD_KEY: None,
        PENDING_TEXT_VALUE_KEY: None,
        PENDING_TEXT_CHAT_ID_KEY: None,
        PENDING_TEXT_SOURCE_MESSAGE_ID_KEY: None,
        PENDING_TEXT_CONFIRM_MESSAGE_ID_KEY: None,
        PENDING_TEXT_SOURCE_KEY: None,
    }


def read_pending_text_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    return {
        PENDING_TEXT_FIELD_KEY: data.get(PENDING_TEXT_FIELD_KEY),
        PENDING_TEXT_VALUE_KEY: data.get(PENDING_TEXT_VALUE_KEY),
        PENDING_TEXT_CHAT_ID_KEY: data.get(PENDING_TEXT_CHAT_ID_KEY),
        PENDING_TEXT_SOURCE_MESSAGE_ID_KEY: data.get(PENDING_TEXT_SOURCE_MESSAGE_ID_KEY),
        PENDING_TEXT_CONFIRM_MESSAGE_ID_KEY: data.get(PENDING_TEXT_CONFIRM_MESSAGE_ID_KEY),
        PENDING_TEXT_SOURCE_KEY: data.get(PENDING_TEXT_SOURCE_KEY),
    }


# Legacy names
pending_voice_payload = pending_text_payload
clear_pending_voice_payload = clear_pending_text_payload
read_pending_voice_snapshot = read_pending_text_snapshot
format_voice_confirm_prompt = lambda lang, text: format_field_confirm_prompt(
    lang, text, source=TEXT_SOURCE_VOICE
)
voice_confirm_keyboard = lambda lang: field_confirm_keyboard(lang, FIELD_IMAGE)
