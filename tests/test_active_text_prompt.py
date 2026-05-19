"""Active free-text wizard prompt cleanup."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest

from handlers import main
from utils.active_text_prompt import (
    ACTIVE_TEXT_PROMPT_CHAT_ID_KEY,
    ACTIVE_TEXT_PROMPT_FIELD_KEY,
    ACTIVE_TEXT_PROMPT_MESSAGE_ID_KEY,
    TEXT_FIELD_HOLIDAY,
    TEXT_FIELD_IMAGE,
    active_text_prompt_payload,
)


@pytest.mark.asyncio
async def test_finalize_text_step_deletes_active_prompt() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            ACTIVE_TEXT_PROMPT_FIELD_KEY: TEXT_FIELD_IMAGE,
            ACTIVE_TEXT_PROMPT_CHAT_ID_KEY: 10,
            ACTIVE_TEXT_PROMPT_MESSAGE_ID_KEY: 20,
        }
    )
    state.update_data = AsyncMock()

    message = MagicMock()
    message.chat.id = 1
    message.message_id = 99
    message.answer = AsyncMock()

    delete_active = AsyncMock()
    with patch.object(main, "_delete_active_text_prompt", delete_active):
        await main._finalize_text_step(
            MagicMock(), state, message, "ru", "confirmed_image_idea", text="x"
        )

    delete_active.assert_awaited_once()
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_apply_confirmed_image_voice_deletes_prompt() -> None:
    state = AsyncMock()
    state.update_data = AsyncMock()

    anchor = MagicMock()
    anchor.chat.id = 1
    anchor.message_id = 50

    with (
        patch.object(main, "validate_image_description", return_value=True),
        patch.object(main, "_finalize_text_step", AsyncMock()) as fin,
        patch.object(main, "_go_to_image_style_prompt", AsyncMock()),
    ):
        await main._apply_confirmed_image_voice(MagicMock(), state, anchor, "ru", "щенок")

    fin.assert_awaited_once()


@pytest.mark.asyncio
async def test_apply_confirmed_holiday_voice_deletes_prompt() -> None:
    state = AsyncMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()

    with (
        patch.object(main, "validate_holiday", return_value=True),
        patch.object(main, "_finalize_text_step", AsyncMock()) as fin,
        patch.object(main, "_go_to_image_idea_prompt", AsyncMock()) as go_idea,
    ):
        await main._apply_confirmed_holiday_voice(
            MagicMock(), state, MagicMock(), "ru", "8 марта"
        )
    fin.assert_awaited_once()
    go_idea.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_active_text_prompt_swallows_telegram_error() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            ACTIVE_TEXT_PROMPT_CHAT_ID_KEY: 1,
            ACTIVE_TEXT_PROMPT_MESSAGE_ID_KEY: 2,
        }
    )
    state.update_data = AsyncMock()
    bot = MagicMock()
    bot.delete_message = AsyncMock(
        side_effect=TelegramBadRequest(method=MagicMock(), message="gone")
    )

    await main._delete_active_text_prompt(bot, state)
    state.update_data.assert_awaited()


@pytest.mark.asyncio
async def test_replace_stored_prompt_clears_previous_same_field() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            ACTIVE_TEXT_PROMPT_FIELD_KEY: TEXT_FIELD_IMAGE,
            ACTIVE_TEXT_PROMPT_CHAT_ID_KEY: 1,
            ACTIVE_TEXT_PROMPT_MESSAGE_ID_KEY: 2,
            "prompt_chat_id": 1,
            "prompt_msg_id": 2,
        }
    )
    state.update_data = AsyncMock()

    anchor = MagicMock()
    anchor.answer = AsyncMock(return_value=MagicMock(chat=MagicMock(id=1), message_id=3))

    delete_active = AsyncMock()
    with (
        patch.object(main, "_edit_stored_prompt", AsyncMock(return_value=False)),
        patch.object(main, "_delete_stored_prompt", AsyncMock()),
        patch.object(main, "_delete_active_text_prompt", delete_active),
    ):
        await main._replace_stored_prompt(
            MagicMock(),
            state,
            anchor,
            "prompt",
            prompt_kind="image_custom",
        )

    delete_active.assert_awaited_once()


@pytest.mark.asyncio
async def test_typed_holiday_offers_confirmation() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    message = MagicMock()
    message.text = "день рождения"
    message.from_user.id = 1

    offer = AsyncMock()
    with (
        patch.object(main, "_lang_from_state", AsyncMock(return_value="ru")),
        patch.object(main, "_offer_field_text_confirm", offer),
        patch.object(main, "is_small_talk_text", return_value=False),
        patch.object(main, "is_wizard_meta_question", return_value=False),
    ):
        await main.on_holiday(message, state, MagicMock())

    offer.assert_awaited_once()


def test_active_text_prompt_payload_keys() -> None:
    p = active_text_prompt_payload(TEXT_FIELD_HOLIDAY, 5, 6)
    assert p[ACTIVE_TEXT_PROMPT_FIELD_KEY] == TEXT_FIELD_HOLIDAY
    assert p[ACTIVE_TEXT_PROMPT_CHAT_ID_KEY] == 5
    assert p[ACTIVE_TEXT_PROMPT_MESSAGE_ID_KEY] == 6
