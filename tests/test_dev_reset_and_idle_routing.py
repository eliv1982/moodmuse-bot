"""Admin dev profile reset and idle small-talk routing after /start."""
from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from handlers.admin import cmd_dev_reset_me
from handlers.main import _idle_small_talk_reply_text, cmd_start, on_small_talk
from handlers.profile import perform_dev_profile_reset
from handlers.states import ProfileStates
from services.storage import get_storage, init_storage, reset_storage_for_tests
from utils.idle_small_talk_session import should_use_idle_ai
from utils.profile_ui import profile_main_keyboard
from utils.wizard_input import is_idle_chat_intent


def test_is_idle_chat_intent_ru_conversation_invite() -> None:
    assert is_idle_chat_intent("а как насчет поговорить?", "ru")
    assert is_idle_chat_intent("давай поболтаем", "ru")
    assert not is_idle_chat_intent("горы", "ru")


def test_should_use_idle_ai_for_chat_invite() -> None:
    assert should_use_idle_ai("а как насчет поговорить?", "ru", {})


def test_on_small_talk_not_limited_to_state_none() -> None:
    import handlers.main as main_mod

    handler_source = inspect.getsource(on_small_talk)
    module_source = inspect.getsource(main_mod)
    assert "StateFilter(None)" not in handler_source
    assert "_NON_IDLE_TEXT_STATES" in module_source
    assert "ProfileStates.onboarding_name" in module_source


def test_cmd_start_returning_does_not_set_profile_onboarding_state() -> None:
    source = inspect.getsource(cmd_start)
    assert "start_profile_onboarding" in source
    assert "ProfileStates.onboarding_name" not in source
    assert "ProfileStates.confirming_name" not in source


def test_profile_keyboard_dev_reset_only_for_admin() -> None:
    kb_user = profile_main_keyboard("ru", show_dev_reset=False)
    kb_admin = profile_main_keyboard("ru", show_dev_reset=True)
    user_cbs = {btn.callback_data for row in kb_user.inline_keyboard for btn in row}
    admin_cbs = {btn.callback_data for row in kb_admin.inline_keyboard for btn in row}
    assert "profile:dev_reset" not in user_cbs
    assert "profile:dev_reset" in admin_cbs


@pytest.mark.asyncio
async def test_dev_reset_me_rejected_for_non_admin() -> None:
    message = MagicMock()
    message.from_user = MagicMock(id=999)
    message.answer = AsyncMock()
    state = MagicMock()
    state.clear = AsyncMock()

    with (
        patch("handlers.admin.get_storage") as mock_storage,
        patch("handlers.admin.is_admin_user_id", return_value=False),
    ):
        mock_storage.return_value.get_user_lang.return_value = "ru"
        await cmd_dev_reset_me(message, state)

    message.answer.assert_awaited_once()
    assert "администратор" in message.answer.await_args.args[0].lower()
    state.clear.assert_not_awaited()
    mock_storage.return_value.reset_user_profile_data.assert_not_called()


@pytest.mark.asyncio
async def test_dev_reset_me_clears_profile_for_admin(tmp_path: Path) -> None:
    reset_storage_for_tests()
    init_storage(tmp_path / "dev_reset.db")
    st = get_storage()
    uid = 123456789
    st.set_user_lang(uid, "en")
    st.update_profile_preference(uid, display_name="Tester", text_tone="playful")
    st.increment_generation(uid)
    st.save_last_card(
        uid,
        __import__("services.storage", fromlist=["LastCardContext"]).LastCardContext(
            occasion="occasion_clients",
            image_description="x",
            holiday="NY",
            image_style="style_realistic",
            text_style="text_warm",
            lang="en",
            image_prompt_en="draft",
        ),
    )

    message = MagicMock()
    message.from_user = MagicMock(id=uid)
    message.answer = AsyncMock()
    state = MagicMock()
    state.clear = AsyncMock()

    with patch("handlers.admin.is_admin_user_id", return_value=True):
        await cmd_dev_reset_me(message, state)

    assert st.user_needs_profile_onboarding(uid) is True
    assert st.get_daily_count(uid) == 1
    assert st.get_last_card(uid) is not None
    state.clear.assert_awaited_once()
    reset_storage_for_tests()


def test_reset_user_profile_data_does_not_touch_other_users(tmp_path: Path) -> None:
    reset_storage_for_tests()
    init_storage(tmp_path / "dev_reset_isolated.db")
    st = get_storage()
    st.update_profile_preference(1, display_name="One")
    st.update_profile_preference(2, display_name="Two")
    st.reset_user_profile_data(1)
    assert st.get_profile_preferences(1).display_name == ""
    assert st.get_profile_preferences(2).display_name == "Two"
    reset_storage_for_tests()


@pytest.mark.asyncio
async def test_idle_chat_invite_uses_ai_not_template() -> None:
    state = MagicMock()
    state.get_data = AsyncMock(return_value={})
    state.update_data = AsyncMock()

    with (
        patch("handlers.main.get_storage") as mock_storage,
        patch("handlers.main.get_settings") as mock_settings,
        patch("handlers.main.text_provider_configured", return_value=True),
        patch(
            "handlers.main.generate_idle_small_talk",
            new_callable=AsyncMock,
            return_value="Sure, let's chat!",
        ) as mock_ai,
    ):
        mock_storage.return_value.is_small_talk_enabled.return_value = True
        text = await _idle_small_talk_reply_text(
            "\u0430 \u043a\u0430\u043a \u043d\u0430\u0441\u0447\u0435\u0442 \u043f\u043e\u0433\u043e\u0432\u043e\u0440\u0438\u0442\u044c?",
            "ru",
            state,
        )

    assert text == "Sure, let's chat!"
    mock_ai.assert_awaited_once()


@pytest.mark.asyncio
async def test_perform_dev_profile_reset_clears_fsm(tmp_path: Path) -> None:
    reset_storage_for_tests()
    init_storage(tmp_path / "fsm_reset.db")
    uid = 42
    get_storage().update_profile_preference(uid, display_name="Ann")
    state = MagicMock()
    state.clear = AsyncMock()

    await perform_dev_profile_reset(uid, state)

    assert get_storage().user_needs_profile_onboarding(uid) is True
    state.clear.assert_awaited_once()
    reset_storage_for_tests()
