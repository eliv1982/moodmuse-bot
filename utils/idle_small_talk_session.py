"""
Idle (no-wizard) conversational small-talk session — FSM data only, no DB schema.
"""
from __future__ import annotations

import time
from typing import Any

from aiogram.fsm.context import FSMContext

from utils.i18n import Lang
from utils.wizard_input import is_idle_casual_text, is_idle_chat_intent, is_small_talk_text

IDLE_SMALL_TALK_ACTIVE = "idle_small_talk_active"
IDLE_SMALL_TALK_TURNS = "idle_small_talk_turns"
IDLE_SMALL_TALK_LAST_AT = "idle_small_talk_last_at"
IDLE_SMALL_TALK_LAST_FALLBACK_IDX = "idle_small_talk_last_fallback_idx"

MAX_IDLE_SMALL_TALK_TURNS = 5
IDLE_SMALL_TALK_SESSION_TTL_SEC = 20 * 60

IDLE_FALLBACK_MESSAGE_KEYS = (
    "small_talk_idle",
    "small_talk_idle_2",
    "small_talk_idle_3",
)


def _session_turns(data: dict[str, Any]) -> int:
    try:
        return int(data.get(IDLE_SMALL_TALK_TURNS) or 0)
    except (TypeError, ValueError):
        return 0


def is_idle_small_talk_session_active(data: dict[str, Any]) -> bool:
    if not data.get(IDLE_SMALL_TALK_ACTIVE):
        return False
    if _session_turns(data) >= MAX_IDLE_SMALL_TALK_TURNS:
        return False
    last_at = data.get(IDLE_SMALL_TALK_LAST_AT)
    if last_at is not None:
        try:
            if time.time() - float(last_at) > IDLE_SMALL_TALK_SESSION_TTL_SEC:
                return False
        except (TypeError, ValueError):
            pass
    return True


def should_use_idle_ai(raw: str, lang: Lang, data: dict[str, Any]) -> bool:
    """Greeting, chat invite, or casual idle text starts AI; follow-ups while session is active."""
    if is_idle_small_talk_session_active(data):
        return True
    if is_small_talk_text(raw, lang):
        return True
    if is_idle_chat_intent(raw, lang):
        return True
    return is_idle_casual_text(raw, lang)


def idle_ai_block_reason(raw: str, lang: Lang, data: dict[str, Any]) -> str | None:
    """Why deterministic routing skips idle AI (for logs). None when AI should run."""
    if should_use_idle_ai(raw, lang, data):
        return None
    return "no_idle_ai_trigger"


def next_idle_small_talk_turn(data: dict[str, Any]) -> int:
    """Turn number for the upcoming AI reply (1-based)."""
    if is_idle_small_talk_session_active(data):
        return _session_turns(data) + 1
    return 1


async def clear_idle_small_talk_session(state: FSMContext) -> None:
    await state.update_data(
        **{
            IDLE_SMALL_TALK_ACTIVE: False,
            IDLE_SMALL_TALK_TURNS: 0,
            IDLE_SMALL_TALK_LAST_AT: None,
            IDLE_SMALL_TALK_LAST_FALLBACK_IDX: None,
        }
    )


async def mark_idle_small_talk_turn(state: FSMContext, turn: int) -> None:
    await state.update_data(
        **{
            IDLE_SMALL_TALK_ACTIVE: True,
            IDLE_SMALL_TALK_TURNS: turn,
            IDLE_SMALL_TALK_LAST_AT: time.time(),
        }
    )


def pick_idle_fallback_index(last_idx: int | None, *, count: int = len(IDLE_FALLBACK_MESSAGE_KEYS)) -> int:
    if last_idx is None or last_idx < 0 or last_idx >= count:
        return 0
    return (last_idx + 1) % count
