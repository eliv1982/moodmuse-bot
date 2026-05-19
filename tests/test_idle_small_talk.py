"""Idle AI small talk (provider-agnostic) and handler wiring."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import Settings
import services.yandex_gpt as yandex_gpt
from handlers.main import _idle_small_talk_reply_text, on_generating_small_talk, on_holiday, on_small_talk
from handlers.states import CardStates
from services.small_talk import (
    IdleSmallTalkError,
    format_small_talk_for_telegram,
    generate_idle_small_talk,
    small_talk_system_prompt,
)
from utils.i18n import t
from utils.wizard_input import is_small_talk_text


def _settings(**kwargs: object) -> Settings:
    base: dict[str, object] = {
        "BOT_TOKEN": "test-token",
        "TEXT_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-test",
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def test_legacy_yandex_small_talk_reply_removed() -> None:
    assert not hasattr(yandex_gpt, "small_talk_reply")


def test_is_small_talk_extended_phrases() -> None:
    assert is_small_talk_text("привет, как жизнь?", "ru")
    assert is_small_talk_text("как дела", "ru")
    assert is_small_talk_text("как настроение?", "ru")
    assert is_small_talk_text("how are you", "en")
    assert is_small_talk_text("ghbdtn", "ru")


def test_valid_holiday_not_small_talk() -> None:
    assert not is_small_talk_text("8 Марта", "ru")
    assert not is_small_talk_text("день рождения", "ru")


def test_format_small_talk_html_escape() -> None:
    assert format_small_talk_for_telegram("<b>Hi</b> & welcome") == "Hi &amp; welcome"
    assert format_small_talk_for_telegram("plain & text") == "plain &amp; text"


def test_format_small_talk_max_length() -> None:
    long = "a" * 600
    out = format_small_talk_for_telegram(long)
    assert len(out) <= 500
    assert out.endswith("…")


def test_small_talk_system_prompt_lang() -> None:
    assert "MoodMuse" in small_talk_system_prompt("en", 1)
    assert "MoodMuse" in small_talk_system_prompt("ru", 1)


@pytest.mark.asyncio
async def test_generate_idle_small_talk_openai_provider() -> None:
    settings = _settings()
    mock_provider = MagicMock()
    mock_provider.generate_greeting_text = AsyncMock(return_value="  Hello there!  ")

    with patch("services.small_talk.get_text_provider", return_value=mock_provider):
        result = await generate_idle_small_talk("hi", lang="en", settings=settings, turn=1)

    assert result == "Hello there!"
    mock_provider.generate_greeting_text.assert_awaited_once()
    call = mock_provider.generate_greeting_text.await_args
    assert "MoodMuse" in call.args[0]
    assert "hi" in call.args[1]
    assert "turn 1" in call.args[1].lower()


def _mock_state(data: dict | None = None) -> MagicMock:
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data or {})
    state.update_data = AsyncMock()
    return state


@pytest.mark.asyncio
async def test_idle_greeting_calls_ai_when_enabled() -> None:
    state = _mock_state()
    with (
        patch("handlers.main.get_storage") as mock_storage,
        patch("handlers.main.get_settings", return_value=_settings()),
        patch("handlers.main.text_provider_configured", return_value=True),
        patch(
            "handlers.main.generate_idle_small_talk",
            new_callable=AsyncMock,
            return_value="AI reply here",
        ) as mock_ai,
    ):
        mock_storage.return_value.is_small_talk_enabled.return_value = True
        text = await _idle_small_talk_reply_text("привет, как жизнь?", "ru", state)

    assert text == "AI reply here"
    mock_ai.assert_awaited_once()
    assert mock_ai.await_args.kwargs["lang"] == "ru"


@pytest.mark.asyncio
async def test_idle_ai_failure_falls_back_to_template() -> None:
    state = _mock_state()
    with (
        patch("handlers.main.get_storage") as mock_storage,
        patch("handlers.main.get_settings", return_value=_settings()),
        patch("handlers.main.text_provider_configured", return_value=True),
        patch(
            "handlers.main.generate_idle_small_talk",
            new_callable=AsyncMock,
            side_effect=IdleSmallTalkError("fail"),
        ),
    ):
        mock_storage.return_value.is_small_talk_enabled.return_value = True
        text = await _idle_small_talk_reply_text("привет", "ru", state)

    assert text == t("small_talk_idle", "ru")


@pytest.mark.asyncio
async def test_smalltalk_off_skips_ai() -> None:
    state = _mock_state()
    with (
        patch("handlers.main.get_storage") as mock_storage,
        patch(
            "handlers.main.generate_idle_small_talk",
            new_callable=AsyncMock,
        ) as mock_ai,
    ):
        mock_storage.return_value.is_small_talk_enabled.return_value = False
        text = await _idle_small_talk_reply_text("привет", "ru", state)

    assert text == t("small_talk_idle", "ru")
    mock_ai.assert_not_awaited()


@pytest.mark.asyncio
async def test_idle_non_small_talk_uses_template_without_ai() -> None:
    state = _mock_state()
    with patch(
        "handlers.main.generate_idle_small_talk",
        new_callable=AsyncMock,
    ) as mock_ai:
        text = await _idle_small_talk_reply_text("горы", "ru", state)

    assert text == t("small_talk_idle", "ru")
    mock_ai.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_small_talk_handler_uses_ai_reply() -> None:
    message = MagicMock()
    message.text = "hello"
    message.from_user = MagicMock(id=42)
    message.answer = AsyncMock()
    state = MagicMock()

    with (
        patch("handlers.main.get_storage") as mock_storage,
        patch(
            "handlers.main._idle_small_talk_reply_text",
            new_callable=AsyncMock,
            return_value="Dynamic hello",
        ) as mock_reply,
    ):
        mock_storage.return_value.get_user_lang.return_value = "en"
        await on_small_talk(message, state)

    mock_reply.assert_awaited_once_with("hello", "en", state)
    message.answer.assert_awaited_once()
    assert message.answer.await_args.args[0] == "Dynamic hello"


@pytest.mark.asyncio
async def test_wizard_holiday_small_talk_does_not_call_idle_ai() -> None:
    message = MagicMock()
    message.text = "привет"
    message.from_user = MagicMock(id=1)
    message.chat = MagicMock(id=1)
    message.message_id = 99
    state = MagicMock()
    state.get_state = AsyncMock(return_value=CardStates.holiday.state)
    state.get_data = AsyncMock(return_value={"prompt_msg_id": 1})
    bot = MagicMock()
    bot.delete_message = AsyncMock()

    with (
        patch("handlers.main._lang_from_state", new_callable=AsyncMock, return_value="ru"),
        patch("handlers.main._safe_delete_message", new_callable=AsyncMock),
        patch("handlers.main._reply_wizard_small_talk", new_callable=AsyncMock) as mock_wiz,
        patch("handlers.main.generate_idle_small_talk", new_callable=AsyncMock) as mock_idle,
    ):
        await on_holiday(message, state, bot)

    mock_wiz.assert_awaited_once()
    mock_idle.assert_not_awaited()


@pytest.mark.asyncio
async def test_generating_small_talk_template_only() -> None:
    message = MagicMock()
    message.text = "привет"
    message.from_user = MagicMock(id=1)
    state = MagicMock()
    state.get_state = AsyncMock(return_value=CardStates.generating.state)
    state.get_data = AsyncMock(return_value={})

    with (
        patch("handlers.main._lang_from_state", new_callable=AsyncMock, return_value="ru"),
        patch("handlers.main._reply_wizard_small_talk", new_callable=AsyncMock) as mock_wiz,
        patch("handlers.main.generate_idle_small_talk", new_callable=AsyncMock) as mock_idle,
    ):
        await on_generating_small_talk(message, state)

    mock_wiz.assert_awaited_once()
    mock_idle.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_idle_small_talk_passes_en_lang_in_system_prompt() -> None:
    settings = _settings(TEXT_PROVIDER="openai")
    mock_provider = MagicMock()
    mock_provider.generate_greeting_text = AsyncMock(
        return_value="Hi! Good to hear from you."
    )

    with patch("services.small_talk.get_text_provider", return_value=mock_provider):
        await generate_idle_small_talk("how are you", lang="en", settings=settings, turn=1)

    system_prompt = mock_provider.generate_greeting_text.await_args.args[0]
    assert "MoodMuse" in system_prompt
    user_prompt = mock_provider.generate_greeting_text.await_args.args[1]
    assert "how are you" in user_prompt
    assert "turn 1" in user_prompt.lower()
