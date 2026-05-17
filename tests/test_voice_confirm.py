"""Voice transcription confirmation flow."""
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest

from handlers import main
from handlers.states import CardStates
from utils.i18n import t
from utils.voice_confirm import (
    PENDING_VOICE_CHAT_ID_KEY,
    PENDING_VOICE_CONFIRM_MESSAGE_ID_KEY,
    PENDING_VOICE_FIELD_KEY,
    PENDING_VOICE_SOURCE_MESSAGE_ID_KEY,
    PENDING_VOICE_TEXT_KEY,
    VOICE_CONFIRM_OK,
    VOICE_CONFIRM_RETRY,
    VOICE_CONFIRM_TYPE,
    VOICE_FIELD_HOLIDAY,
    VOICE_FIELD_IMAGE,
    clear_pending_voice_payload,
    format_voice_confirm_prompt,
    pending_voice_payload,
    state_matches_pending_field,
    voice_confirm_button_labels,
    voice_confirm_keyboard,
)


def test_pending_voice_payload_stores_message_ids() -> None:
    payload = pending_voice_payload(
        VOICE_FIELD_IMAGE,
        "текст",
        chat_id=42,
        source_message_id=100,
        confirm_message_id=101,
    )
    assert payload[PENDING_VOICE_FIELD_KEY] == VOICE_FIELD_IMAGE
    assert payload[PENDING_VOICE_TEXT_KEY] == "текст"
    assert payload[PENDING_VOICE_CHAT_ID_KEY] == 42
    assert payload[PENDING_VOICE_SOURCE_MESSAGE_ID_KEY] == 100
    assert payload[PENDING_VOICE_CONFIRM_MESSAGE_ID_KEY] == 101
    cleared = clear_pending_voice_payload()
    assert cleared[PENDING_VOICE_CONFIRM_MESSAGE_ID_KEY] is None


def test_voice_confirm_prompt_ru_localized() -> None:
    text = format_voice_confirm_prompt("ru", "щенок на снегу")
    assert "Я распознала так" in text
    assert "«щенок на снегу»" in text


def test_image_voice_handler_offers_confirmation_not_advance() -> None:
    source = inspect.getsource(main.on_image_description_voice)
    assert "_transcribe_and_offer_voice_confirm" in source
    assert "_go_to_holiday_prompt" not in source


def test_text_handlers_use_cleanup() -> None:
    assert "_cleanup_pending_voice_confirmation" in inspect.getsource(main.on_image_description)
    assert "_cleanup_pending_voice_confirmation" in inspect.getsource(main.on_holiday)


@pytest.mark.asyncio
async def test_transcribe_and_offer_stores_pending_ids() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.update_data = AsyncMock()

    message = MagicMock()
    message.chat.id = 42
    message.message_id = 100
    message.answer = AsyncMock()
    recognizing = MagicMock()
    recognizing.chat.id = 42
    recognizing.message_id = 99
    confirm_msg = MagicMock()
    confirm_msg.message_id = 101
    message.answer.side_effect = [recognizing, confirm_msg]

    with (
        patch.object(main, "_transcribe_voice_message", AsyncMock(return_value="hello")),
        patch.object(main, "_safe_delete_message", AsyncMock()),
    ):
        await main._transcribe_and_offer_voice_confirm(
            MagicMock(), message, state, "ru", MagicMock(), field=VOICE_FIELD_IMAGE
        )

    payload = state.update_data.await_args.kwargs
    assert payload[PENDING_VOICE_SOURCE_MESSAGE_ID_KEY] == 100
    assert payload[PENDING_VOICE_CONFIRM_MESSAGE_ID_KEY] == 101
    assert payload[PENDING_VOICE_CHAT_ID_KEY] == 42


@pytest.mark.asyncio
async def test_new_voice_cleans_up_previous_pending() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={PENDING_VOICE_FIELD_KEY: VOICE_FIELD_IMAGE})
    state.update_data = AsyncMock()

    message = MagicMock()
    message.chat.id = 1
    message.message_id = 200
    recognizing = MagicMock()
    recognizing.chat.id = 1
    recognizing.message_id = 201
    confirm_msg = MagicMock()
    confirm_msg.message_id = 202
    message.answer = AsyncMock(side_effect=[recognizing, confirm_msg])

    cleanup = AsyncMock()
    with (
        patch.object(main, "_cleanup_pending_voice_confirmation", cleanup),
        patch.object(main, "_transcribe_voice_message", AsyncMock(return_value="new")),
        patch.object(main, "_safe_delete_message", AsyncMock()),
    ):
        await main._transcribe_and_offer_voice_confirm(
            MagicMock(), message, state, "ru", MagicMock(), field=VOICE_FIELD_IMAGE
        )

    cleanup.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_deletes_confirm_and_source() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            PENDING_VOICE_CHAT_ID_KEY: 7,
            PENDING_VOICE_SOURCE_MESSAGE_ID_KEY: 10,
            PENDING_VOICE_CONFIRM_MESSAGE_ID_KEY: 11,
            PENDING_VOICE_FIELD_KEY: VOICE_FIELD_IMAGE,
            PENDING_VOICE_TEXT_KEY: "x",
        }
    )
    state.update_data = AsyncMock()
    bot = MagicMock()
    delete = AsyncMock()

    with patch.object(main, "_safe_delete_message", delete):
        snapshot = await main._cleanup_pending_voice_confirmation(bot, state)

    assert delete.await_count == 2
    delete.assert_any_await(bot, 7, 10)
    delete.assert_any_await(bot, 7, 11)
    assert snapshot[PENDING_VOICE_TEXT_KEY] == "x"
    state.update_data.assert_awaited()


@pytest.mark.asyncio
async def test_cleanup_delete_failure_does_not_crash() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            PENDING_VOICE_CHAT_ID_KEY: 1,
            PENDING_VOICE_SOURCE_MESSAGE_ID_KEY: 2,
            PENDING_VOICE_CONFIRM_MESSAGE_ID_KEY: 3,
        }
    )
    state.update_data = AsyncMock()
    bot = MagicMock()
    bot.delete_message = AsyncMock(
        side_effect=TelegramBadRequest(method=MagicMock(), message="gone")
    )

    await main._cleanup_pending_voice_confirmation(bot, state)
    state.update_data.assert_awaited()


@pytest.mark.asyncio
async def test_confirm_deletes_source_not_confirm_before_finalize() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            PENDING_VOICE_FIELD_KEY: VOICE_FIELD_IMAGE,
            PENDING_VOICE_TEXT_KEY: "щенок",
            PENDING_VOICE_CHAT_ID_KEY: 1,
            PENDING_VOICE_SOURCE_MESSAGE_ID_KEY: 50,
            PENDING_VOICE_CONFIRM_MESSAGE_ID_KEY: 51,
        }
    )
    state.get_state = AsyncMock(return_value=CardStates.image_description.state)

    cq = MagicMock()
    cq.data = VOICE_CONFIRM_OK
    cq.message = MagicMock()
    cq.message.edit_reply_markup = AsyncMock()
    cq.from_user.id = 1
    cq.answer = AsyncMock()

    cleanup = AsyncMock()
    with (
        patch.object(main, "_lang_from_state", AsyncMock(return_value="ru")),
        patch.object(main, "_cleanup_pending_voice_confirmation", cleanup),
        patch.object(main, "_apply_confirmed_image_voice", AsyncMock()),
    ):
        await main.on_voice_confirm_action(cq, state, MagicMock())

    cleanup.assert_awaited_once()
    assert cleanup.await_args.kwargs["delete_confirm"] is False
    assert cleanup.await_args.kwargs["delete_source"] is True


@pytest.mark.asyncio
async def test_retry_deletes_both_messages_and_reprompts() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            PENDING_VOICE_FIELD_KEY: VOICE_FIELD_HOLIDAY,
            PENDING_VOICE_TEXT_KEY: "8 марта",
        }
    )
    state.get_state = AsyncMock(return_value=CardStates.holiday.state)

    cq = MagicMock()
    cq.data = VOICE_CONFIRM_RETRY
    cq.from_user.id = 1
    cq.answer = AsyncMock()

    cleanup = AsyncMock()
    reprompt = AsyncMock()
    with (
        patch.object(main, "_lang_from_state", AsyncMock(return_value="en")),
        patch.object(main, "_cleanup_pending_voice_confirmation", cleanup),
        patch.object(main, "_reprompt_voice_field", reprompt),
    ):
        await main.on_voice_confirm_action(cq, state, MagicMock())

    cleanup.assert_awaited_once()
    reprompt.assert_awaited_once()
    assert reprompt.await_args.args[2] == "en"
    assert reprompt.await_args.args[3] == VOICE_FIELD_HOLIDAY


@pytest.mark.asyncio
async def test_type_instead_deletes_messages() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={PENDING_VOICE_FIELD_KEY: VOICE_FIELD_IMAGE})
    state.get_state = AsyncMock(return_value=CardStates.image_description.state)

    cq = MagicMock()
    cq.data = VOICE_CONFIRM_TYPE
    cq.from_user.id = 1
    cq.answer = AsyncMock()

    cleanup = AsyncMock()
    with (
        patch.object(main, "_lang_from_state", AsyncMock(return_value="ru")),
        patch.object(main, "_cleanup_pending_voice_confirmation", cleanup),
        patch.object(main, "_reprompt_voice_field", AsyncMock()),
    ):
        await main.on_voice_confirm_action(cq, state, MagicMock())

    cleanup.assert_awaited_once()


@pytest.mark.asyncio
async def test_typed_text_triggers_cleanup() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            PENDING_VOICE_FIELD_KEY: VOICE_FIELD_IMAGE,
            "image_idea_mode": "custom",
        }
    )
    state.update_data = AsyncMock()

    message = MagicMock()
    message.text = "щенок"
    message.from_user.id = 1

    cleanup = AsyncMock()
    finalize = AsyncMock()
    with (
        patch.object(main, "_lang_from_state", AsyncMock(return_value="ru")),
        patch.object(main, "_cleanup_pending_voice_confirmation", cleanup),
        patch.object(main, "get_settings", return_value=MagicMock()),
        patch.object(main, "validate_image_description", return_value=True),
        patch.object(main, "_finalize_text_step", finalize),
        patch.object(main, "_go_to_holiday_prompt", AsyncMock()),
        patch.object(main, "is_small_talk_text", return_value=False),
    ):
        await main.on_image_description(message, state, MagicMock())

    cleanup.assert_awaited_once()
    finalize.assert_awaited_once()
