"""State-aware small talk copy and message key routing."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from handlers.main import _reply_wizard_small_talk
from handlers.states import CardStates
from utils.i18n import MESSAGES, t, wizard_small_talk_key

_SMALL_TALK_KEYS = (
    "small_talk_idle",
    "small_talk_idle_2",
    "small_talk_idle_3",
    "wizard_small_talk_recipient",
    "wizard_small_talk_holiday",
    "wizard_small_talk_image_idea",
    "wizard_small_talk_generating",
    "wizard_small_talk_language",
    "wizard_small_talk",
)

_RU_INFORMAL_MARKERS = (
    "тебе",
    "тобой",
    "выбери",
    "подожди",
    "нажми",
    "готова",
    "готов",
    "будешь",
    "давай ",
)


def test_small_talk_ru_avoids_informal_address() -> None:
    for key in _SMALL_TALK_KEYS:
        ru = MESSAGES[key]["ru"].lower()
        for marker in _RU_INFORMAL_MARKERS:
            assert marker not in ru, f"{key} contains informal marker {marker!r}"


@pytest.mark.parametrize(
    ("state", "expected_key"),
    [
        (None, "wizard_small_talk"),
        (CardStates.choosing_occasion.state, "wizard_small_talk_recipient"),
        (CardStates.holiday.state, "wizard_small_talk_holiday"),
        (CardStates.image_description.state, "wizard_small_talk_image_idea"),
        (CardStates.generating.state, "wizard_small_talk_generating"),
        (CardStates.choosing_language.state, "wizard_small_talk_language"),
        (CardStates.image_style.state, "wizard_small_talk"),
        (CardStates.text_style.state, "wizard_small_talk"),
    ],
)
def test_wizard_small_talk_key_by_state(state: str | None, expected_key: str) -> None:
    assert wizard_small_talk_key(state) == expected_key


def test_small_talk_idle_before_wizard_ru_en() -> None:
    ru = t("small_talk_idle", "ru")
    en = t("small_talk_idle", "en")
    assert ru == (
        "Я на месте ✨ Можем собрать открытку — "
        "кнопка «Создать открытку» уже ждёт."
    )
    assert en == (
        "I’m here ✨ We can make a card together — "
        "the Create a card button is ready."
    )


def test_small_talk_recipient_step_ru_en() -> None:
    ru = t("wizard_small_talk_recipient", "ru")
    en = t("wizard_small_talk_recipient", "en")
    assert "для кого" in ru
    assert "who the card is for" in en


def test_small_talk_holiday_step_ru_en() -> None:
    ru = t("wizard_small_talk_holiday", "ru")
    en = t("wizard_small_talk_holiday", "en")
    assert "повод" in ru
    assert "голосом" in ru
    assert "occasion" in en.lower()
    assert "voice" in en.lower()


def test_small_talk_image_idea_step_ru_en() -> None:
    ru = t("wizard_small_talk_image_idea", "ru")
    en = t("wizard_small_talk_image_idea", "en")
    assert ru == (
        "Можно доверить картинку MoodMuse или описать свои пожелания — как удобнее."
    )
    assert "MoodMuse" in en
    assert "wishes" in en.lower()


def test_small_talk_generating_ru_en() -> None:
    ru = t("wizard_small_talk_generating", "ru")
    en = t("wizard_small_talk_generating", "en")
    assert ru == "Уже колдую над открыткой ✨ Осталось немного подождать."
    assert "✨" in en
    assert "card" in en.lower()
    assert "wait" in en.lower()


@pytest.mark.asyncio
async def test_reply_wizard_small_talk_uses_state_key() -> None:
    message = MagicMock()
    message.answer = AsyncMock()
    state = MagicMock()
    state.get_state = AsyncMock(return_value=CardStates.holiday.state)
    state.get_data = AsyncMock(return_value={"prompt_msg_id": 1})

    await _reply_wizard_small_talk(message, state, "ru")

    message.answer.assert_awaited_once()
    text = message.answer.await_args.args[0]
    assert text == t("wizard_small_talk_holiday", "ru")
