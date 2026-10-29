"""
Guided creation, both modes on one creative brief.

* "Choose from options": concept -> mood -> style -> inscription -> optional preferences -> confirmation.
* "My idea": one free-form message is read into the brief; only what is genuinely missing is asked.

Both end on the same confirmation screen, where any field can be edited without starting over. Image
generation happens in exactly one place, ``on_generate``, behind the explicit "Создать" press; everything
before it may use the text model (reading a description, proposing an inscription) but never the image
provider. Private access is enforced upstream by ``AccessMiddleware``, which gates every update before it
reaches any router, this one included.

All user-facing text is in ``utils.creation_ui`` (Russian). The router is included ahead of ``main_router``
so its state-bound handlers run before main's catch-alls.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional, Union

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message

from config import get_settings
from handlers import main as bot_main
from handlers.states import CreationStates as S
from services.brief_ai import (
    BriefAIError,
    apply_extraction,
    extract_brief_fields,
    suggest_inscription,
)
from services.card_generation import run_brief_generation
from services.card_render import check_inscription
from services.providers.openai_image import OpenAIImageError
from services.providers.openai_text import OpenAITextError
from services.providers.stt_factory import SpeechToTextError, stt_configured
from services.proxi import ProxiAPIError
from services.storage import LastCardContext, get_storage
from services.yandex_gpt import YandexGPTError
from utils import creation_ui as ui
from utils.brief_text import asks_for_no_text
from utils.card_lock import card_lock
from utils.creative_brief import (
    CAPTION_AI,
    CAPTION_NONE,
    CAPTION_USER,
    FLOW_FREE,
    FLOW_GUIDED,
    FOLLOW_UP_CONCEPT,
    FOLLOW_UP_INSCRIPTION,
    INSCRIPTION_AI,
    MAX_AI_SUGGESTIONS,
    MAX_RESTRICTIONS,
    MOOD_BY_KEY,
    PURPOSE_BY_KEY,
    PURPOSE_PRESETS,
    RESTRICTION_MAX_LEN,
    SOURCE_AI_APPROVED,
    SOURCE_USER,
    CreativeBrief,
    creative_context,
    first_problem,
    inscription_check,
    inscription_to_draw,
    next_follow_up,
    normalize_inscription,
    resolve_caption_mode,
    text_style_for,
)
from utils.flow_logging import log_generation_prompt_context
from utils.generation_limit import should_increment_daily_count
from utils.i18n import t
from utils.main_menu import main_menu_action_for_text
from utils.prompts import IMAGE_STYLE_LABELS
from utils.wizard_input import is_small_talk_text

logger = logging.getLogger(__name__)
router = Router(name="creation")

BRIEF_KEY = "brief"
AFTER_KEY = "after"  # where a finished field goes next: step | prefs | confirm | followup
FIELD_KEY = "input_field"
OPTIONAL_ASKED_KEY = "optional_asked"
QUESTION_KEY = "pending_question"
CLARIFY_KEY = "clarify_kind"
PANEL_CHAT_KEY = "panel_chat_id"
PANEL_MSG_KEY = "panel_msg_id"
VOICE_KEY = "pending_voice"

AFTER_STEP = "step"
AFTER_PREFS = "prefs"
AFTER_CONFIRM = "confirm"
AFTER_FOLLOWUP = "followup"

GUIDED_ORDER = (S.concept, S.mood, S.style, S.inscription, S.preferences)
TEXT_STATES = (S.concept, S.idea, S.clarifying, S.awaiting_text)
BUTTON_STATES = (S.choosing_mode, S.mood, S.style, S.inscription, S.preferences, S.caption,
                 S.reviewing_suggestion, S.confirming)
CANCELLABLE_STATES = TEXT_STATES + BUTTON_STATES

IDEA_MAX_CHARS = 2000

Target = Union[Message, CallbackQuery]


# ---- plumbing ---------------------------------------------------------------------------------


def _is_plain_input(text: Optional[str]) -> bool:
    """Typed input as opposed to a command or a main-menu button, which main_router handles."""
    stripped = (text or "").strip()
    return bool(stripped) and not stripped.startswith("/") and main_menu_action_for_text(stripped) is None


def _anchor(target: Target) -> Message:
    return target if isinstance(target, Message) else target.message  # type: ignore[return-value]


def _load(data: dict[str, Any]) -> CreativeBrief:
    return CreativeBrief.from_dict(data.get(BRIEF_KEY))


async def _brief(state: FSMContext) -> CreativeBrief:
    return _load(await state.get_data())


async def _save(state: FSMContext, brief: CreativeBrief, **extra: Any) -> None:
    await state.update_data(**{BRIEF_KEY: brief.to_dict()}, **extra)


async def _remember_panel(state: FSMContext, message: Message) -> None:
    await state.update_data(**{PANEL_CHAT_KEY: message.chat.id, PANEL_MSG_KEY: message.message_id})


async def _retire_panel(bot: Bot, state: FSMContext) -> None:
    """Take the buttons off the previous screen so only the newest one is live."""
    data = await state.get_data()
    chat_id, msg_id = data.get(PANEL_CHAT_KEY), data.get(PANEL_MSG_KEY)
    if chat_id is None or msg_id is None:
        return
    try:
        await bot.edit_message_reply_markup(chat_id=int(chat_id), message_id=int(msg_id), reply_markup=None)
    except Exception:  # already gone or unchanged: nothing to retire
        pass


async def _present(
    target: Target,
    state: FSMContext,
    text: str,
    markup: Optional[InlineKeyboardMarkup],
) -> None:
    """
    Show a screen. A button press edits its own message in place; typed input gets a fresh message and the
    previous screen loses its buttons.
    """
    if isinstance(target, CallbackQuery):
        message = target.message
        if isinstance(message, Message):
            try:
                await message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
                await _remember_panel(state, message)
                return
            except TelegramBadRequest as exc:
                if "message is not modified" in str(exc).lower():
                    return
            except Exception:
                pass
            sent = await message.answer(text, reply_markup=markup, parse_mode=ParseMode.HTML)
        else:
            sent = await target.bot.send_message(  # type: ignore[union-attr]
                target.from_user.id, text, reply_markup=markup, parse_mode=ParseMode.HTML
            )
    else:
        await _retire_panel(target.bot, state)  # type: ignore[arg-type]
        sent = await target.answer(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    await _remember_panel(state, sent)


async def _typing(target: Target) -> None:
    message = _anchor(target)
    try:
        await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)  # type: ignore[union-attr]
    except Exception:
        pass


# ---- screens -----------------------------------------------------------------------------------


async def _step_text(state: FSMContext, prompt: str) -> str:
    """A guided step's prompt; without the step counter when it is being edited from the confirmation."""
    editing = (await state.get_data()).get(AFTER_KEY) == AFTER_CONFIRM
    return ui.editing_title(prompt) if editing else prompt


async def screen_mode(target: Target, state: FSMContext) -> None:
    await state.set_state(S.choosing_mode)
    await _present(target, state, ui.MODE_PROMPT, ui.mode_keyboard())


async def screen_concept(target: Target, state: FSMContext) -> None:
    await state.set_state(S.concept)
    await _present(target, state, ui.CONCEPT_PROMPT, ui.concept_keyboard())


async def screen_mood(target: Target, state: FSMContext) -> None:
    await state.set_state(S.mood)
    await _present(target, state, await _step_text(state, ui.MOOD_PROMPT), ui.mood_keyboard())


async def screen_style(target: Target, state: FSMContext) -> None:
    await state.set_state(S.style)
    await _present(target, state, await _step_text(state, ui.STYLE_PROMPT), ui.style_keyboard())


async def screen_inscription(target: Target, state: FSMContext, note: str = "") -> None:
    await state.set_state(S.inscription)
    text = (note + "\n\n" if note else "") + await _step_text(state, ui.INSCRIPTION_PROMPT)
    await _present(target, state, text, ui.inscription_keyboard())


async def screen_preferences(target: Target, state: FSMContext) -> None:
    await state.set_state(S.preferences)
    brief = await _brief(state)
    await _present(target, state, ui.render_preferences(brief), ui.preferences_keyboard(brief))


async def screen_caption(target: Target, state: FSMContext) -> None:
    await state.set_state(S.caption)
    await _present(target, state, ui.CAPTION_PROMPT, ui.caption_keyboard())


async def screen_idea(target: Target, state: FSMContext) -> None:
    await state.set_state(S.idea)
    await state.update_data(**{AFTER_KEY: AFTER_FOLLOWUP})
    await _present(target, state, ui.IDEA_PROMPT, ui.text_input_keyboard())


async def screen_clarify(target: Target, state: FSMContext, kind: str, question: str = "") -> None:
    await state.set_state(S.clarifying)
    await state.update_data(**{CLARIFY_KEY: kind, AFTER_KEY: AFTER_FOLLOWUP})
    if kind == FOLLOW_UP_INSCRIPTION:
        await _present(target, state, ui.INSCRIPTION_QUESTION, ui.inscription_question_keyboard())
    else:
        text = ui.esc(question) if question else ui.CONCEPT_QUESTION_DEFAULT
        await _present(target, state, f"💡 {text}", ui.text_input_keyboard())


async def screen_suggestion(target: Target, state: FSMContext) -> None:
    await state.set_state(S.reviewing_suggestion)
    brief = await _brief(state)
    await _present(
        target,
        state,
        ui.SUGGESTION_SCREEN.format(text=ui.esc(brief.inscription_suggestion)),
        ui.suggestion_keyboard(),
    )


async def screen_confirm(target: Target, state: FSMContext) -> None:
    await state.set_state(S.confirming)
    await state.update_data(**{AFTER_KEY: AFTER_CONFIRM})
    brief = await _brief(state)
    await _present(target, state, ui.render_summary(brief), ui.confirm_keyboard())


def _clearable_value(brief: CreativeBrief, field: str) -> bool:
    return bool(
        {
            ui.FIELD_OCCASION: brief.occasion,
            ui.FIELD_RECIPIENT: brief.recipient,
            ui.FIELD_RESTRICTIONS: brief.restrictions or (brief.source_requests and not brief.restrictions_edited),
            ui.FIELD_SIGNATURE: brief.signature,
        }.get(field)
    )


async def screen_input(target: Target, state: FSMContext, field: str, *, after: Optional[str] = None) -> None:
    """Ask for typed text for one field. ``after`` is where the answer goes next (kept when omitted)."""
    await state.set_state(S.awaiting_text)
    extra: dict[str, Any] = {FIELD_KEY: field}
    if after is not None:
        extra[AFTER_KEY] = after
    await state.update_data(**extra)
    brief = await _brief(state)
    prompt = ui.PROMPTS_BY_FIELD[field]
    if field == ui.FIELD_RESTRICTIONS and brief.restrictions:
        prompt += "\n\nСейчас: " + "; ".join(ui.esc(r) for r in brief.restrictions)
    clearable = field in ui.CLEARABLE_FIELDS and _clearable_value(brief, field)
    await _present(target, state, prompt, ui.text_input_keyboard(clearable=clearable))


async def _show_current(target: Target, state: FSMContext) -> None:
    """Re-show whatever screen the user is on (used when they type where buttons are expected)."""
    current = await state.get_state()
    data = await state.get_data()
    if current == S.concept.state:
        await screen_concept(target, state)
    elif current == S.mood.state:
        await screen_mood(target, state)
    elif current == S.style.state:
        await screen_style(target, state)
    elif current == S.inscription.state:
        await screen_inscription(target, state)
    elif current == S.preferences.state:
        await screen_preferences(target, state)
    elif current == S.caption.state:
        await screen_caption(target, state)
    elif current == S.idea.state:
        await screen_idea(target, state)
    elif current == S.clarifying.state:
        await screen_clarify(target, state, data.get(CLARIFY_KEY, FOLLOW_UP_CONCEPT), data.get(QUESTION_KEY, ""))
    elif current == S.awaiting_text.state:
        await screen_input(target, state, data.get(FIELD_KEY, ui.FIELD_CONCEPT))
    elif current == S.reviewing_suggestion.state:
        await screen_suggestion(target, state)
    elif current == S.confirming.state:
        await screen_confirm(target, state)
    else:
        await screen_mode(target, state)


# ---- navigation --------------------------------------------------------------------------------


async def _advance(target: Target, state: FSMContext, step: Any) -> None:
    """A field is done: go where the flow that asked for it wants to go next."""
    after = (await state.get_data()).get(AFTER_KEY, AFTER_STEP)
    if after == AFTER_CONFIRM:
        await screen_confirm(target, state)
    elif after == AFTER_PREFS:
        await screen_preferences(target, state)
    elif after == AFTER_FOLLOWUP:
        await _follow_up_or_confirm(target, state)
    else:
        index = GUIDED_ORDER.index(step)
        nxt = GUIDED_ORDER[index + 1]
        await {
            S.mood: screen_mood,
            S.style: screen_style,
            S.inscription: screen_inscription,
            S.preferences: screen_preferences,
        }[nxt](target, state)


async def _follow_up_or_confirm(target: Target, state: FSMContext) -> None:
    """Free-form mode: resolve a pending AI inscription, ask the one thing still worth asking, or confirm."""
    brief = await _brief(state)
    data = await state.get_data()
    if brief.inscription_mode == INSCRIPTION_AI:
        await _start_suggestion(target, state)
        return
    asked = int(data.get(OPTIONAL_ASKED_KEY, 0))
    kind = next_follow_up(brief, optional_asked=asked)
    if kind == FOLLOW_UP_CONCEPT:
        await screen_clarify(target, state, kind, data.get(QUESTION_KEY, ""))
    elif kind == FOLLOW_UP_INSCRIPTION:
        await state.update_data(**{OPTIONAL_ASKED_KEY: asked + 1})
        await screen_clarify(target, state, kind)
    else:
        await screen_confirm(target, state)


async def _go_back(target: Target, state: FSMContext) -> None:
    current = await state.get_state()
    data = await state.get_data()
    after = data.get(AFTER_KEY, AFTER_STEP)
    if current == S.concept.state or current == S.idea.state:
        await screen_mode(target, state)
    elif current == S.clarifying.state:
        await screen_idea(target, state)
    elif current == S.preferences.state:
        await screen_inscription(target, state)
    elif current in (S.mood.state, S.style.state, S.inscription.state):
        if after == AFTER_CONFIRM:
            await screen_confirm(target, state)
        else:
            previous = {S.mood.state: screen_concept, S.style.state: screen_mood, S.inscription.state: screen_style}
            await previous[current](target, state)
    elif current == S.caption.state:
        await (screen_preferences if after == AFTER_PREFS else screen_confirm)(target, state)
    elif current == S.reviewing_suggestion.state:
        brief = await _brief(state)
        brief.clear_inscription()
        await _save(state, brief)
        if after == AFTER_FOLLOWUP:
            await screen_clarify(target, state, FOLLOW_UP_INSCRIPTION)
        elif after == AFTER_CONFIRM:
            await screen_confirm(target, state)
        else:
            await screen_inscription(target, state)
    elif current == S.awaiting_text.state:
        field = data.get(FIELD_KEY)
        if after == AFTER_CONFIRM:
            await screen_confirm(target, state)
        elif after == AFTER_PREFS:
            await screen_preferences(target, state)
        elif after == AFTER_FOLLOWUP:
            await screen_clarify(target, state, FOLLOW_UP_INSCRIPTION)
        else:
            step_screen = {
                ui.FIELD_MOOD: screen_mood,
                ui.FIELD_STYLE: screen_style,
                ui.FIELD_INSCRIPTION: screen_inscription,
            }.get(field, screen_concept)
            await step_screen(target, state)
    else:
        await _show_current(target, state)


# ---- entry -------------------------------------------------------------------------------------


async def start_creation(anchor: Message, state: FSMContext, uid: int) -> None:
    """Entry point for "Создать открытку": the choice between the two modes."""
    lang = bot_main.coalesce_lang(get_storage().get_user_lang(uid))
    await state.update_data(
        **{
            BRIEF_KEY: CreativeBrief(lang=lang).to_dict(),
            AFTER_KEY: AFTER_STEP,
            OPTIONAL_ASKED_KEY: 0,
            QUESTION_KEY: "",
            PANEL_CHAT_KEY: None,
            PANEL_MSG_KEY: None,
            VOICE_KEY: None,
        }
    )
    logger.info("creation_start", extra={"user_id": uid, "event": "creation"})
    await screen_mode(anchor, state)


@router.callback_query(F.data.startswith(ui.CB_MODE), StateFilter(S.choosing_mode))
async def on_mode(cq: CallbackQuery, state: FSMContext) -> None:
    await cq.answer()
    brief = await _brief(state)
    if cq.data == ui.CB_MODE + ui.MODE_FREE:
        brief.flow = FLOW_FREE
        await _save(state, brief)
        await screen_idea(cq, state)
    else:
        brief.flow = FLOW_GUIDED
        await _save(state, brief, **{AFTER_KEY: AFTER_STEP})
        await screen_concept(cq, state)


@router.callback_query(F.data == ui.CB_CANCEL, StateFilter(*CANCELLABLE_STATES))
async def on_cancel(cq: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cq.answer()
    await _replace_with_text(cq, ui.CANCELLED)


async def _replace_with_text(cq: CallbackQuery, text: str) -> None:
    message = cq.message
    if not isinstance(message, Message):
        return
    try:
        await message.edit_text(text, reply_markup=None, parse_mode=ParseMode.HTML)
    except Exception:
        await message.answer(text, parse_mode=ParseMode.HTML)


@router.callback_query(F.data == ui.CB_BACK, StateFilter(*CANCELLABLE_STATES))
async def on_back(cq: CallbackQuery, state: FSMContext) -> None:
    await cq.answer()
    await _go_back(cq, state)


# ---- guided steps: buttons ------------------------------------------------------------------------


@router.callback_query(F.data.startswith(ui.CB_PURPOSE), StateFilter(S.concept))
async def on_purpose(cq: CallbackQuery, state: FSMContext) -> None:
    await cq.answer()
    preset = PURPOSE_BY_KEY.get((cq.data or "")[len(ui.CB_PURPOSE):])
    if preset is None:
        return
    brief = await _brief(state)
    brief.concept, brief.occasion, brief.is_card = preset.concept, preset.occasion, True
    await _save(state, brief)
    await _advance(cq, state, S.concept)


@router.callback_query(F.data.startswith(ui.CB_MOOD), StateFilter(S.mood))
async def on_mood(cq: CallbackQuery, state: FSMContext) -> None:
    await cq.answer()
    choice = (cq.data or "")[len(ui.CB_MOOD):]
    if choice == ui.CHOICE_CUSTOM:
        await screen_input(cq, state, ui.FIELD_MOOD)
        return
    brief = await _brief(state)
    if choice == ui.CHOICE_AI:
        brief.delegate_mood()
    elif choice in MOOD_BY_KEY:
        brief.set_mood_preset(choice)
    else:
        return
    await _save(state, brief)
    await _advance(cq, state, S.mood)


@router.callback_query(F.data.startswith(ui.CB_STYLE), StateFilter(S.style))
async def on_style(cq: CallbackQuery, state: FSMContext) -> None:
    await cq.answer()
    choice = (cq.data or "")[len(ui.CB_STYLE):]
    if choice == ui.CHOICE_CUSTOM:
        await screen_input(cq, state, ui.FIELD_STYLE)
        return
    brief = await _brief(state)
    if choice == ui.CHOICE_AI:
        brief.delegate_style()
    elif choice in IMAGE_STYLE_LABELS:
        brief.set_style_preset(choice)
    else:
        return
    await _save(state, brief)
    await _advance(cq, state, S.style)


@router.callback_query(F.data.startswith(ui.CB_INSCRIPTION), StateFilter(S.inscription, S.clarifying))
async def on_inscription_choice(cq: CallbackQuery, state: FSMContext) -> None:
    await cq.answer()
    choice = (cq.data or "")[len(ui.CB_INSCRIPTION):]
    brief = await _brief(state)
    if choice == ui.INSC_TEXT:
        await screen_input(cq, state, ui.FIELD_INSCRIPTION)
    elif choice == ui.INSC_AI:
        brief.request_ai_inscription()
        await _save(state, brief)
        await _start_suggestion(cq, state)
    elif choice == ui.INSC_NONE:
        brief.set_no_inscription()
        await _save(state, brief)
        await _advance(cq, state, S.inscription)


# ---- inscription suggestions (AI proposals are only ever applied by an explicit "use") -----------------


async def _start_suggestion(target: Target, state: FSMContext) -> None:
    brief = await _brief(state)
    if len(brief.suggestions_shown) >= MAX_AI_SUGGESTIONS and brief.inscription_suggestion:
        await screen_suggestion(target, state)
        await _anchor(target).answer(ui.SUGGESTION_LIMIT)
        return
    await _typing(target)
    try:
        phrase = await suggest_inscription(brief, get_settings())
    except BriefAIError:
        logger.warning("inscription_suggestion_failed", extra={"event": "creation"})
        brief.clear_inscription()
        await _save(state, brief)
        data = await state.get_data()
        if data.get(AFTER_KEY) == AFTER_FOLLOWUP:
            await screen_clarify(target, state, FOLLOW_UP_INSCRIPTION)
            await _anchor(target).answer(ui.SUGGESTION_FAILED)
        else:
            await screen_inscription(target, state, note=ui.SUGGESTION_FAILED)
        return
    brief.inscription_suggestion = phrase
    brief.suggestions_shown.append(phrase)
    await _save(state, brief)
    await screen_suggestion(target, state)


@router.callback_query(F.data.startswith(ui.CB_SUGGESTION), StateFilter(S.reviewing_suggestion))
async def on_suggestion(cq: CallbackQuery, state: FSMContext) -> None:
    await cq.answer()
    choice = (cq.data or "")[len(ui.CB_SUGGESTION):]
    brief = await _brief(state)
    if choice == ui.SUG_USE and brief.inscription_suggestion:
        brief.set_inscription(brief.inscription_suggestion, source=SOURCE_AI_APPROVED)
        await _save(state, brief)
        await _advance(cq, state, S.inscription)
    elif choice == ui.SUG_MORE:
        await _start_suggestion(cq, state)
    elif choice == ui.SUG_OWN:
        brief.clear_inscription()
        await _save(state, brief)
        await screen_input(cq, state, ui.FIELD_INSCRIPTION)
    elif choice == ui.SUG_NONE:
        brief.set_no_inscription()
        await _save(state, brief)
        await _advance(cq, state, S.inscription)


# ---- preferences hub and caption ----------------------------------------------------------------------


@router.callback_query(F.data.startswith(ui.CB_PREF), StateFilter(S.preferences))
async def on_preference(cq: CallbackQuery, state: FSMContext) -> None:
    await cq.answer()
    field = (cq.data or "")[len(ui.CB_PREF):]
    if field == ui.FIELD_CAPTION:
        await state.update_data(**{AFTER_KEY: AFTER_PREFS})
        await screen_caption(cq, state)
    elif field in ui.PROMPTS_BY_FIELD and field in (
        ui.FIELD_OCCASION, ui.FIELD_RECIPIENT, ui.FIELD_RESTRICTIONS, ui.FIELD_SIGNATURE,
    ):
        await screen_input(cq, state, field, after=AFTER_PREFS)


@router.callback_query(F.data == ui.CB_NEXT, StateFilter(S.preferences))
async def on_preferences_done(cq: CallbackQuery, state: FSMContext) -> None:
    await cq.answer()
    await screen_confirm(cq, state)


@router.callback_query(F.data.startswith(ui.CB_CAPTION), StateFilter(S.caption))
async def on_caption_choice(cq: CallbackQuery, state: FSMContext) -> None:
    await cq.answer()
    mode = (cq.data or "")[len(ui.CB_CAPTION):]
    if mode == CAPTION_USER:
        await screen_input(cq, state, ui.FIELD_CAPTION)
        return
    if mode not in (CAPTION_AI, CAPTION_NONE):
        return
    brief = await _brief(state)
    brief.set_caption(mode)
    await _save(state, brief)
    await _after_optional_field(cq, state)


async def _after_optional_field(target: Target, state: FSMContext) -> None:
    after = (await state.get_data()).get(AFTER_KEY, AFTER_PREFS)
    await (screen_confirm if after == AFTER_CONFIRM else screen_preferences)(target, state)


# ---- typed input ------------------------------------------------------------------------------------


def _is_just_small_talk(text: str) -> bool:
    """A bare "привет" or "что умеешь" - not a description that merely opens with a greeting."""
    return len(text.split()) <= 3 and is_small_talk_text(text, "ru")


def _clean_concept(raw: str) -> Optional[str]:
    text = " ".join((raw or "").split())
    if not (3 <= len(text) <= 400) or not any(ch.isalnum() for ch in text):
        return None
    return text


def _split_restrictions(raw: str) -> list[str]:
    items = [part.strip() for line in (raw or "").splitlines() for part in line.split(";")]
    return [i for i in items if i]


def _preset_derived(brief: CreativeBrief) -> bool:
    """The concept and occasion are exactly what a purpose button filled in."""
    return any(brief.concept == p.concept and brief.occasion == p.occasion for p in PURPOSE_PRESETS)


async def _reject(target: Target, state: FSMContext, text: str) -> None:
    """Explain what is wrong with the input and keep the user on the same screen."""
    await _anchor(target).answer(text, parse_mode=ParseMode.HTML)


async def _apply_field(target: Target, state: FSMContext, field: str, raw: str) -> None:
    brief = await _brief(state)
    settings = get_settings()
    if field == ui.FIELD_CONCEPT:
        concept = _clean_concept(raw)
        if concept is None or _is_just_small_talk(concept):
            await _reject(target, state, ui.INVALID_BY_FIELD[field] if concept is None else ui.SMALL_TALK_HINT)
            return
        if _preset_derived(brief):
            brief.occasion, brief.is_card = "", False
        brief.concept = concept
    elif field in (ui.FIELD_MOOD, ui.FIELD_STYLE, ui.FIELD_OCCASION, ui.FIELD_RECIPIENT, ui.FIELD_SIGNATURE):
        value = ui.clean_short_field(raw)
        if value is None:
            await _reject(target, state, ui.INVALID_BY_FIELD[field])
            return
        if field == ui.FIELD_MOOD:
            brief.set_mood_text(value)
        elif field == ui.FIELD_STYLE:
            brief.set_style_text(value)
        elif field == ui.FIELD_OCCASION:
            brief.occasion = value
        elif field == ui.FIELD_RECIPIENT:
            brief.recipient = value
        else:
            brief.signature = value
    elif field == ui.FIELD_RESTRICTIONS:
        items = _split_restrictions(raw)
        if not items or len(items) > MAX_RESTRICTIONS or any(len(i) > RESTRICTION_MAX_LEN for i in items):
            await _reject(target, state, ui.INVALID_BY_FIELD[field])
            return
        brief.restrictions = []
        brief.add_restrictions(items)
        brief.restrictions_edited = True
    elif field == ui.FIELD_CAPTION:
        text = (raw or "").strip()
        if not text or len(text) > settings.MAX_CAPTION_LENGTH:
            await _reject(target, state, ui.INVALID_BY_FIELD[field].format(limit=settings.MAX_CAPTION_LENGTH))
            return
        brief.set_caption(CAPTION_USER, text)
    elif field == ui.FIELD_INSCRIPTION:
        text = normalize_inscription(raw)
        check = check_inscription(text)
        if not check.ok:
            await _reject(target, state, ui.inscription_problem_text(check))
            return
        brief.set_inscription(text, source=SOURCE_USER)
    else:
        return
    await _save(state, brief)
    step = {
        ui.FIELD_CONCEPT: S.concept, ui.FIELD_MOOD: S.mood, ui.FIELD_STYLE: S.style,
        ui.FIELD_INSCRIPTION: S.inscription,
    }.get(field, S.preferences)
    if field == ui.FIELD_CAPTION or field in ui.CLEARABLE_FIELDS:
        await _after_optional_field(target, state)
    else:
        await _advance(target, state, step)


async def _read_idea(target: Target, state: FSMContext, raw: str) -> None:
    """Free-form mode: read a description (or a clarifying answer) into the brief."""
    text = (raw or "").strip()
    if len(text) > IDEA_MAX_CHARS:
        await _reject(target, state, f"Описание слишком длинное — уложитесь в {IDEA_MAX_CHARS} символов.")
        return
    if _is_just_small_talk(text):
        await _reject(target, state, ui.SMALL_TALK_HINT)
        return
    await _typing(target)
    brief = await _brief(state)
    extraction = await extract_brief_fields(text, get_settings())
    apply_extraction(brief, extraction, text)
    await _save(state, brief, **{QUESTION_KEY: extraction.question if not brief.concept.strip() else ""})
    logger.info(
        "creation_idea_read",
        extra={"event": "creation", "ai_used": extraction.used_ai, "concept_found": bool(brief.concept)},
    )
    await _follow_up_or_confirm(target, state)


async def _answer_inscription_question(target: Target, state: FSMContext, raw: str) -> None:
    """A typed reply to "нужна ли надпись?": the exact text, or a plain no."""
    text = normalize_inscription(raw)
    brief = await _brief(state)
    if asks_for_no_text(text) or text.casefold() in {"нет", "не надо", "не нужна", "не нужно", "no"}:
        brief.set_no_inscription()
        await _save(state, brief)
        await _follow_up_or_confirm(target, state)
        return
    await _apply_field(target, state, ui.FIELD_INSCRIPTION, text)


async def _consume_text(target: Target, state: FSMContext, raw: str) -> None:
    current = await state.get_state()
    data = await state.get_data()
    if current == S.concept.state:
        await _apply_field(target, state, ui.FIELD_CONCEPT, raw)
    elif current == S.idea.state:
        await _read_idea(target, state, raw)
    elif current == S.clarifying.state:
        if data.get(CLARIFY_KEY) == FOLLOW_UP_INSCRIPTION:
            await _answer_inscription_question(target, state, raw)
        else:
            await _read_idea(target, state, raw)
    elif current == S.awaiting_text.state:
        await _apply_field(target, state, data.get(FIELD_KEY, ui.FIELD_CONCEPT), raw)


@router.message(StateFilter(*TEXT_STATES), F.text.func(_is_plain_input))
async def on_text(message: Message, state: FSMContext) -> None:
    await state.update_data(**{VOICE_KEY: None})  # typing replaces any transcript still waiting for a yes
    await _consume_text(message, state, message.text or "")


@router.callback_query(F.data == ui.CB_CLEAR, StateFilter(S.awaiting_text))
async def on_clear(cq: CallbackQuery, state: FSMContext) -> None:
    await cq.answer()
    data = await state.get_data()
    field = data.get(FIELD_KEY)
    if field not in ui.CLEARABLE_FIELDS:
        return
    brief = await _brief(state)
    if field == ui.FIELD_OCCASION:
        brief.occasion = ""
    elif field == ui.FIELD_RECIPIENT:
        brief.recipient = ""
    elif field == ui.FIELD_RESTRICTIONS:
        brief.restrictions = []
        brief.restrictions_edited = True
    else:
        brief.signature = ""
    await _save(state, brief)
    await _after_optional_field(cq, state)


# ---- voice input (always confirmed before use) --------------------------------------------------------


@router.message(StateFilter(*TEXT_STATES), F.voice)
async def on_voice(message: Message, state: FSMContext, bot: Bot) -> None:
    settings = get_settings()
    if not stt_configured(settings):
        await message.answer(ui.VOICE_UNAVAILABLE)
        return
    recognizing = await message.answer(t("voice_recognizing", "ru"))
    speech_lang = (await _brief(state)).lang  # the language the user speaks: their saved card language
    try:
        text = await bot_main._transcribe_voice_message(bot, message, settings, speech_lang)  # type: ignore[arg-type]
    except SpeechToTextError:
        await bot_main._safe_delete_message(bot, recognizing.chat.id, recognizing.message_id)
        await message.answer(ui.VOICE_EMPTY)
        return
    await bot_main._safe_delete_message(bot, recognizing.chat.id, recognizing.message_id)
    if not (text or "").strip():
        await message.answer(ui.VOICE_EMPTY)
        return
    await _retire_panel(bot, state)
    sent = await message.answer(
        ui.VOICE_CONFIRM.format(text=ui.esc(text)), reply_markup=ui.voice_confirm_keyboard(), parse_mode=ParseMode.HTML
    )
    await state.update_data(**{VOICE_KEY: text.strip()})
    await _remember_panel(state, sent)


@router.callback_query(F.data == ui.CB_VOICE_OK, StateFilter(*TEXT_STATES))
async def on_voice_ok(cq: CallbackQuery, state: FSMContext) -> None:
    await cq.answer()
    text = (await state.get_data()).get(VOICE_KEY)
    if not text:
        await _show_current(cq, state)
        return
    await state.update_data(**{VOICE_KEY: None})
    await _consume_text(cq, state, text)


@router.callback_query(F.data == ui.CB_VOICE_RETRY, StateFilter(*TEXT_STATES))
async def on_voice_retry(cq: CallbackQuery, state: FSMContext) -> None:
    await cq.answer()
    await state.update_data(**{VOICE_KEY: None})
    await _show_current(cq, state)


@router.message(StateFilter(*TEXT_STATES), ~F.text)
async def on_text_state_other(message: Message) -> None:
    """Stickers, photos and the like where text is expected (voice is handled above)."""
    await message.answer(ui.TEXT_ONLY)


# ---- confirmation: edit / generate ----------------------------------------------------------------------


@router.callback_query(F.data.startswith(ui.CB_EDIT), StateFilter(S.confirming))
async def on_edit(cq: CallbackQuery, state: FSMContext) -> None:
    await cq.answer()
    field = (cq.data or "")[len(ui.CB_EDIT):]
    await state.update_data(**{AFTER_KEY: AFTER_CONFIRM})
    if field == ui.FIELD_MOOD:
        await screen_mood(cq, state)
    elif field == ui.FIELD_STYLE:
        await screen_style(cq, state)
    elif field == ui.FIELD_INSCRIPTION:
        await screen_inscription(cq, state)
    elif field == ui.FIELD_CAPTION:
        await screen_caption(cq, state)
    elif field in (
        ui.FIELD_CONCEPT, ui.FIELD_OCCASION, ui.FIELD_RECIPIENT, ui.FIELD_RESTRICTIONS, ui.FIELD_SIGNATURE,
    ):
        await screen_input(cq, state, field, after=AFTER_CONFIRM)


async def _route_to_fix(cq: CallbackQuery, state: FSMContext, code: str) -> None:
    await state.update_data(**{AFTER_KEY: AFTER_CONFIRM})
    if code == "concept_missing":
        await screen_input(cq, state, ui.FIELD_CONCEPT, after=AFTER_CONFIRM)
    elif code == "inscription_unapproved":
        if (await _brief(state)).inscription_suggestion:
            await screen_suggestion(cq, state)
        else:
            await _start_suggestion(cq, state)
    elif code == "inscription_invalid":
        await screen_input(cq, state, ui.FIELD_INSCRIPTION, after=AFTER_CONFIRM)
    else:
        await screen_input(cq, state, ui.FIELD_CAPTION, after=AFTER_CONFIRM)


@router.callback_query(F.data == ui.CB_GO, StateFilter(S.confirming))
async def on_generate(cq: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    """The one place a creation reaches the image provider: only from the confirmation screen."""
    if not cq.from_user or not isinstance(cq.message, Message):
        await cq.answer()
        return
    uid = cq.from_user.id
    anchor = cq.message
    settings = get_settings()
    brief = await _brief(state)

    problem = first_problem(brief, max_caption_len=settings.MAX_CAPTION_LENGTH)
    if problem is not None:
        await cq.answer(ui.PROBLEM_TOASTS[problem.code], show_alert=True)
        await _route_to_fix(cq, state, problem.code)
        if problem.code == "inscription_invalid":
            await anchor.answer(ui.inscription_problem_text(inscription_check(brief)), parse_mode=ParseMode.HTML)
        return

    alert = await bot_main._generation_preflight_alert("ru", uid, settings)
    if alert:
        await cq.answer(alert, show_alert=True)
        return
    lock = card_lock(uid)
    if lock.locked():
        await cq.answer(t("card_busy", "ru"), show_alert=True)
        return

    async with lock:
        # A callback can pass its state filter and then wait on preflight while another confirmation
        # finishes. Revalidate under the lock before making another paid request.
        if await state.get_state() != S.confirming.state:
            await cq.answer(ui.NOTHING_TO_EDIT, show_alert=True)
            return
        await state.set_state(S.generating)
        await cq.answer()
        await _retire_panel(bot, state)
        prefs = get_storage().get_profile_preferences(uid)
        log_generation_prompt_context(
            user_id=uid,
            holiday=brief.occasion,
            occasion_details="",
            recipient_address=brief.recipient,
            sender_signature_present=bool(brief.signature),
            ui_lang="ru",
            card_lang=brief.lang,  # type: ignore[arg-type]
            image_style=brief.style_key or brief.style_text,
            text_style=text_style_for(brief),
            tone=prefs.text_tone,
            length=prefs.text_length,
            address_style=prefs.address_style,
        )
        logger.info(
            "creation_generate",
            extra={
                "user_id": uid,
                "event": "creation",
                "flow": brief.flow,
                "inscription": brief.inscription_mode,
                "inscription_source": brief.inscription_source,
                "caption": resolve_caption_mode(brief),
                "restrictions": len(brief.restrictions),
            },
        )
        status = await anchor.answer(ui.GENERATING)
        try:
            card = await run_brief_generation(settings, brief, profile_prefs=prefs)
        except (ProxiAPIError, OpenAIImageError) as exc:
            logger.exception("Image provider failed: %s", exc, extra={"user_id": uid, "event": "error"})
            await _fail(status, anchor, state, "err_image")
            return
        except (YandexGPTError, OpenAITextError) as exc:
            logger.exception("Text provider failed: %s", exc, extra={"user_id": uid, "event": "error"})
            await _fail(status, anchor, state, "err_text")
            return
        except asyncio.TimeoutError:
            logger.warning("timeout", extra={"user_id": uid, "event": "error"})
            await _fail(status, anchor, state, "err_timeout")
            return
        except Exception as exc:
            logger.exception("generation failed: %s", exc, extra={"user_id": uid, "event": "error"})
            await _fail(status, anchor, state, "err_generic")
            return

        try:
            await status.delete()
        except Exception:
            pass
        try:
            await _deliver(anchor, uid, brief, card)
        except Exception as exc:
            # The image was paid for but could not be sent; the brief is intact, so the user can retry.
            logger.exception("card delivery failed: %s", exc, extra={"user_id": uid, "event": "error"})
            await anchor.answer(t("err_generic", "ru"))
            await screen_confirm(anchor, state)
            return
        if should_increment_daily_count(uid, settings):
            get_storage().increment_generation(uid)
        await state.clear()
        logger.info("generation_ok", extra={"user_id": uid, "event": "generation_ok"})


async def _fail(status: Message, anchor: Message, state: FSMContext, error_key: str) -> None:
    """A provider failed: say so and put the user back on the confirmation screen with the brief intact."""
    try:
        await status.edit_text(t(error_key, "ru"))
    except Exception:
        await anchor.answer(t(error_key, "ru"))
    await screen_confirm(anchor, state)


async def _deliver(anchor: Message, uid: int, brief: CreativeBrief, card: Any) -> None:
    """Send the finished card, remember it for the regeneration buttons, and say if the inscription is missing."""
    short_text = card.texts.short_text
    image, drawn = await bot_main.render_card_image(card.image_bytes, short_text, exact=True)
    ctx = LastCardContext(
        occasion="",
        image_description=brief.concept,
        holiday=brief.occasion,
        image_style=brief.style_key,
        text_style=text_style_for(brief),
        lang=brief.lang,
        image_prompt_en=card.image_prompt_en,
        caption_html=card.texts.caption_html,
        recipient_address=brief.recipient,
        sender_signature=brief.signature,
        short_text=short_text,
        inscription_mode="text" if inscription_to_draw(brief) else "none",
        caption_mode=resolve_caption_mode(brief),
        creative_context=creative_context(brief),
    )
    # The card's own buttons and the menu follow the profile language, as for every card since Stage 2A.
    ui_lang = bot_main._ui_lang_for_user(uid)
    sent = await anchor.answer_photo(
        photo=BufferedInputFile(image, filename="card.png"),
        caption=card.texts.caption_html,
        parse_mode=ParseMode.HTML,
        reply_markup=bot_main.after_card_keyboard(ui_lang, brief.lang, ctx),  # type: ignore[arg-type]
    )
    await bot_main._reassert_main_menu_keyboard(anchor, ui_lang)
    if short_text and not drawn:
        await anchor.answer(ui.RENDER_FAILED_NOTICE)
    ctx.photo_file_id = sent.photo[-1].file_id if sent.photo else ""
    get_storage().save_last_card(uid, ctx, original=card.image_bytes)


# ---- while generating / typing where buttons are expected --------------------------------------------------


@router.callback_query(F.data.startswith("cr:"), StateFilter(S.generating))
async def on_busy_callback(cq: CallbackQuery) -> None:
    await cq.answer(ui.BUSY_GENERATING, show_alert=True)


@router.message(StateFilter(S.generating), F.text.func(_is_plain_input))
async def on_busy_text(message: Message) -> None:
    await message.answer(ui.BUSY_GENERATING)


@router.message(StateFilter(*BUTTON_STATES), F.text.func(_is_plain_input))
async def on_text_where_buttons_expected(message: Message, state: FSMContext) -> None:
    await _show_current(message, state)


@router.message(StateFilter(*BUTTON_STATES), ~F.text)
async def on_media_where_buttons_expected(message: Message, state: FSMContext) -> None:
    await _show_current(message, state)
