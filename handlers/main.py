"""
Main bot handlers: /start, occasion choice, steps, generation, create another.
"""
import asyncio
import logging
from typing import Any, Optional

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import get_settings, get_gigachat_credentials
from handlers.states import CardStates
from services.gigachat import GigaChatError, generate_greeting_text, small_talk_reply
from services.proxi import ProxiAPIError, generate_image
from utils.prompts import (
    OCCASION_LABELS,
    IMAGE_STYLE_LABELS,
    TEXT_STYLE_LABELS,
    build_image_prompt,
    build_text_system_prompt,
    build_text_user_prompt,
)
from utils.translate import translate_holiday_to_english, translate_prompt_to_english

logger = logging.getLogger(__name__)
router = Router()

# ----- Keyboards -----


def occasion_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=OCCASION_LABELS["occasion_clients"], callback_data="occasion_clients")],
        [InlineKeyboardButton(text=OCCASION_LABELS["occasion_colleagues"], callback_data="occasion_colleagues")],
        [InlineKeyboardButton(text=OCCASION_LABELS["occasion_loved"], callback_data="occasion_loved")],
    ])


def image_style_keyboard() -> InlineKeyboardMarkup:
    row1 = [
        InlineKeyboardButton(text=IMAGE_STYLE_LABELS["style_realistic"], callback_data="style_realistic"),
        InlineKeyboardButton(text=IMAGE_STYLE_LABELS["style_cartoon"], callback_data="style_cartoon"),
    ]
    row2 = [
        InlineKeyboardButton(text=IMAGE_STYLE_LABELS["style_humor"], callback_data="style_humor"),
        InlineKeyboardButton(text=IMAGE_STYLE_LABELS["style_fantasy"], callback_data="style_fantasy"),
    ]
    row3 = [
        InlineKeyboardButton(text=IMAGE_STYLE_LABELS["style_minimal"], callback_data="style_minimal"),
        InlineKeyboardButton(text=IMAGE_STYLE_LABELS["style_vintage"], callback_data="style_vintage"),
    ]
    row4 = [
        InlineKeyboardButton(text=IMAGE_STYLE_LABELS["style_watercolor"], callback_data="style_watercolor"),
        InlineKeyboardButton(text=IMAGE_STYLE_LABELS["style_3d"], callback_data="style_3d"),
    ]
    row5 = [InlineKeyboardButton(text=IMAGE_STYLE_LABELS["style_botanical"], callback_data="style_botanical")]
    return InlineKeyboardMarkup(inline_keyboard=[row1, row2, row3, row4, row5])


def text_style_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=TEXT_STYLE_LABELS["text_business"], callback_data="text_business"),
            InlineKeyboardButton(text=TEXT_STYLE_LABELS["text_warm"], callback_data="text_warm"),
        ],
        [
            InlineKeyboardButton(text=TEXT_STYLE_LABELS["text_poetry"], callback_data="text_poetry"),
            InlineKeyboardButton(text=TEXT_STYLE_LABELS["text_humor"], callback_data="text_humor"),
        ],
    ])


def create_another_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Создать ещё одну", callback_data="create_another")],
    ])


# ----- /start -----


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(CardStates.choosing_occasion)
    logger.info("User %s started bot", message.from_user.id if message.from_user else "?")
    await message.answer(
        "🌷 Привет! Я бот весеннего настроения. Помогу создать открытку.\n\nВыберите повод:",
        reply_markup=occasion_keyboard(),
    )


# ----- Occasion (callback) -----


@router.callback_query(F.data.startswith("occasion_"), CardStates.choosing_occasion)
async def on_occasion(cq: CallbackQuery, state: FSMContext) -> None:
    if not cq.data:
        return
    await state.update_data(occasion=cq.data)
    await state.set_state(CardStates.image_description)
    logger.debug("User %s chose occasion=%s", cq.from_user.id if cq.from_user else "?", cq.data)
    await cq.message.edit_text(
        "1) Опишите, что должно быть на картинке (или напишите «придумай сам», я придумаю сам)"
    )
    await cq.answer()


# ----- Image description (text) -----


@router.message(CardStates.image_description)
async def on_image_description(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Пожалуйста, введите текстом, что должно быть на картинке (или напишите «придумай сам»).")
        return
    await state.update_data(image_description=message.text)
    await state.set_state(CardStates.holiday)
    logger.debug("User %s set image_description (len=%d)", message.from_user.id if message.from_user else "?", len(message.text or ""))
    await message.answer("2) Какой праздник/повод? (например: 8 Марта, 1 Мая, День рождения компании, «Просто так (начало весны)»)")


# ----- Holiday (text) -----


@router.message(CardStates.holiday)
async def on_holiday(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Пожалуйста, введите праздник или повод текстом.")
        return
    await state.update_data(holiday=message.text)
    await state.set_state(CardStates.image_style)
    logger.debug("User %s set holiday=%s", message.from_user.id if message.from_user else "?", (message.text or "")[:50])
    await message.answer("3) Выберите стиль изображения:", reply_markup=image_style_keyboard())


# ----- Image style (callback) -----


@router.callback_query(F.data.startswith("style_"), CardStates.image_style)
async def on_image_style(cq: CallbackQuery, state: FSMContext) -> None:
    if not cq.data:
        return
    await state.update_data(image_style=cq.data)
    await state.set_state(CardStates.text_style)
    logger.debug("User %s chose image_style=%s", cq.from_user.id if cq.from_user else "?", cq.data)
    await cq.message.edit_text("4) Выберите стиль текста:", reply_markup=text_style_keyboard())
    await cq.answer()


# ----- Text style (callback) -> run generation -----


@router.callback_query(F.data.startswith("text_"), CardStates.text_style)
async def on_text_style(cq: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not cq.data:
        return
    await state.update_data(text_style=cq.data)
    await state.set_state(CardStates.generating)
    logger.info("User %s started generation (text_style=%s)", cq.from_user.id if cq.from_user else "?", cq.data)
    await cq.message.edit_text("Генерирую открытку…")
    await cq.answer()

    data: dict[str, Any] = (await state.get_data()) or {}
    occasion = data.get("occasion", "")
    image_description = data.get("image_description", "")
    holiday = data.get("holiday", "")
    image_style = data.get("image_style", "style_realistic")
    text_style = data.get("text_style", "text_warm")

    settings = get_settings()

    # English prompt for image (translate description and holiday for ProxiAPI)
    desc_en: Optional[str] = None
    if image_description and image_description.strip().lower() not in ("придумай сам", "придумай сама"):
        desc_en = translate_prompt_to_english(image_description) or image_description
    holiday_en = translate_holiday_to_english(holiday) if holiday else None
    image_prompt = build_image_prompt(occasion, image_style, desc_en, holiday_en or holiday)

    system_prompt = build_text_system_prompt(occasion, text_style)
    user_prompt = build_text_user_prompt(holiday, occasion)

    async def run_image() -> bytes:
        return await generate_image(
            image_prompt,
            api_key=settings.PROXI_API_KEY,
            base_url=settings.PROXI_BASE_URL,
            timeout=120.0,
        )

    async def run_text() -> str:
        return await generate_greeting_text(
            system_prompt,
            user_prompt,
            credentials=get_gigachat_credentials(settings),
            scope=settings.GIGACHAT_SCOPE,
            api_url=settings.GIGACHAT_API_URL,
            auth_url=settings.GIGACHAT_AUTH_URL,
            timeout=60.0,
        )

    try:
        logger.info("Running parallel generation (image + text)")
        image_bytes, greeting_text = await asyncio.gather(run_image(), run_text())
        logger.info("Generation done: image=%d bytes, text=%d chars", len(image_bytes), len(greeting_text))
    except ProxiAPIError as e:
        logger.exception("ProxiAPI failed: %s", e)
        await cq.message.answer(f"Не удалось сгенерировать изображение. Ошибка: {e}")
        await state.set_state(CardStates.text_style)
        await cq.message.edit_text("4) Выберите стиль текста:", reply_markup=text_style_keyboard())
        return
    except GigaChatError as e:
        logger.exception("GigaChat failed: %s", e)
        await cq.message.answer(f"Не удалось сгенерировать текст. Ошибка: {e}")
        await state.set_state(CardStates.text_style)
        await cq.message.edit_text("4) Выберите стиль текста:", reply_markup=text_style_keyboard())
        return
    except asyncio.TimeoutError:
        logger.warning("Generation timeout for user %s", cq.from_user.id if cq.from_user else "?")
        await cq.message.answer("Превышено время ожидания. Попробуйте позже.")
        await state.set_state(CardStates.text_style)
        await cq.message.edit_text("4) Выберите стиль текста:", reply_markup=text_style_keyboard())
        return
    except Exception as e:
        logger.exception("Generation failed: %s", e)
        await cq.message.answer(f"Произошла ошибка: {e}")
        await state.set_state(CardStates.text_style)
        await cq.message.edit_text("4) Выберите стиль текста:", reply_markup=text_style_keyboard())
        return

    photo = BufferedInputFile(image_bytes, filename="card.png")
    await cq.message.delete()
    await cq.message.answer_photo(
        photo=photo,
        caption=greeting_text,
        reply_markup=create_another_keyboard(),
    )
    await state.set_state(CardStates.choosing_occasion)
    logger.info("Card sent to user %s", cq.from_user.id if cq.from_user else "?")


# ----- Create another (callback) -> back to occasion -----


@router.callback_query(F.data == "create_another")
async def on_create_another(cq: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(CardStates.choosing_occasion)
    logger.debug("User %s requested create another", cq.from_user.id if cq.from_user else "?")
    await cq.message.answer(
        "Выберите повод:",
        reply_markup=occasion_keyboard(),
    )
    await cq.answer()


# ----- Small talk (registered last: only when no FSM step expects this text) -----

REMINDER_FALLBACK = (
    "Привет! Я бот весеннего настроения — помогаю создавать поздравительные открытки. "
    "Отправь /start, чтобы создать открытку с картинкой и текстом."
)


@router.message(F.text)
async def on_small_talk(message: Message, state: FSMContext) -> None:
    """
    Reply to casual messages (greetings, questions) and remind about /start.
    Runs only when no FSM handler took the message (image_description and holiday handle their states first).
    """
    current = await state.get_state()
    if current == CardStates.image_description.state or current == CardStates.holiday.state:
        return  # Let the FSM handlers process (they are registered with state filter and run first)
    settings = get_settings()
    creds = get_gigachat_credentials(settings)
    if not creds:
        await message.answer(REMINDER_FALLBACK)
        return
    try:
        reply = await small_talk_reply(
            message.text,
            credentials=creds,
            scope=settings.GIGACHAT_SCOPE,
            api_url=settings.GIGACHAT_API_URL,
            auth_url=settings.GIGACHAT_AUTH_URL,
            timeout=30.0,
        )
        await message.answer(reply or REMINDER_FALLBACK)
    except (GigaChatError, asyncio.TimeoutError) as e:
        logger.warning("Small talk GigaChat failed: %s", e)
        await message.answer(REMINDER_FALLBACK)
