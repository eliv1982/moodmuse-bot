"""Temporary wizard helper message tracking and cleanup."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest

from handlers import main
from handlers.states import CardStates
from utils.active_wizard_help import (
    ACTIVE_HELP_FIELD_KEY,
    ACTIVE_HELP_MESSAGE_ID_KEY,
    HELP_FIELD_IMAGE_IDEA,
    active_help_payload,
)
from utils.field_confirm import FIELD_HOLIDAY, FIELD_IMAGE


@pytest.mark.asyncio
async def test_holiday_meta_help_stores_active_helper() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.update_data = AsyncMock()
    message = MagicMock()
    message.chat.id = 10
    message.message_id = 20
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=99, chat=MagicMock(id=10)))

    with patch.object(main, "_safe_delete_message", AsyncMock()):
        await main._reply_wizard_meta_help(bot, message, state, "ru", FIELD_HOLIDAY)

    payload = state.update_data.await_args.kwargs
    assert payload[ACTIVE_HELP_FIELD_KEY] == FIELD_HOLIDAY
    assert payload[ACTIVE_HELP_MESSAGE_ID_KEY] == 99


@pytest.mark.asyncio
async def test_second_meta_help_deletes_previous() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value=active_help_payload(FIELD_HOLIDAY, 10, 50)
    )
    state.update_data = AsyncMock()
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=51, chat=MagicMock(id=10)))
    delete_help = AsyncMock()

    with patch.object(main, "_delete_active_wizard_help", delete_help):
        await main._send_wizard_helper(bot, state, 10, "ru", FIELD_HOLIDAY, "help again")

    delete_help.assert_awaited_once_with(bot, state, FIELD_HOLIDAY)
    assert state.update_data.await_args.kwargs[ACTIVE_HELP_MESSAGE_ID_KEY] == 51


@pytest.mark.asyncio
async def test_finalize_holiday_deletes_active_helper() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.update_data = AsyncMock()
    message = MagicMock()
    message.chat.id = 1
    message.message_id = 2
    message.answer = AsyncMock()
    bot = MagicMock()
    delete_help = AsyncMock()

    with (
        patch.object(main, "_delete_active_text_prompt", AsyncMock()),
        patch.object(main, "_delete_active_wizard_help", delete_help),
        patch.object(main, "_safe_delete_message", AsyncMock()),
        patch.object(main, "_clear_stored_prompt", AsyncMock()),
    ):
        await main._finalize_text_step(
            bot, state, message, "ru", "confirmed_holiday", text="8 Марта"
        )

    delete_help.assert_awaited_once_with(bot, state, FIELD_HOLIDAY)
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_finalize_image_deletes_active_helper() -> None:
    state = AsyncMock()
    message = MagicMock()
    message.answer = AsyncMock()
    bot = MagicMock()
    delete_help = AsyncMock()

    with (
        patch.object(main, "_delete_active_text_prompt", AsyncMock()),
        patch.object(main, "_delete_active_wizard_help", delete_help),
        patch.object(main, "_safe_delete_message", AsyncMock()),
        patch.object(main, "_clear_stored_prompt", AsyncMock()),
    ):
        await main._finalize_text_step(
            bot, state, message, "en", "confirmed_image_idea", text="puppy"
        )

    delete_help.assert_awaited_once_with(bot, state, FIELD_IMAGE)


@pytest.mark.asyncio
async def test_delete_active_help_failure_does_not_crash() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value=active_help_payload(FIELD_HOLIDAY, 1, 5)
    )
    state.update_data = AsyncMock()
    bot = MagicMock()
    bot.delete_message = AsyncMock(
        side_effect=TelegramBadRequest(method=MagicMock(), message="gone")
    )

    with patch.object(main, "_safe_delete_message", AsyncMock()):
        await main._delete_active_wizard_help(bot, state, FIELD_HOLIDAY)

    state.update_data.assert_awaited()


@pytest.mark.asyncio
async def test_finalize_does_not_delete_confirmation_message() -> None:
    """Finalize posts confirmation via answer(); only helper is deleted via _delete_active_wizard_help."""
    state = AsyncMock()
    message = MagicMock()
    message.answer = AsyncMock(return_value=MagicMock(message_id=200))
    bot = MagicMock()

    with (
        patch.object(main, "_delete_active_text_prompt", AsyncMock()),
        patch.object(main, "_delete_active_wizard_help", AsyncMock()),
        patch.object(main, "_safe_delete_message", AsyncMock()) as delete_msg,
        patch.object(main, "_clear_stored_prompt", AsyncMock()),
    ):
        await main._finalize_text_step(
            bot, state, message, "ru", "confirmed_holiday", text="день рождения"
        )

    message.answer.assert_awaited_once()
    delete_msg.assert_awaited_once_with(bot, message.chat.id, message.message_id)


@pytest.mark.asyncio
async def test_holiday_meta_question_uses_tracked_helper() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    message = MagicMock()
    message.text = "что предложишь?"
    message.from_user.id = 1
    message.chat.id = 5
    message.message_id = 6

    tracked = AsyncMock()
    with (
        patch.object(main, "_lang_from_state", AsyncMock(return_value="ru")),
        patch.object(main, "_cleanup_pending_field_confirmation", AsyncMock()),
        patch.object(main, "is_small_talk_text", return_value=False),
        patch.object(main, "_reply_wizard_meta_help", tracked),
    ):
        await main.on_holiday(message, state, MagicMock())

    tracked.assert_awaited_once()
    assert tracked.await_args.args[4] == FIELD_HOLIDAY
