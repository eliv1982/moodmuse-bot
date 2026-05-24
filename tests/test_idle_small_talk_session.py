"""Idle small-talk session state, turn steering, and handler integration."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import Settings
from handlers.main import _idle_small_talk_reply_text, on_action_create_card, on_small_talk
from services.small_talk import (
    build_idle_small_talk_user_prompt,
    generate_idle_small_talk,
    small_talk_system_prompt,
)
from utils.i18n import t
from utils.idle_small_talk_session import (
    IDLE_SMALL_TALK_ACTIVE,
    IDLE_SMALL_TALK_LAST_FALLBACK_IDX,
    IDLE_SMALL_TALK_TURNS,
    clear_idle_small_talk_session,
    is_idle_small_talk_session_active,
    mark_idle_small_talk_turn,
    next_idle_small_talk_turn,
    pick_idle_fallback_index,
    should_use_idle_ai,
)
from utils.wizard_input import is_idle_casual_text, is_small_talk_text


def _settings(**kwargs: object) -> Settings:
    base: dict[str, object] = {
        "BOT_TOKEN": "test-token",
        "TEXT_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-test",
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def test_should_use_idle_ai_casual_fun_request() -> None:
    assert should_use_idle_ai("расскажи что-то прикольное", "ru", {})
    assert is_idle_casual_text("расскажи что-то прикольное", "ru")


def test_should_use_idle_ai_follow_up_without_greeting_phrase() -> None:
    data = {IDLE_SMALL_TALK_ACTIVE: True, IDLE_SMALL_TALK_TURNS: 1}
    follow_up = "прекрасный день, тебя дорабатываю, вот small talk настраиваю"
    assert not is_small_talk_text(follow_up, "ru")
    assert should_use_idle_ai(follow_up, "ru", data)


def test_next_turn_increments_in_session() -> None:
    data = {IDLE_SMALL_TALK_ACTIVE: True, IDLE_SMALL_TALK_TURNS: 2}
    assert next_idle_small_talk_turn(data) == 3


def test_steer_prompt_from_turn_3() -> None:
    ru = small_talk_system_prompt("ru", 3)
    en = small_talk_system_prompt("en", 4)
    assert "ход 3" in ru or "3–5" in ru
    assert "Turns 3–5" in en
    assert "открытк" in ru.lower()


def test_early_prompt_turn_1() -> None:
    ru = small_talk_system_prompt("ru", 1)
    assert "ход 1" in ru or "1–2" in ru
    assert "3–5" not in ru


def test_build_user_prompt_includes_turn() -> None:
    assert "turn 2" in build_idle_small_talk_user_prompt("hello", 2).lower()


def test_pick_idle_fallback_rotates() -> None:
    assert pick_idle_fallback_index(0) == 1
    assert pick_idle_fallback_index(2) == 0


@pytest.mark.asyncio
async def test_first_greeting_starts_session() -> None:
    state = MagicMock()
    state.get_data = AsyncMock(return_value={})
    state.update_data = AsyncMock()

    with (
        patch("handlers.main.get_storage") as mock_storage,
        patch("handlers.main.get_settings", return_value=_settings()),
        patch("handlers.main.text_provider_configured", return_value=True),
        patch(
            "handlers.main.generate_idle_small_talk",
            new_callable=AsyncMock,
            return_value="AI one",
        ) as mock_ai,
    ):
        mock_storage.return_value.is_small_talk_enabled.return_value = True
        text = await _idle_small_talk_reply_text("привет, как жизнь?", "ru", state)

    assert text == "AI one"
    mock_ai.assert_awaited_once()
    assert mock_ai.await_args.kwargs["turn"] == 1
    state.update_data.assert_awaited()
    assert is_idle_small_talk_session_active(
        {IDLE_SMALL_TALK_ACTIVE: True, IDLE_SMALL_TALK_TURNS: 1}
    )


@pytest.mark.asyncio
async def test_follow_up_in_session_calls_ai_not_primary_template() -> None:
    state = MagicMock()
    state.get_data = AsyncMock(
        return_value={IDLE_SMALL_TALK_ACTIVE: True, IDLE_SMALL_TALK_TURNS: 1}
    )
    state.update_data = AsyncMock()
    follow_up = "прекрасный день, тебя дорабатываю, вот small talk настраиваю"

    with (
        patch("handlers.main.get_storage") as mock_storage,
        patch("handlers.main.get_settings", return_value=_settings()),
        patch("handlers.main.text_provider_configured", return_value=True),
        patch(
            "handlers.main.generate_idle_small_talk",
            new_callable=AsyncMock,
            return_value="Sounds like a productive day!",
        ) as mock_ai,
    ):
        mock_storage.return_value.is_small_talk_enabled.return_value = True
        text = await _idle_small_talk_reply_text(follow_up, "ru", state)

    assert text == "Sounds like a productive day!"
    assert text != t("small_talk_idle", "ru")
    mock_ai.assert_awaited_once()
    assert mock_ai.await_args.kwargs["turn"] == 2


@pytest.mark.asyncio
async def test_provider_failure_rotates_fallback() -> None:
    state = MagicMock()
    state.get_data = AsyncMock(
        return_value={IDLE_SMALL_TALK_LAST_FALLBACK_IDX: 0}
    )
    state.update_data = AsyncMock()

    with (
        patch("handlers.main.get_storage") as mock_storage,
        patch("handlers.main.get_settings", return_value=_settings()),
        patch("handlers.main.text_provider_configured", return_value=True),
        patch(
            "handlers.main.generate_idle_small_talk",
            new_callable=AsyncMock,
            side_effect=Exception("fail"),
        ),
    ):
        mock_storage.return_value.is_small_talk_enabled.return_value = True
        text = await _idle_small_talk_reply_text("привет", "ru", state)

    assert text == t("small_talk_idle_2", "ru")
    fallback_updates = [
        c.kwargs
        for c in state.update_data.await_args_list
        if IDLE_SMALL_TALK_LAST_FALLBACK_IDX in c.kwargs
    ]
    assert fallback_updates[-1][IDLE_SMALL_TALK_LAST_FALLBACK_IDX] == 1


@pytest.mark.asyncio
async def test_smalltalk_off_skips_ai_during_session() -> None:
    state = MagicMock()
    state.get_data = AsyncMock(
        return_value={IDLE_SMALL_TALK_ACTIVE: True, IDLE_SMALL_TALK_TURNS: 1}
    )
    state.update_data = AsyncMock()

    with (
        patch("handlers.main.get_storage") as mock_storage,
        patch(
            "handlers.main.generate_idle_small_talk",
            new_callable=AsyncMock,
        ) as mock_ai,
    ):
        mock_storage.return_value.is_small_talk_enabled.return_value = False
        text = await _idle_small_talk_reply_text(
            "прекрасный день, тебя дорабатываю", "ru", state
        )

    mock_ai.assert_not_awaited()
    assert text == t("small_talk_idle", "ru")


@pytest.mark.asyncio
async def test_create_card_clears_idle_session() -> None:
    cq = MagicMock()
    cq.from_user = MagicMock(id=1)
    cq.message = MagicMock()
    cq.answer = AsyncMock()
    cq.data = None
    state = MagicMock()
    state.get_data = AsyncMock(return_value={})
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()

    storage = MagicMock()
    storage.get_user_lang.return_value = "ru"

    with (
        patch("handlers.main.get_storage", return_value=storage),
        patch("handlers.main._send_wizard_prompt", new_callable=AsyncMock),
        patch(
            "handlers.main.clear_idle_small_talk_session",
            new_callable=AsyncMock,
        ) as mock_clear,
    ):
        await on_action_create_card(cq, state)

    mock_clear.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_idle_small_talk_turn_3_system_has_steering() -> None:
    settings = _settings()
    mock_provider = MagicMock()
    mock_provider.generate_greeting_text = AsyncMock(return_value="Nice mood for a card.")

    with patch("services.small_talk.get_text_provider", return_value=mock_provider):
        await generate_idle_small_talk("nice day", lang="en", settings=settings, turn=3)

    system = mock_provider.generate_greeting_text.await_args.args[0]
    assert "Turns 3–5" in system
    user = mock_provider.generate_greeting_text.await_args.args[1]
    assert "turn 3" in user.lower()


@pytest.mark.asyncio
async def test_mark_and_clear_session() -> None:
    state = MagicMock()
    state.update_data = AsyncMock()
    await mark_idle_small_talk_turn(state, 2)
    state.update_data.assert_awaited()
    await clear_idle_small_talk_session(state)
    assert state.update_data.await_count == 2


@pytest.mark.asyncio
async def test_on_small_talk_passes_state() -> None:
    message = MagicMock()
    message.text = "hello"
    message.from_user = MagicMock(id=1)
    message.answer = AsyncMock()
    state = MagicMock()
    state.get_state = AsyncMock(return_value=None)

    with (
        patch("handlers.main.get_storage") as mock_storage,
        patch(
            "handlers.main._idle_small_talk_reply_text",
            new_callable=AsyncMock,
            return_value="Hi",
        ) as mock_reply,
    ):
        mock_storage.return_value.get_user_lang.return_value = "en"
        await on_small_talk(message, state)

    mock_reply.assert_awaited_once_with("hello", "en", state, user_id=1)
