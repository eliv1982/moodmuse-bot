"""Flow logging helpers."""
from __future__ import annotations

import io
import json
import logging
from contextlib import contextmanager
from typing import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import Settings
from handlers import main
from services.small_talk import IdleSmallTalkError
from utils.flow_logging import (
    log_card_lang_toggle,
    log_generation_prompt_context,
    log_idle_route,
    log_idle_small_talk_decision,
    truncate_flow_text,
)
from utils.logging_config import JsonFormatter


def test_truncate_flow_text() -> None:
    assert truncate_flow_text("short") == "short"
    long = "x" * 200
    assert len(truncate_flow_text(long)) == 120
    assert truncate_flow_text(long).endswith("…")


def test_flow_logging_helpers_do_not_crash(caplog) -> None:
    caplog.set_level(logging.INFO)
    log_idle_route(
        user_id=1,
        fsm_state=None,
        text_len=6,
        intent="small_talk",
        handler_path="test",
    )
    log_idle_small_talk_decision(
        user_id=1,
        text_len=6,
        smalltalk_enabled=True,
        should_use_idle_ai=True,
        ai_called=True,
    )
    log_card_lang_toggle(
        user_id=1,
        ui_lang="ru",
        previous_card_lang="ru",
        target_card_lang="en",
        profile_lang_before="ru",
        profile_lang_after="ru",
        image_reused=True,
        run_text_only_called=True,
        final_card_lang="en",
    )
    log_generation_prompt_context(
        user_id=1,
        holiday="NY",
        occasion_details="",
        recipient_address="Ann",
        sender_signature_present=False,
        ui_lang="ru",
        card_lang="en",
        image_style="style_realistic",
        text_style="text_warm",
        tone="warm",
        length="balanced",
        address_style="informal",
    )
    assert any("idle_route" in r.message for r in caplog.records)


# ----- Privacy: raw idle-chat text must never reach structured logs -----

SECRET = "мой секретный пароль zebra-4711, пожалуйста не логируй"
SECRET_FRAGMENTS = ("zebra-4711", "секретный", "пароль", "не логируй")


@contextmanager
def _json_log_output(level: int) -> Iterator[io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    old_level = root.level
    root.setLevel(level)
    root.addHandler(handler)
    try:
        yield stream
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)


def _events(stream: io.StringIO, name: str) -> list[dict[str, object]]:
    lines = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
    return [row for row in lines if row.get("event") == name]


def _assert_no_chat_text(stream: io.StringIO) -> None:
    output = stream.getvalue()
    assert output
    for fragment in SECRET_FRAGMENTS:
        assert fragment not in output
    assert '"text"' not in output


HOLIDAY_SECRET = "день рождения Зебры zebra-4711-holiday " + "h" * 100
DETAILS_SECRET = "она боится пауков, adoption-secret-4711 " + "d" * 100
ADDRESS_SECRET = "Дорогая тётя Клава-4711 " + "a" * 60
PROMPT_CONTEXT_FRAGMENTS = (
    "zebra-4711",
    "Зебры",
    "рождения",
    "adoption-secret",
    "пауков",
    "Клава",
    "тётя",
)


def _log_prompt_context(holiday: str, occasion_details: str, recipient_address: str) -> None:
    log_generation_prompt_context(
        user_id=7,
        holiday=holiday,
        occasion_details=occasion_details,
        recipient_address=recipient_address,
        sender_signature_present=True,
        ui_lang="ru",
        card_lang="en",
        image_style="style_realistic",
        text_style="text_warm",
        tone="warm",
        length="balanced",
        address_style="informal",
    )


def _assert_prompt_context_metadata(row: dict[str, object]) -> None:
    assert row["user_id"] == 7
    assert row["sender_signature_present"] is True
    assert row["ui_lang"] == "ru"
    assert row["card_lang"] == "en"
    assert row["image_style"] == "style_realistic"
    assert row["text_style"] == "text_warm"
    assert row["tone"] == "warm"
    assert row["length"] == "balanced"
    assert row["address_style"] == "informal"
    for raw_key in ("holiday", "occasion_details", "recipient_address"):
        assert raw_key not in row


def test_generation_prompt_context_json_log_has_no_raw_content_with_debug_flow_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEBUG_FLOW_LOGS", "1")

    with _json_log_output(logging.INFO) as stream:
        _log_prompt_context(HOLIDAY_SECRET, DETAILS_SECRET, ADDRESS_SECRET)

    output = stream.getvalue()
    for fragment in PROMPT_CONTEXT_FRAGMENTS:
        assert fragment not in output
    (row,) = _events(stream, "generation_prompt_context")
    assert row["level"] == "INFO"
    _assert_prompt_context_metadata(row)
    assert row["holiday_len"] == len(HOLIDAY_SECRET)
    assert row["occasion_details_len"] == len(DETAILS_SECRET)
    assert row["recipient_address_len"] == len(ADDRESS_SECRET)


def test_generation_prompt_context_json_log_has_no_raw_content_at_debug_level() -> None:
    with _json_log_output(logging.DEBUG) as stream:
        _log_prompt_context(HOLIDAY_SECRET, DETAILS_SECRET, ADDRESS_SECRET)

    output = stream.getvalue()
    for fragment in PROMPT_CONTEXT_FRAGMENTS:
        assert fragment not in output
    (row,) = _events(stream, "generation_prompt_context")
    _assert_prompt_context_metadata(row)
    assert row["holiday_len"] == len(HOLIDAY_SECRET)
    assert row["occasion_details_len"] == len(DETAILS_SECRET)
    assert row["recipient_address_len"] == len(ADDRESS_SECRET)


def test_generation_prompt_context_is_suppressed_at_info_without_debug_flow_logs() -> None:
    with _json_log_output(logging.INFO) as stream:
        _log_prompt_context(HOLIDAY_SECRET, DETAILS_SECRET, ADDRESS_SECRET)

    assert _events(stream, "generation_prompt_context") == []
    for fragment in PROMPT_CONTEXT_FRAGMENTS:
        assert fragment not in stream.getvalue()


def test_generation_prompt_context_reports_zero_lengths_for_empty_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEBUG_FLOW_LOGS", "1")

    with _json_log_output(logging.INFO) as stream:
        _log_prompt_context("", "", "")

    (row,) = _events(stream, "generation_prompt_context")
    assert row["holiday_len"] == 0
    assert row["occasion_details_len"] == 0
    assert row["recipient_address_len"] == 0


def _settings() -> Settings:
    return Settings(BOT_TOKEN="test-token", TEXT_PROVIDER="openai", OPENAI_API_KEY="sk-test")  # type: ignore[call-arg]


@pytest.mark.parametrize("level", [logging.INFO, logging.DEBUG])
@pytest.mark.asyncio
async def test_idle_route_json_log_has_routing_metadata_but_no_chat_text(level: int) -> None:
    message = MagicMock()
    message.text = SECRET
    message.from_user.id = 7
    state = MagicMock()
    state.get_state = AsyncMock(return_value=None)

    with (
        _json_log_output(level) as stream,
        patch.object(main, "_idle_small_talk_reply_text", AsyncMock(return_value="ok")),
        patch.object(main, "_answer_with_main_menu", AsyncMock()),
    ):
        await main.on_small_talk(message, state)

    _assert_no_chat_text(stream)
    (row,) = _events(stream, "idle_route")
    assert row["user_id"] == 7
    assert row["fsm_state"] == "none"
    assert row["intent"] == "small_talk"
    assert row["handler_path"] == "on_small_talk->idle_small_talk"
    assert row["text_len"] == len(SECRET)


DECISION_CASES = [
    # id, smalltalk enabled, use AI, provider configured, AI outcome, expected metadata
    ("disabled", False, True, True, "ok", {"ai_block_reason": "smalltalk_disabled"}),
    ("no_trigger", True, False, True, "ok", {"should_use_idle_ai": False}),
    ("no_provider", True, True, False, "ok", {"ai_block_reason": "text_provider_not_configured"}),
    ("ai_ok", True, True, True, "ok", {"ai_called": True, "should_use_idle_ai": True}),
    ("ai_error", True, True, True, "error", {"fallback_reason": "ai_error"}),
]


@pytest.mark.parametrize("level", [logging.INFO, logging.DEBUG])
@pytest.mark.parametrize(
    ("enabled", "use_ai", "configured", "outcome", "expected"),
    [case[1:] for case in DECISION_CASES],
    ids=[case[0] for case in DECISION_CASES],
)
@pytest.mark.asyncio
async def test_idle_decision_json_log_has_metadata_but_no_chat_text(
    level: int,
    enabled: bool,
    use_ai: bool,
    configured: bool,
    outcome: str,
    expected: dict[str, object],
) -> None:
    state = MagicMock()
    state.get_data = AsyncMock(return_value={})
    state.update_data = AsyncMock()
    ai = AsyncMock(return_value="reply")
    if outcome == "error":
        ai = AsyncMock(side_effect=IdleSmallTalkError("model unavailable"))
    storage = MagicMock()
    storage.is_small_talk_enabled.return_value = enabled

    with (
        _json_log_output(level) as stream,
        patch.object(main, "get_storage", return_value=storage),
        patch.object(main, "get_settings", return_value=_settings()),
        patch.object(main, "should_use_idle_ai", return_value=use_ai),
        patch.object(main, "text_provider_configured", return_value=configured),
        patch.object(main, "generate_idle_small_talk", ai),
    ):
        await main._idle_small_talk_reply_text(SECRET, "ru", state, user_id=7)

    _assert_no_chat_text(stream)
    (row,) = _events(stream, "idle_small_talk_decision")
    assert row["user_id"] == 7
    assert row["smalltalk_enabled"] is enabled
    assert row["text_len"] == len(SECRET)
    for key, value in expected.items():
        assert row[key] == value
