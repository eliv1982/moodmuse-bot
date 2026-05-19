"""
Idle (no-wizard) AI small talk via the configured text provider.
"""
from __future__ import annotations

import html
import logging
import re

from config import Settings
from services.providers.factory import get_text_provider
from services.providers.openai_text import OpenAITextError
from services.yandex_gpt import YandexGPTError
from utils.i18n import Lang, t
from utils.idle_small_talk_session import IDLE_FALLBACK_MESSAGE_KEYS

logger = logging.getLogger(__name__)

MAX_IDLE_SMALL_TALK_CHARS = 500

_SMALL_TALK_BASE_RU = (
    "Ты — MoodMuse, тёплый ассистент для поздравительных открыток. "
    "Отвечай на языке пользователя (русский или английский по контексту). "
    "Дай 1–2 коротких предложения: дружелюбно, легко, чуть игриво. "
    "Не притворяйся, что у тебя есть личная жизнь или реальные переживания. "
    "Не давай медицинских, юридических или финансовых советов. "
    "Не звучи как меню, шаблонная подсказка или повторяющийся призыв. "
    "Без markdown, таблиц и длинных пояснений. "
    "Избегай обращений на «ты/вы» и гендерных форм, где возможно. "
    "Не используй HTML-разметку."
)

_SMALL_TALK_BASE_EN = (
    "You are MoodMuse, a warm greeting-card assistant. "
    "Reply in the user's language (Russian or English as appropriate). "
    "Give 1–2 short sentences: friendly, light, slightly playful. "
    "Do not pretend to have a real personal life or lived experiences. "
    "Do not give medical, legal, or financial advice. "
    "Do not sound like a menu, generic CTA, or repeated stock phrase. "
    "No markdown, tables, long explanations, or HTML markup."
)

_EARLY_TURN_RU = (
    "Сейчас ход 1–2: ответь естественно на сообщение. "
    "Про открытки — только лёгкое упоминание, если уместно."
)

_EARLY_TURN_EN = (
    "Turns 1–2: respond naturally to the message. "
    "Mention cards only as a very soft aside if it fits."
)

_STEER_TURN_RU = (
    "Сейчас ход 3–5: мягко направь к идее открытки, без спешки и без меню. "
    "Не повторяй одну и ту же формулировку. Примеры тона (не копируй дословно): "
    "«Можем превратить это настроение в открытку, если хочется.»; "
    "«Кстати, из такого настроения уже просится маленькая открытка.»; "
    "«Можно собрать открытку под этот день — без спешки.»"
)

_STEER_TURN_EN = (
    "Turns 3–5: gently steer toward making a card—unhurried, not menu-like. "
    "Do not repeat the same wording. Tone examples (do not copy verbatim): "
    "'We could turn that mood into a card, if you feel like it.'; "
    "'That actually sounds like a nice mood for a little card.'; "
    "'We can make a card from this vibe whenever you're ready.'"
)


class IdleSmallTalkError(Exception):
    """Idle small talk generation failed (provider or formatting)."""


def small_talk_system_prompt(lang: Lang, turn: int) -> str:
    base = _SMALL_TALK_BASE_EN if lang == "en" else _SMALL_TALK_BASE_RU
    phase = _STEER_TURN_EN if lang == "en" else _STEER_TURN_RU
    if turn <= 2:
        phase = _EARLY_TURN_EN if lang == "en" else _EARLY_TURN_RU
    return f"{base}\n\n{phase}"


def build_idle_small_talk_user_prompt(user_message: str, turn: int) -> str:
    text = (user_message or "").strip()
    return f"Idle small-talk turn {turn}.\nUser message:\n{text or '(empty)'}"


def _small_talk_timeout(settings: Settings) -> float:
    name = (settings.TEXT_PROVIDER or "yandex").strip().lower()
    if name == "openai":
        return min(30.0, float(settings.OPENAI_TIMEOUT))
    return min(30.0, float(settings.YANDEX_TIMEOUT))


def format_small_talk_for_telegram(text: str) -> str:
    """Trim, strip lightweight markdown, cap length, HTML-escape for Telegram."""
    cleaned = (text or "").replace("\n", " ").strip()
    cleaned = re.sub(r"\*\*|__|`", "", cleaned)
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        raise IdleSmallTalkError("empty model response")
    if len(cleaned) > MAX_IDLE_SMALL_TALK_CHARS:
        cleaned = cleaned[: MAX_IDLE_SMALL_TALK_CHARS - 1].rstrip() + "…"
    return html.escape(cleaned)


def is_idle_ai_reply_too_generic(reply_html: str, lang: Lang) -> bool:
    """True if model output is empty or matches a static idle fallback."""
    plain = html.unescape(reply_html).strip().lower()
    if len(plain) < 8:
        return True
    for key in IDLE_FALLBACK_MESSAGE_KEYS:
        if plain == t(key, lang).strip().lower():
            return True
    return False


async def generate_idle_small_talk(
    user_message: str,
    *,
    lang: Lang,
    settings: Settings,
    turn: int = 1,
) -> str:
    """
    Generate a short idle small-talk reply using TEXT_PROVIDER (Yandex or OpenAI).
    Returns HTML-safe text for ParseMode.HTML.
    """
    provider = get_text_provider(settings)
    turn = max(1, min(int(turn), 5))
    system = small_talk_system_prompt(lang, turn)
    user = build_idle_small_talk_user_prompt(user_message, turn)
    try:
        raw = await provider.generate_greeting_text(
            system,
            user,
            timeout=_small_talk_timeout(settings),
            max_tokens=200,
            temperature=0.55,
        )
    except (YandexGPTError, OpenAITextError) as e:
        raise IdleSmallTalkError(str(e)) from e
    except Exception as e:
        logger.exception("idle_small_talk_provider_error", extra={"event": "idle_small_talk"})
        raise IdleSmallTalkError(str(e)) from e
    formatted = format_small_talk_for_telegram(raw)
    if is_idle_ai_reply_too_generic(formatted, lang):
        raise IdleSmallTalkError("generic model response")
    return formatted
