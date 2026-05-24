"""
Profile settings v1: summary screen, nested settings, onboarding, name flow.
"""
from __future__ import annotations

import logging
from typing import Optional, cast

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import Settings, get_settings
from handlers.filters import is_admin_user_id
from handlers.states import ProfileStates
from services.providers.stt_factory import SpeechToTextError, stt_configured, transcribe_audio
from services.storage import get_storage
from utils.i18n import Lang, t
from utils.profile_name_confirm import (
    CB_PROFILE_NAME_CHANGE,
    CB_PROFILE_NAME_OK,
    PENDING_PROFILE_NAME_CHAT_ID_KEY,
    PENDING_PROFILE_NAME_CONFIRM_MSG_ID_KEY,
    PENDING_PROFILE_NAME_KEY,
    PENDING_PROFILE_NAME_MODE_KEY,
    PENDING_PROFILE_NAME_SOURCE_MSG_ID_KEY,
    PROFILE_NAME_CONFIRM_CALLBACKS,
    NameConfirmMode,
    clear_pending_profile_name_payload,
    format_profile_name_confirm_prompt,
    pending_profile_name_payload,
    profile_name_confirm_keyboard,
    read_pending_profile_name_snapshot,
)
from utils.display_name import parse_display_name_input, validate_display_name
from utils.profile_preferences import (
    CB_PROFILE_ADDRESS,
    CB_PROFILE_BACK,
    CB_PROFILE_DEV_RESET,
    CB_PROFILE_HOME,
    CB_PROFILE_LANG,
    CB_PROFILE_LENGTH,
    CB_PROFILE_MAIN,
    CB_PROFILE_NAME,
    CB_PROFILE_NAME_CANCEL,
    CB_PROFILE_TONE,
    PROFILE_MENU_CALLBACKS,
    ProfilePreferences,
    is_profile_callback,
    parse_profile_set_callback,
)
from utils.profile_ui import (
    profile_address_keyboard,
    profile_language_keyboard,
    profile_length_keyboard,
    profile_main_keyboard,
    profile_main_text,
    profile_name_cancel_keyboard,
    profile_tone_keyboard,
)
from utils.voice_stt import voice_stt_user_message

logger = logging.getLogger(__name__)
router = Router()


def coalesce_lang(raw: Optional[str]) -> Lang:
    return "en" if raw == "en" else "ru"


def home_keyboard(lang: Lang) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("btn_create_card", lang), callback_data="action_create_card")],
            [
                InlineKeyboardButton(
                    text=t("btn_profile_settings", lang),
                    callback_data=CB_PROFILE_MAIN,
                ),
            ],
            [InlineKeyboardButton(text=t("btn_help_short", lang), callback_data="action_help")],
        ]
    )


async def _safe_delete_message(bot: Bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


async def _edit_inline_screen(
    cq: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    if not cq.message:
        return
    try:
        await cq.message.edit_text(
            text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )
    except TelegramBadRequest:
        await cq.message.answer(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


def _user_lang(uid: int) -> Lang:
    return coalesce_lang(get_storage().get_user_lang(uid))


def _telegram_first_name(message_or_cq: Message | CallbackQuery) -> Optional[str]:
    user = message_or_cq.from_user
    if user and user.first_name:
        return user.first_name
    return None


async def perform_dev_profile_reset(uid: int, state: FSMContext) -> Lang:
    get_storage().reset_user_profile_data(uid)
    await state.clear()
    return _user_lang(uid)


async def show_profile_main(
    target: Message | CallbackQuery,
    uid: int,
    *,
    ui_lang: Optional[Lang] = None,
) -> None:
    storage = get_storage()
    prefs = storage.get_profile_preferences(uid)
    lang = _user_lang(uid)
    display_lang = ui_lang or lang
    first = _telegram_first_name(target)
    text = profile_main_text(prefs, lang, ui_lang=display_lang, telegram_first_name=first)
    markup = profile_main_keyboard(display_lang, show_dev_reset=is_admin_user_id(uid))
    if isinstance(target, CallbackQuery):
        await _edit_inline_screen(target, text, markup)
    else:
        await target.answer(text, reply_markup=markup, parse_mode=ParseMode.HTML)


async def start_profile_onboarding(message: Message, state: FSMContext, lang: Lang) -> None:
    await state.set_state(ProfileStates.onboarding_name)
    await message.answer(
        t("onboarding_ask_name", lang),
        parse_mode=ParseMode.HTML,
    )


async def _finish_onboarding(message: Message, state: FSMContext, lang: Lang) -> None:
    await state.clear()
    await message.answer(
        t("onboarding_done", lang),
        reply_markup=home_keyboard(lang),
        parse_mode=ParseMode.HTML,
    )


def _apply_profile_set(uid: int, field: str, value: str) -> ProfilePreferences:
    storage = get_storage()
    kwargs: dict[str, str] = {}
    if field == "address":
        kwargs["address_style"] = value
    elif field == "tone":
        kwargs["text_tone"] = value
    elif field == "length":
        kwargs["text_length"] = value
    elif field == "lang":
        storage.set_user_lang(uid, value)
        return storage.get_profile_preferences(uid)
    return storage.update_profile_preference(uid, **kwargs)


def _name_confirm_mode(state_name: str | None) -> NameConfirmMode | None:
    if state_name == ProfileStates.onboarding_name.state:
        return "onboarding"
    if state_name == ProfileStates.editing_name.state:
        return "editing"
    return None


async def _cleanup_pending_name_confirmation(
    bot: Bot,
    state: FSMContext,
    *,
    delete_confirm: bool = True,
    delete_source: bool = True,
) -> dict[str, object]:
    data = await state.get_data()
    snapshot = read_pending_profile_name_snapshot(data)
    chat_id = snapshot.get(PENDING_PROFILE_NAME_CHAT_ID_KEY)
    if chat_id is not None:
        cid = int(chat_id)
        if delete_source:
            source_id = snapshot.get(PENDING_PROFILE_NAME_SOURCE_MSG_ID_KEY)
            if source_id is not None:
                await _safe_delete_message(bot, cid, int(source_id))
        if delete_confirm:
            confirm_id = snapshot.get(PENDING_PROFILE_NAME_CONFIRM_MSG_ID_KEY)
            if confirm_id is not None:
                await _safe_delete_message(bot, cid, int(confirm_id))
    await state.update_data(**clear_pending_profile_name_payload())
    return snapshot


async def _reprompt_name(message: Message, state: FSMContext, lang: Lang, mode: NameConfirmMode) -> None:
    target_state = (
        ProfileStates.onboarding_name if mode == "onboarding" else ProfileStates.editing_name
    )
    await state.set_state(target_state)
    kwargs: dict[str, object] = {"parse_mode": ParseMode.HTML}
    if mode == "editing":
        kwargs["reply_markup"] = profile_name_cancel_keyboard(lang)
    await message.answer(t("profile_ask_name", lang), **kwargs)


async def _offer_name_confirm(
    bot: Bot,
    message: Message,
    state: FSMContext,
    lang: Lang,
    name: str,
    mode: NameConfirmMode,
) -> None:
    data = await state.get_data()
    if data.get(PENDING_PROFILE_NAME_KEY):
        await _cleanup_pending_name_confirmation(bot, state)

    confirm_msg = await message.answer(
        format_profile_name_confirm_prompt(lang, name),
        reply_markup=profile_name_confirm_keyboard(lang),
        parse_mode=ParseMode.HTML,
    )
    await state.set_state(ProfileStates.confirming_name)
    await state.update_data(
        **pending_profile_name_payload(
            name,
            mode,
            chat_id=message.chat.id,
            source_message_id=message.message_id,
            confirm_message_id=confirm_msg.message_id,
        )
    )


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


async def _handle_name_input(
    bot: Bot,
    message: Message,
    state: FSMContext,
    lang: Lang,
    raw: str,
    mode: NameConfirmMode,
) -> None:
    name = parse_display_name_input(raw, lang)
    if not name:
        await message.answer(t("profile_name_invalid", lang), parse_mode=ParseMode.HTML)
        return
    await _offer_name_confirm(bot, message, state, lang, name, mode)


@router.callback_query(F.data == CB_PROFILE_MAIN)
async def on_profile_main(cq: CallbackQuery, state: FSMContext) -> None:
    if not cq.from_user or not cq.message:
        return
    await state.set_state(None)
    await show_profile_main(cq, cq.from_user.id)
    await cq.answer()


@router.callback_query(F.data == CB_PROFILE_HOME)
async def on_profile_home(cq: CallbackQuery, state: FSMContext) -> None:
    if not cq.from_user or not cq.message:
        return
    await state.clear()
    lang = _user_lang(cq.from_user.id)
    await _edit_inline_screen(cq, t("home_welcome", lang), home_keyboard(lang))
    await cq.answer()


@router.callback_query(F.data == CB_PROFILE_BACK)
async def on_profile_back(cq: CallbackQuery) -> None:
    if not cq.from_user or not cq.message:
        return
    await show_profile_main(cq, cq.from_user.id)
    await cq.answer()


@router.callback_query(F.data == CB_PROFILE_NAME)
async def on_profile_name_start(cq: CallbackQuery, state: FSMContext) -> None:
    if not cq.from_user or not cq.message:
        return
    lang = _user_lang(cq.from_user.id)
    await state.set_state(ProfileStates.editing_name)
    await cq.message.answer(
        t("profile_ask_name", lang),
        reply_markup=profile_name_cancel_keyboard(lang),
        parse_mode=ParseMode.HTML,
    )
    await cq.answer()


@router.callback_query(F.data == CB_PROFILE_NAME_CANCEL)
async def on_profile_name_cancel(cq: CallbackQuery, state: FSMContext) -> None:
    if not cq.from_user or not cq.message:
        return
    await state.clear()
    lang = _user_lang(cq.from_user.id)
    await cq.answer(t("profile_name_cancelled", lang))
    await show_profile_main(cq, cq.from_user.id)


@router.callback_query(F.data == CB_PROFILE_DEV_RESET)
async def on_profile_dev_reset(cq: CallbackQuery, state: FSMContext) -> None:
    if not cq.from_user or not cq.message:
        return
    uid = cq.from_user.id
    if not is_admin_user_id(uid):
        await cq.answer(t("dev_reset_denied", _user_lang(uid)), show_alert=True)
        return
    lang = await perform_dev_profile_reset(uid, state)
    await cq.message.answer(t("dev_reset_done", lang), parse_mode=ParseMode.HTML)
    await cq.answer()


@router.callback_query(F.data == CB_PROFILE_LANG)
async def on_profile_lang_screen(cq: CallbackQuery) -> None:
    if not cq.message:
        return
    lang = _user_lang(cq.from_user.id) if cq.from_user else "ru"
    await _edit_inline_screen(
        cq,
        t("profile_screen_lang", lang),
        profile_language_keyboard(lang),
    )
    await cq.answer()


@router.callback_query(F.data == CB_PROFILE_ADDRESS)
async def on_profile_address_screen(cq: CallbackQuery) -> None:
    if not cq.message:
        return
    lang = _user_lang(cq.from_user.id) if cq.from_user else "ru"
    await _edit_inline_screen(
        cq,
        t("profile_screen_address", lang),
        profile_address_keyboard(lang),
    )
    await cq.answer()


@router.callback_query(F.data == CB_PROFILE_TONE)
async def on_profile_tone_screen(cq: CallbackQuery) -> None:
    if not cq.message:
        return
    lang = _user_lang(cq.from_user.id) if cq.from_user else "ru"
    await _edit_inline_screen(
        cq,
        t("profile_screen_tone", lang),
        profile_tone_keyboard(lang),
    )
    await cq.answer()


@router.callback_query(F.data == CB_PROFILE_LENGTH)
async def on_profile_length_screen(cq: CallbackQuery) -> None:
    if not cq.message:
        return
    lang = _user_lang(cq.from_user.id) if cq.from_user else "ru"
    await _edit_inline_screen(
        cq,
        t("profile_screen_length", lang),
        profile_length_keyboard(lang),
    )
    await cq.answer()


@router.callback_query(F.data.startswith("profile:set:"))
async def on_profile_set(cq: CallbackQuery, state: FSMContext) -> None:
    if not cq.data or not cq.from_user or not cq.message:
        return
    parsed = parse_profile_set_callback(cq.data)
    if not parsed:
        await cq.answer()
        return
    field, value = parsed
    uid = cq.from_user.id
    storage = get_storage()

    if field == "lang" and value in ("ru", "en"):
        storage.set_user_lang(uid, value)
        await cq.answer(t("lang_saved_toast", cast(Lang, value)))
        await show_profile_main(cq, uid, ui_lang=cast(Lang, value))
        return

    _apply_profile_set(uid, field, value)
    await cq.answer()
    await show_profile_main(cq, uid)


@router.callback_query(F.data.in_(PROFILE_NAME_CONFIRM_CALLBACKS))
async def on_profile_name_confirm_action(cq: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not cq.data or not cq.message or not cq.from_user:
        return
    uid = cq.from_user.id
    lang = _user_lang(uid)
    current = await state.get_state()
    if current != ProfileStates.confirming_name.state:
        await cq.answer(t("stale_callback", lang), show_alert=True)
        return

    data = await state.get_data()
    name = data.get(PENDING_PROFILE_NAME_KEY)
    mode = data.get(PENDING_PROFILE_NAME_MODE_KEY)
    if not name or mode not in ("onboarding", "editing"):
        await cq.answer(t("stale_callback", lang), show_alert=True)
        return

    if cq.data == CB_PROFILE_NAME_CHANGE:
        await _cleanup_pending_name_confirmation(bot, state)
        await _reprompt_name(cq.message, state, lang, cast(NameConfirmMode, mode))
        await cq.answer()
        return

    if cq.data == CB_PROFILE_NAME_OK:
        validated = validate_display_name(str(name))
        if not validated:
            await cq.answer(t("stale_callback", lang), show_alert=True)
            return
        await _cleanup_pending_name_confirmation(
            bot, state, delete_confirm=False, delete_source=True
        )
        try:
            await cq.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        get_storage().update_profile_preference(uid, display_name=validated)
        if mode == "onboarding":
            await _finish_onboarding(cq.message, state, lang)
        else:
            await state.clear()
            await show_profile_main(cq, uid)
        await cq.answer()
        return


@router.message(ProfileStates.onboarding_name, F.text)
async def on_onboarding_name_text(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.from_user or not message.text:
        return
    lang = _user_lang(message.from_user.id)
    await _handle_name_input(bot, message, state, lang, message.text, "onboarding")


@router.message(ProfileStates.editing_name, F.text)
async def on_editing_name_text(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.from_user or not message.text:
        return
    lang = _user_lang(message.from_user.id)
    await _handle_name_input(bot, message, state, lang, message.text, "editing")


@router.message(
    StateFilter(ProfileStates.onboarding_name, ProfileStates.editing_name),
    F.voice,
)
async def on_name_voice(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.from_user:
        return
    uid = message.from_user.id
    lang = _user_lang(uid)
    current = await state.get_state()
    mode = _name_confirm_mode(current)
    if not mode:
        return

    settings = get_settings()
    if not stt_configured(settings):
        await message.answer(t("voice_unavailable", lang))
        return

    recognizing = await message.answer(t("voice_recognizing", lang))
    try:
        text = await _transcribe_voice_message(bot, message, settings, lang)
    except SpeechToTextError as exc:
        await _safe_delete_message(bot, recognizing.chat.id, recognizing.message_id)
        await message.answer(voice_stt_user_message(lang, exc))
        return

    await _safe_delete_message(bot, recognizing.chat.id, recognizing.message_id)
    if not text or not text.strip():
        await message.answer(t("profile_name_invalid", lang), parse_mode=ParseMode.HTML)
        return
    await _handle_name_input(bot, message, state, lang, text.strip(), mode)


@router.message(ProfileStates.confirming_name, F.text)
async def on_confirming_name_text(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.from_user or not message.text:
        return
    lang = _user_lang(message.from_user.id)
    data = await state.get_data()
    mode = data.get(PENDING_PROFILE_NAME_MODE_KEY)
    if mode not in ("onboarding", "editing"):
        return
    await _cleanup_pending_name_confirmation(bot, state)
    await _handle_name_input(bot, message, state, lang, message.text, cast(NameConfirmMode, mode))


@router.message(ProfileStates.confirming_name, F.voice)
async def on_confirming_name_voice(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.from_user:
        return
    lang = _user_lang(message.from_user.id)
    data = await state.get_data()
    mode = data.get(PENDING_PROFILE_NAME_MODE_KEY)
    if mode not in ("onboarding", "editing"):
        return
    await _cleanup_pending_name_confirmation(bot, state)
    await state.set_state(
        ProfileStates.onboarding_name if mode == "onboarding" else ProfileStates.editing_name
    )
    await on_name_voice(message, state, bot)


@router.message(StateFilter(ProfileStates.onboarding_name, ProfileStates.editing_name))
async def on_name_non_text_voice(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = _user_lang(uid)
    await message.answer(t("profile_name_text_or_voice", lang), parse_mode=ParseMode.HTML)


@router.callback_query(F.data == "change_lang")
async def on_change_lang_redirect(cq: CallbackQuery) -> None:
    """Legacy entry points (e.g. after card) open profile language screen."""
    if not cq.message:
        return
    lang = _user_lang(cq.from_user.id) if cq.from_user else "ru"
    await _edit_inline_screen(
        cq,
        t("profile_screen_lang", lang),
        profile_language_keyboard(lang),
    )
    await cq.answer()


@router.callback_query(F.data.func(lambda d: bool(d and is_profile_callback(d))))
async def on_unknown_profile_callback(cq: CallbackQuery) -> None:
    if not cq.data or cq.data in PROFILE_MENU_CALLBACKS or cq.data.startswith("profile:set:"):
        return
    if cq.data in PROFILE_NAME_CONFIRM_CALLBACKS:
        return
    if not cq.from_user:
        return
    lang = _user_lang(cq.from_user.id)
    await cq.answer(t("stale_callback", lang), show_alert=True)
