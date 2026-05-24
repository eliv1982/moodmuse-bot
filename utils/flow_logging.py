"""
Structured flow logs for Telegram routing and generation (no secrets or full prompts).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Literal, Optional

from utils.i18n import Lang

logger = logging.getLogger(__name__)

IdleRouteIntent = Literal["create_card", "small_talk", "menu_button", "unknown"]

_TEXT_TRUNCATE = 120


def flow_logs_verbose() -> bool:
    if os.getenv("DEBUG_FLOW_LOGS", "").strip().lower() in ("1", "true", "yes"):
        return True
    return logger.isEnabledFor(logging.DEBUG)


def truncate_flow_text(text: str | None, *, max_len: int = _TEXT_TRUNCATE) -> str:
    raw = (text or "").replace("\n", " ").strip()
    if len(raw) <= max_len:
        return raw
    return raw[: max_len - 1] + "…"


def _log(event: str, *, level: int = logging.INFO, **fields: Any) -> None:
    payload = {"event": event, **{k: v for k, v in fields.items() if v is not None}}
    logger.log(level, event, extra=payload)


def log_idle_route(
    *,
    user_id: int,
    fsm_state: str | None,
    text: str,
    intent: IdleRouteIntent,
    handler_path: str,
) -> None:
    _log(
        "idle_route",
        user_id=user_id,
        fsm_state=fsm_state or "none",
        text=truncate_flow_text(text),
        intent=intent,
        handler_path=handler_path,
    )


def log_idle_small_talk_decision(
    *,
    user_id: int,
    text: str,
    smalltalk_enabled: bool,
    should_use_idle_ai: bool,
    ai_block_reason: str | None = None,
    ai_called: bool = False,
    fallback_reason: str | None = None,
) -> None:
    level = logging.DEBUG if flow_logs_verbose() else logging.INFO
    _log(
        "idle_small_talk_decision",
        level=level,
        user_id=user_id,
        text=truncate_flow_text(text),
        smalltalk_enabled=smalltalk_enabled,
        should_use_idle_ai=should_use_idle_ai,
        ai_block_reason=ai_block_reason,
        ai_called=ai_called,
        fallback_reason=fallback_reason,
    )


def log_card_lang_toggle(
    *,
    user_id: int,
    ui_lang: Lang,
    previous_card_lang: Lang,
    target_card_lang: Lang,
    profile_lang_before: Lang,
    profile_lang_after: Lang,
    image_reused: bool,
    run_text_only_called: bool,
    final_card_lang: Lang | None = None,
) -> None:
    _log(
        "card_lang_toggle",
        user_id=user_id,
        ui_lang=ui_lang,
        previous_card_lang=previous_card_lang,
        target_card_lang=target_card_lang,
        profile_lang_before=profile_lang_before,
        profile_lang_after=profile_lang_after,
        image_reused=image_reused,
        run_text_only_called=run_text_only_called,
        final_card_lang=final_card_lang,
    )


def log_generation_prompt_context(
    *,
    user_id: int,
    holiday: str,
    occasion_details: str,
    recipient_address: str,
    sender_signature_present: bool,
    ui_lang: Lang,
    card_lang: Lang,
    image_style: str,
    text_style: str,
    tone: str,
    length: str,
    address_style: str,
) -> None:
    level = logging.DEBUG if not flow_logs_verbose() else logging.INFO
    _log(
        "generation_prompt_context",
        level=level,
        user_id=user_id,
        holiday=truncate_flow_text(holiday, max_len=80),
        occasion_details=truncate_flow_text(occasion_details, max_len=80),
        recipient_address=truncate_flow_text(recipient_address, max_len=40),
        sender_signature_present=sender_signature_present,
        ui_lang=ui_lang,
        card_lang=card_lang,
        image_style=image_style,
        text_style=text_style,
        tone=tone,
        length=length,
        address_style=address_style,
    )
