"""
Main bot handlers: language, FSM flow, generation, regen shortcuts, small talk.
"""
from __future__ import annotations

import asyncio
import html
import logging
from typing import Any, Optional, cast

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import Settings, get_settings
from handlers.states import CardStates, ProfileStates
from services.card_generation import run_card_generation, run_image_only, run_text_only
from services.proxi import ProxiAPIError
from services.providers.factory import (
    text_provider_configured,
    text_provider_preflight_message_key,
)
from services.small_talk import (
    IdleSmallTalkError,
    generate_idle_small_talk,
    generate_returning_start_greeting,
)
from utils.flow_logging import (
    log_card_lang_toggle,
    log_generation_prompt_context,
    log_idle_route,
    log_idle_small_talk_decision,
)
from utils.idle_small_talk_session import (
    IDLE_SMALL_TALK_LAST_FALLBACK_IDX,
    MAX_IDLE_SMALL_TALK_TURNS,
    clear_idle_small_talk_session,
    idle_ai_block_reason,
    is_idle_small_talk_session_active,
    mark_idle_small_talk_turn,
    next_idle_small_talk_turn,
    pick_idle_fallback_index,
    should_use_idle_ai,
)
from utils.idle_small_talk_session import IDLE_FALLBACK_MESSAGE_KEYS
from services.providers.image_factory import (
    image_provider_configured,
    image_provider_preflight_message_key,
)
from services.providers.openai_image import OpenAIImageError
from services.providers.openai_text import OpenAITextError
from services.providers.stt_factory import SpeechToTextError, stt_configured, transcribe_audio
from services.storage import LastCardContext, get_storage
from services.yandex_gpt import YandexGPTError
from utils.i18n import Lang, t, wizard_small_talk_key
from utils.field_confirm import (
    FIELD_CONFIRM_CALLBACKS,
    FIELD_HOLIDAY,
    FIELD_IMAGE,
    FIELD_OCCASION_DETAILS,
    FIELD_RECIPIENT_ADDRESS,
    FIELD_SENDER_SIGNATURE,
    PENDING_TEXT_CHAT_ID_KEY,
    PENDING_TEXT_CONFIRM_MESSAGE_ID_KEY,
    PENDING_TEXT_FIELD_KEY,
    PENDING_TEXT_SOURCE_MESSAGE_ID_KEY,
    PENDING_TEXT_VALUE_KEY,
    TEXT_CONFIRM_CHANGE,
    TEXT_CONFIRM_OK,
    TEXT_CONFIRM_SUGGEST,
    TEXT_SOURCE_TYPED,
    TEXT_SOURCE_VOICE,
    clear_pending_text_payload,
    field_confirm_keyboard,
    field_prompt_for_field,
    field_reprompt_key,
    format_field_confirm_prompt,
    pending_text_payload,
    read_pending_text_snapshot,
    state_matches_pending_field,
)
from utils.occasion_details import (
    WIZARD_OCCASION_DETAILS_NO,
    WIZARD_OCCASION_DETAILS_YES,
    occasion_details_toggle_keyboard,
    occasion_needs_details,
    validate_occasion_details,
)
from utils.wizard_personalization import (
    WIZARD_RECIPIENT_NO,
    WIZARD_RECIPIENT_YES,
    WIZARD_SIGNATURE_NO,
    WIZARD_SIGNATURE_YES,
    recipient_toggle_keyboard,
    signature_toggle_keyboard,
    validate_recipient_address,
    validate_sender_signature,
)
from utils.wizard_input import (
    is_create_card_intent,
    is_small_talk_text,
    is_wizard_meta_question,
    validate_holiday,
    validate_image_description,
)
from utils.wizard_summary import build_generation_summary
from utils.active_text_prompt import (
    ACTIVE_TEXT_PROMPT_CHAT_ID_KEY,
    ACTIVE_TEXT_PROMPT_FIELD_KEY,
    ACTIVE_TEXT_PROMPT_MESSAGE_ID_KEY,
    TEXT_FIELD_HOLIDAY,
    TEXT_FIELD_IMAGE,
    active_text_prompt_payload,
    clear_active_text_prompt_payload,
    text_field_for_prompt_kind,
)
from utils.active_wizard_help import (
    ACTIVE_HELP_CHAT_ID_KEY,
    ACTIVE_HELP_FIELD_KEY,
    ACTIVE_HELP_MESSAGE_ID_KEY,
    HELP_FIELD_IMAGE_IDEA,
    HELP_FIELD_OCCASION,
    active_help_payload,
    clear_active_help_payload,
    help_field_for_confirm_key,
)
from utils.voice_stt import voice_stt_user_message
from utils.wizard_ui import (
    IMAGE_IDEA_CUSTOM,
    IMAGE_IDEA_SURPRISE,
    image_idea_keyboard,
)
from handlers.profile import show_profile_main, start_profile_onboarding
from utils.main_menu import main_menu_action_for_text, main_menu_reply_keyboard
from utils.generation_limit import can_consume_generation, should_increment_daily_count
from utils.profile_preferences import resolve_display_name
from utils.prompts import (
    IMAGE_STYLE_CALLBACKS,
    IMAGE_STYLE_KEYBOARD_ORDER,
    IMAGE_STYLE_LABELS,
    OCCASION_LABELS,
    TEXT_STYLE_CALLBACKS,
    TEXT_STYLE_LABELS,
    image_variation_suffix,
)

logger = logging.getLogger(__name__)
router = Router()


def coalesce_lang(raw: Optional[str]) -> Lang:
    return "en" if raw == "en" else "ru"


def _lbl(pair: tuple[str, str], lang: Lang) -> str:
    return pair[1] if lang == "en" else pair[0]


def _language_label(lang: Lang) -> str:
    return "English" if lang == "en" else "Русский"


async def _collapse_callback_message(
    cq: CallbackQuery,
    lang: Lang,
    message_key: str,
    **fmt: object,
) -> None:
    """Replace inline menu with a short confirmation (no active buttons)."""
    if not cq.message:
        return
    try:
        await cq.message.edit_text(
            t(message_key, lang, **fmt),
            reply_markup=None,
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        try:
            await cq.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass


async def _register_active_text_prompt(
    state: FSMContext,
    sent: Message,
    prompt_kind: str | None,
) -> None:
    field = text_field_for_prompt_kind(prompt_kind)
    if not field:
        return
    await state.update_data(
        **active_text_prompt_payload(field, sent.chat.id, sent.message_id)
    )


async def _delete_active_text_prompt(bot: Bot, state: FSMContext) -> None:
    data = await state.get_data()
    chat_id = data.get(ACTIVE_TEXT_PROMPT_CHAT_ID_KEY)
    msg_id = data.get(ACTIVE_TEXT_PROMPT_MESSAGE_ID_KEY)
    if chat_id is not None and msg_id is not None:
        await _safe_delete_message(bot, int(chat_id), int(msg_id))
    await state.update_data(**clear_active_text_prompt_payload())


async def _delete_active_wizard_help(
    bot: Bot,
    state: FSMContext,
    field: str | None = None,
) -> None:
    """Delete tracked helper message for field (or any active help if field is None)."""
    data = await state.get_data()
    active_field = data.get(ACTIVE_HELP_FIELD_KEY)
    if field is not None and active_field != field:
        return
    if active_field is None:
        return
    chat_id = data.get(ACTIVE_HELP_CHAT_ID_KEY)
    msg_id = data.get(ACTIVE_HELP_MESSAGE_ID_KEY)
    if chat_id is not None and msg_id is not None:
        await _safe_delete_message(bot, int(chat_id), int(msg_id))
    await state.update_data(**clear_active_help_payload())


async def _send_wizard_helper(
    bot: Bot,
    state: FSMContext,
    chat_id: int,
    lang: Lang,
    field: str,
    text: str,
    **answer_kwargs: object,
) -> Message:
    """Send a temporary wizard helper; replace any previous helper for the same field."""
    await _delete_active_wizard_help(bot, state, field)
    sent = await bot.send_message(
        chat_id,
        text,
        parse_mode=ParseMode.HTML,
        **answer_kwargs,  # type: ignore[arg-type]
    )
    await state.update_data(**active_help_payload(field, chat_id, sent.message_id))
    return sent


async def _store_prompt_message(
    state: FSMContext,
    sent: Message,
    *,
    prompt_kind: str | None = None,
) -> None:
    payload: dict[str, object] = {
        "prompt_chat_id": sent.chat.id,
        "prompt_msg_id": sent.message_id,
    }
    if prompt_kind is not None:
        payload["prompt_kind"] = prompt_kind
    await state.update_data(**payload)
    await _register_active_text_prompt(state, sent, prompt_kind)


async def _clear_stored_prompt(state: FSMContext) -> None:
    await state.update_data(prompt_chat_id=None, prompt_msg_id=None, prompt_kind=None)


async def _delete_stored_prompt(bot: Bot, state: FSMContext) -> None:
    data = await state.get_data()
    chat_id = data.get("prompt_chat_id")
    msg_id = data.get("prompt_msg_id")
    if chat_id and msg_id:
        try:
            await bot.delete_message(chat_id=int(chat_id), message_id=int(msg_id))
        except Exception:
            pass
    await _clear_stored_prompt(state)


async def _send_wizard_prompt(
    anchor: Message,
    state: FSMContext,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    *,
    prompt_kind: str | None = None,
) -> Message:
    field = text_field_for_prompt_kind(prompt_kind)
    if field:
        data = await state.get_data()
        if data.get(ACTIVE_TEXT_PROMPT_FIELD_KEY) == field:
            await _delete_active_text_prompt(anchor.bot, state)
    sent = await anchor.answer(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    await _store_prompt_message(state, sent, prompt_kind=prompt_kind)
    return sent


async def _edit_stored_prompt(
    bot: Bot,
    state: FSMContext,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> bool:
    data = await state.get_data()
    chat_id = data.get("prompt_chat_id")
    msg_id = data.get("prompt_msg_id")
    if not chat_id or not msg_id:
        return False
    try:
        await bot.edit_message_text(
            text,
            chat_id=int(chat_id),
            message_id=int(msg_id),
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )
        return True
    except Exception:
        return False


async def _replace_stored_prompt(
    bot: Bot,
    state: FSMContext,
    anchor: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    *,
    prompt_kind: str | None = None,
) -> None:
    field = text_field_for_prompt_kind(prompt_kind)
    if field:
        data = await state.get_data()
        if data.get(ACTIVE_TEXT_PROMPT_FIELD_KEY) == field:
            await _delete_active_text_prompt(bot, state)

    if await _edit_stored_prompt(bot, state, text, reply_markup):
        if prompt_kind is not None:
            await state.update_data(prompt_kind=prompt_kind)
        data = await state.get_data()
        chat_id = data.get("prompt_chat_id")
        msg_id = data.get("prompt_msg_id")
        if field and chat_id and msg_id:
            await state.update_data(
                **active_text_prompt_payload(field, int(chat_id), int(msg_id))
            )
        return
    await _delete_stored_prompt(bot, state)
    sent = await anchor.answer(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    await _store_prompt_message(state, sent, prompt_kind=prompt_kind)


async def _resolve_prompt_to_confirmation(
    bot: Bot,
    state: FSMContext,
    anchor: Message,
    lang: Lang,
    message_key: str,
    **fmt: object,
) -> None:
    confirm_text = t(message_key, lang, **fmt)
    if await _edit_stored_prompt(bot, state, confirm_text, reply_markup=None):
        await _clear_stored_prompt(state)
        return
    await _delete_stored_prompt(bot, state)
    await anchor.answer(confirm_text, parse_mode=ParseMode.HTML)


async def _safe_delete_message(
    bot: Bot,
    chat_id: int | None,
    message_id: int | None,
) -> None:
    if chat_id is None or message_id is None:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        logger.debug(
            "delete_message skipped chat_id=%s message_id=%s: %s",
            chat_id,
            message_id,
            exc,
        )
    except Exception as exc:
        logger.info(
            "delete_message unexpected error chat_id=%s message_id=%s: %s",
            chat_id,
            message_id,
            exc,
        )


async def _show_validation_retry(
    bot: Bot,
    state: FSMContext,
    anchor: Message,
    lang: Lang,
    retry_key: str,
    user_message: Message | None,
    *,
    prompt_kind: str,
    delete_user_message: bool = True,
) -> None:
    """Replace the active wizard prompt with a retry hint; do not touch FSM field values."""
    if delete_user_message and user_message is not None:
        await _safe_delete_message(bot, user_message.chat.id, user_message.message_id)
    await _replace_stored_prompt(
        bot,
        state,
        anchor,
        t(retry_key, lang),
        prompt_kind=prompt_kind,
    )


async def _finalize_text_step(
    bot: Bot,
    state: FSMContext,
    message: Message,
    lang: Lang,
    confirm_key: str,
    **fmt: object,
) -> None:
    await _delete_active_text_prompt(bot, state)
    help_field = help_field_for_confirm_key(confirm_key)
    if help_field:
        await _delete_active_wizard_help(bot, state, help_field)
    await message.answer(t(confirm_key, lang, **fmt), parse_mode=ParseMode.HTML)
    await _safe_delete_message(bot, message.chat.id, message.message_id)
    await _clear_stored_prompt(state)


async def _handle_stale_callback(cq: CallbackQuery, lang: Lang) -> None:
    await cq.answer(t("stale_callback", lang), show_alert=True)
    if cq.message:
        try:
            await cq.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass


async def _resend_current_prompt(
    anchor: Message,
    state: FSMContext,
    lang: Lang,
) -> None:
    current = await state.get_state()
    settings = get_settings()
    data = await state.get_data()

    if current == CardStates.choosing_occasion.state:
        await _send_wizard_prompt(
            anchor, state, t("choose_occasion", lang), occasion_keyboard(lang), prompt_kind="occasion"
        )
    elif current == CardStates.holiday.state:
        await _send_wizard_prompt(anchor, state, t("step2_holiday", lang), prompt_kind="holiday")
    elif current == CardStates.occasion_details_toggle.state:
        await _send_wizard_prompt(
            anchor,
            state,
            t("step_occasion_details_toggle", lang),
            occasion_details_toggle_keyboard(lang),
            prompt_kind="occasion_details_toggle",
        )
    elif current == CardStates.occasion_details.state:
        await _send_wizard_prompt(
            anchor, state, t("wizard_occasion_details_ask", lang), prompt_kind="occasion_details"
        )
    elif current == CardStates.image_description.state:
        mode = data.get("image_idea_mode", "pick")
        if mode == "custom":
            await _send_wizard_prompt(
                anchor, state, t("image_idea_custom_prompt", lang), prompt_kind="image_custom"
            )
        else:
            await _send_wizard_prompt(
                anchor,
                state,
                t("image_idea_question", lang),
                _image_idea_inline_keyboard(lang, settings),
                prompt_kind="image_idea",
            )
    elif current == CardStates.image_style.state:
        await _send_wizard_prompt(
            anchor, state, t("step3_image_style", lang), image_style_keyboard(lang), prompt_kind="image_style"
        )
    elif current == CardStates.text_style.state:
        await _send_wizard_prompt(
            anchor, state, t("step4_text_style", lang), text_style_keyboard(lang), prompt_kind="text_style"
        )
    elif current == CardStates.recipient_address_toggle.state:
        await _send_wizard_prompt(
            anchor,
            state,
            t("step5_recipient_toggle", lang),
            recipient_toggle_keyboard(lang),
            prompt_kind="recipient_toggle",
        )
    elif current == CardStates.recipient_address.state:
        await _send_wizard_prompt(
            anchor, state, t("wizard_recipient_address_ask", lang), prompt_kind="recipient_address"
        )
    elif current == CardStates.signature_toggle.state:
        await _send_wizard_prompt(
            anchor,
            state,
            t("step6_signature_toggle", lang),
            signature_toggle_keyboard(lang),
            prompt_kind="signature_toggle",
        )
    elif current == CardStates.sender_signature.state:
        await _send_wizard_prompt(
            anchor, state, t("wizard_signature_ask", lang), prompt_kind="sender_signature"
        )
    elif current == CardStates.choosing_language.state:
        await anchor.answer(t("pick_language", lang), reply_markup=language_keyboard())


async def _idle_template_fallback(lang: Lang, state: FSMContext) -> str:
    data = await state.get_data()
    last_idx = data.get(IDLE_SMALL_TALK_LAST_FALLBACK_IDX)
    try:
        last_i = int(last_idx) if last_idx is not None else None
    except (TypeError, ValueError):
        last_i = None
    idx = pick_idle_fallback_index(last_i)
    await state.update_data(**{IDLE_SMALL_TALK_LAST_FALLBACK_IDX: idx})
    return t(IDLE_FALLBACK_MESSAGE_KEYS[idx], lang)


async def _idle_small_talk_reply_text(
    raw: str,
    lang: Lang,
    state: FSMContext,
    *,
    user_id: int = 0,
) -> str:
    """AI for greetings and active idle session; rotated templates on fallback."""
    data = await state.get_data()
    storage = get_storage()
    smalltalk_on = storage.is_small_talk_enabled()
    use_ai = should_use_idle_ai(raw, lang, data)
    block_reason: str | None = None
    fallback_reason: str | None = None
    ai_called = False

    if not smalltalk_on:
        block_reason = "smalltalk_disabled"
        fallback_reason = block_reason
        log_idle_small_talk_decision(
            user_id=user_id,
            text=raw,
            smalltalk_enabled=False,
            should_use_idle_ai=False,
            ai_block_reason=block_reason,
            fallback_reason=fallback_reason,
        )
        return await _idle_template_fallback(lang, state)

    if not use_ai:
        block_reason = idle_ai_block_reason(raw, lang, data) or "no_idle_ai_trigger"
        fallback_reason = block_reason
        log_idle_small_talk_decision(
            user_id=user_id,
            text=raw,
            smalltalk_enabled=True,
            should_use_idle_ai=False,
            ai_block_reason=block_reason,
            fallback_reason=fallback_reason,
        )
        return await _idle_template_fallback(lang, state)

    settings = get_settings()
    if not text_provider_configured(settings):
        block_reason = "text_provider_not_configured"
        fallback_reason = block_reason
        log_idle_small_talk_decision(
            user_id=user_id,
            text=raw,
            smalltalk_enabled=True,
            should_use_idle_ai=True,
            ai_block_reason=block_reason,
            fallback_reason=fallback_reason,
        )
        return await _idle_template_fallback(lang, state)

    turn = next_idle_small_talk_turn(data)
    if turn > MAX_IDLE_SMALL_TALK_TURNS:
        await clear_idle_small_talk_session(state)
        fallback_reason = "max_turns_exceeded"
        log_idle_small_talk_decision(
            user_id=user_id,
            text=raw,
            smalltalk_enabled=True,
            should_use_idle_ai=True,
            ai_block_reason="max_turns_exceeded",
            fallback_reason=fallback_reason,
        )
        return await _idle_template_fallback(lang, state)

    try:
        reply = await generate_idle_small_talk(
            raw, lang=lang, settings=settings, turn=turn
        )
        await mark_idle_small_talk_turn(state, turn)
        ai_called = True
        log_idle_small_talk_decision(
            user_id=user_id,
            text=raw,
            smalltalk_enabled=True,
            should_use_idle_ai=True,
            ai_called=True,
        )
        return reply
    except (IdleSmallTalkError, Exception):
        logger.exception("idle_small_talk_failed", extra={"event": "idle_small_talk"})
        fallback_reason = "ai_error"
        if is_small_talk_text(raw, lang) or is_idle_small_talk_session_active(data):
            await mark_idle_small_talk_turn(state, min(turn, MAX_IDLE_SMALL_TALK_TURNS))
        log_idle_small_talk_decision(
            user_id=user_id,
            text=raw,
            smalltalk_enabled=True,
            should_use_idle_ai=True,
            ai_called=ai_called,
            fallback_reason=fallback_reason,
        )
        return await _idle_template_fallback(lang, state)


def _returning_start_fallback(name: str, lang: Lang) -> str:
    return t("start_returning_fallback", lang, name=_esc_user_text(name))


async def _returning_start_greeting(name: str, lang: Lang) -> str:
    """Warm returning /start copy: AI when small talk is enabled, else static fallback."""
    storage = get_storage()
    if not storage.is_small_talk_enabled():
        return _returning_start_fallback(name, lang)
    settings = get_settings()
    if not text_provider_configured(settings):
        return _returning_start_fallback(name, lang)
    try:
        return await generate_returning_start_greeting(name, lang=lang, settings=settings)
    except IdleSmallTalkError:
        logger.warning("returning_greeting_fallback", extra={"event": "returning_greeting"})
        return _returning_start_fallback(name, lang)


async def _answer_with_main_menu(message: Message, text: str, lang: Lang) -> None:
    await message.answer(
        text,
        reply_markup=main_menu_reply_keyboard(lang),
        parse_mode=ParseMode.HTML,
    )


def _ui_lang_for_user(uid: int) -> Lang:
    """Bot interface language from profile/storage (not card caption language)."""
    return coalesce_lang(get_storage().get_user_lang(uid))


async def _reassert_main_menu_keyboard(message: Message, ui_lang: Lang) -> None:
    """Reattach persistent reply menu after inline-only card photo (Telegram allows one markup type)."""
    await message.answer(
        t("card_ready_menu", ui_lang),
        reply_markup=main_menu_reply_keyboard(ui_lang),
        parse_mode=ParseMode.HTML,
    )


async def _reply_wizard_small_talk(
    message: Message,
    state: FSMContext,
    lang: Lang,
) -> None:
    current = await state.get_state()
    await message.answer(t(wizard_small_talk_key(current), lang), parse_mode=ParseMode.HTML)
    data = await state.get_data()
    if not data.get("prompt_msg_id"):
        await _resend_current_prompt(message, state, lang)


def _esc_user_text(text: str) -> str:
    return html.escape(text.strip())


def _surprise_phrase(lang: Lang) -> str:
    return "surprise me" if lang == "en" else "придумай сам"


async def _download_voice_bytes(
    bot: Bot, message: Message
) -> tuple[bytes, str, str | None] | None:
    if not message.voice:
        return None
    file = await bot.get_file(message.voice.file_id)
    bio = await bot.download_file(file.file_path)
    audio_bytes = bio.read() if hasattr(bio, "read") else bytes(bio)
    if not audio_bytes:
        return None
    path_ext = (file.file_path or "").rsplit(".", 1)[-1].lower() if file.file_path else ""
    if path_ext in ("oga", "ogg", "opus"):
        ext = path_ext
    else:
        mime = (getattr(message.voice, "mime_type", None) or "").lower()
        ext = "oga" if "ogg" in mime or "opus" in mime else "oga"
    mime_type = getattr(message.voice, "mime_type", None)
    return audio_bytes, f"voice.{ext}", mime_type


async def _transcribe_voice_message(
    bot: Bot,
    message: Message,
    settings: Settings,
    lang: Lang,
) -> str:
    downloaded = await _download_voice_bytes(bot, message)
    if not downloaded:
        raise SpeechToTextError("voice download empty", reason="technical")
    audio_bytes, filename, mime_type = downloaded
    return await transcribe_audio(
        audio_bytes,
        settings,
        filename=filename,
        timeout=settings.STT_TIMEOUT,
        language=lang,
        mime_type=mime_type,
    )


async def _cleanup_pending_field_confirmation(
    bot: Bot,
    state: FSMContext,
    *,
    delete_confirm: bool = True,
    delete_source: bool = True,
) -> dict[str, object]:
    """
    Delete pending typed/voice confirmation messages (best-effort) and clear FSM keys.
    Returns a snapshot of pending data read before cleanup.
    """
    data = await state.get_data()
    snapshot = read_pending_text_snapshot(data)
    chat_id = snapshot.get(PENDING_TEXT_CHAT_ID_KEY)
    if chat_id is not None:
        cid = int(chat_id)
        if delete_source:
            source_id = snapshot.get(PENDING_TEXT_SOURCE_MESSAGE_ID_KEY)
            if source_id is not None:
                await _safe_delete_message(bot, cid, int(source_id))
        if delete_confirm:
            confirm_id = snapshot.get(PENDING_TEXT_CONFIRM_MESSAGE_ID_KEY)
            if confirm_id is not None:
                await _safe_delete_message(bot, cid, int(confirm_id))
    await state.update_data(**clear_pending_text_payload())
    return snapshot


_cleanup_pending_voice_confirmation = _cleanup_pending_field_confirmation


async def _reprompt_field(
    bot: Bot,
    state: FSMContext,
    lang: Lang,
    field: str,
) -> None:
    """Restore the wizard input prompt after confirmation was cancelled."""
    prompt_pair = field_prompt_for_field(field)
    if not prompt_pair:
        return
    prompt_key, prompt_kind = prompt_pair
    retry_key = field_reprompt_key(field)
    text = t(retry_key, lang) if retry_key else t(prompt_key, lang)
    field_name = text_field_for_prompt_kind(prompt_kind) or field
    data = await state.get_data()
    if data.get(ACTIVE_TEXT_PROMPT_FIELD_KEY) == field_name:
        await _delete_active_text_prompt(bot, state)

    if await _edit_stored_prompt(bot, state, text):
        await state.update_data(prompt_kind=prompt_kind)
        data = await state.get_data()
        chat_id = data.get("prompt_chat_id")
        msg_id = data.get("prompt_msg_id")
        if chat_id and msg_id:
            await state.update_data(
                **active_text_prompt_payload(field_name, int(chat_id), int(msg_id))
            )
        return
    data = await state.get_data()
    chat_id = data.get("prompt_chat_id")
    if chat_id:
        sent = await bot.send_message(int(chat_id), text, parse_mode=ParseMode.HTML)
        await _store_prompt_message(state, sent, prompt_kind=prompt_kind)


async def _offer_field_text_confirm(
    bot: Bot,
    message: Message,
    state: FSMContext,
    lang: Lang,
    field: str,
    text: str,
    *,
    source: str,
) -> None:
    """Show confirmation UI for typed or transcribed wizard free text."""
    data = await state.get_data()
    if data.get(PENDING_TEXT_FIELD_KEY):
        await _cleanup_pending_field_confirmation(bot, state)

    confirm_msg = await message.answer(
        format_field_confirm_prompt(lang, text, source=source, field=field),  # type: ignore[arg-type]
        reply_markup=field_confirm_keyboard(lang, field),
        parse_mode=ParseMode.HTML,
    )
    await state.update_data(
        **pending_text_payload(
            field,
            text.strip(),
            chat_id=message.chat.id,
            source_message_id=message.message_id,
            confirm_message_id=confirm_msg.message_id,
            source=source,  # type: ignore[arg-type]
        )
    )


async def _reply_wizard_meta_help(
    bot: Bot,
    message: Message,
    state: FSMContext,
    lang: Lang,
    field: str,
) -> None:
    key = "wizard_meta_holiday_help" if field == FIELD_HOLIDAY else "wizard_meta_image_help"
    await _safe_delete_message(bot, message.chat.id, message.message_id)
    await _send_wizard_helper(bot, state, message.chat.id, lang, field, t(key, lang))


async def _transcribe_and_offer_voice_confirm(
    bot: Bot,
    message: Message,
    state: FSMContext,
    lang: Lang,
    settings: Settings,
    *,
    field: str,
) -> None:
    """Transcribe voice, delete status message, prompt user to confirm text."""
    prompt_pair = field_prompt_for_field(field)
    prompt_kind = prompt_pair[1] if prompt_pair else "image_custom"

    recognizing = await message.answer(t("voice_recognizing", lang))
    try:
        text = await _transcribe_voice_message(bot, message, settings, lang)
    except SpeechToTextError as exc:
        await _safe_delete_message(bot, recognizing.chat.id, recognizing.message_id)
        await message.answer(voice_stt_user_message(lang, exc))
        return

    await _safe_delete_message(bot, recognizing.chat.id, recognizing.message_id)

    if not text or not text.strip():
        await _show_validation_retry(
            bot,
            state,
            message,
            lang,
            "voice_empty",
            None,
            prompt_kind=prompt_kind,
            delete_user_message=False,
        )
        return

    await _offer_field_text_confirm(
        bot, message, state, lang, field, text.strip(), source=TEXT_SOURCE_VOICE
    )


async def _apply_confirmed_image(
    bot: Bot,
    state: FSMContext,
    anchor: Message,
    lang: Lang,
    text: str,
) -> None:
    if not validate_image_description(text, lang):
        await _show_validation_retry(
            bot,
            state,
            anchor,
            lang,
            "invalid_image_desc",
            anchor,
            prompt_kind="image_custom",
            delete_user_message=False,
        )
        return
    await state.update_data(image_description=text, image_idea_mode=None)
    await _finalize_text_step(
        bot, state, anchor, lang, "confirmed_image_idea", text=_esc_user_text(text)
    )
    await _go_to_image_style_prompt(anchor, state, lang)


async def _apply_confirmed_holiday(
    bot: Bot,
    state: FSMContext,
    anchor: Message,
    lang: Lang,
    text: str,
) -> None:
    if not validate_holiday(text, lang):
        await _show_validation_retry(
            bot,
            state,
            anchor,
            lang,
            "invalid_holiday",
            anchor,
            prompt_kind="holiday",
            delete_user_message=False,
        )
        return
    await state.update_data(holiday=text)
    await _finalize_text_step(
        bot, state, anchor, lang, "confirmed_holiday", text=_esc_user_text(text)
    )
    await _go_after_holiday_confirmed(anchor, state, lang)


async def _go_after_holiday_confirmed(
    anchor: Message,
    state: FSMContext,
    lang: Lang,
) -> None:
    data = await state.get_data()
    holiday = str(data.get("holiday", ""))
    if occasion_needs_details(holiday):
        await _go_to_occasion_details_toggle(anchor, state, lang)
    else:
        await state.update_data(occasion_details=None)
        await _go_to_image_idea_prompt(anchor, state, lang)


async def _go_to_occasion_details_toggle(
    anchor: Message,
    state: FSMContext,
    lang: Lang,
) -> None:
    await state.set_state(CardStates.occasion_details_toggle)
    await _send_wizard_prompt(
        anchor,
        state,
        t("step_occasion_details_toggle", lang),
        occasion_details_toggle_keyboard(lang),
        prompt_kind="occasion_details_toggle",
    )


async def _go_to_occasion_details_input(
    bot: Bot,
    anchor: Message,
    state: FSMContext,
    lang: Lang,
) -> None:
    await state.set_state(CardStates.occasion_details)
    text = t("wizard_occasion_details_ask", lang)
    data = await state.get_data()
    if data.get("prompt_msg_id"):
        await _replace_stored_prompt(
            bot, state, anchor, text, prompt_kind="occasion_details"
        )
    else:
        await _send_wizard_prompt(anchor, state, text, prompt_kind="occasion_details")


async def _apply_confirmed_occasion_details(
    bot: Bot,
    state: FSMContext,
    anchor: Message,
    lang: Lang,
    text: str,
) -> None:
    detail = validate_occasion_details(text)
    if not detail:
        await _show_validation_retry(
            bot,
            state,
            anchor,
            lang,
            "invalid_occasion_details",
            anchor,
            prompt_kind="occasion_details",
            delete_user_message=False,
        )
        return
    await state.update_data(occasion_details=detail)
    await _finalize_text_step(
        bot, state, anchor, lang, "confirmed_occasion_details", value=_esc_user_text(detail)
    )
    await _go_to_image_idea_prompt(anchor, state, lang)


async def _apply_confirmed_recipient_address(
    bot: Bot,
    state: FSMContext,
    anchor: Message,
    lang: Lang,
    text: str,
) -> None:
    address = validate_recipient_address(text)
    if not address:
        await _show_validation_retry(
            bot,
            state,
            anchor,
            lang,
            "invalid_recipient_address",
            anchor,
            prompt_kind="recipient_address",
            delete_user_message=False,
        )
        return
    await state.update_data(recipient_address=address)
    await _finalize_text_step(
        bot, state, anchor, lang, "confirmed_recipient_address", value=_esc_user_text(address)
    )
    await _go_to_signature_toggle(anchor, state, lang)


async def _apply_confirmed_sender_signature(
    bot: Bot,
    state: FSMContext,
    anchor: Message,
    lang: Lang,
    text: str,
) -> None:
    signature = validate_sender_signature(text)
    if not signature:
        await _show_validation_retry(
            bot,
            state,
            anchor,
            lang,
            "invalid_signature",
            anchor,
            prompt_kind="sender_signature",
            delete_user_message=False,
        )
        return
    await state.update_data(sender_signature=signature)
    await _finalize_text_step(
        bot,
        state,
        anchor,
        lang,
        "confirmed_signature",
        signature=_esc_user_text(signature),
    )


async def _go_to_recipient_address_toggle(
    anchor: Message,
    state: FSMContext,
    lang: Lang,
) -> None:
    await state.set_state(CardStates.recipient_address_toggle)
    await _send_wizard_prompt(
        anchor,
        state,
        t("step5_recipient_toggle", lang),
        recipient_toggle_keyboard(lang),
        prompt_kind="recipient_toggle",
    )


async def _go_to_recipient_address_input(
    bot: Bot,
    anchor: Message,
    state: FSMContext,
    lang: Lang,
) -> None:
    await state.set_state(CardStates.recipient_address)
    text = t("wizard_recipient_address_ask", lang)
    data = await state.get_data()
    if data.get("prompt_msg_id"):
        await _replace_stored_prompt(bot, state, anchor, text, prompt_kind="recipient_address")
    else:
        await _send_wizard_prompt(anchor, state, text, prompt_kind="recipient_address")


async def _go_to_signature_toggle(
    anchor: Message,
    state: FSMContext,
    lang: Lang,
) -> None:
    await state.set_state(CardStates.signature_toggle)
    await _send_wizard_prompt(
        anchor,
        state,
        t("step6_signature_toggle", lang),
        signature_toggle_keyboard(lang),
        prompt_kind="signature_toggle",
    )


async def _go_to_sender_signature_input(
    bot: Bot,
    anchor: Message,
    state: FSMContext,
    lang: Lang,
) -> None:
    await state.set_state(CardStates.sender_signature)
    text = t("wizard_signature_ask", lang)
    data = await state.get_data()
    if data.get("prompt_msg_id"):
        await _replace_stored_prompt(bot, state, anchor, text, prompt_kind="sender_signature")
    else:
        await _send_wizard_prompt(anchor, state, text, prompt_kind="sender_signature")


async def _generation_preflight_alert(lang: Lang, uid: int, settings: Settings) -> str | None:
    """Return alert message key/text if generation must not start; else None."""
    if not image_provider_configured(settings):
        return t(image_provider_preflight_message_key(settings), lang)
    if not text_provider_configured(settings):
        return t(text_provider_preflight_message_key(settings), lang)
    if not can_consume_generation(uid, settings):
        return t("rate_limited", lang)
    return None


async def _run_card_generation_from_wizard(
    bot: Bot,
    anchor: Message,
    state: FSMContext,
    uid: int,
    lang: Lang,
    *,
    cq: CallbackQuery | None = None,
) -> None:
    settings = get_settings()
    alert = await _generation_preflight_alert(lang, uid, settings)
    if alert:
        if cq is not None:
            await cq.answer(alert, show_alert=True)
        else:
            await anchor.answer(alert)
        return

    await state.set_state(CardStates.generating)
    ui_lang = _ui_lang_for_user(uid)
    logger.info("generation_start", extra={"user_id": uid, "event": "generation_start"})

    data: dict[str, Any] = (await state.get_data()) or {}
    occasion = str(data.get("occasion", ""))
    image_description = str(data.get("image_description", ""))
    holiday = str(data.get("holiday", ""))
    image_style = str(data.get("image_style", "style_realistic"))
    text_style = str(data.get("text_style", "text_warm"))
    recipient_address = data.get("recipient_address")
    sender_signature = data.get("sender_signature")
    occasion_details = data.get("occasion_details")
    ra = str(recipient_address).strip() if recipient_address else None
    ss = str(sender_signature).strip() if sender_signature else None
    od = str(occasion_details).strip() if occasion_details else None
    prefs = get_storage().get_profile_preferences(uid)
    log_generation_prompt_context(
        user_id=uid,
        holiday=holiday,
        occasion_details=od or "",
        recipient_address=ra or "",
        sender_signature_present=bool(ss),
        ui_lang=ui_lang,
        card_lang=lang,
        image_style=image_style,
        text_style=text_style,
        tone=prefs.text_tone,
        length=prefs.text_length,
        address_style=prefs.address_style,
    )

    summary = build_generation_summary(
        lang=lang,
        occasion=occasion,
        image_description=image_description,
        holiday=holiday,
        image_style=image_style,
        text_style=text_style,
        occasion_details=od,
        recipient_address=ra,
        sender_signature=ss,
    )
    status_msg = await anchor.answer(summary, parse_mode=ParseMode.HTML)
    profile_prefs = get_storage().get_profile_preferences(uid)

    try:
        image_bytes, caption_html, final_prompt = await run_card_generation(
            settings,
            occasion=occasion,
            image_description=image_description,
            holiday=holiday,
            image_style=image_style,
            text_style=text_style,
            lang=lang,
            refine_prompt=True,
            image_prompt_override=None,
            profile_prefs=profile_prefs,
            recipient_address=ra,
            sender_signature=ss,
            occasion_details=od,
        )
    except (ProxiAPIError, OpenAIImageError) as e:
        logger.exception("Image provider failed: %s", e, extra={"user_id": uid, "event": "error"})
        await status_msg.edit_text(t("err_image", lang, err=e))
        await state.set_state(CardStates.signature_toggle)
        await anchor.answer(
            t("step6_signature_toggle", lang),
            reply_markup=signature_toggle_keyboard(lang),
            parse_mode=ParseMode.HTML,
        )
        return
    except (YandexGPTError, OpenAITextError) as e:
        logger.exception("Text provider failed: %s", e, extra={"user_id": uid, "event": "error"})
        await status_msg.edit_text(t("err_text", lang, err=e))
        await state.set_state(CardStates.signature_toggle)
        await anchor.answer(
            t("step6_signature_toggle", lang),
            reply_markup=signature_toggle_keyboard(lang),
            parse_mode=ParseMode.HTML,
        )
        return
    except asyncio.TimeoutError:
        logger.warning("timeout", extra={"user_id": uid, "event": "error"})
        await status_msg.edit_text(t("err_timeout", lang))
        await state.set_state(CardStates.signature_toggle)
        await anchor.answer(
            t("step6_signature_toggle", lang),
            reply_markup=signature_toggle_keyboard(lang),
            parse_mode=ParseMode.HTML,
        )
        return
    except Exception as e:
        logger.exception("generation failed: %s", e, extra={"user_id": uid, "event": "error"})
        await status_msg.edit_text(t("err_generic", lang, err=e))
        await state.set_state(CardStates.signature_toggle)
        await anchor.answer(
            t("step6_signature_toggle", lang),
            reply_markup=signature_toggle_keyboard(lang),
            parse_mode=ParseMode.HTML,
        )
        return

    photo = BufferedInputFile(image_bytes, filename="card.png")
    try:
        await status_msg.delete()
    except Exception:
        pass
    sent = await anchor.answer_photo(
        photo=photo,
        caption=caption_html,
        parse_mode=ParseMode.HTML,
        reply_markup=after_card_keyboard(ui_lang, lang),
    )
    await _reassert_main_menu_keyboard(anchor, ui_lang)
    fid = sent.photo[-1].file_id if sent.photo else ""
    ctx = LastCardContext(
        occasion=occasion,
        image_description=image_description,
        holiday=holiday,
        image_style=image_style,
        text_style=text_style,
        lang=lang,
        image_prompt_en=final_prompt,
        photo_file_id=fid,
        caption_html=caption_html,
        recipient_address=ra or "",
        sender_signature=ss or "",
        occasion_details=od or "",
    )
    get_storage().save_last_card(uid, ctx)
    if should_increment_daily_count(uid, settings):
        get_storage().increment_generation(uid)
    await state.clear()
    logger.info("generation_ok", extra={"user_id": uid, "event": "generation_ok"})


def _image_idea_inline_keyboard(lang: Lang, settings: Settings) -> InlineKeyboardMarkup:
    del settings  # keyboard no longer depends on STT availability
    rows_data = image_idea_keyboard(lang)
    inline_rows: list[list[InlineKeyboardButton]] = []
    for row in rows_data:
        inline_rows.append(
            [InlineKeyboardButton(text=label, callback_data=cb) for label, cb in row]
        )
    return InlineKeyboardMarkup(inline_keyboard=inline_rows)


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Русский", callback_data="lang_ru"),
                InlineKeyboardButton(text="English", callback_data="lang_en"),
            ],
        ]
    )


def occasion_keyboard(lang: Lang) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_lbl(OCCASION_LABELS["occasion_clients"], lang), callback_data="occasion_clients")],
            [InlineKeyboardButton(text=_lbl(OCCASION_LABELS["occasion_colleagues"], lang), callback_data="occasion_colleagues")],
            [InlineKeyboardButton(text=_lbl(OCCASION_LABELS["occasion_loved"], lang), callback_data="occasion_loved")],
        ]
    )


def image_style_keyboard(lang: Lang) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    keys = [k for k in IMAGE_STYLE_KEYBOARD_ORDER if k in IMAGE_STYLE_LABELS]
    for i in range(0, len(keys), 2):
        row = [
            InlineKeyboardButton(
                text=_lbl(IMAGE_STYLE_LABELS[keys[i]], lang),
                callback_data=keys[i],
            )
        ]
        if i + 1 < len(keys):
            row.append(
                InlineKeyboardButton(
                    text=_lbl(IMAGE_STYLE_LABELS[keys[i + 1]], lang),
                    callback_data=keys[i + 1],
                )
            )
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def text_style_keyboard(lang: Lang) -> InlineKeyboardMarkup:
    keys = list(TEXT_STYLE_LABELS.keys())
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(keys), 2):
        if i + 1 < len(keys):
            rows.append(
                [
                    InlineKeyboardButton(
                        text=_lbl(TEXT_STYLE_LABELS[keys[i]], lang),
                        callback_data=keys[i],
                    ),
                    InlineKeyboardButton(
                        text=_lbl(TEXT_STYLE_LABELS[keys[i + 1]], lang),
                        callback_data=keys[i + 1],
                    ),
                ]
            )
        else:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=_lbl(TEXT_STYLE_LABELS[keys[i]], lang),
                        callback_data=keys[i],
                    ),
                ]
            )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def after_card_keyboard(ui_lang: Lang, card_lang: Lang) -> InlineKeyboardMarkup:
    """Post-generation inline actions: ui_lang for labels, card_lang for caption toggle target."""
    toggle_key = "regen_card_lang_en" if card_lang == "ru" else "regen_card_lang_ru"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("regen_repeat", ui_lang), callback_data="regen_repeat"),
                InlineKeyboardButton(text=t("regen_text", ui_lang), callback_data="regen_text"),
            ],
            [
                InlineKeyboardButton(text=t("regen_image", ui_lang), callback_data="regen_image"),
                InlineKeyboardButton(text=t(toggle_key, ui_lang), callback_data="regen_card_lang"),
            ],
        ]
    )


async def _start_create_card_flow(anchor: Message, state: FSMContext, uid: int) -> None:
    storage = get_storage()
    lang_stored = storage.get_user_lang(uid)
    if lang_stored not in ("ru", "en"):
        await clear_idle_small_talk_session(state)
        await state.set_state(CardStates.choosing_language)
        await _send_wizard_prompt(anchor, state, t("start_intro", "ru"), language_keyboard())
        return
    lang = coalesce_lang(lang_stored)
    await clear_idle_small_talk_session(state)
    await state.update_data(lang=lang_stored)
    await state.set_state(CardStates.choosing_occasion)
    await _send_wizard_prompt(
        anchor, state, t("choose_occasion", lang), occasion_keyboard(lang), prompt_kind="occasion"
    )


async def _lang_from_state(state: FSMContext, user_id: int) -> Lang:
    data = await state.get_data()
    raw = data.get("lang")
    if raw in ("ru", "en"):
        return cast(Lang, raw)
    stored = get_storage().get_user_lang(user_id)
    return coalesce_lang(stored)


# ----- /start -----


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    uid = message.from_user.id if message.from_user else 0
    storage = get_storage()
    lang_stored = storage.get_user_lang(uid)
    lang = coalesce_lang(lang_stored)
    if lang_stored in ("ru", "en"):
        await state.update_data(lang=lang_stored)
    logger.info("start", extra={"user_id": uid, "event": "start"})
    if storage.user_needs_profile_onboarding(uid):
        await start_profile_onboarding(message, state, lang)
        return
    prefs = storage.get_profile_preferences(uid)
    first = message.from_user.first_name if message.from_user else None
    name = resolve_display_name(prefs, first) or first or ("friend" if lang == "en" else "друг")
    greeting = await _returning_start_greeting(name, lang)
    await _answer_with_main_menu(message, greeting, lang)


@router.message(
    ~StateFilter(
        ProfileStates.onboarding_name,
        ProfileStates.confirming_name,
        ProfileStates.editing_name,
    ),
    F.text.func(lambda text: main_menu_action_for_text(text) is not None),
)
async def on_main_menu_reply(message: Message, state: FSMContext) -> None:
    if not message.from_user or not message.text:
        return
    uid = message.from_user.id
    action = main_menu_action_for_text(message.text)
    lang = coalesce_lang(get_storage().get_user_lang(uid))
    if action == "create_card":
        await state.clear()
        await _start_create_card_flow(message, state, uid)
        return
    if action == "profile":
        await state.clear()
        await show_profile_main(message, uid)
        return
    if action == "help":
        await _answer_with_main_menu(message, t("help_text", lang), lang)
        return


@router.callback_query(F.data == "action_create_card")
async def on_action_create_card(cq: CallbackQuery, state: FSMContext) -> None:
    if not cq.from_user or not cq.message:
        return
    uid = cq.from_user.id
    await state.clear()
    await _start_create_card_flow(cq.message, state, uid)
    await cq.answer()


@router.callback_query(F.data == "action_help")
async def on_action_help(cq: CallbackQuery) -> None:
    if not cq.from_user or not cq.message:
        return
    lang = coalesce_lang(get_storage().get_user_lang(cq.from_user.id))
    await _answer_with_main_menu(cq.message, t("help_text", lang), lang)
    await cq.answer()


# ----- Language -----


@router.message(Command("lang"))
async def cmd_lang(message: Message, state: FSMContext) -> None:
    from utils.profile_ui import profile_language_keyboard

    uid = message.from_user.id if message.from_user else 0
    cur = coalesce_lang(get_storage().get_user_lang(uid))
    await clear_idle_small_talk_session(state)
    await state.clear()
    await message.answer(
        t("profile_screen_lang", cur),
        reply_markup=profile_language_keyboard(cur),
        parse_mode=ParseMode.HTML,
    )
    logger.info("cmd_lang", extra={"user_id": uid, "event": "cmd_lang"})


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = coalesce_lang(get_storage().get_user_lang(uid))
    await _answer_with_main_menu(message, t("help_text", lang), lang)
    logger.info("cmd_help", extra={"user_id": uid, "event": "cmd_help"})


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    storage = get_storage()
    lang_stored = storage.get_user_lang(uid)
    lang = coalesce_lang(lang_stored)
    prev = await state.get_state()
    await state.clear()
    if prev is None:
        await message.answer(
            t("cancel_nothing", lang),
            reply_markup=main_menu_reply_keyboard(lang),
            parse_mode=ParseMode.HTML,
        )
        logger.info("cmd_cancel_idle", extra={"user_id": uid, "event": "cmd_cancel"})
        return
    await message.answer(
        t("cancel_done", lang),
        reply_markup=main_menu_reply_keyboard(lang),
        parse_mode=ParseMode.HTML,
    )
    logger.info("cmd_cancel", extra={"user_id": uid, "event": "cmd_cancel"})


@router.callback_query(F.data.in_(("lang_ru", "lang_en")), CardStates.choosing_language)
async def on_language_chosen(cq: CallbackQuery, state: FSMContext) -> None:
    if not cq.data or not cq.from_user or not cq.message:
        return
    uid = cq.from_user.id
    lang: Lang = "en" if cq.data == "lang_en" else "ru"
    get_storage().set_user_lang(uid, lang)
    await state.update_data(lang=lang)
    current = await state.get_state()
    await cq.answer(t("lang_saved_toast", lang))

    await _collapse_callback_message(
        cq,
        lang,
        "selected_language",
        label=_language_label(lang),
    )

    if current == CardStates.choosing_language.state:
        await clear_idle_small_talk_session(state)
        await state.set_state(CardStates.choosing_occasion)
        await _send_wizard_prompt(
            cq.message,
            state,
            t("choose_occasion", lang),
            occasion_keyboard(lang),
            prompt_kind="occasion",
        )
        return

    await cq.message.answer(t("lang_saved", lang), parse_mode=ParseMode.HTML)


# ----- Occasion -----


@router.message(CardStates.choosing_occasion, F.text)
async def on_occasion_need_buttons(message: Message, state: FSMContext) -> None:
    """Не даём уйти в small talk: без кнопок «для кого» сценарий не начинается."""
    txt = (message.text or "").strip()
    if txt.startswith("/"):
        return
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    if is_small_talk_text(txt, lang):
        await _reply_wizard_small_talk(message, state, lang)
        return
    await _send_wizard_helper(
        message.bot,
        state,
        message.chat.id,
        lang,
        HELP_FIELD_OCCASION,
        t("use_buttons_below", lang),
        reply_markup=occasion_keyboard(lang),
    )


@router.message(CardStates.choosing_occasion, F.voice)
async def on_occasion_need_buttons_voice(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    await _send_wizard_helper(
        message.bot,
        state,
        message.chat.id,
        lang,
        HELP_FIELD_OCCASION,
        t("use_buttons_below", lang),
        reply_markup=occasion_keyboard(lang),
    )


@router.callback_query(F.data.startswith("occasion_"), CardStates.choosing_occasion)
async def on_occasion(cq: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not cq.data or not cq.message or cq.data not in OCCASION_LABELS:
        return
    await _delete_active_wizard_help(bot, state, HELP_FIELD_OCCASION)
    lang = await _lang_from_state(state, cq.from_user.id)
    label = _lbl(OCCASION_LABELS[cq.data], lang)
    await state.update_data(occasion=cq.data)
    logger.debug(
        "occasion=%s",
        cq.data,
        extra={"user_id": cq.from_user.id, "event": "fsm"},
    )
    await _collapse_callback_message(cq, lang, "selected_occasion", label=label)
    await _go_to_holiday_prompt(cq.message, state, lang)
    await cq.answer()


# ----- Holiday -----


async def _go_to_holiday_prompt(
    anchor: Message,
    state: FSMContext,
    lang: Lang,
) -> None:
    await state.set_state(CardStates.holiday)
    await _send_wizard_prompt(anchor, state, t("step2_holiday", lang), prompt_kind="holiday")


# ----- Image idea -----


async def _go_to_image_idea_prompt(
    anchor: Message,
    state: FSMContext,
    lang: Lang,
) -> None:
    settings = get_settings()
    await state.update_data(image_idea_mode="pick")
    await state.set_state(CardStates.image_description)
    await _send_wizard_prompt(
        anchor,
        state,
        t("image_idea_question", lang),
        _image_idea_inline_keyboard(lang, settings),
        prompt_kind="image_idea",
    )


async def _go_to_image_style_prompt(
    anchor: Message,
    state: FSMContext,
    lang: Lang,
) -> None:
    await state.set_state(CardStates.image_style)
    await _send_wizard_prompt(
        anchor,
        state,
        t("step3_image_style", lang),
        image_style_keyboard(lang),
        prompt_kind="image_style",
    )


@router.callback_query(F.data == IMAGE_IDEA_SURPRISE, CardStates.image_description)
async def on_image_idea_surprise(cq: CallbackQuery, state: FSMContext) -> None:
    if not cq.message or not cq.from_user:
        return
    lang = await _lang_from_state(state, cq.from_user.id)
    await state.update_data(image_description=_surprise_phrase(lang), image_idea_mode=None)
    await _collapse_callback_message(cq, lang, "confirmed_image_idea_auto")
    await _go_to_image_style_prompt(cq.message, state, lang)
    await cq.answer()


@router.callback_query(F.data == IMAGE_IDEA_CUSTOM, CardStates.image_description)
async def on_image_idea_custom(cq: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not cq.message or not cq.from_user:
        return
    lang = await _lang_from_state(state, cq.from_user.id)
    await state.update_data(image_idea_mode="custom")
    await _replace_stored_prompt(
        bot,
        state,
        cq.message,
        t("image_idea_custom_prompt", lang),
        prompt_kind="image_custom",
    )
    await cq.answer()


@router.message(CardStates.image_description, F.text)
async def on_image_description(message: Message, state: FSMContext, bot: Bot) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    data = await state.get_data()
    mode = data.get("image_idea_mode", "pick")
    settings = get_settings()

    if data.get(PENDING_TEXT_FIELD_KEY):
        await _cleanup_pending_field_confirmation(bot, state)

    if not message.text or not message.text.strip():
        await _show_validation_retry(
            bot, state, message, lang, "empty_image_desc", message, prompt_kind="image_custom"
        )
        return
    text = message.text.strip()
    if is_small_talk_text(text, lang):
        await _safe_delete_message(bot, message.chat.id, message.message_id)
        await _reply_wizard_small_talk(message, state, lang)
        return

    if mode != "custom":
        await _safe_delete_message(bot, message.chat.id, message.message_id)
        await _send_wizard_helper(
            bot, state, message.chat.id, lang, HELP_FIELD_IMAGE_IDEA, t("use_buttons_below", lang)
        )
        await _replace_stored_prompt(
            bot,
            state,
            message,
            t("image_idea_use_buttons", lang),
            _image_idea_inline_keyboard(lang, settings),
            prompt_kind="image_idea",
        )
        return

    if is_wizard_meta_question(text, FIELD_IMAGE, lang):
        await _reply_wizard_meta_help(bot, message, state, lang, FIELD_IMAGE)
        return

    await _offer_field_text_confirm(
        bot, message, state, lang, FIELD_IMAGE, text, source=TEXT_SOURCE_TYPED
    )


@router.message(CardStates.image_description, F.voice)
async def on_image_description_voice(message: Message, state: FSMContext, bot: Bot) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    data = await state.get_data()
    mode = data.get("image_idea_mode", "pick")
    settings = get_settings()

    if mode != "custom":
        await message.answer(
            t("image_idea_use_buttons", lang),
            reply_markup=_image_idea_inline_keyboard(lang, settings),
            parse_mode=ParseMode.HTML,
        )
        return
    if not stt_configured(settings):
        await message.answer(t("voice_unavailable", lang))
        return
    await _transcribe_and_offer_voice_confirm(
        bot, message, state, lang, settings, field=FIELD_IMAGE
    )


@router.message(CardStates.image_description)
async def on_image_description_other(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    settings = get_settings()
    await message.answer(
        t("image_idea_use_buttons", lang),
        reply_markup=_image_idea_inline_keyboard(lang, settings),
        parse_mode=ParseMode.HTML,
    )


# ----- Holiday -----


@router.message(CardStates.holiday, F.text)
async def on_holiday(message: Message, state: FSMContext, bot: Bot) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    data = await state.get_data()
    if data.get(PENDING_TEXT_FIELD_KEY):
        await _cleanup_pending_field_confirmation(bot, state)

    if not message.text or not message.text.strip():
        await _show_validation_retry(
            bot, state, message, lang, "empty_holiday", message, prompt_kind="holiday"
        )
        return
    text = message.text.strip()
    if is_small_talk_text(text, lang):
        await _safe_delete_message(bot, message.chat.id, message.message_id)
        await _reply_wizard_small_talk(message, state, lang)
        return
    if is_wizard_meta_question(text, FIELD_HOLIDAY, lang):
        await _reply_wizard_meta_help(bot, message, state, lang, FIELD_HOLIDAY)
        return

    await _offer_field_text_confirm(
        bot, message, state, lang, FIELD_HOLIDAY, text, source=TEXT_SOURCE_TYPED
    )


@router.message(CardStates.holiday, F.voice)
async def on_holiday_voice(message: Message, state: FSMContext, bot: Bot) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    if not message.voice:
        return
    settings = get_settings()
    if not stt_configured(settings):
        await message.answer(t("voice_unavailable", lang))
        return
    await _transcribe_and_offer_voice_confirm(
        bot, message, state, lang, settings, field=FIELD_HOLIDAY
    )


@router.callback_query(F.data.in_(FIELD_CONFIRM_CALLBACKS))
async def on_field_confirm_action(cq: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not cq.data or not cq.message or not cq.from_user:
        return
    lang = await _lang_from_state(state, cq.from_user.id)
    data = await state.get_data()
    field = data.get(PENDING_TEXT_FIELD_KEY)
    text = data.get(PENDING_TEXT_VALUE_KEY)
    current = await state.get_state()

    if cq.data == TEXT_CONFIRM_OK:
        if not field or not text or not state_matches_pending_field(current, field):
            await cq.answer(t("stale_callback", lang), show_alert=True)
            return
        await _cleanup_pending_field_confirmation(
            bot, state, delete_confirm=False, delete_source=True
        )
        try:
            await cq.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        if field == FIELD_IMAGE:
            await _apply_confirmed_image(bot, state, cq.message, lang, text)
        elif field == FIELD_HOLIDAY:
            await _apply_confirmed_holiday(bot, state, cq.message, lang, text)
        elif field == FIELD_OCCASION_DETAILS:
            await _apply_confirmed_occasion_details(bot, state, cq.message, lang, text)
        elif field == FIELD_RECIPIENT_ADDRESS:
            await _apply_confirmed_recipient_address(bot, state, cq.message, lang, text)
        elif field == FIELD_SENDER_SIGNATURE:
            await _apply_confirmed_sender_signature(bot, state, cq.message, lang, text)
            await _run_card_generation_from_wizard(
                bot, cq.message, state, cq.from_user.id, lang, cq=cq
            )
            return
        await cq.answer()
        return

    if cq.data == TEXT_CONFIRM_CHANGE:
        if not field or not state_matches_pending_field(current, field):
            await cq.answer(t("stale_callback", lang), show_alert=True)
            return
        await _cleanup_pending_field_confirmation(bot, state)
        await _reprompt_field(bot, state, lang, field)
        await cq.answer()
        return

    if cq.data == TEXT_CONFIRM_SUGGEST:
        if not field or not state_matches_pending_field(current, field):
            await cq.answer(t("stale_callback", lang), show_alert=True)
            return
        await _cleanup_pending_field_confirmation(bot, state)
        key = "wizard_meta_holiday_help" if field == FIELD_HOLIDAY else "wizard_meta_image_help"
        await _send_wizard_helper(bot, state, cq.message.chat.id, lang, field, t(key, lang))
        await _reprompt_field(bot, state, lang, field)
        await cq.answer()


on_voice_confirm_action = on_field_confirm_action
_apply_confirmed_image_voice = _apply_confirmed_image
_apply_confirmed_holiday_voice = _apply_confirmed_holiday
_apply_confirmed_occasion_details_voice = _apply_confirmed_occasion_details
_apply_confirmed_recipient_address_voice = _apply_confirmed_recipient_address
_apply_confirmed_sender_signature_voice = _apply_confirmed_sender_signature
_reprompt_voice_field = _reprompt_field


@router.message(CardStates.holiday)
async def on_holiday_other(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    await message.answer(t("only_text_voice_step2", lang))


# ----- Occasion details (conditional) -----


@router.callback_query(F.data == WIZARD_OCCASION_DETAILS_YES, CardStates.occasion_details_toggle)
async def on_occasion_details_toggle_yes(cq: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not cq.message or not cq.from_user:
        return
    lang = await _lang_from_state(state, cq.from_user.id)
    await _collapse_callback_message(cq, lang, "toggle_occasion_details_yes")
    await _go_to_occasion_details_input(bot, cq.message, state, lang)
    await cq.answer()


@router.callback_query(F.data == WIZARD_OCCASION_DETAILS_NO, CardStates.occasion_details_toggle)
async def on_occasion_details_toggle_no(cq: CallbackQuery, state: FSMContext) -> None:
    if not cq.message or not cq.from_user:
        return
    lang = await _lang_from_state(state, cq.from_user.id)
    await state.update_data(occasion_details=None)
    await _collapse_callback_message(cq, lang, "toggle_occasion_details_no")
    await _go_to_image_idea_prompt(cq.message, state, lang)
    await cq.answer()


@router.message(CardStates.occasion_details, F.text)
async def on_occasion_details(message: Message, state: FSMContext, bot: Bot) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    data = await state.get_data()
    if data.get(PENDING_TEXT_FIELD_KEY):
        await _cleanup_pending_field_confirmation(bot, state)

    if not message.text or not message.text.strip():
        await _show_validation_retry(
            bot,
            state,
            message,
            lang,
            "empty_occasion_details",
            message,
            prompt_kind="occasion_details",
        )
        return
    text = message.text.strip()
    if is_small_talk_text(text, lang):
        await _safe_delete_message(bot, message.chat.id, message.message_id)
        await _reply_wizard_small_talk(message, state, lang)
        return

    await _offer_field_text_confirm(
        bot, message, state, lang, FIELD_OCCASION_DETAILS, text, source=TEXT_SOURCE_TYPED
    )


@router.message(CardStates.occasion_details, F.voice)
async def on_occasion_details_voice(message: Message, state: FSMContext, bot: Bot) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    settings = get_settings()
    if not stt_configured(settings):
        await message.answer(t("voice_unavailable", lang))
        return
    await _transcribe_and_offer_voice_confirm(
        bot, message, state, lang, settings, field=FIELD_OCCASION_DETAILS
    )


@router.message(CardStates.occasion_details)
async def on_occasion_details_other(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    await message.answer(t("only_text_voice_occasion_details", lang))


# ----- Image style -----


@router.callback_query(F.data.in_(IMAGE_STYLE_CALLBACKS), CardStates.image_style)
async def on_image_style(cq: CallbackQuery, state: FSMContext) -> None:
    if not cq.data or not cq.message or not cq.from_user:
        return
    lang = await _lang_from_state(state, cq.from_user.id)
    label = _lbl(IMAGE_STYLE_LABELS[cq.data], lang)
    await state.update_data(image_style=cq.data)
    await state.set_state(CardStates.text_style)
    await _collapse_callback_message(cq, lang, "selected_image_style", label=label)
    await _send_wizard_prompt(
        cq.message,
        state,
        t("step4_text_style", lang),
        text_style_keyboard(lang),
        prompt_kind="text_style",
    )
    await cq.answer()


# ----- Generation (small talk while waiting) -----


@router.message(CardStates.generating, F.text)
async def on_generating_small_talk(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if raw.startswith("/"):
        return
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    if is_small_talk_text(raw, lang):
        await _reply_wizard_small_talk(message, state, lang)


# ----- Text style -> personalization -> generation -----


@router.callback_query(F.data.in_(TEXT_STYLE_CALLBACKS), CardStates.text_style)
async def on_text_style(cq: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not cq.data or not cq.message or not cq.from_user:
        return
    lang = await _lang_from_state(state, cq.from_user.id)
    label = _lbl(TEXT_STYLE_LABELS[cq.data], lang)
    await state.update_data(text_style=cq.data)
    await _collapse_callback_message(cq, lang, "selected_text_style", label=label)
    await _go_to_recipient_address_toggle(cq.message, state, lang)
    await cq.answer()


# ----- Recipient name toggle & input -----


@router.callback_query(F.data == WIZARD_RECIPIENT_YES, CardStates.recipient_address_toggle)
async def on_recipient_toggle_yes(cq: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not cq.message or not cq.from_user:
        return
    lang = await _lang_from_state(state, cq.from_user.id)
    await _collapse_callback_message(cq, lang, "toggle_recipient_yes")
    await _go_to_recipient_address_input(bot, cq.message, state, lang)
    await cq.answer()


@router.callback_query(F.data == WIZARD_RECIPIENT_NO, CardStates.recipient_address_toggle)
async def on_recipient_toggle_no(cq: CallbackQuery, state: FSMContext) -> None:
    if not cq.message or not cq.from_user:
        return
    lang = await _lang_from_state(state, cq.from_user.id)
    await state.update_data(recipient_address=None)
    await _collapse_callback_message(cq, lang, "toggle_recipient_no")
    await _go_to_signature_toggle(cq.message, state, lang)
    await cq.answer()


@router.message(CardStates.recipient_address, F.text)
async def on_recipient_address(message: Message, state: FSMContext, bot: Bot) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    data = await state.get_data()
    if data.get(PENDING_TEXT_FIELD_KEY):
        await _cleanup_pending_field_confirmation(bot, state)

    if not message.text or not message.text.strip():
        await _show_validation_retry(
            bot, state, message, lang, "empty_recipient_address", message, prompt_kind="recipient_address"
        )
        return
    text = message.text.strip()
    if is_small_talk_text(text, lang):
        await _safe_delete_message(bot, message.chat.id, message.message_id)
        await _reply_wizard_small_talk(message, state, lang)
        return

    await _offer_field_text_confirm(
        bot, message, state, lang, FIELD_RECIPIENT_ADDRESS, text, source=TEXT_SOURCE_TYPED
    )


@router.message(CardStates.recipient_address, F.voice)
async def on_recipient_address_voice(message: Message, state: FSMContext, bot: Bot) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    settings = get_settings()
    if not stt_configured(settings):
        await message.answer(t("voice_unavailable", lang))
        return
    await _transcribe_and_offer_voice_confirm(
        bot, message, state, lang, settings, field=FIELD_RECIPIENT_ADDRESS
    )


@router.message(CardStates.recipient_address)
async def on_recipient_address_other(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    await message.answer(t("only_text_voice_recipient_address", lang))


# ----- Signature toggle & input -----


@router.callback_query(F.data == WIZARD_SIGNATURE_YES, CardStates.signature_toggle)
async def on_signature_toggle_yes(cq: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not cq.message or not cq.from_user:
        return
    lang = await _lang_from_state(state, cq.from_user.id)
    await _collapse_callback_message(cq, lang, "toggle_signature_yes")
    await _go_to_sender_signature_input(bot, cq.message, state, lang)
    await cq.answer()


@router.callback_query(F.data == WIZARD_SIGNATURE_NO, CardStates.signature_toggle)
async def on_signature_toggle_no(cq: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not cq.message or not cq.from_user:
        return
    uid = cq.from_user.id
    lang = await _lang_from_state(state, uid)
    await state.update_data(sender_signature=None)
    await _collapse_callback_message(cq, lang, "toggle_signature_no")
    await _run_card_generation_from_wizard(bot, cq.message, state, uid, lang, cq=cq)
    await cq.answer()


@router.message(CardStates.sender_signature, F.text)
async def on_sender_signature(message: Message, state: FSMContext, bot: Bot) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    data = await state.get_data()
    if data.get(PENDING_TEXT_FIELD_KEY):
        await _cleanup_pending_field_confirmation(bot, state)

    if not message.text or not message.text.strip():
        await _show_validation_retry(
            bot, state, message, lang, "empty_signature", message, prompt_kind="sender_signature"
        )
        return
    text = message.text.strip()
    if is_small_talk_text(text, lang):
        await _safe_delete_message(bot, message.chat.id, message.message_id)
        await _reply_wizard_small_talk(message, state, lang)
        return

    await _offer_field_text_confirm(
        bot, message, state, lang, FIELD_SENDER_SIGNATURE, text, source=TEXT_SOURCE_TYPED
    )


@router.message(CardStates.sender_signature, F.voice)
async def on_sender_signature_voice(message: Message, state: FSMContext, bot: Bot) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    settings = get_settings()
    if not stt_configured(settings):
        await message.answer(t("voice_unavailable", lang))
        return
    await _transcribe_and_offer_voice_confirm(
        bot, message, state, lang, settings, field=FIELD_SENDER_SIGNATURE
    )


@router.message(CardStates.sender_signature)
async def on_sender_signature_other(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    await message.answer(t("only_text_voice_signature", lang))


# ----- Regen -----


def _photo_file_fallback(cq: CallbackQuery, ctx: LastCardContext) -> Optional[str]:
    if ctx.photo_file_id:
        return ctx.photo_file_id
    if cq.message and cq.message.photo:
        return cq.message.photo[-1].file_id
    return None


@router.callback_query(F.data == "regen_repeat")
async def regen_repeat(cq: CallbackQuery) -> None:
    if not cq.from_user or not cq.message:
        return
    uid = cq.from_user.id
    ctx = get_storage().get_last_card(uid)
    ui_lang = _ui_lang_for_user(uid)
    card_lang = coalesce_lang(ctx.lang if ctx else None)
    if not ctx or not ctx.photo_file_id or not ctx.caption_html:
        await cq.answer(t("no_saved_card", ui_lang), show_alert=True)
        return
    await cq.answer()
    await cq.message.answer_photo(
        photo=ctx.photo_file_id,
        caption=ctx.caption_html,
        parse_mode=ParseMode.HTML,
        reply_markup=after_card_keyboard(ui_lang, card_lang),
    )
    logger.info("regen_repeat", extra={"user_id": uid, "event": "regen_repeat"})


@router.callback_query(F.data == "regen_text")
async def regen_text(cq: CallbackQuery) -> None:
    if not cq.from_user or not cq.message:
        return
    uid = cq.from_user.id
    settings = get_settings()
    ctx = get_storage().get_last_card(uid)
    ui_lang = _ui_lang_for_user(uid)
    card_lang = coalesce_lang(ctx.lang if ctx else None)
    if not ctx:
        await cq.answer(t("no_saved_card", ui_lang), show_alert=True)
        return
    if not can_consume_generation(uid, settings):
        await cq.answer(t("rate_limited", ui_lang), show_alert=True)
        return
    if not text_provider_configured(settings):
        await cq.answer(
            t(text_provider_preflight_message_key(settings), ui_lang),
            show_alert=True,
        )
        return
    photo_id = _photo_file_fallback(cq, ctx)
    if not photo_id:
        await cq.answer("No image reference", show_alert=True)
        return
    await cq.answer(t("generating", ui_lang))
    try:
        cap = await run_text_only(
            settings,
            occasion=ctx.occasion,
            holiday=ctx.holiday,
            text_style=ctx.text_style,
            lang=card_lang,
            profile_prefs=get_storage().get_profile_preferences(uid),
            recipient_address=ctx.recipient_address or None,
            sender_signature=ctx.sender_signature or None,
            occasion_details=ctx.occasion_details or None,
        )
    except (YandexGPTError, OpenAITextError, asyncio.TimeoutError) as e:
        logger.warning("regen_text failed: %s", e, extra={"user_id": uid, "event": "error"})
        await cq.message.answer(t("err_text", ui_lang, err=e))
        return
    sent = await cq.message.answer_photo(
        photo=photo_id,
        caption=cap,
        parse_mode=ParseMode.HTML,
        reply_markup=after_card_keyboard(ui_lang, card_lang),
    )
    ctx.caption_html = cap
    if sent.photo:
        ctx.photo_file_id = sent.photo[-1].file_id
    get_storage().save_last_card(uid, ctx)
    if should_increment_daily_count(uid, settings):
        get_storage().increment_generation(uid)
    logger.info("regen_text_ok", extra={"user_id": uid, "event": "regen_text"})


@router.callback_query(F.data == "regen_image")
async def regen_image(cq: CallbackQuery) -> None:
    if not cq.from_user or not cq.message:
        return
    uid = cq.from_user.id
    settings = get_settings()
    ctx = get_storage().get_last_card(uid)
    ui_lang = _ui_lang_for_user(uid)
    card_lang = coalesce_lang(ctx.lang if ctx else None)
    if not ctx:
        await cq.answer(t("no_saved_card", ui_lang), show_alert=True)
        return
    if not can_consume_generation(uid, settings):
        await cq.answer(t("rate_limited", ui_lang), show_alert=True)
        return
    if not image_provider_configured(settings):
        await cq.answer(
            t(image_provider_preflight_message_key(settings), ui_lang),
            show_alert=True,
        )
        return
    base = (ctx.image_prompt_en or "").strip()
    if not base:
        await cq.answer(t("no_saved_card", ui_lang), show_alert=True)
        return
    new_prompt = f"{base}, {image_variation_suffix()}"
    await cq.answer(t("generating", ui_lang))
    try:
        image_bytes, used = await run_image_only(settings, new_prompt or base)
    except (ProxiAPIError, OpenAIImageError) as e:
        logger.warning("regen_image failed: %s", e, extra={"user_id": uid, "event": "error"})
        await cq.message.answer(t("err_image", ui_lang, err=e))
        return
    except asyncio.TimeoutError:
        await cq.message.answer(t("err_timeout", ui_lang))
        return
    photo = BufferedInputFile(image_bytes, filename="card.png")
    cap = ctx.caption_html or ""
    sent = await cq.message.answer_photo(
        photo=photo,
        caption=cap,
        parse_mode=ParseMode.HTML,
        reply_markup=after_card_keyboard(ui_lang, card_lang),
    )
    ctx.image_prompt_en = used
    if sent.photo:
        ctx.photo_file_id = sent.photo[-1].file_id
    get_storage().save_last_card(uid, ctx)
    if should_increment_daily_count(uid, settings):
        get_storage().increment_generation(uid)
    logger.info("regen_image_ok", extra={"user_id": uid, "event": "regen_image"})


# ----- Card caption language toggle (not UI language) -----


@router.callback_query(F.data == "regen_card_lang")
async def regen_card_lang(cq: CallbackQuery) -> None:
    if not cq.from_user or not cq.message:
        return
    uid = cq.from_user.id
    settings = get_settings()
    ctx = get_storage().get_last_card(uid)
    ui_lang = _ui_lang_for_user(uid)
    if not ctx:
        await cq.answer(t("no_saved_card", ui_lang), show_alert=True)
        return
    if not can_consume_generation(uid, settings):
        await cq.answer(t("rate_limited", ui_lang), show_alert=True)
        return
    if not text_provider_configured(settings):
        await cq.answer(
            t(text_provider_preflight_message_key(settings), ui_lang),
            show_alert=True,
        )
        return
    photo_id = _photo_file_fallback(cq, ctx)
    if not photo_id:
        await cq.answer("No image reference", show_alert=True)
        return
    current = coalesce_lang(ctx.lang)
    new_lang: Lang = "en" if current == "ru" else "ru"
    profile_before = coalesce_lang(get_storage().get_user_lang(uid))
    log_card_lang_toggle(
        user_id=uid,
        ui_lang=ui_lang,
        previous_card_lang=current,
        target_card_lang=new_lang,
        profile_lang_before=profile_before,
        profile_lang_after=profile_before,
        image_reused=True,
        run_text_only_called=True,
    )
    await cq.answer(t("generating", ui_lang))
    try:
        cap = await run_text_only(
            settings,
            occasion=ctx.occasion,
            holiday=ctx.holiday,
            text_style=ctx.text_style,
            lang=new_lang,
            profile_prefs=get_storage().get_profile_preferences(uid),
            recipient_address=ctx.recipient_address or None,
            sender_signature=ctx.sender_signature or None,
            occasion_details=ctx.occasion_details or None,
        )
    except (YandexGPTError, OpenAITextError, asyncio.TimeoutError) as e:
        logger.warning("regen_card_lang failed: %s", e, extra={"user_id": uid, "event": "error"})
        await cq.message.answer(t("err_text", ui_lang, err=e))
        return
    sent = await cq.message.answer_photo(
        photo=photo_id,
        caption=cap,
        parse_mode=ParseMode.HTML,
        reply_markup=after_card_keyboard(ui_lang, new_lang),
    )
    await _reassert_main_menu_keyboard(cq.message, ui_lang)
    ctx.lang = new_lang
    ctx.caption_html = cap
    ctx.photo_file_id = photo_id
    get_storage().save_last_card(uid, ctx)
    profile_after = coalesce_lang(get_storage().get_user_lang(uid))
    log_card_lang_toggle(
        user_id=uid,
        ui_lang=ui_lang,
        previous_card_lang=current,
        target_card_lang=new_lang,
        profile_lang_before=profile_before,
        profile_lang_after=profile_after,
        image_reused=True,
        run_text_only_called=True,
        final_card_lang=new_lang,
    )
    if should_increment_daily_count(uid, settings):
        get_storage().increment_generation(uid)
    logger.info("regen_card_lang_ok", extra={"user_id": uid, "event": "regen_card_lang"})


# ----- Choosing language: typed «русский» / «english» or nudge -----


@router.message(CardStates.choosing_language, F.text)
async def on_lang_wait_text(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.text:
        return
    uid = message.from_user.id if message.from_user else 0
    low = message.text.strip().lower()
    picked: Optional[Lang] = None
    if low in (
        "английский",
        "english",
        "en",
        "англ",
        "in english",
        "на английском",
    ):
        picked = "en"
    elif low in ("русский", "russian", "ru", "на русском"):
        picked = "ru"
    if picked is not None:
        get_storage().set_user_lang(uid, picked)
        await clear_idle_small_talk_session(state)
        await state.update_data(lang=picked)
        await state.set_state(CardStates.choosing_occasion)
        await _safe_delete_message(bot, message.chat.id, message.message_id)
        await _send_wizard_prompt(
            message,
            state,
            t("choose_occasion", picked),
            occasion_keyboard(picked),
            prompt_kind="occasion",
        )
        logger.info("lang_text_pick", extra={"user_id": uid, "event": "lang_pick_text"})
        return
    lang = coalesce_lang(get_storage().get_user_lang(uid))
    if is_small_talk_text(low, lang):
        await _reply_wizard_small_talk(message, state, lang)
        return
    await message.answer(t("pick_language", lang), reply_markup=language_keyboard())


@router.message(CardStates.choosing_language)
async def on_lang_wait_other(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = coalesce_lang(get_storage().get_user_lang(uid))
    await message.answer(t("pick_language", lang), reply_markup=language_keyboard())


# ----- Small talk -----

_NON_IDLE_TEXT_STATES = (
    CardStates.choosing_language,
    CardStates.choosing_occasion,
    CardStates.image_description,
    CardStates.holiday,
    CardStates.occasion_details_toggle,
    CardStates.occasion_details,
    CardStates.image_style,
    CardStates.text_style,
    CardStates.recipient_address_toggle,
    CardStates.recipient_address,
    CardStates.signature_toggle,
    CardStates.sender_signature,
    CardStates.generating,
    ProfileStates.onboarding_name,
    ProfileStates.confirming_name,
    ProfileStates.editing_name,
)


@router.message(~StateFilter(*_NON_IDLE_TEXT_STATES), F.text)
async def on_small_talk(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if raw.startswith("/"):
        return
    uid = message.from_user.id if message.from_user else 0
    lang = coalesce_lang(get_storage().get_user_lang(uid))
    fsm_state = await state.get_state()
    menu_action = main_menu_action_for_text(raw)
    if menu_action == "create_card":
        intent = "create_card"
        handler_path = "on_small_talk->main_menu_create_card"
    elif is_create_card_intent(raw, lang):
        intent = "create_card"
        handler_path = "on_small_talk->create_card_intent"
    elif menu_action in ("profile", "help"):
        intent = "menu_button"
        handler_path = f"on_small_talk->menu_{menu_action}"
    else:
        intent = "small_talk"
        handler_path = "on_small_talk->idle_small_talk"
    log_idle_route(
        user_id=uid,
        fsm_state=fsm_state,
        text=raw,
        intent=intent,
        handler_path=handler_path,
    )
    if menu_action == "create_card" or is_create_card_intent(raw, lang):
        await clear_idle_small_talk_session(state)
        await state.clear()
        await _start_create_card_flow(message, state, uid)
        return
    reply_text = await _idle_small_talk_reply_text(raw, lang, state, user_id=uid)
    await _answer_with_main_menu(message, reply_text, lang)


@router.callback_query()
async def on_stale_callback(cq: CallbackQuery, state: FSMContext) -> None:
    """Stale inline buttons from earlier wizard steps."""
    if not cq.from_user or not cq.data:
        return
    lang = coalesce_lang(get_storage().get_user_lang(cq.from_user.id))
    await _handle_stale_callback(cq, lang)
