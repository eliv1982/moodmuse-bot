"""
Lightweight validation for wizard free-text fields (no external API calls).
"""
from __future__ import annotations

import re

from utils.i18n import Lang, surprise_me_phrases

# Latin typed while Russian keyboard layout was expected (physical key → Cyrillic).
_EN_TO_RU_LAYOUT = str.maketrans(
    "qwertyuiop[]asdfghjkl;'zxcvbnm,./"
    "QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>?",
    "йцукенгшщзхъфывапролджэячсмитьбю."
    "ЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ,",
)

_CYRILLIC_VOWELS = set("аеёиоуыэюяAEIOUYАЕЁИОУЫЭЮЯ")
_LATIN_VOWELS = set("aeiouyAEIOUY")

# Short English tokens often used intentionally in Russian prompts.
_EN_IMAGE_TERMS = frozenset(
    {
        "ai",
        "anime",
        "art",
        "cat",
        "cyberpunk",
        "dog",
        "fantasy",
        "flower",
        "flowers",
        "love",
        "moon",
        "neon",
        "retro",
        "sun",
        "sunset",
        "winter",
        "spring",
        "summer",
        "autumn",
        "fall",
        "space",
        "city",
        "card",
        "cute",
        "cozy",
    }
)

_VALID_HOLIDAY_PHRASES = frozenset(
    {
        "просто так",
        "без повода",
        "для хорошего настроения",
        "хорошее настроение",
        "just because",
        "no occasion",
        "for a good mood",
        "good mood",
    }
)

_WORD_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9]+")
_NORMALIZE_RE = re.compile(r"[^\w\s]+", re.UNICODE)

_RU_SMALL_TALK_PHRASES = frozenset(
    {
        "привет",
        "здравствуй",
        "здравствуйте",
        "приветик",
        "ку",
        "хай",
        "помощь",
        "помоги",
        "помогите",
        "что ты умеешь",
        "что умеешь",
        "кто ты",
        "что дальше",
        "что делать",
        "как дела",
        "как жизнь",
        "как настроение",
        "как ты",
    }
)
_EN_SMALL_TALK_PHRASES = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "help",
        "what can you do",
        "what do you do",
        "who are you",
        "what next",
        "how are you",
        "how are things",
        "how is it going",
    }
)


def _normalize_small_talk(text: str) -> str:
    cleaned = _NORMALIZE_RE.sub("", (text or "").strip().lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _matches_small_talk_phrase(normalized: str, lang: Lang) -> bool:
    if not normalized:
        return False
    phrases = _EN_SMALL_TALK_PHRASES if lang == "en" else _RU_SMALL_TALK_PHRASES
    if normalized in phrases:
        return True
    return any(normalized.startswith(p + " ") or normalized == p for p in phrases if len(p) >= 4)


FIELD_HOLIDAY = "holiday"
FIELD_IMAGE = "image_description"

_RU_META_HOLIDAY = frozenset(
    {
        "что предложишь",
        "что посоветуешь",
        "как лучше",
        "не знаю",
        "помоги выбрать",
        "предложи",
        "придумай",
        "на твой вкус",
        "что написать",
        "помоги",
    }
)
_EN_META_HOLIDAY = frozenset(
    {
        "what do you suggest",
        "what would you suggest",
        "help me choose",
        "suggest something",
        "i don't know",
        "i dont know",
        "you choose",
        "what should i write",
        "help",
    }
)
_RU_META_IMAGE = frozenset(
    {
        "что предложишь",
        "что посоветуешь",
        "как лучше",
        "не знаю",
        "помоги выбрать",
        "предложи",
        "придумай",
        "придумай сам",
        "придумай сама",
        "на твой вкус",
        "сам",
        "сама",
        "помоги",
    }
)
_EN_META_IMAGE = frozenset(
    {
        "what do you suggest",
        "what would you suggest",
        "help me choose",
        "suggest something",
        "i don't know",
        "i dont know",
        "you choose",
        "surprise me",
        "help",
    }
)


def _matches_meta_phrase(normalized: str, phrases: frozenset[str]) -> bool:
    if not normalized:
        return False
    if normalized in phrases:
        return True
    return any(
        normalized.startswith(p + " ")
        or normalized.endswith(" " + p)
        or normalized == p
        or (len(p) >= 5 and p in normalized)
        for p in phrases
    )


def is_wizard_meta_question(text: str, field: str, lang: Lang) -> bool:
    """User asks for help/suggestions instead of providing a field value."""
    normalized = _normalize_small_talk(text)
    if field == FIELD_HOLIDAY:
        phrases = _EN_META_HOLIDAY if lang == "en" else _RU_META_HOLIDAY
    elif field == FIELD_IMAGE:
        phrases = _EN_META_IMAGE if lang == "en" else _RU_META_IMAGE
    else:
        return False
    return _matches_meta_phrase(normalized, phrases)


def is_small_talk_text(text: str, lang: Lang) -> bool:
    """Greetings / help — not valid wizard field input."""
    normalized = _normalize_small_talk(text)
    if _matches_small_talk_phrase(normalized, lang):
        return True
    if lang == "ru" and _is_latin_keyboard_gibberish(text):
        converted = _normalize_small_talk(_layout_to_cyrillic(text))
        if converted != normalized and _matches_small_talk_phrase(converted, lang):
            return True
    return False


_RU_IDLE_CHAT_FRAGMENTS = (
    "поговор",
    "поболт",
    "пообщ",
    "разгов",
    "болт",
)
_EN_IDLE_CHAT_FRAGMENTS = (
    "talk",
    "chat",
    "convers",
)


def is_idle_chat_intent(text: str, lang: Lang) -> bool:
    """Casual chat invitations at the home menu (not wizard field input)."""
    normalized = _normalize_small_talk(text)
    if len(normalized) < 4:
        return False
    frags = _EN_IDLE_CHAT_FRAGMENTS if lang == "en" else _RU_IDLE_CHAT_FRAGMENTS
    return any(frag in normalized for frag in frags)


def _letters(text: str) -> list[str]:
    return [c for c in text if c.isalpha()]


def _cyrillic_ratio(text: str) -> float:
    letters = _letters(text)
    if not letters:
        return 0.0
    cyr = sum(1 for c in letters if "\u0400" <= c <= "\u04FF")
    return cyr / len(letters)


def _latin_vowel_ratio(text: str) -> float:
    latin = [c for c in text if c.isascii() and c.isalpha()]
    if not latin:
        return 0.0
    return sum(1 for c in latin if c in _LATIN_VOWELS) / len(latin)


def _has_cyrillic_vowel(text: str) -> bool:
    return any(c in _CYRILLIC_VOWELS for c in text)


def _layout_to_cyrillic(text: str) -> str:
    return text.translate(_EN_TO_RU_LAYOUT)


def _is_surprise_phrase(text: str, lang: Lang) -> bool:
    low = text.strip().lower()
    return low in surprise_me_phrases(lang)


def _latin_words(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text) if w.isascii()]


def _looks_like_intentional_english(text: str) -> bool:
    words = _latin_words(text)
    if not words:
        return False
    if all(w in _EN_IMAGE_TERMS for w in words):
        return True
    if len(words) == 1 and len(words[0]) >= 4 and _latin_vowel_ratio(words[0]) >= 0.2:
        return words[0] in _EN_IMAGE_TERMS or words[0].endswith("punk")
    if len(words) >= 2:
        return all(len(w) >= 2 and _latin_vowel_ratio(w) >= 0.15 for w in words)
    return False


def _is_latin_keyboard_gibberish(text: str) -> bool:
    """Russian UI: Latin that maps to Cyrillic via layout swap (wrong keyboard)."""
    letters = _letters(text)
    if not letters:
        return True
    latin = [c for c in letters if c.isascii()]
    if len(latin) / len(letters) < 0.7:
        return False
    converted = _layout_to_cyrillic(text)
    if _cyrillic_ratio(converted) >= 0.55 and _has_cyrillic_vowel(converted):
        return True
    if len(text.strip()) < 12 and _latin_vowel_ratio(text) < 0.12:
        return True
    words = _latin_words(text)
    if words and all(len(w) <= 4 for w in words) and _latin_vowel_ratio(text) < 0.15:
        return True
    return False


def _is_cyrillic_garbage(text: str) -> bool:
    letters = _letters(text)
    if len(letters) < 3:
        return True
    if not _has_cyrillic_vowel(text):
        return True
    return False


def validate_image_description(text: str, lang: Lang) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    if _is_surprise_phrase(raw, lang):
        return True

    if lang == "en":
        if len(raw) < 2:
            return False
        if _cyrillic_ratio(raw) > 0.5:
            return not _is_cyrillic_garbage(raw)
        return not _is_latin_keyboard_gibberish(raw) or _looks_like_intentional_english(raw)

    # Russian UI
    if _cyrillic_ratio(raw) >= 0.25:
        return not _is_cyrillic_garbage(raw)

    if _looks_like_intentional_english(raw):
        return True

    if _is_latin_keyboard_gibberish(raw):
        return False

    if len(raw) < 4:
        return False

    return _latin_vowel_ratio(raw) >= 0.18


def validate_holiday(text: str, lang: Lang) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    low = raw.lower()
    if low in _VALID_HOLIDAY_PHRASES:
        return True
    for phrase in _VALID_HOLIDAY_PHRASES:
        if phrase in low and len(low) <= len(phrase) + 4:
            return True

    if lang == "en":
        if len(raw) < 2:
            return False
        return not _is_latin_keyboard_gibberish(raw) or _looks_like_intentional_english(raw)

    if _cyrillic_ratio(raw) >= 0.25:
        return len(raw) >= 2 and not _is_cyrillic_garbage(raw)

    if _looks_like_intentional_english(raw):
        return True

    if _is_latin_keyboard_gibberish(raw):
        return False

    return len(raw) >= 3 and _latin_vowel_ratio(raw) >= 0.15
