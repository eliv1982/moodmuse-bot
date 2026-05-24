"""
FSM tracking for free-text wizard instruction prompts (voice/text input steps).
"""
from __future__ import annotations

from typing import Any

ACTIVE_TEXT_PROMPT_FIELD_KEY = "active_text_prompt_field"
ACTIVE_TEXT_PROMPT_CHAT_ID_KEY = "active_text_prompt_chat_id"
ACTIVE_TEXT_PROMPT_MESSAGE_ID_KEY = "active_text_prompt_message_id"

TEXT_FIELD_IMAGE = "image_description"
TEXT_FIELD_HOLIDAY = "holiday"
TEXT_FIELD_OCCASION_DETAILS = "occasion_details"
TEXT_FIELD_RECIPIENT_ADDRESS = "recipient_address"
TEXT_FIELD_SENDER_SIGNATURE = "sender_signature"

PROMPT_KIND_TO_TEXT_FIELD: dict[str, str] = {
    "image_custom": TEXT_FIELD_IMAGE,
    "holiday": TEXT_FIELD_HOLIDAY,
    "occasion_details": TEXT_FIELD_OCCASION_DETAILS,
    "recipient_address": TEXT_FIELD_RECIPIENT_ADDRESS,
    "sender_signature": TEXT_FIELD_SENDER_SIGNATURE,
}


def text_field_for_prompt_kind(prompt_kind: str | None) -> str | None:
    if not prompt_kind:
        return None
    return PROMPT_KIND_TO_TEXT_FIELD.get(prompt_kind)


def active_text_prompt_payload(
    field: str,
    chat_id: int,
    message_id: int,
) -> dict[str, Any]:
    return {
        ACTIVE_TEXT_PROMPT_FIELD_KEY: field,
        ACTIVE_TEXT_PROMPT_CHAT_ID_KEY: chat_id,
        ACTIVE_TEXT_PROMPT_MESSAGE_ID_KEY: message_id,
    }


def clear_active_text_prompt_payload() -> dict[str, None]:
    return {
        ACTIVE_TEXT_PROMPT_FIELD_KEY: None,
        ACTIVE_TEXT_PROMPT_CHAT_ID_KEY: None,
        ACTIVE_TEXT_PROMPT_MESSAGE_ID_KEY: None,
    }
