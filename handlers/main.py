"""
Main bot handlers: language, FSM flow, generation, regen shortcuts, small talk.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional, cast

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import Settings, get_settings
from handlers.states import CardStates
from services.card_generation import run_card_generation, run_image_only, run_text_only
from services.proxi import ProxiAPIError
from services.speech_to_text import SpeechToTextError, transcribe_audio
from services.storage import LastCardContext, get_storage
from services.yandex_gpt import YandexGPTError, small_talk_reply
from utils.i18n import Lang, t
from utils.prompts import (
    IMAGE_STYLE_LABELS,
    OCCASION_LABELS,
    TEXT_STYLE_LABELS,
    image_variation_suffix,
)

logger = logging.getLogger(__name__)
router = Router()


def coalesce_lang(raw: Optional[str]) -> Lang:
    return "en" if raw == "en" else "ru"


def _lbl(pair: tuple[str, str], lang: Lang) -> str:
    return pair[1] if lang == "en" else pair[0]


def is_admin_user(uid: int, settings: Settings) -> bool:
    return uid in settings.admin_ids()


def can_consume_generation(uid: int, settings: Settings) -> bool:
    if is_admin_user(uid, settings):
        return True
    return get_storage().get_daily_count(uid) < settings.DAILY_GENERATION_LIMIT


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
    keys = list(IMAGE_STYLE_LABELS.keys())
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
    settings = get_settings()
    uid = message.from_user.id if message.from_user else 0
    storage = get_storage()
    lang_stored = storage.get_user_lang(uid)
    logger.info("start", extra={"user_id": uid, "event": "start"})
    if lang_stored in ("ru", "en"):
        await state.update_data(lang=lang_stored)
        await state.set_state(CardStates.choosing_occasion)
        lang = coalesce_lang(lang_stored)
        await message.answer(
            t("choose_occasion", lang) + "\n\n" + t("lang_hint", lang),
            reply_markup=occasion_keyboard(lang),
            parse_mode=ParseMode.HTML,
        )
        return
    await state.set_state(CardStates.choosing_language)
    await message.answer(t("start_intro", "ru"), reply_markup=language_keyboard())


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
        await message.answer(t("cancel_nothing", lang))
        logger.info("cmd_cancel_idle", extra={"user_id": uid, "event": "cmd_cancel"})
        return
    if lang_stored in ("ru", "en"):
        await state.update_data(lang=lang_stored)
        await state.set_state(CardStates.choosing_occasion)
        await message.answer(
            t("cancel_done", lang)
            + "\n\n"
            + t("choose_occasion", lang)
            + "\n\n"
            + t("lang_hint", lang),
            reply_markup=occasion_keyboard(lang),
            parse_mode=ParseMode.HTML,
        )
    else:
        await state.set_state(CardStates.choosing_language)
        await message.answer(
            t("cancel_done", "ru") + "\n\n" + t("start_intro", "ru"),
            reply_markup=language_keyboard(),
        )
    logger.info("cmd_cancel", extra={"user_id": uid, "event": "cmd_cancel"})


@router.callback_query(F.data.in_(("lang_ru", "lang_en")))
async def on_language_chosen(cq: CallbackQuery, state: FSMContext) -> None:
    if not cq.data or not cq.from_user or not cq.message:
        return
    uid = cq.from_user.id
    lang: Lang = "en" if cq.data == "lang_en" else "ru"
    get_storage().set_user_lang(uid, lang)
    await state.update_data(lang=lang)
    current = await state.get_state()
    await cq.answer(t("lang_saved_toast", lang))

    if current == CardStates.choosing_language.state:
        await state.set_state(CardStates.choosing_occasion)
        try:
            await cq.message.edit_text(
                t("choose_occasion", lang) + "\n\n" + t("lang_hint", lang),
                reply_markup=occasion_keyboard(lang),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            await cq.message.answer(
                t("choose_occasion", lang) + "\n\n" + t("lang_hint", lang),
                reply_markup=occasion_keyboard(lang),
                parse_mode=ParseMode.HTML,
            )
        return

    try:
        await cq.message.edit_text(t("lang_saved", lang), reply_markup=None)
    except Exception:
        await cq.message.answer(t("lang_saved", lang))


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
    await message.answer(t("use_occasion_buttons", lang), reply_markup=occasion_keyboard(lang))


@router.message(CardStates.choosing_occasion, F.voice)
async def on_occasion_need_buttons_voice(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    await message.answer(t("use_occasion_buttons", lang), reply_markup=occasion_keyboard(lang))


@router.callback_query(F.data.startswith("occasion_"), CardStates.choosing_occasion)
async def on_occasion(cq: CallbackQuery, state: FSMContext) -> None:
    if not cq.data or not cq.message:
        return
    lang = await _lang_from_state(state, cq.from_user.id)
    await state.update_data(occasion=cq.data)
    await state.set_state(CardStates.image_description)
    logger.debug(
        "occasion=%s",
        cq.data,
        extra={"user_id": cq.from_user.id, "event": "fsm"},
    )
    await cq.message.edit_text(t("step1_image", lang), parse_mode=ParseMode.HTML)
    await cq.answer()


# ----- Image description -----


@router.message(CardStates.image_description, F.text)
async def on_image_description(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    if not message.text or not message.text.strip():
        await message.answer(t("empty_image_desc", lang))
        return
    await state.update_data(image_description=message.text.strip())
    await state.set_state(CardStates.holiday)
    await message.answer(t("step2_holiday", lang), parse_mode=ParseMode.HTML)


@router.message(CardStates.image_description, F.voice)
async def on_image_description_voice(message: Message, state: FSMContext, bot: Bot) -> None:
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
        await message.answer(t("voice_empty", lang))
        return
    await state.update_data(image_description=text.strip())
    await state.set_state(CardStates.holiday)
    await message.answer(t("after_voice_holiday", lang), parse_mode=ParseMode.HTML)


@router.message(CardStates.image_description)
async def on_image_description_other(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    await message.answer(t("only_text_voice_step1", lang))


# ----- Holiday -----


@router.message(CardStates.holiday, F.text)
async def on_holiday(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    if not message.text or not message.text.strip():
        await message.answer(t("empty_holiday", lang))
        return
    await state.update_data(holiday=message.text.strip())
    await state.set_state(CardStates.image_style)
    await message.answer(
        t("step3_image_style", lang),
        reply_markup=image_style_keyboard(lang),
        parse_mode=ParseMode.HTML,
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
        await message.answer(t("voice_empty", lang))
        return
    await state.update_data(holiday=text.strip())
    await state.set_state(CardStates.image_style)
    await message.answer(
        t("after_voice_style", lang),
        reply_markup=image_style_keyboard(lang),
        parse_mode=ParseMode.HTML,
    )


@router.message(CardStates.holiday)
async def on_holiday_other(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = await _lang_from_state(state, uid)
    await message.answer(t("only_text_voice_step2", lang))


# ----- Image style -----


@router.callback_query(F.data.startswith("style_"), CardStates.image_style)
async def on_image_style(cq: CallbackQuery, state: FSMContext) -> None:
    if not cq.data or not cq.message or not cq.from_user:
        return
    lang = await _lang_from_state(state, cq.from_user.id)
    await state.update_data(image_style=cq.data)
    await state.set_state(CardStates.text_style)
    await cq.message.edit_text(
        t("step4_text_style", lang),
        reply_markup=text_style_keyboard(lang),
        parse_mode=ParseMode.HTML,
    )
    await cq.answer()


# ----- Text style -> generation -----


@router.callback_query(F.data.startswith("text_"), CardStates.text_style)
async def on_text_style(cq: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not cq.data or not cq.message or not cq.from_user:
        return
    uid = cq.from_user.id
    settings = get_settings()
    lang = await _lang_from_state(state, uid)

    if not settings.PROXI_API_KEY:
        await cq.answer(t("err_image", lang, err="Proxi API key missing"), show_alert=True)
        return
    if not settings.YANDEX_API_KEY or not settings.YANDEX_FOLDER_ID:
        await cq.answer(t("yandex_env_missing", lang), show_alert=True)
        return

    if not can_consume_generation(uid, settings):
        await cq.answer(t("rate_limited", lang, limit=settings.DAILY_GENERATION_LIMIT), show_alert=True)
        return

    await state.update_data(text_style=cq.data)
    await state.set_state(CardStates.generating)
    logger.info("generation_start", extra={"user_id": uid, "event": "generation_start"})
    await cq.message.edit_text(t("generating", lang), parse_mode=ParseMode.HTML)
    await cq.answer()

    data: dict[str, Any] = (await state.get_data()) or {}
    occasion = str(data.get("occasion", ""))
    image_description = str(data.get("image_description", ""))
    holiday = str(data.get("holiday", ""))
    image_style = str(data.get("image_style", "style_realistic"))
    text_style = str(data.get("text_style", "text_warm"))

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
    except ProxiAPIError as e:
        logger.exception("Proxi failed: %s", e, extra={"user_id": uid, "event": "error"})
        await cq.message.answer(t("err_image", lang, err=e))
        await state.set_state(CardStates.text_style)
        await cq.message.answer(
            t("step4_text_style", lang),
            reply_markup=text_style_keyboard(lang),
            parse_mode=ParseMode.HTML,
        )
        return
    except YandexGPTError as e:
        logger.exception("Yandex failed: %s", e, extra={"user_id": uid, "event": "error"})
        await cq.message.answer(t("err_text", lang, err=e))
        await state.set_state(CardStates.text_style)
        await cq.message.answer(
            t("step4_text_style", lang),
            reply_markup=text_style_keyboard(lang),
            parse_mode=ParseMode.HTML,
        )
        return
    except asyncio.TimeoutError:
        logger.warning("timeout", extra={"user_id": uid, "event": "error"})
        await cq.message.answer(t("err_timeout", lang))
        await state.set_state(CardStates.text_style)
        await cq.message.answer(
            t("step4_text_style", lang),
            reply_markup=text_style_keyboard(lang),
            parse_mode=ParseMode.HTML,
        )
        return
    except Exception as e:
        logger.exception("generation failed: %s", e, extra={"user_id": uid, "event": "error"})
        await cq.message.answer(t("err_generic", lang, err=e))
        await state.set_state(CardStates.text_style)
        await cq.message.answer(
            t("step4_text_style", lang),
            reply_markup=text_style_keyboard(lang),
            parse_mode=ParseMode.HTML,
        )
        return

    photo = BufferedInputFile(image_bytes, filename="card.png")
    try:
        await cq.message.delete()
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
    if not settings.YANDEX_API_KEY or not settings.YANDEX_FOLDER_ID:
        await cq.answer(t("yandex_env_missing", lang), show_alert=True)
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
    except (YandexGPTError, asyncio.TimeoutError) as e:
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
    if not settings.PROXI_API_KEY:
        await cq.answer("Proxi not configured", show_alert=True)
        return
    base = (ctx.image_prompt_en or "").strip()
    if not base:
        await cq.answer(t("no_saved_card", lang), show_alert=True)
        return
    new_prompt = f"{base}, {image_variation_suffix()}"
    await cq.answer(t("generating", lang))
    try:
        image_bytes, used = await run_image_only(settings, new_prompt or base)
    except ProxiAPIError as e:
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
    await cq.message.answer(
        t("choose_occasion", lang),
        reply_markup=occasion_keyboard(lang),
        parse_mode=ParseMode.HTML,
    )
    await cq.answer()
    logger.info("create_another", extra={"user_id": uid, "event": "create_another"})


# ----- Choosing language: typed «русский» / «english» or nudge -----


@router.message(CardStates.choosing_language, F.text)
async def on_lang_wait_text(message: Message, state: FSMContext) -> None:
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
        await message.answer(
            t("lang_saved", picked)
            + "\n\n"
            + t("choose_occasion", picked)
            + "\n\n"
            + t("lang_hint", picked),
            reply_markup=occasion_keyboard(picked),
            parse_mode=ParseMode.HTML,
        )
        logger.info("lang_text_pick", extra={"user_id": uid, "event": "lang_pick_text"})
        return
    lang = coalesce_lang(get_storage().get_user_lang(uid))
    await message.answer(t("pick_language", lang), reply_markup=language_keyboard())


@router.message(CardStates.choosing_language)
async def on_lang_wait_other(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = coalesce_lang(get_storage().get_user_lang(uid))
    await message.answer(t("pick_language", lang), reply_markup=language_keyboard())


# ----- Small talk -----


@router.message(F.text)
async def on_small_talk(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if raw.startswith("/"):
        return
    current = await state.get_state()
    # Только «свободный» чат без активного мастера; на choosing_occasion — отдельный handler
    allowed = {None}
    if current not in allowed:
        return
    uid = message.from_user.id if message.from_user else 0
    settings = get_settings()
    storage = get_storage()
    lang = coalesce_lang(storage.get_user_lang(uid))
    if not storage.is_small_talk_enabled():
        await message.answer(t("reminder_fallback", lang))
        return
    if not settings.YANDEX_API_KEY or not settings.YANDEX_FOLDER_ID:
        await message.answer(t("reminder_fallback", lang))
        return
    try:
        reply = await small_talk_reply(
            message.text or "",
            lang=lang,
            api_key=settings.YANDEX_API_KEY,
            folder_id=settings.YANDEX_FOLDER_ID,
            model_uri=settings.model_uri(),
            url=settings.YANDEX_COMPLETION_URL,
            timeout=30.0,
        )
        await message.answer(reply or t("reminder_fallback", lang))
    except (YandexGPTError, asyncio.TimeoutError) as e:
        logger.warning("small_talk failed: %s", e, extra={"user_id": uid, "event": "small_talk_fail"})
        await message.answer(t("reminder_fallback", lang))
