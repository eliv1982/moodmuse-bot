"""Wizard recipient address, sender signature, and occasion details."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from handlers import main
from handlers.states import CardStates
from utils.field_confirm import (
    FIELD_OCCASION_DETAILS,
    FIELD_RECIPIENT_ADDRESS,
    FIELD_SENDER_SIGNATURE,
    TEXT_CONFIRM_CHANGE,
    TEXT_CONFIRM_OK,
    TEXT_SOURCE_TYPED,
    format_field_confirm_prompt,
)
from utils.i18n import t
from utils.occasion_details import (
    WIZARD_OCCASION_DETAILS_NO,
    occasion_needs_details,
    validate_occasion_details,
)
from utils.prompts import build_image_prompt, build_text_system_prompt
from utils.wizard_personalization import (
    WIZARD_RECIPIENT_NO,
    WIZARD_RECIPIENT_YES,
    WIZARD_SIGNATURE_NO,
    build_personalization_prompt_suffix,
    validate_recipient_address,
)
from utils.wizard_summary import build_generation_summary


def test_validate_recipient_address_accepts_phrases() -> None:
    assert validate_recipient_address("Дорогие наши женщины") == "Дорогие наши женщины"
    assert validate_recipient_address("Любимая мама") == "Любимая мама"
    assert validate_recipient_address("Dear colleagues") == "Dear colleagues"
    assert validate_recipient_address("Никита") == "Никита"


def test_recipient_address_confirm_uses_obrashenie_copy() -> None:
    text = format_field_confirm_prompt(
        "ru", "Дорогие коллеги", source=TEXT_SOURCE_TYPED, field=FIELD_RECIPIENT_ADDRESS
    )
    assert "обращение" in text.lower()
    assert "имя" not in text.lower()
    assert "Дорогие коллеги" in text


def test_summary_uses_obrashenie_not_name() -> None:
    full = build_generation_summary(
        lang="ru",
        occasion="occasion_colleagues",
        image_description="снег",
        holiday="Новый год",
        image_style="style_realistic",
        text_style="text_warm",
        recipient_address="Дорогие наши женщины",
    )
    assert "✅ Обращение: Дорогие наши женщины" in full
    assert "по имени" not in full


def test_occasion_needs_details_birthday_jubilee_anniversary() -> None:
    assert occasion_needs_details("день рождения")
    assert occasion_needs_details("День рождения")
    assert occasion_needs_details("др")
    assert occasion_needs_details("юбилей")
    assert occasion_needs_details("годовщина свадьбы")
    assert occasion_needs_details("15 лет брака")
    assert occasion_needs_details("birthday")
    assert occasion_needs_details("wedding anniversary")
    assert occasion_needs_details("years together")


def test_occasion_needs_details_ordinary_occasion_false() -> None:
    assert not occasion_needs_details("8 Марта")
    assert not occasion_needs_details("Новый год")
    assert not occasion_needs_details("just because")


def test_validate_occasion_details_accepts_age_phrases() -> None:
    assert validate_occasion_details("19 лет") == "19 лет"
    assert validate_occasion_details("50th birthday") == "50th birthday"


def test_summary_includes_occasion_details_only_when_set() -> None:
    base = build_generation_summary(
        lang="ru",
        occasion="occasion_loved",
        image_description="торт",
        holiday="день рождения",
        image_style="style_realistic",
        text_style="text_warm",
    )
    assert "Уточнение" not in base

    with_detail = build_generation_summary(
        lang="ru",
        occasion="occasion_loved",
        image_description="торт",
        holiday="день рождения",
        image_style="style_realistic",
        text_style="text_warm",
        occasion_details="19 лет",
    )
    assert "✅ Уточнение: 19 лет" in with_detail


def test_text_prompt_includes_occasion_details_when_present() -> None:
    prompt = build_text_system_prompt(
        "occasion_loved",
        "text_warm",
        "ru",
        holiday="день рождения",
        occasion_details="20 лет",
    )
    assert "20 лет" in prompt
    assert "ОБЯЗАТЕЛЬНОЕ" in prompt or "REQUIRED" in prompt


def test_text_prompt_forbids_inventing_numbers_without_details() -> None:
    prompt = build_text_system_prompt(
        "occasion_loved",
        "text_warm",
        "ru",
        holiday="день рождения",
        occasion_details=None,
    )
    assert "Не придумывай" in prompt or "Do not invent" in prompt


def test_image_prompt_forbids_visible_numbers_without_details() -> None:
    prompt = build_image_prompt(
        "occasion_loved",
        "style_realistic",
        holiday="день рождения",
    )
    assert "avoid visible age numbers" in prompt.lower()


def test_image_prompt_includes_occasion_details_context() -> None:
    prompt = build_image_prompt(
        "occasion_loved",
        "style_realistic",
        holiday="день рождения",
        occasion_details="20 лет",
    )
    assert "20 лет" in prompt
    assert "must match" in prompt.lower()


def test_image_prompt_recipient_address_neutral_people() -> None:
    prompt = build_image_prompt(
        "occasion_loved",
        "style_realistic",
        recipient_address="Влад",
    )
    assert "Влад" in prompt
    assert "do not infer gender" in prompt.lower()


def test_personalization_prompt_treats_address_as_phrase() -> None:
    suffix = build_personalization_prompt_suffix("Моё солнышко", None, "ru")
    assert "Моё солнышко" in suffix
    assert "не считай" in suffix.lower() or "do not assume" in suffix.lower()


@pytest.mark.asyncio
async def test_holiday_birthday_advances_to_details_toggle() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"holiday": "день рождения"})
    anchor = MagicMock()

    with patch.object(main, "_go_to_occasion_details_toggle", AsyncMock()) as go_toggle:
        await main._go_after_holiday_confirmed(anchor, state, "ru")

    go_toggle.assert_awaited_once_with(anchor, state, "ru")


@pytest.mark.asyncio
async def test_holiday_ordinary_skips_details_toggle() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"holiday": "8 Марта"})
    state.update_data = AsyncMock()
    anchor = MagicMock()

    with patch.object(main, "_go_to_image_idea_prompt", AsyncMock()) as go_idea:
        await main._go_after_holiday_confirmed(anchor, state, "ru")

    state.update_data.assert_awaited()
    go_idea.assert_awaited_once_with(anchor, state, "ru")


@pytest.mark.asyncio
async def test_occasion_details_toggle_no_skips_to_image_idea() -> None:
    cq = MagicMock()
    cq.message = MagicMock()
    cq.from_user.id = 1
    cq.answer = AsyncMock()
    state = AsyncMock()
    state.update_data = AsyncMock()

    with (
        patch.object(main, "_lang_from_state", AsyncMock(return_value="ru")),
        patch.object(main, "_collapse_callback_message", AsyncMock()),
        patch.object(main, "_go_to_image_idea_prompt", AsyncMock()) as go_idea,
    ):
        await main.on_occasion_details_toggle_no(cq, state)

    state.update_data.assert_awaited()
    go_idea.assert_awaited_once()


@pytest.mark.asyncio
async def test_occasion_details_confirmed_advances_to_image_idea() -> None:
    state = AsyncMock()
    state.update_data = AsyncMock()
    anchor = MagicMock()

    with (
        patch.object(main, "validate_occasion_details", return_value="19 лет"),
        patch.object(main, "_finalize_text_step", AsyncMock()),
        patch.object(main, "_go_to_image_idea_prompt", AsyncMock()) as go_idea,
    ):
        await main._apply_confirmed_occasion_details(
            MagicMock(), state, anchor, "ru", "19 лет"
        )

    go_idea.assert_awaited_once_with(anchor, state, "ru")


@pytest.mark.asyncio
async def test_text_style_advances_to_recipient_toggle() -> None:
    cq = MagicMock()
    cq.data = "text_warm"
    cq.message = MagicMock()
    cq.from_user.id = 1
    cq.answer = AsyncMock()
    state = AsyncMock()
    state.update_data = AsyncMock()

    with (
        patch.object(main, "_lang_from_state", AsyncMock(return_value="ru")),
        patch.object(main, "_collapse_callback_message", AsyncMock()),
        patch.object(main, "_go_to_recipient_address_toggle", AsyncMock()) as go_toggle,
    ):
        await main.on_text_style(cq, state, MagicMock())

    go_toggle.assert_awaited_once()


@pytest.mark.asyncio
async def test_recipient_toggle_no_skips_to_signature() -> None:
    cq = MagicMock()
    cq.message = MagicMock()
    cq.from_user.id = 1
    cq.answer = AsyncMock()
    state = AsyncMock()
    state.update_data = AsyncMock()

    with (
        patch.object(main, "_lang_from_state", AsyncMock(return_value="ru")),
        patch.object(main, "_collapse_callback_message", AsyncMock()),
        patch.object(main, "_go_to_signature_toggle", AsyncMock()) as go_sig,
    ):
        await main.on_recipient_toggle_no(cq, state)

    go_sig.assert_awaited_once()


@pytest.mark.asyncio
async def test_recipient_address_confirmed_advances_to_signature() -> None:
    state = AsyncMock()
    state.update_data = AsyncMock()
    anchor = MagicMock()

    with (
        patch.object(main, "validate_recipient_address", return_value="Лена"),
        patch.object(main, "_finalize_text_step", AsyncMock()),
        patch.object(main, "_go_to_signature_toggle", AsyncMock()) as go_sig,
    ):
        await main._apply_confirmed_recipient_address(
            MagicMock(), state, anchor, "ru", "Лена"
        )

    go_sig.assert_awaited_once()


@pytest.mark.asyncio
async def test_signature_toggle_no_starts_generation() -> None:
    cq = MagicMock()
    cq.message = MagicMock()
    cq.from_user.id = 1
    cq.answer = AsyncMock()
    state = AsyncMock()
    state.update_data = AsyncMock()
    bot = MagicMock()

    run_gen = AsyncMock()
    with (
        patch.object(main, "_lang_from_state", AsyncMock(return_value="ru")),
        patch.object(main, "_collapse_callback_message", AsyncMock()),
        patch.object(main, "_run_card_generation_from_wizard", run_gen),
    ):
        await main.on_signature_toggle_no(cq, state, bot)

    run_gen.assert_awaited_once()


@pytest.mark.asyncio
async def test_signature_confirmed_starts_generation() -> None:
    cq = MagicMock()
    cq.data = TEXT_CONFIRM_OK
    cq.message = MagicMock()
    cq.from_user.id = 1
    cq.answer = AsyncMock()
    cq.message.edit_reply_markup = AsyncMock()

    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "pending_text_field": FIELD_SENDER_SIGNATURE,
            "pending_text_value": "С любовью, Лена",
        }
    )
    state.get_state = AsyncMock(return_value=CardStates.sender_signature.state)

    with (
        patch.object(main, "_lang_from_state", AsyncMock(return_value="ru")),
        patch.object(main, "state_matches_pending_field", return_value=True),
        patch.object(main, "_cleanup_pending_field_confirmation", AsyncMock()),
        patch.object(main, "_apply_confirmed_sender_signature", AsyncMock()),
        patch.object(main, "_run_card_generation_from_wizard", AsyncMock()) as run_gen,
    ):
        await main.on_field_confirm_action(cq, state, MagicMock())

    run_gen.assert_awaited_once()


@pytest.mark.asyncio
async def test_recipient_address_change_reprompts() -> None:
    cq = MagicMock()
    cq.data = TEXT_CONFIRM_CHANGE
    cq.message = MagicMock()
    cq.from_user.id = 1
    cq.answer = AsyncMock()

    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "pending_text_field": FIELD_RECIPIENT_ADDRESS,
            "pending_text_value": "Лена",
        }
    )
    state.get_state = AsyncMock(return_value=CardStates.recipient_address.state)

    reprompt = AsyncMock()
    with (
        patch.object(main, "_lang_from_state", AsyncMock(return_value="ru")),
        patch.object(main, "state_matches_pending_field", return_value=True),
        patch.object(main, "_cleanup_pending_field_confirmation", AsyncMock()),
        patch.object(main, "_reprompt_field", reprompt),
    ):
        await main.on_field_confirm_action(cq, state, MagicMock())

    assert reprompt.await_args.args[3] == FIELD_RECIPIENT_ADDRESS
    assert "обращение" in t("wizard_recipient_address_retry", "ru").lower()


def test_toggle_callback_constants() -> None:
    assert WIZARD_RECIPIENT_YES == "wizard:recipient:yes"
    assert WIZARD_RECIPIENT_NO == "wizard:recipient:no"
    assert WIZARD_OCCASION_DETAILS_NO == "wizard:occasion_details:no"
