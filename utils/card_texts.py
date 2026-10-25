"""
Splits the single text-model reply into the short phrase printed on the card image and the expanded
Telegram caption, and cleans the short phrase so the bundled font can draw it.
"""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Optional

# Hard cap on what reaches the renderer; the prompt asks for far less (under 60 characters).
SHORT_TEXT_MAX_CHARS = 100

_FENCE_RE = re.compile(r"^```[A-Za-z0-9_-]*[ \t]*\n?|\n?```\s*$")
_QUOTES = "\"'«»„“”‘’`"
# Emoji and pictographs are not in the font (they would render as empty boxes).
_DROPPED_CATEGORIES = frozenset({"So", "Sk", "Cc", "Cf", "Cs", "Co", "Cn"})
_DROPPED_CHARS = frozenset({"︎", "️", "‍"})


def _strip_fences(raw: str) -> str:
    return _FENCE_RE.sub("", raw.strip()).strip()


def _loads_object(text: str) -> Optional[dict[str, object]]:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        obj = json.loads(text[start : end + 1], strict=False)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _salvage_field(text: str, key: str) -> str:
    """Best-effort read of one string field from JSON that does not parse (e.g. cut off mid-reply)."""
    match = re.search(rf'"{key}"\s*:\s*"((?:[^"\\]|\\.)*)', text, re.DOTALL)
    if not match:
        return ""
    body = match.group(1)
    try:
        return str(json.loads(f'"{body}"', strict=False))
    except ValueError:
        return body.replace("\\n", "\n").replace('\\"', '"')


def _as_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def parse_card_texts(raw: str) -> tuple[str, str]:
    """
    Return ``(short, full)`` from the model reply.

    The reply should be ``{"short": ..., "full": ...}``. A reply that is not JSON at all (a provider that
    ignored the format) is the expanded caption as-is with no short phrase, i.e. the previous behaviour.
    """
    text = _strip_fences(raw or "")
    obj = _loads_object(text)
    if obj is not None:
        short, full = _as_text(obj.get("short")), _as_text(obj.get("full"))
    elif text.startswith("{"):
        short, full = _salvage_field(text, "short").strip(), _salvage_field(text, "full").strip()
    else:
        return "", text
    if not short and not full:
        return "", text
    return short, full or short


def clean_short_text(text: str, max_chars: int = SHORT_TEXT_MAX_CHARS) -> str:
    """One plain line without quotes, emoji or control characters, capped at ``max_chars``."""
    kept = [
        ch
        for ch in (text or "")
        if ch not in _DROPPED_CHARS and (ch.isspace() or unicodedata.category(ch) not in _DROPPED_CATEGORIES)
    ]
    line = re.sub(r"\s+", " ", "".join(kept)).strip().strip(_QUOTES).strip()
    if len(line) <= max_chars:
        return line
    cut = line[: max_chars - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:-—–") + "…"
