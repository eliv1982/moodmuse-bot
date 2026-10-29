"""
Deterministic reading of a free-form creation request (no network, no Telegram).

The LLM extraction in ``services.brief_ai`` is a helper, not an authority: whether the user explicitly
asked for "no text", and whether an inscription is really their own words, are decided here from the
message itself. The same helpers are the fallback when the text provider is unavailable.
"""
from __future__ import annotations

import re
from typing import Optional

# «…», “…”, „…“ and straight double quotes. Single quotes are skipped: apostrophes are common in text.
_QUOTED_RE = re.compile(r"«([^«»]+)»|“([^“”]+)”|„([^„“”]+)[“”]|\"([^\"]+)\"")

# Whole-word forms only: "без текстуры" (without texture) or "без словаря" is not a request for no text.
_INSCRIPTION_WORD = r"(?:надпис(?:ь|и|ей|ью|ям|ями|ях)?|текст(?:а|у|е|ом|ы|ов)?)(?!\w)"
_ANY_TEXT_WORD = (
    r"(?:надпис(?:ь|и|ей|ью|ям|ями|ях)?|текст(?:а|у|е|ом|ы|ов)?|слов(?:а|ам|ами|ах)?|букв(?:а|ы|ам|ами|ах)?)(?!\w)"
)

# "no inscription" in the user's own words. Evaluated with quoted passages removed, so an inscription such as
# «Жизнь без слов» does not count as a request for no text.
_NO_TEXT_RE = re.compile(
    rf"без\s+(?:какой[-\s]?либо\s+|любой\s+|всякой\s+|лишней\s+)?{_ANY_TEXT_WORD}"
    r"|без\s+подпис\w*\s+на\s+(?:картинк\w*|изображени\w*|открытк\w*)"
    rf"|{_INSCRIPTION_WORD}\s+не\s+(?:нуж(?:ен|на|но|ны)|надо)(?!\w)"
    rf"|не\s+(?:нуж(?:ен|на|но|ны)|надо)(?!\w)\s+(?:никаких\s+)?{_INSCRIPTION_WORD}"
    r"|no\s+(?:text|inscription|caption|words|lettering)\b"
    r"|without\s+(?:any\s+)?(?:text|inscription|caption|words|lettering)\b",
    re.IGNORECASE,
)

# Words that introduce an inscription right before a quoted passage («надпись «…»», "text: "..."").
_INSCRIPTION_MARKER_RE = re.compile(
    r"надпис|текст|напис|напиш|подпис|слова|фраз|гласит|caption|text|says|write|reads|inscription",
    re.IGNORECASE,
)

_CAPTION_MARKER_RE = re.compile(
    r"(?:текст|сообщени\w*|подпис\w*)\s+под\s+(?:картинк\w*|изображени\w*|открытк\w*)"
    r"|(?:text|message|caption)\s+(?:under|below)\s+(?:the\s+)?(?:image|picture|card)",
    re.IGNORECASE,
)

# Heuristic restriction clauses, used only when the LLM extraction is unavailable.
_RESTRICTION_RE = re.compile(
    r"(?:\bбез\s+(?!надпис|текст|слов|букв)|\bникаких\s+|\bне\s+(?:рисуй|добавляй|используй|показывай)\s+|"
    r"\bизбегай\s+|\bнельзя\s+|\bno\s+(?!text\b|inscription\b|caption\b|words\b|lettering\b)|\bavoid\s+|\bwithout\s+(?!text\b|any\b))"
    r"[^.,;!?\n]+",
    re.IGNORECASE,
)

_MAX_RESTRICTIONS = 8


def collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def quoted_passages(text: str) -> list[str]:
    """Passages in quotes, in order, without the quote marks."""
    found: list[str] = []
    for match in _QUOTED_RE.finditer(text or ""):
        passage = next(g for g in match.groups() if g is not None).strip()
        if passage:
            found.append(passage)
    return found


def _strip_quoted(text: str) -> str:
    return _QUOTED_RE.sub(" ", text or "")


def asks_for_no_text(text: str) -> bool:
    """The user explicitly says the picture should carry no text/inscription."""
    return bool(_NO_TEXT_RE.search(_strip_quoted(text)))


def is_verbatim(source: str, candidate: str) -> bool:
    """``candidate`` appears in ``source`` word for word, letter case included (whitespace runs aside)."""
    return verbatim_span(source, candidate) is not None


def verbatim_span(source: str, candidate: str) -> Optional[str]:
    """Recover the source's exact whitespace too, even when extraction collapsed it."""
    words = (candidate or "").split()
    if not words:
        return None
    match = re.search(r"\s+".join(re.escape(word) for word in words), source)
    return match.group(0) if match else None


def asks_for_ai_caption(text: str) -> bool:
    """A free-form AI message requires an explicit writing/delegation request, not greeting context."""
    source = _strip_quoted(text)
    if asks_for_no_caption(source):
        return False
    action = r"(?:напиши|напишите|сочини|составь|придумай|сгенерируй|добавь|write|compose|generate|add)"
    message = (
        r"(?:поздравлени\w*|пожелани\w*|сообщени\w*|greeting\b|message\b|wish\w*\b|"
        r"(?:текст|подпись|caption)\s+(?:под|к|below|under|for)\b)"
    )
    delegation = r"(?:доверь\w*\s+ИИ|на\s+(?:твой|ваш)\s+вкус|на\s+усмотрение\s+ИИ|AI)"
    return bool(re.search(
        action + r"\b[^.!?\n]{0,100}?" + message
        + "|" + message + r"[^.!?\n]{0,60}?(?:" + action + "|" + delegation + ")",
        source, re.IGNORECASE,
    ))


def asks_for_no_caption(text: str) -> bool:
    """An explicit decline of the separate message, independent of image lettering."""
    message = r"(?:сообщени\w*|поздравлени\w*|пожелани\w*|message\b|greeting\b|caption\b)"
    return bool(re.search(
        r"(?:без\s+(?:дополнительного\s+|развёрнутого\s+)?|no\s+(?:additional\s+)?)" + message
        + "|" + message + r"\s+не\s+(?:нуж\w*|надо)"
        + r"|(?:do\s+not|don't|не)\s+(?:write|add|пиши|добавляй)[^.!?\n]{0,60}?" + message,
        _strip_quoted(text), re.IGNORECASE,
    ))


def marked_quoted_passage(text: str) -> Optional[str]:
    """
    The one quoted passage introduced by an inscription marker ("надпись «…»"), or None when there is no
    such passage or it is ambiguous.
    """
    hits: list[str] = []
    for match in _QUOTED_RE.finditer(text or ""):
        passage = next(g for g in match.groups() if g is not None).strip()
        before = text[max(0, match.start() - 40) : match.start()]
        if passage and _INSCRIPTION_MARKER_RE.search(before) and not _CAPTION_MARKER_RE.search(before):
            hits.append(passage)
    return hits[0] if len(hits) == 1 else None


def heuristic_restrictions(text: str) -> list[str]:
    """Clauses like "без людей" / "не рисуй собак", verbatim. Fallback only; the LLM does this normally."""
    seen: set[str] = set()
    found: list[str] = []
    for match in _RESTRICTION_RE.finditer(_strip_quoted(text)):
        clause = collapse_spaces(match.group(0))
        key = clause.casefold()
        if len(clause) >= 4 and key not in seen:
            seen.add(key)
            found.append(clause)
    return found[:_MAX_RESTRICTIONS]
