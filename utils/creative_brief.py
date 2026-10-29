"""
The structured creative brief shared by both creation modes ("choose from options" and "my idea").

A brief is plain data plus a few rules, with no Telegram or network code: both modes fill it in, the
confirmation screen shows it, and ``services.card_generation.run_brief_generation`` consumes it.

Two rules shape the model:

* The concept is the only required value. Mood, style, occasion, recipient, restrictions, the extended
  message and the signature may be set, delegated to the AI, or left out.
* The inscription (the text drawn on the image) has four distinct states. ``unspecified`` means the user
  has not said anything about it; it is never filled in on their behalf. ``none`` is an explicit
  "no text". ``text`` is a phrase that is drawn exactly as stored, whether the user wrote it or approved
  an AI suggestion (``inscription_source`` tells which). ``ai`` is a pending request for a suggestion and
  can never reach generation: a suggestion becomes ``text`` only when the user approves it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from services.card_render import InscriptionCheck, check_inscription

INSCRIPTION_UNSPECIFIED = "unspecified"
INSCRIPTION_TEXT = "text"
INSCRIPTION_NONE = "none"
INSCRIPTION_AI = "ai"
INSCRIPTION_MODES = frozenset({INSCRIPTION_UNSPECIFIED, INSCRIPTION_TEXT, INSCRIPTION_NONE, INSCRIPTION_AI})

SOURCE_USER = "user"
SOURCE_AI_APPROVED = "ai_approved"
INSCRIPTION_SOURCES = frozenset({"", SOURCE_USER, SOURCE_AI_APPROVED})

CAPTION_UNSPECIFIED = "unspecified"
CAPTION_NONE = "none"
CAPTION_AI = "ai"
CAPTION_USER = "user"
CAPTION_MODES = frozenset({CAPTION_UNSPECIFIED, CAPTION_NONE, CAPTION_AI, CAPTION_USER})

FLOW_GUIDED = "guided"
FLOW_FREE = "free"

CONCEPT_MAX_LEN = 400
SHORT_FIELD_MAX_LEN = 80
RESTRICTION_MAX_LEN = 160
MAX_RESTRICTIONS = 8
MAX_AI_SUGGESTIONS = 5


@dataclass(frozen=True)
class MoodPreset:
    key: str
    label: str
    """Russian button label."""
    prompt: str
    """English wording for the image prompt."""
    text_style: str
    """Key of ``utils.prompts.TEXT_STYLES`` used for the expanded message."""


MOOD_PRESETS: tuple[MoodPreset, ...] = (
    MoodPreset("warm", "🤗 Тёплое, душевное", "warm, heartfelt", "text_warm"),
    MoodPreset("festive", "🎉 Праздничное", "festive, joyful, celebratory", "text_emotional"),
    MoodPreset("cozy", "🕯 Уютное", "cozy, calm, intimate", "text_warm"),
    MoodPreset("playful", "😄 Весёлое, с юмором", "playful, humorous, lighthearted", "text_humor"),
    MoodPreset("tender", "💖 Нежное, романтичное", "tender, romantic, gentle", "text_emotional"),
    MoodPreset("calm", "🌿 Спокойное", "serene, peaceful, calm", "text_warm"),
    MoodPreset("magic", "✨ Волшебное", "magical, dreamy, enchanting", "text_warm"),
    MoodPreset("elegant", "🏢 Сдержанное, деловое", "restrained, elegant, professional", "text_business"),
)
MOOD_BY_KEY = {m.key: m for m in MOOD_PRESETS}


@dataclass(frozen=True)
class PurposePreset:
    key: str
    label: str
    occasion: str
    concept: str


PURPOSE_PRESETS: tuple[PurposePreset, ...] = (
    PurposePreset("birthday", "🎂 День рождения", "день рождения", "Поздравительная открытка с днём рождения"),
    PurposePreset("newyear", "🎄 Новый год", "Новый год", "Новогодняя открытка"),
    PurposePreset("march8", "🌸 8 Марта", "8 Марта", "Открытка к 8 Марта"),
    PurposePreset("thanks", "🙏 Благодарность", "благодарность", "Открытка с благодарностью"),
    PurposePreset("justbecause", "💌 Просто так", "просто так", "Тёплая открытка просто так, для хорошего настроения"),
    PurposePreset("business", "🏢 Деловое поздравление", "деловое поздравление", "Деловая поздравительная открытка"),
)
PURPOSE_BY_KEY = {p.key: p for p in PURPOSE_PRESETS}


@dataclass
class CreativeBrief:
    lang: str = "ru"
    """Language of the card's own texts (the user's saved language)."""
    flow: str = ""
    concept: str = ""
    occasion: str = ""
    recipient: str = ""
    is_card: bool = False
    """The user is making a greeting card (as opposed to a standalone picture)."""

    mood_key: str = ""
    mood_text: str = ""
    mood_ai: bool = False
    style_key: str = ""
    style_text: str = ""
    style_ai: bool = False

    inscription_mode: str = INSCRIPTION_UNSPECIFIED
    inscription_text: str = ""
    inscription_source: str = ""
    inscription_suggestion: str = ""
    """The AI proposal awaiting approval; never drawn unless approved."""
    suggestions_shown: list[str] = field(default_factory=list)

    restrictions: list[str] = field(default_factory=list)
    source_requests: list[str] = field(default_factory=list)
    """Original descriptions, retained independently of model extraction and its field limits."""
    restrictions_edited: bool = False
    """An explicit replacement/clear of restrictions supersedes those in the original descriptions."""
    caption_mode: str = CAPTION_UNSPECIFIED
    caption_text: str = ""
    signature: str = ""

    # ---- (de)serialisation ------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Optional[dict[str, Any]]) -> "CreativeBrief":
        brief = cls()
        if not isinstance(raw, dict):
            return brief
        for name in (
            "lang", "flow", "concept", "occasion", "recipient", "mood_key", "mood_text", "style_key",
            "style_text", "inscription_text", "inscription_suggestion", "caption_text", "signature",
        ):
            value = raw.get(name)
            if isinstance(value, str):
                setattr(brief, name, value)
        for name in ("is_card", "mood_ai", "style_ai", "restrictions_edited"):
            setattr(brief, name, bool(raw.get(name, False)))
        if raw.get("inscription_mode") in INSCRIPTION_MODES:
            brief.inscription_mode = raw["inscription_mode"]
        if raw.get("inscription_source") in INSCRIPTION_SOURCES:
            brief.inscription_source = raw["inscription_source"]
        if raw.get("caption_mode") in CAPTION_MODES:
            brief.caption_mode = raw["caption_mode"]
        for name in ("restrictions", "suggestions_shown", "source_requests"):
            value = raw.get(name)
            if isinstance(value, list):
                setattr(brief, name, [str(v) for v in value if isinstance(v, str) and v.strip()])
        if brief.lang not in ("ru", "en"):
            brief.lang = "ru"
        return brief

    # ---- setters that keep related fields consistent ---------------------------

    def set_mood_preset(self, key: str) -> None:
        self.mood_key, self.mood_text, self.mood_ai = key, "", False

    def set_mood_text(self, text: str) -> None:
        self.mood_key, self.mood_text, self.mood_ai = "", text.strip(), False

    def delegate_mood(self) -> None:
        self.mood_key, self.mood_text, self.mood_ai = "", "", True

    def set_style_preset(self, key: str) -> None:
        self.style_key, self.style_text, self.style_ai = key, "", False

    def set_style_text(self, text: str) -> None:
        self.style_key, self.style_text, self.style_ai = "", text.strip(), False

    def delegate_style(self) -> None:
        self.style_key, self.style_text, self.style_ai = "", "", True

    def set_inscription(self, text: str, *, source: str) -> None:
        """An exact inscription: the user's own words, or an AI suggestion the user approved."""
        self.inscription_mode = INSCRIPTION_TEXT
        self.inscription_text = normalize_inscription(text)
        self.inscription_source = source
        self.inscription_suggestion = ""

    def set_no_inscription(self) -> None:
        self.inscription_mode, self.inscription_text, self.inscription_source = INSCRIPTION_NONE, "", ""
        self.inscription_suggestion = ""

    def request_ai_inscription(self) -> None:
        self.inscription_mode, self.inscription_text, self.inscription_source = INSCRIPTION_AI, "", ""

    def clear_inscription(self) -> None:
        self.inscription_mode, self.inscription_text, self.inscription_source = (
            INSCRIPTION_UNSPECIFIED, "", "",
        )
        self.inscription_suggestion = ""

    def add_restrictions(self, items: list[str]) -> None:
        known = {" ".join(r.split()).casefold() for r in self.restrictions}
        for item in items:
            text = item.strip()[:RESTRICTION_MAX_LEN]
            key = " ".join(text.split()).casefold()
            if text and key not in known and len(self.restrictions) < MAX_RESTRICTIONS:
                self.restrictions.append(text)
                known.add(key)

    def set_caption(self, mode: str, text: str = "") -> None:
        self.caption_mode = mode
        self.caption_text = text.strip() if mode == CAPTION_USER else ""


def normalize_inscription(text: str) -> str:
    """Line endings and the edges only; the words, punctuation and line breaks stay as written."""
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


# ---- derived values -------------------------------------------------------------------------


def has_greeting_context(brief: CreativeBrief) -> bool:
    """Whether this is a greeting rather than a standalone picture."""
    return bool(
        brief.is_card
        or brief.occasion.strip()
        or brief.recipient.strip()
        or brief.signature.strip()
        or brief.caption_mode in (CAPTION_AI, CAPTION_USER)
    )


def resolve_caption_mode(brief: CreativeBrief) -> str:
    """The extended message is absent unless the user selected or delegated one."""
    if brief.caption_mode != CAPTION_UNSPECIFIED:
        return brief.caption_mode
    return CAPTION_NONE


def caption_is_default(brief: CreativeBrief) -> bool:
    return brief.caption_mode == CAPTION_UNSPECIFIED


def inscription_to_draw(brief: CreativeBrief) -> str:
    """Exactly what is drawn on the image: only an approved or user-written text, never anything else."""
    return brief.inscription_text if brief.inscription_mode == INSCRIPTION_TEXT else ""


def mood_prompt(brief: CreativeBrief) -> str:
    preset = MOOD_BY_KEY.get(brief.mood_key)
    return preset.prompt if preset else brief.mood_text.strip()


def text_style_for(brief: CreativeBrief) -> str:
    preset = MOOD_BY_KEY.get(brief.mood_key)
    return preset.text_style if preset else "text_warm"


def creative_context(brief: CreativeBrief) -> str:
    """
    Short English briefing for the expanded-message prompt: what the card is about, the user's limits and
    the inscription already on the image (which the message must not simply repeat).
    """
    parts = [f"The card is based on this idea (the requester's words): “{brief.concept.strip()}”."]
    mood = mood_prompt(brief)
    if mood:
        parts.append(f"Mood: {mood}.")
    if brief.restrictions:
        parts.append("Respect these requester restrictions: " + "; ".join(brief.restrictions) + ".")
    parts.append(authoritative_constraints(brief))
    drawn = inscription_to_draw(brief)
    if drawn:
        parts.append(
            f"The image already carries the inscription “{drawn}”: complement it, do not just repeat it."
        )
    return " ".join(parts)


def authoritative_constraints(brief: CreativeBrief) -> str:
    """Unabridged user authority, also appended *after* image-prompt refinement."""
    if brief.restrictions_edited:
        return (
            "The requester explicitly replaced all earlier restrictions. Only these current restrictions "
            "are authoritative; do not restore restrictions from earlier descriptions or summaries: "
            + repr(brief.restrictions) + "."
        )
    requests = brief.source_requests or [brief.concept]
    return (
        "Original requester descriptions follow verbatim. Every hard constraint in them is authoritative "
        "and takes precedence over any conflicting extracted summary or refined prompt. Do not omit, "
        "weaken, reinterpret or contradict those constraints. Later descriptions revise earlier ones "
        "only where the requester explicitly changes a requirement.\n<original_requests>\n"
        + "\n\n".join(requests) + "\n</original_requests>"
    )


# ---- readiness --------------------------------------------------------------------------


PROBLEM_CONCEPT_MISSING = "concept_missing"
PROBLEM_INSCRIPTION_UNAPPROVED = "inscription_unapproved"
PROBLEM_INSCRIPTION_INVALID = "inscription_invalid"
PROBLEM_CAPTION_INVALID = "caption_invalid"


@dataclass(frozen=True)
class BriefProblem:
    code: str
    detail: str = ""


def inscription_check(brief: CreativeBrief) -> InscriptionCheck:
    return check_inscription(brief.inscription_text)


def first_problem(brief: CreativeBrief, *, max_caption_len: int) -> Optional[BriefProblem]:
    """Why this brief must not be generated yet, or None when it is ready."""
    if not brief.concept.strip():
        return BriefProblem(PROBLEM_CONCEPT_MISSING)
    if brief.inscription_mode == INSCRIPTION_AI:
        return BriefProblem(PROBLEM_INSCRIPTION_UNAPPROVED)
    if brief.inscription_mode == INSCRIPTION_TEXT:
        check = inscription_check(brief)
        if not check.ok:
            return BriefProblem(PROBLEM_INSCRIPTION_INVALID, check.reason)
    if brief.caption_mode == CAPTION_USER:
        text = brief.caption_text.strip()
        if not text or len(text) > max_caption_len:
            return BriefProblem(PROBLEM_CAPTION_INVALID)
    return None


# ---- follow-up policy (Mode 2) ---------------------------------------------------------------

FOLLOW_UP_CONCEPT = "concept"
FOLLOW_UP_INSCRIPTION = "inscription"
MAX_OPTIONAL_FOLLOW_UPS = 1


def next_follow_up(brief: CreativeBrief, *, optional_asked: int) -> Optional[str]:
    """
    The one thing still worth asking, or None to go straight to confirmation.

    Only a missing concept requires collection. Optional values, including a greeting's inscription,
    remain editable on the confirmation screen without blocking a complete description.
    """
    if not brief.concept.strip():
        return FOLLOW_UP_CONCEPT
    return None
