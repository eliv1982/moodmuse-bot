"""
FSM tracking for temporary wizard helper/meta messages (deleted on field completion).
"""
from __future__ import annotations

from typing import Any

ACTIVE_HELP_FIELD_KEY = "active_help_field"
ACTIVE_HELP_CHAT_ID_KEY = "active_help_chat_id"
ACTIVE_HELP_MESSAGE_ID_KEY = "active_help_message_id"

HELP_FIELD_OCCASION = "choosing_occasion"
HELP_FIELD_IMAGE_IDEA = "image_idea"

CONFIRM_KEY_TO_HELP_FIELD: dict[str, str] = {
    "confirmed_holiday": "holiday",
    "confirmed_image_idea": "image_description",
}


def help_field_for_confirm_key(confirm_key: str) -> str | None:
    return CONFIRM_KEY_TO_HELP_FIELD.get(confirm_key)


def active_help_payload(field: str, chat_id: int, message_id: int) -> dict[str, Any]:
    return {
        ACTIVE_HELP_FIELD_KEY: field,
        ACTIVE_HELP_CHAT_ID_KEY: chat_id,
        ACTIVE_HELP_MESSAGE_ID_KEY: message_id,
    }


def clear_active_help_payload() -> dict[str, None]:
    return {
        ACTIVE_HELP_FIELD_KEY: None,
        ACTIVE_HELP_CHAT_ID_KEY: None,
        ACTIVE_HELP_MESSAGE_ID_KEY: None,
    }


def read_active_help_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    return {
        ACTIVE_HELP_FIELD_KEY: data.get(ACTIVE_HELP_FIELD_KEY),
        ACTIVE_HELP_CHAT_ID_KEY: data.get(ACTIVE_HELP_CHAT_ID_KEY),
        ACTIVE_HELP_MESSAGE_ID_KEY: data.get(ACTIVE_HELP_MESSAGE_ID_KEY),
    }
