"""Idle small-talk routing and create-card intent (Telegram regressions)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from handlers.main import on_small_talk
from utils.idle_small_talk_session import (
    IDLE_SMALL_TALK_ACTIVE,
    IDLE_SMALL_TALK_TURNS,
    should_use_idle_ai,
)
from utils.prompts import build_text_system_prompt
from utils.wizard_input import is_create_card_intent, is_idle_casual_text


def test_is_idle_casual_text_ru_fun_request() -> None:
    assert is_idle_casual_text("расскажи что-то прикольное", "ru")
    assert is_idle_casual_text("а еще что-нибудь?", "ru")
    assert not is_idle_casual_text("создать открытку", "ru")


def test_should_use_idle_ai_for_casual_phrases() -> None:
    assert should_use_idle_ai("расскажи что-то прикольное", "ru", {})
    assert should_use_idle_ai(
        "а еще что-нибудь?",
        "ru",
        {IDLE_SMALL_TALK_ACTIVE: True, IDLE_SMALL_TALK_TURNS: 1},
    )


def test_create_card_intent_explicit_only() -> None:
    assert is_create_card_intent("создать открытку", "ru")
    assert is_create_card_intent("хочу открытку", "ru")
    assert is_create_card_intent("давай сделаем открытку", "ru")
    assert not is_create_card_intent("давай сделаем", "ru")
    assert not is_create_card_intent("расскажи что-то прикольное", "ru")
    assert not is_create_card_intent("поболтаем", "ru")
    assert not is_create_card_intent("как дела", "ru")


def test_build_text_system_prompt_en_language_lock() -> None:
    prompt = build_text_system_prompt("occasion_loved", "text_warm", "en")
    assert "CRITICAL OUTPUT LANGUAGE" in prompt
    assert "English only" in prompt


@pytest.mark.asyncio
async def test_on_small_talk_fun_request_calls_ai() -> None:
    message = MagicMock()
    message.text = "расскажи что-то прикольное"
    message.from_user = MagicMock(id=7)
    message.answer = AsyncMock()
    state = MagicMock()
    state.get_state = AsyncMock(return_value=None)
    state.update_data = AsyncMock()

    with (
        patch("handlers.main.get_storage") as mock_storage,
        patch(
            "handlers.main._idle_small_talk_reply_text",
            new_callable=AsyncMock,
            return_value="AI fun fact",
        ) as mock_reply,
        patch("handlers.main._start_create_card_flow", new_callable=AsyncMock) as mock_wizard,
    ):
        mock_storage.return_value.get_user_lang.return_value = "ru"
        await on_small_talk(message, state)

    mock_wizard.assert_not_awaited()
    mock_reply.assert_awaited_once()
    assert mock_reply.await_args.args[0] == "расскажи что-то прикольное"


@pytest.mark.asyncio
async def test_on_small_talk_create_card_starts_wizard() -> None:
    message = MagicMock()
    message.text = "создать открытку"
    message.from_user = MagicMock(id=8)
    message.answer = AsyncMock()
    state = MagicMock()
    state.get_state = AsyncMock(return_value=None)
    state.clear = AsyncMock()
    state.update_data = AsyncMock()

    with (
        patch("handlers.main.get_storage") as mock_storage,
        patch("handlers.main.clear_idle_small_talk_session", new_callable=AsyncMock),
        patch(
            "handlers.main._start_create_card_flow",
            new_callable=AsyncMock,
        ) as mock_wizard,
        patch(
            "handlers.main._idle_small_talk_reply_text",
            new_callable=AsyncMock,
        ) as mock_reply,
    ):
        mock_storage.return_value.get_user_lang.return_value = "ru"
        await on_small_talk(message, state)

    mock_wizard.assert_awaited_once()
    mock_reply.assert_not_awaited()
