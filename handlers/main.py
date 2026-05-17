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
from handlers.states import CardStates
from services.card_generation import run_card_generation, run_image_only, run_text_only
from services.proxi import ProxiAPIError
from services.providers.factory import (
    text_provider_configured,
    text_provider_preflight_message_key,
)
from services.providers.image_factory import (
    image_provider_configured,
    image_provider_preflight_message_key,
)
from services.providers.openai_image import OpenAIImageError
from services.providers.openai_text import OpenAITextError
from services.speech_to_text import SpeechToTextError, transcribe_audio
from services.storage import LastCardContext, get_storage
from services.yandex_gpt import YandexGPTError
from utils.i18n import Lang, t
from utils.wizard_input import is_small_talk_text, validate_holiday, validate_image_description
from utils.wizard_summary import build_generation_summary
from utils.wizard_ui import (
    IMAGE_IDEA_CUSTOM,
    IMAGE_IDEA_SURPRISE,
    IMAGE_IDEA_VOICE,
    image_idea_keyboard,
)
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
    if await _edit_stored_prompt(bot, state, text, reply_markup):
        if prompt_kind is not None:
            await state.update_data(prompt_kind=prompt_kind)
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
    await _resolve_prompt_to_confirmation(bot, state, message, lang, confirm_key, **fmt)
    await _safe_delete_message(bot, message.chat.id, message.message_id)


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
    elif current == CardStates.image_description.state:
        mode = data.get("image_idea_mode", "pick")
        if mode == "custom":
            kind = data.get("prompt_kind")
            if kind == "image_voice":
                await _send_wizard_prompt(anchor, state, t("image_idea_voice_prompt", lang), prompt_kind="image_voice")
            else:
                await _send_wizard_prompt(anchor, state, t("image_idea_custom_prompt", lang), prompt_kind="image_custom")
        else:
            await _send_wizard_prompt(
                anchor,
                state,
                t("image_idea_question", lang),
                _image_idea_inline_keyboard(lang, settings),
                prompt_kind="image_idea",
            )
    elif current == CardStates.holiday.state:
        await _send_wizard_prompt(anchor, state, t("step2_holiday", lang), prompt_kind="holiday")
    elif current == CardStates.image_style.state:
        await _send_wizard_prompt(
            anchor, state, t("step3_image_style", lang), image_style_keyboard(lang), prompt_kind="image_style"
        )
    elif current == CardStates.text_style.state:
        await _send_wizard_prompt(
            anchor, state, t("step4_text_style", lang), text_style_keyboard(lang), prompt_kind="text_style"
        )
    elif current == CardStates.choosing_language.state:
        await anchor.answer(t("pick_language", lang), reply_markup=language_keyboard())


async def _reply_wizard_small_talk(
    message: Message,
    state: FSMContext,
    lang: Lang,
) -> None:
    await message.answer(t("wizard_small_talk", lang), parse_mode=ParseMode.HTML)
    data = await state.get_data()
    if not data.get("prompt_msg_id"):
        await _resend_current_prompt(message, state, lang)


def _esc_user_text(text: str) -> str:
    return html.escape(text.strip())


def _stt_configured(settings: Settings) -> bool:
    return bool((settings.PROXI_API_KEY or "").strip() and (settings.PROXI_BASE_URL or "").strip())


def _surprise_phrase(lang: Lang) -> str:
    return "surprise me" if lang == "en" else "придумай сам"


def _image_idea_inline_keyboard(lang: Lang, settings: Settings) -> InlineKeyboardMarkup:
    rows_data = image_idea_keyboard(lang, stt_available=_stt_configured(settings))
    inline_rows: list[list[InlineKeyboardButton]] = []
    for row in rows_data:
        inline_rows.append(
            [InlineKeyboardButton(text=label, callback_data=cb) for label, cb in row]
        )
    return InlineKeyboardMarkup(inline_keyboard=inline_rows)


def is_admin_user(uid: int, settings: Settings) -> bool:
    return uid in settings.admin_ids()


def can_consume_generation(uid: int, settings: Settings) -> bool:
    if is_admin_user(uid, settings):
        return True
    return get_storage().get_daily_count(uid) < settings.DAILY_GENERATION_LIMIT


def home_keyboard(lang: Lang) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("btn_create_card", lang), callback_data="action_create_card")],
            [
                InlineKeyboardButton(text=t("btn_help_short", lang), callback_data="action_help"),
                InlineKeyboardButton(text=t("btn_change_lang_short", lang), callback_data="change_lang"),
            ],
        ]
    )


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


def after_card_keyboard(lang: Lang) -> InlineKeyboardMarkup:
    # По 1–2 кнопки в ряд — так надёжнее отображается в Telegram
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("regen_repeat", lang), callback_data="regen_repeat")],
            [
                InlineKeyboardButton(text=t("regen_text", lang), callback_data="regen_text"),
                InlineKeyboardButton(text=t("regen_image", lang), callback_data="regen_image"),
            ],
            [
                InlineKeyboardButton(text=t("create_another", lang), callback_data="create_another"),
                InlineKeyboardButton(text=t("change_language", lang), callback_data="change_lang"),
            ],
        ]
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
    await message.answer(
        t("home_welcome", lang),
        reply_markup=home_keyboard(lang),
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data == "action_create_card")
async def on_action_create_card(cq: CallbackQuery, state: FSMContext) -> None:
    if not cq.from_user or not cq.message:
        return
    uid = cq.from_user.id
    storage = get_storage()
    lang_stored = storage.get_user_lang(uid)
    if lang_stored not in ("ru", "en"):
        await state.set_state(CardStates.choosing_language)
        await _send_wizard_prompt(cq.message, state, t("start_intro", "ru"), language_keyboard())
        await cq.answer()
        return
    lang = coalesce_lang(lang_stored)
    await state.update_data(lang=lang_stored)
    await state.set_state(CardStates.choosing_occasion)
    await _send_wizard_prompt(
        cq.message, state, t("choose_occasion", lang), occasion_keyboard(lang), prompt_kind="occasion"
    )
    await cq.answer()


@router.callback_query(F.data == "action_help")
async def on_action_help(cq: CallbackQuery) -> None:
    if not cq.from_user or not cq.message:
        return
    lang = coalesce_lang(get_storage().get_user_lang(cq.from_user.id))
    await cq.message.answer(t("help_text", lang), parse_mode=ParseMode.HTML)
    await cq.answer()


# ----- Language -----


@router.message(Command("lang"))
async def cmd_lang(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    cur = coalesce_lang(get_storage().get_user_lang(uid))
    await state.set_state(CardStates.choosing_language)
    await message.answer(t("pick_language", cur), reply_markup=language_keyboard())
    logger.info("cmd_lang", extra={"user_id": uid, "event": "cmd_lang"})


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = coalesce_lang(get_storage().get_user_lang(uid))
    await message.answer(t("help_text", lang), parse_mode=ParseMode.HTML)
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
            reply_markup=home_keyboard(lang),
            parse_mode=ParseMode.HTML,
        )
        logger.info("cmd_cancel_idle", extra={"user_id": uid, "event": "cmd_cancel"})
        return
    await message.answer(
        t("cancel_done", lang),
        reply_markup=home_keyboard(lang),
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


@router.callback_query(F.data == "change_lang")
async def on_change_lang(cq: CallbackQuery, state: FSMContext) -> None:
    if not cq.from_user or not cq.message:
        return
    cur = coalesce_lang(get_storage().get_user_lang(cq.from_user.id))
    await state.set_state(CardStates.choosing_language)
    await cq.message.answer(t("pick_language", cur), reply_markup=language_keyboard())
    await cq.answer()


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
    await message.answer(t("use_occasion_buttons", lang), reply_markup=occasion_keyboard(lang))


@router.message(CardStates.choosing_occasion, F.voice)
async def on_occasion_need_buttons_voice(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    await message.answer(t("use_occasion_buttons", lang), reply_markup=occasion_keyboard(lang))


@router.callback_query(F.data.startswith("occasion_"), CardStates.choosing_occasion)
async def on_occasion(cq: CallbackQuery, state: FSMContext) -> None:
    if not cq.data or not cq.message or cq.data not in OCCASION_LABELS:
        return
    lang = await _lang_from_state(state, cq.from_user.id)
    label = _lbl(OCCASION_LABELS[cq.data], lang)
    await state.update_data(occasion=cq.data, image_idea_mode="pick")
    await state.set_state(CardStates.image_description)
    logger.debug(
        "occasion=%s",
        cq.data,
        extra={"user_id": cq.from_user.id, "event": "fsm"},
    )
    await _collapse_callback_message(cq, lang, "selected_occasion", label=label)
    settings = get_settings()
    await _send_wizard_prompt(
        cq.message,
        state,
        t("image_idea_question", lang),
        _image_idea_inline_keyboard(lang, settings),
        prompt_kind="image_idea",
    )
    await cq.answer()


# ----- Image idea -----


async def _go_to_holiday_prompt(
    anchor: Message,
    state: FSMContext,
    lang: Lang,
) -> None:
    await state.set_state(CardStates.holiday)
    await _send_wizard_prompt(anchor, state, t("step2_holiday", lang), prompt_kind="holiday")


@router.callback_query(F.data == IMAGE_IDEA_SURPRISE, CardStates.image_description)
async def on_image_idea_surprise(cq: CallbackQuery, state: FSMContext) -> None:
    if not cq.message or not cq.from_user:
        return
    lang = await _lang_from_state(state, cq.from_user.id)
    await state.update_data(image_description=_surprise_phrase(lang), image_idea_mode=None)
    await _collapse_callback_message(cq, lang, "confirmed_image_idea_auto")
    await _go_to_holiday_prompt(cq.message, state, lang)
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


@router.callback_query(F.data == IMAGE_IDEA_VOICE, CardStates.image_description)
async def on_image_idea_voice(cq: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not cq.message or not cq.from_user:
        return
    lang = await _lang_from_state(state, cq.from_user.id)
    settings = get_settings()
    if not _stt_configured(settings):
        await cq.answer(t("voice_unavailable", lang), show_alert=True)
        return
    await state.update_data(image_idea_mode="custom")
    await _replace_stored_prompt(
        bot,
        state,
        cq.message,
        t("image_idea_voice_prompt", lang),
        prompt_kind="image_voice",
    )
    await cq.answer()


@router.message(CardStates.image_description, F.text)
async def on_image_description(message: Message, state: FSMContext, bot: Bot) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    data = await state.get_data()
    mode = data.get("image_idea_mode", "pick")
    settings = get_settings()

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
        await _replace_stored_prompt(
            bot,
            state,
            message,
            t("image_idea_use_buttons", lang),
            _image_idea_inline_keyboard(lang, settings),
            prompt_kind="image_idea",
        )
        return

    if not validate_image_description(text, lang):
        await _show_validation_retry(
            bot, state, message, lang, "invalid_image_desc", message, prompt_kind="image_custom"
        )
        return
    await state.update_data(image_description=text, image_idea_mode=None)
    await _finalize_text_step(
        bot, state, message, lang, "confirmed_image_idea", text=_esc_user_text(text)
    )
    await _go_to_holiday_prompt(message, state, lang)


@router.message(CardStates.image_description, F.voice)
async def on_image_description_voice(message: Message, state: FSMContext, bot: Bot) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    data = await state.get_data()
    mode = data.get("image_idea_mode", "pick")
    settings = get_settings()

    if mode == "pick":
        if not _stt_configured(settings):
            await message.answer(t("voice_unavailable", lang))
            return
        await state.update_data(image_idea_mode="custom")

    if not message.voice:
        return
    if not _stt_configured(settings):
        await message.answer(t("voice_unavailable", lang))
        return
    await message.answer(t("voice_recognizing", lang))
    try:
        file = await bot.get_file(message.voice.file_id)
        bio = await bot.download_file(file.file_path)
        audio_bytes = bio.read() if hasattr(bio, "read") else bytes(bio)
        if not audio_bytes:
            await message.answer(t("voice_dl_fail", lang))
            return
        ext = (file.file_path or "").split(".")[-1] if file.file_path else "ogg"
        filename = f"voice.{ext}"
        text = await transcribe_audio(
            audio_bytes,
            api_key=settings.PROXI_API_KEY,
            base_url=settings.PROXI_BASE_URL,
            filename=filename,
            timeout=settings.STT_TIMEOUT,
        )
    except SpeechToTextError as e:
        await message.answer(t("voice_fail", lang, err=e))
        return
    if not text or not text.strip():
        await _show_validation_retry(
            bot, state, message, lang, "voice_empty", None, prompt_kind="image_custom", delete_user_message=False
        )
        return
    text = text.strip()
    if not validate_image_description(text, lang):
        await _show_validation_retry(
            bot, state, message, lang, "invalid_image_desc", None, prompt_kind="image_custom", delete_user_message=False
        )
        return
    await state.update_data(image_description=text, image_idea_mode=None)
    await _finalize_text_step(
        bot, state, message, lang, "confirmed_image_idea", text=_esc_user_text(text)
    )
    await _go_to_holiday_prompt(message, state, lang)


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
    if not validate_holiday(text, lang):
        await _show_validation_retry(
            bot, state, message, lang, "invalid_holiday", message, prompt_kind="holiday"
        )
        return
    await state.update_data(holiday=text)
    await state.set_state(CardStates.image_style)
    await _finalize_text_step(
        bot, state, message, lang, "confirmed_holiday", text=_esc_user_text(text)
    )
    await _send_wizard_prompt(
        message,
        state,
        t("step3_image_style", lang),
        image_style_keyboard(lang),
        prompt_kind="image_style",
    )


@router.message(CardStates.holiday, F.voice)
async def on_holiday_voice(message: Message, state: FSMContext, bot: Bot) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    if not message.voice:
        return
    await message.answer(t("voice_recognizing", lang))
    settings = get_settings()
    if not settings.PROXI_API_KEY or not settings.PROXI_BASE_URL:
        await message.answer(t("voice_unavailable", lang))
        return
    try:
        file = await bot.get_file(message.voice.file_id)
        bio = await bot.download_file(file.file_path)
        audio_bytes = bio.read() if hasattr(bio, "read") else bytes(bio)
        if not audio_bytes:
            await message.answer(t("voice_dl_fail", lang))
            return
        ext = (file.file_path or "").split(".")[-1] if file.file_path else "ogg"
        filename = f"voice.{ext}"
        text = await transcribe_audio(
            audio_bytes,
            api_key=settings.PROXI_API_KEY,
            base_url=settings.PROXI_BASE_URL,
            filename=filename,
            timeout=settings.STT_TIMEOUT,
        )
    except SpeechToTextError as e:
        await message.answer(t("voice_fail", lang, err=e))
        return
    if not text or not text.strip():
        await _show_validation_retry(
            bot, state, message, lang, "voice_empty", None, prompt_kind="holiday", delete_user_message=False
        )
        return
    text = text.strip()
    if not validate_holiday(text, lang):
        await _show_validation_retry(
            bot, state, message, lang, "invalid_holiday", None, prompt_kind="holiday", delete_user_message=False
        )
        return
    await state.update_data(holiday=text)
    await state.set_state(CardStates.image_style)
    await _finalize_text_step(
        bot, state, message, lang, "confirmed_holiday", text=_esc_user_text(text)
    )
    await _send_wizard_prompt(
        message,
        state,
        t("step3_image_style", lang),
        image_style_keyboard(lang),
        prompt_kind="image_style",
    )


@router.message(CardStates.holiday)
async def on_holiday_other(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    await message.answer(t("only_text_voice_step2", lang))


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


# ----- Text style -> generation -----


@router.callback_query(F.data.in_(TEXT_STYLE_CALLBACKS), CardStates.text_style)
async def on_text_style(cq: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not cq.data or not cq.message or not cq.from_user:
        return
    uid = cq.from_user.id
    settings = get_settings()
    lang = await _lang_from_state(state, uid)
    label = _lbl(TEXT_STYLE_LABELS[cq.data], lang)

    if not image_provider_configured(settings):
        await cq.answer(
            t(image_provider_preflight_message_key(settings), lang),
            show_alert=True,
        )
        return
    if not text_provider_configured(settings):
        await cq.answer(
            t(text_provider_preflight_message_key(settings), lang),
            show_alert=True,
        )
        return

    if not can_consume_generation(uid, settings):
        await cq.answer(t("rate_limited", lang, limit=settings.DAILY_GENERATION_LIMIT), show_alert=True)
        return

    await state.update_data(text_style=cq.data)
    await state.set_state(CardStates.generating)
    logger.info("generation_start", extra={"user_id": uid, "event": "generation_start"})
    await _collapse_callback_message(cq, lang, "selected_text_style", label=label)

    data: dict[str, Any] = (await state.get_data()) or {}
    occasion = str(data.get("occasion", ""))
    image_description = str(data.get("image_description", ""))
    holiday = str(data.get("holiday", ""))
    image_style = str(data.get("image_style", "style_realistic"))
    text_style = str(data.get("text_style", "text_warm"))

    summary = build_generation_summary(
        lang=lang,
        occasion=occasion,
        image_description=image_description,
        holiday=holiday,
        image_style=image_style,
        text_style=text_style,
    )
    status_msg = await cq.message.answer(summary, parse_mode=ParseMode.HTML)
    await cq.answer()

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
        )
    except (ProxiAPIError, OpenAIImageError) as e:
        logger.exception("Image provider failed: %s", e, extra={"user_id": uid, "event": "error"})
        await status_msg.edit_text(t("err_image", lang, err=e))
        await state.set_state(CardStates.text_style)
        await cq.message.answer(
            t("step4_text_style", lang),
            reply_markup=text_style_keyboard(lang),
            parse_mode=ParseMode.HTML,
        )
        return
    except (YandexGPTError, OpenAITextError) as e:
        logger.exception("Text provider failed: %s", e, extra={"user_id": uid, "event": "error"})
        await status_msg.edit_text(t("err_text", lang, err=e))
        await state.set_state(CardStates.text_style)
        await cq.message.answer(
            t("step4_text_style", lang),
            reply_markup=text_style_keyboard(lang),
            parse_mode=ParseMode.HTML,
        )
        return
    except asyncio.TimeoutError:
        logger.warning("timeout", extra={"user_id": uid, "event": "error"})
        await status_msg.edit_text(t("err_timeout", lang))
        await state.set_state(CardStates.text_style)
        await cq.message.answer(
            t("step4_text_style", lang),
            reply_markup=text_style_keyboard(lang),
            parse_mode=ParseMode.HTML,
        )
        return
    except Exception as e:
        logger.exception("generation failed: %s", e, extra={"user_id": uid, "event": "error"})
        await status_msg.edit_text(t("err_generic", lang, err=e))
        await state.set_state(CardStates.text_style)
        await cq.message.answer(
            t("step4_text_style", lang),
            reply_markup=text_style_keyboard(lang),
            parse_mode=ParseMode.HTML,
        )
        return

    photo = BufferedInputFile(image_bytes, filename="card.png")
    try:
        await status_msg.delete()
    except Exception:
        pass
    sent = await cq.message.answer_photo(
        photo=photo,
        caption=caption_html,
        parse_mode=ParseMode.HTML,
        reply_markup=after_card_keyboard(lang),
    )
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
    )
    get_storage().save_last_card(uid, ctx)
    if not is_admin_user(uid, settings):
        get_storage().increment_generation(uid)
    await state.set_state(CardStates.choosing_occasion)
    logger.info("generation_ok", extra={"user_id": uid, "event": "generation_ok"})


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
    lang = coalesce_lang(ctx.lang if ctx else None)
    if not ctx or not ctx.photo_file_id or not ctx.caption_html:
        await cq.answer(t("no_saved_card", lang), show_alert=True)
        return
    await cq.answer()
    await cq.message.answer_photo(
        photo=ctx.photo_file_id,
        caption=ctx.caption_html,
        parse_mode=ParseMode.HTML,
        reply_markup=after_card_keyboard(coalesce_lang(ctx.lang)),
    )
    logger.info("regen_repeat", extra={"user_id": uid, "event": "regen_repeat"})


@router.callback_query(F.data == "regen_text")
async def regen_text(cq: CallbackQuery) -> None:
    if not cq.from_user or not cq.message:
        return
    uid = cq.from_user.id
    settings = get_settings()
    ctx = get_storage().get_last_card(uid)
    lang = coalesce_lang(ctx.lang if ctx else None)
    if not ctx:
        await cq.answer(t("no_saved_card", lang), show_alert=True)
        return
    if not can_consume_generation(uid, settings):
        await cq.answer(t("rate_limited", lang, limit=settings.DAILY_GENERATION_LIMIT), show_alert=True)
        return
    if not text_provider_configured(settings):
        await cq.answer(
            t(text_provider_preflight_message_key(settings), lang),
            show_alert=True,
        )
        return
    photo_id = _photo_file_fallback(cq, ctx)
    if not photo_id:
        await cq.answer("No image reference", show_alert=True)
        return
    await cq.answer(t("generating", lang))
    try:
        cap = await run_text_only(
            settings,
            occasion=ctx.occasion,
            holiday=ctx.holiday,
            text_style=ctx.text_style,
            lang=coalesce_lang(ctx.lang),
        )
    except (YandexGPTError, OpenAITextError, asyncio.TimeoutError) as e:
        logger.warning("regen_text failed: %s", e, extra={"user_id": uid, "event": "error"})
        await cq.message.answer(t("err_text", lang, err=e))
        return
    sent = await cq.message.answer_photo(
        photo=photo_id,
        caption=cap,
        parse_mode=ParseMode.HTML,
        reply_markup=after_card_keyboard(coalesce_lang(ctx.lang)),
    )
    ctx.caption_html = cap
    if sent.photo:
        ctx.photo_file_id = sent.photo[-1].file_id
    get_storage().save_last_card(uid, ctx)
    if not is_admin_user(uid, settings):
        get_storage().increment_generation(uid)
    logger.info("regen_text_ok", extra={"user_id": uid, "event": "regen_text"})


@router.callback_query(F.data == "regen_image")
async def regen_image(cq: CallbackQuery) -> None:
    if not cq.from_user or not cq.message:
        return
    uid = cq.from_user.id
    settings = get_settings()
    ctx = get_storage().get_last_card(uid)
    lang = coalesce_lang(ctx.lang if ctx else None)
    if not ctx:
        await cq.answer(t("no_saved_card", lang), show_alert=True)
        return
    if not can_consume_generation(uid, settings):
        await cq.answer(t("rate_limited", lang, limit=settings.DAILY_GENERATION_LIMIT), show_alert=True)
        return
    if not image_provider_configured(settings):
        await cq.answer(
            t(image_provider_preflight_message_key(settings), lang),
            show_alert=True,
        )
        return
    base = (ctx.image_prompt_en or "").strip()
    if not base:
        await cq.answer(t("no_saved_card", lang), show_alert=True)
        return
    new_prompt = f"{base}, {image_variation_suffix()}"
    await cq.answer(t("generating", lang))
    try:
        image_bytes, used = await run_image_only(settings, new_prompt or base)
    except (ProxiAPIError, OpenAIImageError) as e:
        logger.warning("regen_image failed: %s", e, extra={"user_id": uid, "event": "error"})
        await cq.message.answer(t("err_image", lang, err=e))
        return
    except asyncio.TimeoutError:
        await cq.message.answer(t("err_timeout", lang))
        return
    photo = BufferedInputFile(image_bytes, filename="card.png")
    cap = ctx.caption_html or ""
    sent = await cq.message.answer_photo(
        photo=photo,
        caption=cap,
        parse_mode=ParseMode.HTML,
        reply_markup=after_card_keyboard(coalesce_lang(ctx.lang)),
    )
    ctx.image_prompt_en = used
    if sent.photo:
        ctx.photo_file_id = sent.photo[-1].file_id
    get_storage().save_last_card(uid, ctx)
    if not is_admin_user(uid, settings):
        get_storage().increment_generation(uid)
    logger.info("regen_image_ok", extra={"user_id": uid, "event": "regen_image"})


# ----- Create another -----


@router.callback_query(F.data == "create_another")
async def on_create_another(cq: CallbackQuery, state: FSMContext) -> None:
    if not cq.from_user or not cq.message:
        return
    uid = cq.from_user.id
    storage = get_storage()
    lang_s = storage.get_user_lang(uid)
    lang = coalesce_lang(lang_s)
    alang: Lang = "en" if lang_s == "en" else "ru"
    await state.clear()
    await state.update_data(lang=alang)
    await state.set_state(CardStates.choosing_occasion)
    await _send_wizard_prompt(
        cq.message, state, t("choose_occasion", lang), occasion_keyboard(lang), prompt_kind="occasion"
    )
    await cq.answer()
    logger.info("create_another", extra={"user_id": uid, "event": "create_another"})


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


@router.message(StateFilter(None), F.text)
async def on_small_talk(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if raw.startswith("/"):
        return
    uid = message.from_user.id if message.from_user else 0
    lang = coalesce_lang(get_storage().get_user_lang(uid))
    await message.answer(
        t("small_talk_idle", lang),
        reply_markup=home_keyboard(lang),
        parse_mode=ParseMode.HTML,
    )


@router.callback_query()
async def on_stale_callback(cq: CallbackQuery, state: FSMContext) -> None:
    """Stale inline buttons from earlier wizard steps."""
    if not cq.from_user or not cq.data:
        return
    lang = coalesce_lang(get_storage().get_user_lang(cq.from_user.id))
    await _handle_stale_callback(cq, lang)
