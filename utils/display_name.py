"""
Display-name extraction and validation for profile/onboarding.
"""
from __future__ import annotations

import re
from typing import Optional

from utils.i18n import Lang

_DISPLAY_NAME_MAX_LEN = 40
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
_JSONISH_RE = re.compile(r"[\{\}\[\]]|\"[\w]+\":")
_ALLOWED_NAME_RE = re.compile(r"^[\w\s\-']+$", re.UNICODE)

_RU_NAME_PREFIXES: tuple[str, ...] = (
    "можешь обращаться ко мне",
    "можно обращаться ко мне",
    "можешь называть меня",
    "можно называть меня",
    "обращайся ко мне",
    "обращайтесь ко мне",
    "зови меня",
    "называй меня",
    "меня зовут",
    "моё имя",
    "мое имя",
    "я",
)

_EN_NAME_PREFIXES: tuple[str, ...] = (
    "you can call me",
    "you can address me as",
    "please call me",
    "call me",
    "my name is",
    "my name's",
    "i am",
    "i'm",
    "it's",
    "this is",
    "name is",
)


def _normalize_raw(raw: str) -> str:
    return re.sub(r"\s+", " ", (raw or "").strip())


def _strip_prefixes(text: str, prefixes: tuple[str, ...]) -> str:
    current = text
    for _ in range(4):
        changed = False
        for prefix in sorted(prefixes, key=len, reverse=True):
            pattern = rf"(?i:{re.escape(prefix)})\s*[,:\-]?\s*"
            match = re.match(pattern, current)
            if match:
                current = current[match.end() :].strip()
                changed = True
                break
        if not changed:
            break
    return current.strip(".,!?;: \"'")


def extract_display_name(raw: str, lang: Lang) -> str:
    """Extract a likely display name from free text or STT (deterministic, no LLM)."""
    text = _normalize_raw(raw)
    if not text:
        return ""
    primary = _RU_NAME_PREFIXES if lang == "ru" else _EN_NAME_PREFIXES
    secondary = _EN_NAME_PREFIXES if lang == "ru" else _RU_NAME_PREFIXES
    extracted = _strip_prefixes(text, primary)
    if extracted == text:
        extracted = _strip_prefixes(text, secondary)
    return _normalize_raw(extracted)


def validate_display_name(raw: str) -> Optional[str]:
    if "\n" in (raw or "") or "\r" in (raw or ""):
        return None
    name = _normalize_raw(raw)
    if not name or len(name) > _DISPLAY_NAME_MAX_LEN:
        return None
    if _CONTROL_CHARS_RE.search(name):
        return None
    if _URL_RE.search(name) or _JSONISH_RE.search(name):
        return None
    if not _ALLOWED_NAME_RE.match(name):
        return None
    letters = sum(1 for c in name if c.isalpha())
    if letters == 0:
        return None
    punct = sum(
        1 for c in name if not c.isalnum() and not c.isspace() and c not in "-'"
    )
    if punct > 2:
        return None
    return name


def parse_display_name_input(raw: str, lang: Lang) -> Optional[str]:
    """Extract then validate; returns normalized display name or None."""
    if "\n" in (raw or "") or "\r" in (raw or ""):
        return None
    extracted = extract_display_name(raw, lang)
    if not extracted:
        return None
    return validate_display_name(extracted)
