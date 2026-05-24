"""Main menu reply keyboard and post-generation UX."""
from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from handlers import main
from handlers.profile import on_profile_home
from services.storage import LastCardContext, get_storage, init_storage, reset_storage_for_tests
from utils.i18n import t
from utils.main_menu import MAIN_MENU_BUTTON_TEXTS, main_menu_action_for_text, main_menu_reply_keyboard


def test_main_menu_two_rows_no_language_button() -> None:
    kb = main_menu_reply_keyboard("en")
    assert len(kb.keyboard) == 2
    assert len(kb.keyboard[0]) == 2
    assert len(kb.keyboard[1]) == 1
    assert kb.is_persistent is True
    assert kb.one_time_keyboard is False
    all_labels = {btn.text for row in kb.keyboard for btn in row}
    assert t("btn_create_card", "en") in all_labels
    assert t("btn_profile_settings", "en") in all_labels
    assert t("btn_help_short", "en") in all_labels
    assert t("btn_change_lang_short", "en") not in all_labels


def test_main_menu_action_for_text() -> None:
    assert main_menu_action_for_text(t("btn_create_card", "ru")) == "create_card"
    assert main_menu_action_for_text(t("btn_profile_settings", "en")) == "profile"
    assert main_menu_action_for_text("random") is None
    assert len(MAIN_MENU_BUTTON_TEXTS) == 6


def test_after_card_keyboard_two_by_two_layout() -> None:
    kb = main.after_card_keyboard("ru", "ru")
    assert len(kb.inline_keyboard) == 2
    assert len(kb.inline_keyboard[0]) == 2
    assert len(kb.inline_keyboard[1]) == 2
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert callbacks == ["regen_repeat", "regen_text", "regen_image", "regen_card_lang"]


def test_after_card_keyboard_ru_ui_ru_card_shows_in_english() -> None:
    kb = main.after_card_keyboard("ru", "ru")
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert labels[0] == t("regen_repeat", "ru")
    assert labels[1] == t("regen_text", "ru")
    assert labels[2] == t("regen_image", "ru")
    assert labels[3] == t("regen_card_lang_en", "ru")


def test_after_card_keyboard_ru_ui_en_card_shows_na_russkom() -> None:
    kb = main.after_card_keyboard("ru", "en")
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert labels[0] == t("regen_repeat", "ru")
    assert labels[3] == t("regen_card_lang_ru", "ru")


def test_after_card_keyboard_en_ui_en_card_shows_na_russkom() -> None:
    kb = main.after_card_keyboard("en", "en")
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert labels[0] == t("regen_repeat", "en")
    assert labels[3] == t("regen_card_lang_ru", "en")


def test_after_card_keyboard_no_create_another_or_change_lang() -> None:
    kb = main.after_card_keyboard("ru", "ru")
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "create_another" not in callbacks
    assert "change_lang" not in callbacks


def test_small_talk_attaches_reply_main_menu() -> None:
    source = inspect.getsource(main.on_small_talk)
    assert "_answer_with_main_menu" in source
    assert "home_keyboard" not in source


def test_wizard_holiday_handler_does_not_attach_main_menu() -> None:
    source = inspect.getsource(main.on_holiday)
    assert "main_menu_reply_keyboard" not in source
    assert "_answer_with_main_menu" not in source


def test_generation_reasserts_main_menu_after_card_photo() -> None:
    source = inspect.getsource(main._run_card_generation_from_wizard)
    assert "_reassert_main_menu_keyboard" in source
    assert "after_card_keyboard" in source
    assert "ReplyKeyboardRemove" not in source


def test_card_ready_menu_is_meaningful_not_bare_sparkle() -> None:
    ru = t("card_ready_menu", "ru")
    en = t("card_ready_menu", "en")
    assert ru != "✨"
    assert en != "✨"
    assert "кнопка уже внизу" in ru.lower()
    assert "button is below" in en.lower()


def test_reassert_main_menu_uses_reply_keyboard() -> None:
    source = inspect.getsource(main._reassert_main_menu_keyboard)
    assert 't("card_ready_menu"' in source
    assert "main_menu_reply_keyboard" in source


def test_regen_card_lang_reasserts_main_menu() -> None:
    source = inspect.getsource(main.regen_card_lang)
    assert "_reassert_main_menu_keyboard" in source


@pytest.mark.asyncio
async def test_regen_card_lang_does_not_change_profile_language(tmp_path) -> None:
    reset_storage_for_tests()
    init_storage(tmp_path / "bot.db")
    uid = 42
    st = get_storage()
    st.set_user_lang(uid, "ru")
    ctx = LastCardContext(
        occasion="occasion_loved",
        image_description="cake",
        holiday="день рождения",
        image_style="style_realistic",
        text_style="text_warm",
        lang="ru",
        image_prompt_en="cake",
        photo_file_id="photo123",
        caption_html="Привет",
        recipient_address="Влад",
        sender_signature="С Леной",
        occasion_details="20 лет",
    )
    st.save_last_card(uid, ctx)

    cq = MagicMock()
    cq.from_user.id = uid
    cq.message = MagicMock()
    cq.message.photo = [MagicMock(file_id="photo123")]
    cq.answer = AsyncMock()
    cq.message.answer_photo = AsyncMock(return_value=MagicMock(photo=[MagicMock(file_id="photo456")]))
    cq.message.answer = AsyncMock()

    with (
        patch.object(main, "can_consume_generation", return_value=True),
        patch.object(main, "text_provider_configured", return_value=True),
        patch.object(main, "run_text_only", AsyncMock(return_value="Hello")) as run_text,
        patch.object(main, "run_image_only", AsyncMock()) as run_image,
        patch.object(main, "should_increment_daily_count", return_value=False),
    ):
        await main.regen_card_lang(cq)

    run_text.assert_awaited_once()
    run_image.assert_not_called()
    assert run_text.await_args.kwargs["lang"] == "en"
    from utils.prompts import build_text_system_prompt

    system = build_text_system_prompt(
        ctx.occasion,
        ctx.text_style,
        "en",
        profile_prefs=st.get_profile_preferences(uid),
        recipient_address=ctx.recipient_address,
        sender_signature=ctx.sender_signature,
        holiday=ctx.holiday,
        occasion_details=ctx.occasion_details,
    )
    assert "CRITICAL OUTPUT LANGUAGE" in system
    assert run_text.await_args.kwargs["recipient_address"] == "Влад"
    assert run_text.await_args.kwargs["sender_signature"] == "С Леной"
    assert run_text.await_args.kwargs["occasion_details"] == "20 лет"
    assert st.get_user_lang(uid) == "ru"
    saved = st.get_last_card(uid)
    assert saved is not None
    assert saved.lang == "en"
    assert saved.photo_file_id == "photo123"
    photo_call = cq.message.answer_photo.await_args
    assert photo_call.kwargs["photo"] == "photo123"
    kb = photo_call.kwargs["reply_markup"]
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert labels[0] == t("regen_repeat", "ru")
    assert labels[3] == t("regen_card_lang_ru", "ru")


@pytest.mark.asyncio
async def test_profile_home_sends_home_return_message() -> None:
    cq = MagicMock()
    cq.from_user.id = 1
    cq.message = MagicMock()
    cq.message.edit_reply_markup = AsyncMock()
    cq.message.answer = AsyncMock()
    cq.answer = AsyncMock()
    state = AsyncMock()
    state.clear = AsyncMock()

    with patch("handlers.profile._user_lang", return_value="ru"):
        await on_profile_home(cq, state)

    cq.message.answer.assert_awaited_once()
    text = cq.message.answer.await_args.args[0]
    assert text == t("home_return", "ru")
    assert t("home_welcome", "ru") not in text
