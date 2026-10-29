"""
Russian texts, keyboards and the confirmation summary of the creation flow (no handlers, no network).

All Telegram-facing strings of both creation modes live here. Callback data is namespaced ``cr:`` and stays
well under Telegram's 64-byte limit.
"""
from __future__ import annotations

import html
import re
from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from services.card_render import INSCRIPTION_MAX_CHARS, InscriptionCheck
from utils.creative_brief import (
    CAPTION_AI,
    CAPTION_NONE,
    CAPTION_USER,
    INSCRIPTION_AI,
    INSCRIPTION_NONE,
    INSCRIPTION_TEXT,
    MOOD_BY_KEY,
    MOOD_PRESETS,
    PURPOSE_PRESETS,
    SOURCE_AI_APPROVED,
    CreativeBrief,
    caption_is_default,
    resolve_caption_mode,
)
from utils.prompts import IMAGE_STYLE_KEYBOARD_ORDER, IMAGE_STYLE_LABELS

# ---- callback data ------------------------------------------------------------------------------

CB_CANCEL = "cr:cancel"
CB_BACK = "cr:back"
CB_NEXT = "cr:next"
CB_GO = "cr:go"
CB_CLEAR = "cr:clear"
CB_VOICE_OK = "cr:vok"
CB_VOICE_RETRY = "cr:vno"

CB_MODE = "cr:mode:"
MODE_GUIDED = "guided"
MODE_FREE = "free"

CB_PURPOSE = "cr:purpose:"
CB_MOOD = "cr:mood:"
CB_STYLE = "cr:style:"
CB_INSCRIPTION = "cr:insc:"
CB_SUGGESTION = "cr:sug:"
CB_PREF = "cr:pref:"
CB_CAPTION = "cr:cap:"
CB_EDIT = "cr:edit:"

CHOICE_AI = "ai"
CHOICE_CUSTOM = "custom"
INSC_TEXT = "text"
INSC_AI = "ai"
INSC_NONE = "none"
SUG_USE = "use"
SUG_MORE = "more"
SUG_OWN = "own"
SUG_NONE = "none"

# Fields that take typed text (``awaiting_text`` state) and the ones that may be emptied again.
FIELD_CONCEPT = "concept"
FIELD_MOOD = "mood"
FIELD_STYLE = "style"
FIELD_INSCRIPTION = "inscription"
FIELD_OCCASION = "occasion"
FIELD_RECIPIENT = "recipient"
FIELD_RESTRICTIONS = "restrictions"
FIELD_CAPTION = "caption"
FIELD_SIGNATURE = "signature"
CLEARABLE_FIELDS = frozenset({FIELD_OCCASION, FIELD_RECIPIENT, FIELD_RESTRICTIONS, FIELD_SIGNATURE})

# ---- messages -----------------------------------------------------------------------------------

MODE_PROMPT = (
    "✨ <b>Как будем создавать?</b>\n\n"
    "🧩 <b>Выбрать из вариантов</b> — пройдём по шагам: идея, настроение, стиль, надпись.\n"
    "💬 <b>Опишу своими словами</b> — расскажите всё одним сообщением, остальное я пойму сам "
    "и спрошу только то, что действительно важно."
)

CONCEPT_PROMPT = (
    "💡 <b>Шаг 1 из 5 — что создаём?</b>\n\n"
    "Выберите повод кнопкой или опишите идею своими словами — например, "
    "«открытка маме на день рождения» или «закат над морем»."
)
MOOD_PROMPT = "🎭 <b>Шаг 2 из 5 — настроение</b>\n\nВыберите настроение или доверьте выбор ИИ."
STYLE_PROMPT = "🖼 <b>Шаг 3 из 5 — визуальный стиль</b>\n\nВыберите стиль или доверьте выбор ИИ."


def editing_title(prompt: str) -> str:
    """The same screen reached from the confirmation screen: no "step N of 5", it is not a step any more."""
    return re.sub(r"Шаг \d из 5 — (\w)", lambda m: m.group(1).upper(), prompt, count=1)


INSCRIPTION_PROMPT = (
    "🔤 <b>Шаг 4 из 5 — надпись на картинке</b>\n\n"
    "Свой текст будет нанесён ровно так, как вы его напишете. "
    "Предложение ИИ я покажу заранее — на картинке оно появится только после вашего одобрения."
)
PREFERENCES_PROMPT = (
    "🎛 <b>Шаг 5 из 5 — дополнительные пожелания</b>\n\n"
    "Всё необязательно — отметьте только то, что нужно, и нажмите «К проверке»."
)
IDEA_PROMPT = (
    "💬 <b>Расскажите, что хотите создать</b>\n\n"
    "Одним сообщением: идея, настроение, стиль, текст надписи, кому и по какому поводу, "
    "что учесть или чего избежать. Точные формулировки и ограничения я сохраню как есть."
)
CONCEPT_QUESTION_DEFAULT = "Что должно быть на картинке или для чего она? Опишите идею в паре слов."
INSCRIPTION_QUESTION = (
    "🔤 <b>Нужна ли надпись на картинке?</b>\n\n"
    "Пришлите точный текст сообщением — или выберите вариант ниже."
)
SUGGESTION_SCREEN = (
    "💡 <b>Предложение ИИ для надписи</b>\n\n«{text}»\n\n"
    "Это только предложение: на картинке оно появится, если вы его одобрите."
)
SUGGESTION_FAILED = "Не получилось придумать надпись. Напишите свой текст или выберите другой вариант."
SUGGESTION_LIMIT = "Это уже много вариантов — выберите один из показанных, напишите свой текст или откажитесь от надписи."
CAPTION_PROMPT = (
    "💬 <b>Сообщение под картинкой</b>\n\n"
    "Развёрнутый текст (поздравление, пожелание), который придёт подписью к картинке."
)
CANCELLED = "Создание отменено. Если захотите вернуться, нажмите «Создать открытку»."
NOTHING_TO_EDIT = "Это уже не актуально — начните заново через «Создать открытку»."
GENERATING = "⏳ Создаю изображение — это займёт около минуты. Ничего больше нажимать не нужно."
BUSY_GENERATING = "Идёт создание — подождите, пожалуйста, пока оно закончится."
VOICE_UNAVAILABLE = "Голосовые сообщения сейчас недоступны — напишите текстом, пожалуйста."
VOICE_EMPTY = "Не удалось разобрать голосовое сообщение — напишите текстом, пожалуйста."
VOICE_CONFIRM = "🎙 Я услышал: «{text}»\n\nВсё верно?"
TEXT_ONLY = "Здесь нужен текст — напишите сообщением, пожалуйста."
SMALL_TALK_HINT = "Давайте сначала создадим картинку 🙂 Опишите, что хотите увидеть."
INSCRIPTION_SAVED_NOTE = "Надпись сохранена: «{text}»"
RENDER_FAILED_NOTICE = (
    "⚠️ Не удалось нанести надпись на картинку — отправил её без текста. "
    "Надпись сохранена, её можно нанести заново через «Новая картинка»."
)

PROMPTS_BY_FIELD = {
    FIELD_CONCEPT: "💡 Опишите идею: что должно быть на картинке или для чего она.",
    FIELD_MOOD: "🎭 Опишите настроение своими словами — например, «тёплое и немного ностальгическое».",
    FIELD_STYLE: "🖼 Опишите стиль своими словами — например, «в духе импрессионистов».",
    FIELD_INSCRIPTION: (
        "🔤 Пришлите точный текст надписи. Он будет нанесён на картинку ровно так, как вы его напишете "
        f"(до {INSCRIPTION_MAX_CHARS} символов, без эмодзи; переносы строк сохраню)."
    ),
    FIELD_OCCASION: "🎁 Какой повод? Например: «день рождения» или «выпускной».",
    FIELD_RECIPIENT: "👤 Кому адресована открытка? Например: «маме» или «коллегам».",
    FIELD_RESTRICTIONS: (
        "🚫 Что учесть или чего избежать? Напишите своими словами — например, «без людей» или "
        "«только тёплые цвета». Каждая строка — отдельное ограничение. "
        "Новый список заменит прежние ограничения, в том числе из исходного описания."
    ),
    FIELD_CAPTION: "✍️ Пришлите текст сообщения под картинкой — я отправлю его без изменений.",
    FIELD_SIGNATURE: "✍️ Подпись отправителя — например, имя.",
}

INVALID_BY_FIELD = {
    FIELD_CONCEPT: "Опишите идею чуть подробнее (от 3 до 400 символов) — хотя бы в паре слов.",
    FIELD_MOOD: "Опишите настроение коротко, одной строкой (до 80 символов).",
    FIELD_STYLE: "Опишите стиль коротко, одной строкой (до 80 символов).",
    FIELD_OCCASION: "Напишите повод коротко, одной строкой (до 80 символов).",
    FIELD_RECIPIENT: "Напишите адресата коротко, одной строкой (до 80 символов).",
    FIELD_SIGNATURE: "Напишите подпись коротко, одной строкой (до 80 символов).",
    FIELD_RESTRICTIONS: "Напишите, что учесть или чего избежать (до 160 символов на каждое ограничение).",
    FIELD_CAPTION: "Текст сообщения пустой или длиннее лимита Telegram ({limit} символов) — сократите его.",
}

_INSCRIPTION_PROBLEMS = {
    "empty": "Текст надписи пустой.",
    "too_long": f"Надпись слишком длинная — максимум {INSCRIPTION_MAX_CHARS} символов.",
    "does_not_fit": "Надпись не помещается на картинке целиком. Сократите её или разбейте на строки.",
}

PROBLEM_TOASTS = {
    "concept_missing": "Сначала опишите идею.",
    "inscription_unapproved": "Сначала одобрите или отклоните предложенную надпись.",
    "inscription_invalid": "Надпись нужно поправить, прежде чем создавать картинку.",
    "caption_invalid": "Сообщение под картинкой нужно поправить, прежде чем создавать картинку.",
}


def inscription_problem_text(check: InscriptionCheck) -> str:
    if check.reason == "unsupported":
        chars = html.escape(" ".join(check.detail))
        return (
            f"В шрифте открытки нет символов: {chars}. Уберите их или замените — "
            "я не меняю вашу надпись сам."
        )
    return _INSCRIPTION_PROBLEMS.get(check.reason, "Эту надпись нельзя нанести на картинку.")


def esc(text: str) -> str:
    return html.escape(text.strip())


# ---- keyboard helpers -------------------------------------------------------------------------------


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _grid(buttons: list[InlineKeyboardButton], columns: int = 2) -> list[list[InlineKeyboardButton]]:
    return [buttons[i : i + columns] for i in range(0, len(buttons), columns)]


def _nav(*, back: bool = True, cancel: bool = True) -> list[InlineKeyboardButton]:
    row: list[InlineKeyboardButton] = []
    if back:
        row.append(_btn("⬅️ Назад", CB_BACK))
    if cancel:
        row.append(_btn("✖️ Отмена", CB_CANCEL))
    return row


def mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("🧩 Выбрать из вариантов", CB_MODE + MODE_GUIDED)],
            [_btn("💬 Опишу своими словами", CB_MODE + MODE_FREE)],
            [_btn("✖️ Отмена", CB_CANCEL)],
        ]
    )


def concept_keyboard() -> InlineKeyboardMarkup:
    rows = _grid([_btn(p.label, CB_PURPOSE + p.key) for p in PURPOSE_PRESETS])
    rows.append(_nav())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def mood_keyboard() -> InlineKeyboardMarkup:
    rows = _grid([_btn(m.label, CB_MOOD + m.key) for m in MOOD_PRESETS])
    rows.append([_btn("🤖 На усмотрение ИИ", CB_MOOD + CHOICE_AI), _btn("✏️ Своё", CB_MOOD + CHOICE_CUSTOM)])
    rows.append(_nav())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def style_keyboard() -> InlineKeyboardMarkup:
    keys = [k for k in IMAGE_STYLE_KEYBOARD_ORDER if k in IMAGE_STYLE_LABELS]
    rows = _grid([_btn(IMAGE_STYLE_LABELS[k][0], CB_STYLE + k) for k in keys])
    rows.append([_btn("🤖 На усмотрение ИИ", CB_STYLE + CHOICE_AI), _btn("✏️ Свой стиль", CB_STYLE + CHOICE_CUSTOM)])
    rows.append(_nav())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def inscription_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("✍️ Свой текст", CB_INSCRIPTION + INSC_TEXT)],
            [_btn("💡 Предложить варианты ИИ", CB_INSCRIPTION + INSC_AI)],
            [_btn("🚫 Без надписи", CB_INSCRIPTION + INSC_NONE)],
            _nav(),
        ]
    )


def inscription_question_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("💡 Предложить варианты ИИ", CB_INSCRIPTION + INSC_AI)],
            [_btn("🚫 Без надписи", CB_INSCRIPTION + INSC_NONE)],
            _nav(back=False),
        ]
    )


def suggestion_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("✅ Использовать", CB_SUGGESTION + SUG_USE)],
            [_btn("🔄 Другой вариант", CB_SUGGESTION + SUG_MORE), _btn("✍️ Свой текст", CB_SUGGESTION + SUG_OWN)],
            [_btn("🚫 Без надписи", CB_SUGGESTION + SUG_NONE)],
            _nav(),
        ]
    )


def preferences_keyboard(brief: CreativeBrief) -> InlineKeyboardMarkup:
    def mark(label: str, filled: bool) -> str:
        return f"{label} ✓" if filled else label

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(mark("🎁 Повод", bool(brief.occasion)), CB_PREF + FIELD_OCCASION),
                _btn(mark("👤 Кому", bool(brief.recipient)), CB_PREF + FIELD_RECIPIENT),
            ],
            [
                _btn(mark("🚫 Ограничения", bool(brief.restrictions)), CB_PREF + FIELD_RESTRICTIONS),
                _btn(mark("💬 Сообщение", brief.caption_mode != "unspecified"), CB_PREF + FIELD_CAPTION),
            ],
            [_btn(mark("✍️ Подпись", bool(brief.signature)), CB_PREF + FIELD_SIGNATURE)],
            [_btn("➡️ К проверке", CB_NEXT)],
            _nav(),
        ]
    )


def caption_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("🤖 Напишет ИИ", CB_CAPTION + CAPTION_AI)],
            [_btn("✍️ Свой текст", CB_CAPTION + CAPTION_USER)],
            [_btn("🚫 Без сообщения", CB_CAPTION + CAPTION_NONE)],
            _nav(cancel=False),
        ]
    )


def text_input_keyboard(*, clearable: bool = False, back: bool = True) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if clearable:
        rows.append([_btn("🗑 Убрать", CB_CLEAR)])
    rows.append(_nav(back=back))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def voice_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_btn("✅ Верно", CB_VOICE_OK), _btn("✏️ Ввести заново", CB_VOICE_RETRY)]]
    )


def confirm_keyboard() -> InlineKeyboardMarkup:
    edits = [
        ("💡 Идея", FIELD_CONCEPT),
        ("🎭 Настроение", FIELD_MOOD),
        ("🖼 Стиль", FIELD_STYLE),
        ("🔤 Надпись", FIELD_INSCRIPTION),
        ("🎁 Повод", FIELD_OCCASION),
        ("👤 Кому", FIELD_RECIPIENT),
        ("🚫 Ограничения", FIELD_RESTRICTIONS),
        ("💬 Сообщение", FIELD_CAPTION),
        ("✍️ Подпись", FIELD_SIGNATURE),
    ]
    rows: list[list[InlineKeyboardButton]] = [[_btn("✅ Создать", CB_GO)]]
    rows += _grid([_btn(label, CB_EDIT + field) for label, field in edits], columns=3)
    rows.append([_btn("✖️ Отмена", CB_CANCEL)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---- confirmation summary -------------------------------------------------------------------------

# Display only: a long user message is previewed on the summary (the full text is what gets sent), which
# keeps the screen well inside Telegram's 4096-character message limit.
_CAPTION_PREVIEW_CHARS = 300


def _or_dash(value: str) -> str:
    return esc(value) if value.strip() else "—"


def _mood_line(brief: CreativeBrief) -> str:
    if brief.mood_key in MOOD_BY_KEY:
        return esc(MOOD_BY_KEY[brief.mood_key].label)
    if brief.mood_text:
        return esc(brief.mood_text)
    return "на усмотрение ИИ" if brief.mood_ai else "не указано — ИИ подберёт по идее"


def _style_line(brief: CreativeBrief) -> str:
    if brief.style_key in IMAGE_STYLE_LABELS:
        return esc(IMAGE_STYLE_LABELS[brief.style_key][0])
    if brief.style_text:
        return esc(brief.style_text)
    return "на усмотрение ИИ" if brief.style_ai else "не указан — ИИ подберёт по идее"


def _inscription_line(brief: CreativeBrief) -> str:
    if brief.inscription_mode == INSCRIPTION_TEXT:
        origin = (
            "предложено ИИ, вы одобрили" if brief.inscription_source == SOURCE_AI_APPROVED else "ваш текст"
        )
        return f"«{esc(brief.inscription_text)}» — {origin}, нанесу без изменений"
    if brief.inscription_mode == INSCRIPTION_NONE:
        return "без надписи — по вашему выбору"
    if brief.inscription_mode == INSCRIPTION_AI:
        return "ждёт вашего решения по предложению ИИ"
    return "не указана — текста на картинке не будет"


def _caption_line(brief: CreativeBrief) -> str:
    mode = resolve_caption_mode(brief)
    default = " (по умолчанию)" if caption_is_default(brief) else ""
    if mode == CAPTION_USER:
        text = brief.caption_text.strip()
        shown = text if len(text) <= _CAPTION_PREVIEW_CHARS else text[: _CAPTION_PREVIEW_CHARS].rstrip() + "…"
        return f"«{esc(shown)}» — ваш текст, отправлю без изменений"
    if mode == CAPTION_AI:
        return f"ИИ напишет{default}"
    return f"нет{default}"


def render_summary(brief: CreativeBrief) -> str:
    restrictions = "\n".join(f"   • {esc(r)}" for r in brief.restrictions)
    if brief.source_requests and not brief.restrictions_edited:
        restrictions += "\n   Ограничения из исходного описания сохранены целиком и обязательны."
    return (
        "📋 <b>Проверьте задумку</b>\n\n"
        f"💡 <b>Идея:</b> {_or_dash(brief.concept)}\n"
        f"🎭 <b>Настроение:</b> {_mood_line(brief)}\n"
        f"🖼 <b>Стиль:</b> {_style_line(brief)}\n"
        f"🔤 <b>Надпись:</b> {_inscription_line(brief)}\n"
        f"🎁 <b>Повод:</b> {_or_dash(brief.occasion)}\n"
        f"👤 <b>Кому:</b> {_or_dash(brief.recipient)}\n"
        f"🚫 <b>Ограничения:</b>{chr(10) + restrictions if restrictions else ' —'}\n"
        f"💬 <b>Сообщение под картинкой:</b> {_caption_line(brief)}\n"
        f"✍️ <b>Подпись:</b> {_or_dash(brief.signature)}\n\n"
        "Генерация изображения платная и начнётся только после нажатия «✅ Создать». "
        "Любой пункт можно поправить кнопками ниже."
    )


def render_preferences(brief: CreativeBrief) -> str:
    lines = []
    if brief.occasion:
        lines.append(f"🎁 Повод: {esc(brief.occasion)}")
    if brief.recipient:
        lines.append(f"👤 Кому: {esc(brief.recipient)}")
    if brief.restrictions:
        lines.append("🚫 Ограничения: " + "; ".join(esc(r) for r in brief.restrictions))
    if brief.caption_mode != "unspecified":
        lines.append(f"💬 Сообщение: {_caption_line(brief)}")
    if brief.signature:
        lines.append(f"✍️ Подпись: {esc(brief.signature)}")
    current = ("\n\n" + "\n".join(lines)) if lines else ""
    return PREFERENCES_PROMPT + current


def clean_short_field(raw: str, max_len: int = 80) -> Optional[str]:
    """One line of plain text, or None: empty, too long, multi-line, a link, or without a letter/digit."""
    text = " ".join((raw or "").split())
    if "\n" in (raw or "").strip() or not text or len(text) > max_len:
        return None
    lowered = text.lower()
    if "http://" in lowered or "https://" in lowered or "www." in lowered:
        return None
    return text if any(ch.isalnum() for ch in text) else None
