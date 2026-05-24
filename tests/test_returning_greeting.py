"""Returning /start greeting and create-card intent from idle chat."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from handlers import main
from services.small_talk import IdleSmallTalkError, generate_returning_start_greeting
from utils.i18n import t
from utils.main_menu import main_menu_reply_keyboard
from utils.wizard_input import is_create_card_intent


def test_start_returning_fallback_copy() -> None:
    text = t("start_returning_fallback", "ru", name="Лена")
    assert "Лена" in text
    assert "настроение" in text.lower()
    assert "кнопка ниже" in text.lower()
    assert "рада" not in text.lower()


def test_is_create_card_intent_ru() -> None:
    assert is_create_card_intent("давай сделаем открытку", "ru")
    assert is_create_card_intent("хочу открытку", "ru")
    assert not is_create_card_intent("давай сделаем", "ru")
    assert not is_create_card_intent("как дела", "ru")


def test_is_create_card_intent_en() -> None:
    assert is_create_card_intent("let's make a card", "en")
    assert is_create_card_intent("create a card", "en")
    assert not is_create_card_intent("nice weather", "en")


@pytest.mark.asyncio
async def test_returning_start_uses_ai_when_available() -> None:
    storage = MagicMock()
    storage.is_small_talk_enabled.return_value = True
    with (
        patch("handlers.main.get_storage", return_value=storage),
        patch.object(main, "text_provider_configured", return_value=True),
        patch.object(
            main,
            "generate_returning_start_greeting",
            AsyncMock(return_value="👋 Лена, с возвращением!"),
        ) as gen,
    ):
        text = await main._returning_start_greeting("Лена", "ru")
    gen.assert_awaited_once()
    assert "Лена" in text


@pytest.mark.asyncio
async def test_returning_start_falls_back_when_ai_unavailable() -> None:
    storage = MagicMock()
    storage.is_small_talk_enabled.return_value = True
    with (
        patch("handlers.main.get_storage", return_value=storage),
        patch.object(main, "text_provider_configured", return_value=True),
        patch.object(
            main,
            "generate_returning_start_greeting",
            AsyncMock(side_effect=IdleSmallTalkError("fail")),
        ),
    ):
        text = await main._returning_start_greeting("Лена", "ru")
    assert text == main._returning_start_fallback("Лена", "ru")


@pytest.mark.asyncio
async def test_cmd_start_returning_attaches_main_menu() -> None:
    message = MagicMock()
    message.from_user = MagicMock(id=1, first_name="Лена")
    message.answer = AsyncMock()
    state = AsyncMock()
    state.clear = AsyncMock()
    state.update_data = AsyncMock()
    storage = MagicMock()
    storage.get_user_lang.return_value = "ru"
    storage.user_needs_profile_onboarding.return_value = False
    storage.get_profile_preferences.return_value = MagicMock(display_name="Лена")

    with (
        patch.object(main, "get_storage", return_value=storage),
        patch.object(main, "_returning_start_greeting", AsyncMock(return_value="👋 hi")),
        patch.object(main, "_answer_with_main_menu", AsyncMock()) as answer_menu,
    ):
        await main.cmd_start(message, state)

    answer_menu.assert_awaited_once()
    assert answer_menu.await_args.args[2] == "ru"


@pytest.mark.asyncio
async def test_on_small_talk_attaches_main_menu() -> None:
    message = MagicMock()
    message.text = "привет"
    message.from_user = MagicMock(id=1)
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})

    with (
        patch.object(main, "is_create_card_intent", return_value=False),
        patch.object(main, "_idle_small_talk_reply_text", AsyncMock(return_value="Привет!")),
        patch.object(main, "_answer_with_main_menu", AsyncMock()) as answer_menu,
        patch.object(main, "get_storage") as storage_mock,
    ):
        storage_mock.return_value.get_user_lang.return_value = "ru"
        await main.on_small_talk(message, state)

    answer_menu.assert_awaited_once()
    assert answer_menu.await_args.args[2] == "ru"


@pytest.mark.asyncio
async def test_on_small_talk_create_card_intent_starts_wizard() -> None:
    message = MagicMock()
    message.text = "создать открытку"
    message.from_user = MagicMock(id=1)
    state = AsyncMock()
    state.get_state = AsyncMock(return_value=None)
    state.clear = AsyncMock()

    with (
        patch.object(main, "get_storage") as storage_mock,
        patch.object(main, "clear_idle_small_talk_session", AsyncMock()),
        patch.object(main, "_start_create_card_flow", AsyncMock()) as start_flow,
        patch.object(main, "_idle_small_talk_reply_text", AsyncMock()) as idle,
    ):
        storage_mock.return_value.get_user_lang.return_value = "ru"
        await main.on_small_talk(message, state)

    start_flow.assert_awaited_once()
    idle.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_returning_start_greeting_prefixes_name() -> None:
    settings = MagicMock()
    mock_provider = MagicMock()
    mock_provider.generate_greeting_text = AsyncMock(return_value="С возвращением!")
    with patch("services.small_talk.get_text_provider", return_value=mock_provider):
        text = await generate_returning_start_greeting("Лена", lang="ru", settings=settings)
    assert "Лена" in text
