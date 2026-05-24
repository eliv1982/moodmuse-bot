"""Wizard typed free-text confirmation and meta-questions."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from handlers import main
from handlers.states import CardStates
from utils.field_confirm import (
    FIELD_HOLIDAY,
    FIELD_IMAGE,
    PENDING_TEXT_FIELD_KEY,
    PENDING_TEXT_VALUE_KEY,
    TEXT_CONFIRM_CHANGE,
    TEXT_CONFIRM_OK,
    TEXT_SOURCE_TYPED,
)
from utils.i18n import t
from utils.wizard_input import is_wizard_meta_question


@pytest.mark.asyncio
async def test_holiday_typed_shows_confirmation_not_finalize() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    message = MagicMock()
    message.text = "день рождения"
    message.from_user.id = 1
    message.chat.id = 1
    message.message_id = 10

    offer = AsyncMock()
    with (
        patch.object(main, "_lang_from_state", AsyncMock(return_value="ru")),
        patch.object(main, "_offer_field_text_confirm", offer),
        patch.object(main, "is_small_talk_text", return_value=False),
        patch.object(main, "is_wizard_meta_question", return_value=False),
    ):
        await main.on_holiday(message, state, MagicMock())

    offer.assert_awaited_once()
    assert offer.await_args.args[5] == "день рождения"
    assert offer.await_args.kwargs["source"] == TEXT_SOURCE_TYPED


@pytest.mark.asyncio
async def test_holiday_meta_question_not_saved() -> None:
    assert is_wizard_meta_question("что предложишь?", FIELD_HOLIDAY, "ru")

    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    message = MagicMock()
    message.text = "что предложишь?"
    message.from_user.id = 1
    message.chat.id = 1
    message.message_id = 11
    message.answer = AsyncMock()

    offer = AsyncMock()
    finalize = AsyncMock()
    meta_help = AsyncMock()
    with (
        patch.object(main, "_lang_from_state", AsyncMock(return_value="ru")),
        patch.object(main, "_safe_delete_message", AsyncMock()),
        patch.object(main, "_reply_wizard_meta_help", meta_help),
        patch.object(main, "_offer_field_text_confirm", offer),
        patch.object(main, "_finalize_text_step", finalize),
        patch.object(main, "is_small_talk_text", return_value=False),
    ):
        await main.on_holiday(message, state, MagicMock())

    meta_help.assert_awaited_once()
    offer.assert_not_awaited()
    finalize.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirm_holiday_saves_and_advances() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            PENDING_TEXT_FIELD_KEY: FIELD_HOLIDAY,
            PENDING_TEXT_VALUE_KEY: "8 Марта",
        }
    )
    state.get_state = AsyncMock(return_value=CardStates.holiday.state)

    cq = MagicMock()
    cq.data = TEXT_CONFIRM_OK
    cq.message = MagicMock()
    cq.message.edit_reply_markup = AsyncMock()
    cq.from_user.id = 1
    cq.answer = AsyncMock()

    apply_holiday = AsyncMock()
    with (
        patch.object(main, "_lang_from_state", AsyncMock(return_value="ru")),
        patch.object(main, "_cleanup_pending_field_confirmation", AsyncMock()),
        patch.object(main, "_apply_confirmed_holiday", apply_holiday),
    ):
        await main.on_field_confirm_action(cq, state, MagicMock())

    apply_holiday.assert_awaited_once()
    assert apply_holiday.await_args.args[4] == "8 Марта"


@pytest.mark.asyncio
async def test_confirm_change_reprompts_holiday() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={PENDING_TEXT_FIELD_KEY: FIELD_HOLIDAY})
    state.get_state = AsyncMock(return_value=CardStates.holiday.state)

    cq = MagicMock()
    cq.data = TEXT_CONFIRM_CHANGE
    cq.from_user.id = 1
    cq.answer = AsyncMock()

    reprompt = AsyncMock()
    with (
        patch.object(main, "_lang_from_state", AsyncMock(return_value="ru")),
        patch.object(main, "_cleanup_pending_field_confirmation", AsyncMock()),
        patch.object(main, "_reprompt_field", reprompt),
    ):
        await main.on_field_confirm_action(cq, state, MagicMock())

    reprompt.assert_awaited_once()
    assert reprompt.await_args.args[3] == FIELD_HOLIDAY


@pytest.mark.asyncio
async def test_image_meta_points_to_surprise_button() -> None:
    assert is_wizard_meta_question("придумай сам", FIELD_IMAGE, "ru")

    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"image_idea_mode": "custom"})
    message = MagicMock()
    message.text = "придумай сам"
    message.from_user.id = 1
    message.chat.id = 2
    message.message_id = 20
    message.answer = AsyncMock()

    meta_help = AsyncMock()
    with (
        patch.object(main, "_lang_from_state", AsyncMock(return_value="ru")),
        patch.object(main, "get_settings", return_value=MagicMock()),
        patch.object(main, "_safe_delete_message", AsyncMock()),
        patch.object(main, "_reply_wizard_meta_help", meta_help),
        patch.object(main, "_offer_field_text_confirm", AsyncMock()),
        patch.object(main, "is_small_talk_text", return_value=False),
    ):
        await main.on_image_description(message, state, MagicMock())

    meta_help.assert_awaited_once()
    assert meta_help.await_args.args[4] == FIELD_IMAGE


@pytest.mark.asyncio
async def test_image_typed_offers_confirmation() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"image_idea_mode": "custom"})
    message = MagicMock()
    message.text = "щенок на снегу"
    message.from_user.id = 1

    offer = AsyncMock()
    with (
        patch.object(main, "_lang_from_state", AsyncMock(return_value="ru")),
        patch.object(main, "get_settings", return_value=MagicMock()),
        patch.object(main, "_offer_field_text_confirm", offer),
        patch.object(main, "is_small_talk_text", return_value=False),
        patch.object(main, "is_wizard_meta_question", return_value=False),
    ):
        await main.on_image_description(message, state, MagicMock())

    offer.assert_awaited_once()
    assert offer.await_args.args[4] == FIELD_IMAGE


def test_text_confirm_prompt_ru_en() -> None:
    from utils.field_confirm import format_field_confirm_prompt, TEXT_SOURCE_TYPED

    ru = format_field_confirm_prompt("ru", "тест", source=TEXT_SOURCE_TYPED)
    en = format_field_confirm_prompt("en", "test", source=TEXT_SOURCE_TYPED)
    assert "Я понял так" in ru
    assert "Is that correct" in en


def test_meta_question_en_holiday() -> None:
    assert is_wizard_meta_question("what do you suggest", FIELD_HOLIDAY, "en")
