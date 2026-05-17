"""Card wizard step order: recipient → holiday → image idea → styles."""
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from handlers import main
from handlers.states import CardStates
from utils.i18n import t
from utils.wizard_summary import build_generation_summary
from utils.wizard_ui import IMAGE_IDEA_CUSTOM, IMAGE_IDEA_SURPRISE


@pytest.mark.asyncio
async def test_occasion_advances_to_holiday() -> None:
    cq = MagicMock()
    cq.data = "occasion_colleagues"
    cq.message = MagicMock()
    cq.from_user.id = 1
    cq.answer = AsyncMock()
    state = AsyncMock()
    state.update_data = AsyncMock()

    with (
        patch.object(main, "_lang_from_state", AsyncMock(return_value="ru")),
        patch.object(main, "_collapse_callback_message", AsyncMock()),
        patch.object(main, "_go_to_holiday_prompt", AsyncMock()) as go_holiday,
    ):
        await main.on_occasion(cq, state)

    go_holiday.assert_awaited_once_with(cq.message, state, "ru")


@pytest.mark.asyncio
async def test_holiday_typed_advances_to_image_idea() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.update_data = AsyncMock()

    message = MagicMock()
    message.text = "8 Марта"
    message.from_user.id = 1

    with (
        patch.object(main, "_lang_from_state", AsyncMock(return_value="ru")),
        patch.object(main, "_cleanup_pending_voice_confirmation", AsyncMock()),
        patch.object(main, "validate_holiday", return_value=True),
        patch.object(main, "_finalize_text_step", AsyncMock()),
        patch.object(main, "_go_to_image_idea_prompt", AsyncMock()) as go_idea,
        patch.object(main, "is_small_talk_text", return_value=False),
    ):
        await main.on_holiday(message, state, MagicMock())

    go_idea.assert_awaited_once_with(message, state, "ru")


@pytest.mark.asyncio
async def test_holiday_voice_confirm_advances_to_image_idea() -> None:
    state = AsyncMock()
    state.update_data = AsyncMock()
    anchor = MagicMock()

    with (
        patch.object(main, "validate_holiday", return_value=True),
        patch.object(main, "_finalize_text_step", AsyncMock()),
        patch.object(main, "_go_to_image_idea_prompt", AsyncMock()) as go_idea,
    ):
        await main._apply_confirmed_holiday_voice(
            MagicMock(), state, anchor, "ru", "день рождения"
        )

    go_idea.assert_awaited_once_with(anchor, state, "ru")


@pytest.mark.asyncio
async def test_image_idea_surprise_advances_to_image_style() -> None:
    cq = MagicMock()
    cq.message = MagicMock()
    cq.from_user.id = 1
    cq.answer = AsyncMock()
    state = AsyncMock()
    state.update_data = AsyncMock()

    with (
        patch.object(main, "_lang_from_state", AsyncMock(return_value="ru")),
        patch.object(main, "_collapse_callback_message", AsyncMock()),
        patch.object(main, "_go_to_image_style_prompt", AsyncMock()) as go_style,
        patch.object(main, "_surprise_phrase", return_value="придумай сам"),
    ):
        await main.on_image_idea_surprise(cq, state)

    go_style.assert_awaited_once_with(cq.message, state, "ru")


@pytest.mark.asyncio
async def test_image_idea_custom_opens_custom_prompt() -> None:
    cq = MagicMock()
    cq.message = MagicMock()
    cq.from_user.id = 1
    cq.answer = AsyncMock()
    state = AsyncMock()
    state.update_data = AsyncMock()
    bot = MagicMock()

    replace = AsyncMock()
    with (
        patch.object(main, "_lang_from_state", AsyncMock(return_value="ru")),
        patch.object(main, "_replace_stored_prompt", replace),
    ):
        await main.on_image_idea_custom(cq, state, bot)

    state.update_data.assert_awaited_once()
    assert state.update_data.await_args.kwargs.get("image_idea_mode") == "custom"
    replace.assert_awaited_once()
    assert replace.await_args.kwargs.get("prompt_kind") == "image_custom"


@pytest.mark.asyncio
async def test_custom_image_idea_typed_advances_to_image_style() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"image_idea_mode": "custom"})
    state.update_data = AsyncMock()

    message = MagicMock()
    message.text = "щенок на снегу"
    message.from_user.id = 1

    with (
        patch.object(main, "_lang_from_state", AsyncMock(return_value="ru")),
        patch.object(main, "_cleanup_pending_voice_confirmation", AsyncMock()),
        patch.object(main, "get_settings", return_value=MagicMock()),
        patch.object(main, "validate_image_description", return_value=True),
        patch.object(main, "_finalize_text_step", AsyncMock()),
        patch.object(main, "_go_to_image_style_prompt", AsyncMock()) as go_style,
        patch.object(main, "is_small_talk_text", return_value=False),
    ):
        await main.on_image_description(message, state, MagicMock())

    go_style.assert_awaited_once_with(message, state, "ru")


@pytest.mark.asyncio
async def test_custom_image_idea_voice_confirm_advances_to_image_style() -> None:
    state = AsyncMock()
    state.update_data = AsyncMock()
    anchor = MagicMock()

    with (
        patch.object(main, "validate_image_description", return_value=True),
        patch.object(main, "_finalize_text_step", AsyncMock()),
        patch.object(main, "_go_to_image_style_prompt", AsyncMock()) as go_style,
    ):
        await main._apply_confirmed_image_voice(
            MagicMock(), state, anchor, "ru", "щенок на снегу"
        )

    go_style.assert_awaited_once_with(anchor, state, "ru")


def test_go_to_image_idea_prompt_uses_question_keyboard() -> None:
    source = inspect.getsource(main._go_to_image_idea_prompt)
    assert "image_idea_question" in source
    assert "image_idea_mode" in source
    assert "CardStates.image_description" in source


def test_resend_prompt_order_holiday_before_image_idea() -> None:
    source = inspect.getsource(main._resend_current_prompt)
    holiday_pos = source.index("CardStates.holiday.state")
    image_pos = source.index("CardStates.image_description.state")
    assert holiday_pos < image_pos


def test_generation_summary_field_order() -> None:
    text = build_generation_summary(
        lang="ru",
        occasion="occasion_colleagues",
        image_description="щенок на снегу",
        holiday="8 Марта",
        image_style="style_realistic",
        text_style="text_humor",
    )
    occasion_pos = text.index("Для кого")
    holiday_pos = text.index("Повод")
    idea_pos = text.index("Идея картинки")
    image_style_pos = text.index("Стиль картинки")
    text_style_pos = text.index("Стиль текста")
    assert occasion_pos < holiday_pos < idea_pos < image_style_pos < text_style_pos


def test_image_idea_keyboard_has_only_two_buttons() -> None:
    from utils.wizard_ui import image_idea_keyboard

    callbacks = {cb for row in image_idea_keyboard("ru") for _, cb in row}
    assert callbacks == {IMAGE_IDEA_SURPRISE, IMAGE_IDEA_CUSTOM}
    assert t("step2_holiday", "ru").startswith("Какой праздник или повод")
