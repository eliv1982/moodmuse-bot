"""
Text-model helpers for the creation flow: reading a free-form request ("my idea" mode) into brief fields
and proposing an inscription. Both use the configured text provider's plain completion; there is no new
provider layer. Neither generates an image.

The model only proposes. ``apply_extraction`` merges its answer into the brief under deterministic
guardrails: an inscription counts as the user's only if it appears verbatim in their message, "no text" only
if they said so, and an AI suggestion is stored apart until the user approves it.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from config import Settings
from services.card_render import check_inscription
from services.providers.factory import get_text_provider, text_provider_configured
from utils.brief_text import (
    asks_for_no_text,
    asks_for_ai_caption,
    asks_for_no_caption,
    collapse_spaces,
    heuristic_restrictions,
    is_verbatim,
    marked_quoted_passage,
    verbatim_span,
)
from utils.card_texts import clean_short_text
from utils.creative_brief import (
    CAPTION_AI,
    CAPTION_NONE,
    CAPTION_USER,
    CONCEPT_MAX_LEN,
    INSCRIPTION_AI,
    INSCRIPTION_NONE,
    INSCRIPTION_TEXT,
    INSCRIPTION_UNSPECIFIED,
    SHORT_FIELD_MAX_LEN,
    SOURCE_USER,
    CreativeBrief,
    creative_context,
)

logger = logging.getLogger(__name__)

EXTRACTION_MAX_TOKENS = 700
SUGGESTION_MAX_TOKENS = 80
_SOURCE_MAX_CHARS = 2000
_MIN_WORDS_FOR_RAW_CONCEPT = 6

_JSON_FENCE_RE = re.compile(r"^```[A-Za-z0-9_-]*[ \t]*\n?|\n?```\s*$")


class BriefAIError(Exception):
    """The text model could not produce a usable inscription suggestion."""


@dataclass
class Extraction:
    concept: str = ""
    occasion: str = ""
    recipient: str = ""
    mood: str = ""
    style: str = ""
    inscription_mode: str = INSCRIPTION_UNSPECIFIED
    inscription_text: str = ""
    restrictions: list[str] = field(default_factory=list)
    caption_mode: str = "unspecified"
    caption_text: str = ""
    signature: str = ""
    is_card: bool = False
    question: str = ""
    """One clarifying question from the model; used only while the concept is missing."""
    used_ai: bool = False


_EXTRACTION_SYSTEM = (
    "You read a user's free-form request for a greeting card or an image and extract a structured brief. "
    "Return ONLY one JSON object, no markdown, with exactly these keys: "
    '{"concept": string|null, "occasion": string|null, "recipient": string|null, "mood": string|null, '
    '"style": string|null, "inscription": {"mode": "text"|"ai"|"none"|"unspecified", "text": string|null}, '
    '"restrictions": [string], "caption": {"mode": "ai"|"user"|"none"|"unspecified", "text": string|null}, '
    '"signature": string|null, "greeting_card": boolean, "question": string|null}. '
    "Rules: "
    "(1) Copy the user's own words and language. Never paraphrase or translate the inscription, the "
    "restrictions, names or the message text. "
    "(2) concept is what the picture should show or what the card is for, in the user's words; do not put the "
    "inscription text or the restrictions into it. null if the request gives nothing to depict. "
    "(3) inscription.mode is \"text\" only when the user gives the exact words to print (put them in text, "
    "without the surrounding quotes); \"ai\" only when the user asks you or the AI to come up with the "
    "inscription; \"none\" only when the user explicitly says the picture needs no text; otherwise "
    "\"unspecified\". Never invent an inscription. "
    "(4) restrictions are things the user explicitly does not want or insists on, each as a short phrase in "
    "their own wording. "
    "(5) caption is a longer message under the picture: \"user\" only when the user dictates its exact text, "
    "\"ai\" when they ask for a written greeting or message, \"none\" when they say they do not want one, "
    "otherwise \"unspecified\". "
    "(6) greeting_card is true when the user asks for a greeting card, congratulation or postcard. "
    "(7) Use null, [] or \"unspecified\" for everything not stated; do not guess. "
    "(8) question: only when concept is null, one short friendly Russian question asking what to depict; "
    "otherwise null."
)


def _text_timeout(settings: Settings) -> float:
    if (settings.TEXT_PROVIDER or "openai").strip().lower() == "openai":
        return settings.OPENAI_TIMEOUT
    return settings.YANDEX_TIMEOUT


def _str(value: Any, limit: int) -> str:
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


def _loads_object(raw: str) -> Optional[dict[str, Any]]:
    text = _JSON_FENCE_RE.sub("", (raw or "").strip()).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        obj = json.loads(text[start : end + 1], strict=False)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def parse_extraction(raw: str) -> Optional[Extraction]:
    """The model's JSON as an ``Extraction``; None when the reply is not a usable JSON object."""
    obj = _loads_object(raw)
    if obj is None:
        return None
    inscription = obj.get("inscription") if isinstance(obj.get("inscription"), dict) else {}
    caption = obj.get("caption") if isinstance(obj.get("caption"), dict) else {}
    restrictions = obj.get("restrictions")
    return Extraction(
        concept=_str(obj.get("concept"), CONCEPT_MAX_LEN),
        occasion=_str(obj.get("occasion"), SHORT_FIELD_MAX_LEN),
        recipient=_str(obj.get("recipient"), SHORT_FIELD_MAX_LEN),
        mood=_str(obj.get("mood"), SHORT_FIELD_MAX_LEN),
        style=_str(obj.get("style"), SHORT_FIELD_MAX_LEN),
        inscription_mode=str(inscription.get("mode") or INSCRIPTION_UNSPECIFIED),
        # Kept as sent (line breaks included); apply_extraction checks it against the user's message.
        inscription_text=str(inscription.get("text") or "").strip(),
        restrictions=[s for s in (_str(r, 160) for r in restrictions) if s] if isinstance(restrictions, list) else [],
        caption_mode=str(caption.get("mode") or "unspecified"),
        caption_text=str(caption.get("text") or "").strip(),
        signature=_str(obj.get("signature"), SHORT_FIELD_MAX_LEN),
        is_card=bool(obj.get("greeting_card")),
        question=_str(obj.get("question"), 200),
        used_ai=True,
    )


def heuristic_extraction(text: str) -> Extraction:
    """Fallback without a model: the message is the concept; explicit signals are read from its wording."""
    source = text.strip()[:_SOURCE_MAX_CHARS]
    ex = Extraction(concept=_str(source, CONCEPT_MAX_LEN), restrictions=heuristic_restrictions(source))
    quoted = marked_quoted_passage(source)
    if quoted:
        ex.inscription_mode, ex.inscription_text = INSCRIPTION_TEXT, quoted
    return ex


async def extract_brief_fields(text: str, settings: Settings) -> Extraction:
    """One text-model call; any failure degrades to the deterministic reading of the message."""
    source = text.strip()[:_SOURCE_MAX_CHARS]
    if not text_provider_configured(settings):
        return heuristic_extraction(source)
    try:
        reply = await get_text_provider(settings).generate_greeting_text(
            _EXTRACTION_SYSTEM,
            source,
            timeout=_text_timeout(settings),
            max_tokens=EXTRACTION_MAX_TOKENS,
            temperature=0.1,
        )
    except Exception:
        logger.exception("brief_extraction_failed", extra={"event": "brief_extraction"})
        return heuristic_extraction(source)
    parsed = parse_extraction(reply)
    if parsed is None:
        logger.warning("brief_extraction_unparsable", extra={"event": "brief_extraction"})
        return heuristic_extraction(source)
    return parsed


def apply_extraction(brief: CreativeBrief, ex: Extraction, source_text: str) -> None:
    """
    Merge ``ex`` into ``brief``. Values the message does not mention are left alone, so a follow-up answer
    adds to the brief instead of resetting it.
    """
    source = source_text.strip()[:_SOURCE_MAX_CHARS]
    if source and source not in brief.source_requests:
        brief.source_requests.append(source)

    if ex.concept:
        brief.concept = ex.concept
    elif (
        not brief.concept.strip()
        and not ex.question
        and len(source.split()) >= _MIN_WORDS_FOR_RAW_CONCEPT
    ):
        brief.concept = _str(source, CONCEPT_MAX_LEN)

    if ex.occasion:
        brief.occasion = ex.occasion
    if ex.recipient:
        brief.recipient = ex.recipient
    if ex.mood:
        brief.set_mood_text(ex.mood)
    if ex.style:
        brief.set_style_text(ex.style)
    if ex.signature:
        brief.signature = ex.signature
    brief.is_card = brief.is_card or ex.is_card
    # Extracted labels are convenience only. Reject invented/reworded restrictions; the unabridged
    # source above remains authoritative even if extraction omitted or shortened every restriction.
    brief.add_restrictions([
        original for item in ex.restrictions
        if (original := verbatim_span(source, item)) is not None
    ])

    _apply_inscription(brief, ex, source)

    if asks_for_no_caption(source):
        brief.set_caption(CAPTION_NONE)
    elif ex.caption_mode == CAPTION_USER and ex.caption_text and is_verbatim(source, ex.caption_text):
        brief.set_caption(CAPTION_USER, verbatim_span(source, ex.caption_text) or "")
    elif ex.caption_mode == CAPTION_AI and asks_for_ai_caption(source):
        brief.set_caption(CAPTION_AI)


def _apply_inscription(brief: CreativeBrief, ex: Extraction, source: str) -> None:
    # Explicit user prohibitions outrank every model field, including a proposed AI mode.
    if asks_for_no_text(source):
        brief.set_no_inscription()
        return
    # Only the user's own words may be drawn: the model's copy must match their message word for word,
    # otherwise a quoted passage the message itself marks as the inscription is used instead.
    exact = marked_quoted_passage(source)
    if not exact and ex.inscription_mode == INSCRIPTION_TEXT:
        exact = verbatim_span(source, ex.inscription_text)
    if exact:
        brief.set_inscription(exact, source=SOURCE_USER)
    elif ex.inscription_mode == INSCRIPTION_AI and brief.inscription_mode != INSCRIPTION_NONE:
        brief.request_ai_inscription()


# ---- inscription suggestion ----------------------------------------------------------------


def _suggestion_system(lang: str, avoid: list[str]) -> str:
    language = "English" if lang == "en" else "Russian"
    system = (
        "You write one short inscription to be printed on a greeting card image. "
        f"Write it in {language}. Reply with the inscription only: at most 8 words (under 60 characters), "
        "no quotation marks, no emoji, no names, no explanation. It should fit the idea and the mood."
    )
    if avoid:
        system += " Do not repeat these earlier options: " + "; ".join(avoid) + "."
    return system


async def suggest_inscription(brief: CreativeBrief, settings: Settings) -> str:
    """
    One AI proposal for the inscription, cleaned for the card font. It is only a proposal: the caller keeps
    it in ``brief.inscription_suggestion`` until the user approves it.
    """
    if not text_provider_configured(settings):
        raise BriefAIError("text provider is not configured")
    user = creative_context(brief)
    if brief.occasion.strip():
        user += f" Occasion: {brief.occasion.strip()}."
    if brief.recipient.strip():
        user += f" For: {brief.recipient.strip()}."
    try:
        reply = await get_text_provider(settings).generate_greeting_text(
            _suggestion_system(brief.lang, brief.suggestions_shown),
            user,
            timeout=_text_timeout(settings),
            max_tokens=SUGGESTION_MAX_TOKENS,
            temperature=0.9,
        )
    except Exception as exc:
        raise BriefAIError("suggestion request failed") from exc
    first_line = next((ln for ln in (reply or "").splitlines() if ln.strip()), "")
    phrase = clean_short_text(collapse_spaces(first_line))
    if not phrase or not check_inscription(phrase).ok:
        raise BriefAIError("suggestion is empty or cannot be drawn")
    return phrase
