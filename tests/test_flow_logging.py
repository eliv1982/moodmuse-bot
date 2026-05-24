"""Flow logging helpers."""
from __future__ import annotations

import logging

from utils.flow_logging import (
    log_card_lang_toggle,
    log_generation_prompt_context,
    log_idle_route,
    log_idle_small_talk_decision,
    truncate_flow_text,
)


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
        text="привет",
        intent="small_talk",
        handler_path="test",
    )
    log_idle_small_talk_decision(
        user_id=1,
        text="привет",
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
