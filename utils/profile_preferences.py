"""
Profile settings: name, wording preference, address, tone, length.
"""
from __future__ import annotations

from utils.display_name import parse_display_name_input, validate_display_name

ADDRESS_INFORMAL = "informal"
ADDRESS_FORMAL = "formal"

TONE_WARM = "warm"
TONE_NEUTRAL = "neutral"
TONE_PLAYFUL = "playful"
TONE_TENDER = "tender"
TONE_ELEGANT = "elegant"
TONE_INSPIRING = "inspiring"
TONE_IRONIC = "ironic"

LENGTH_SHORT = "short"
LENGTH_BALANCED = "balanced"
LENGTH_DETAILED = "detailed"
LENGTH_EXPANDED = "expanded"

PREF_FIELD_NAME = "display_name"
PREF_FIELD_GENDER = "gender_or_wording"  # legacy DB key; ignored in MoodMuse UX
PREF_FIELD_ADDRESS = "address_style"
PREF_FIELD_TONE = "text_tone"
PREF_FIELD_LENGTH = "text_length"

VALID_ADDRESS_STYLE = frozenset({ADDRESS_INFORMAL, ADDRESS_FORMAL})
VALID_TEXT_TONE = frozenset(
    {
        TONE_WARM,
        TONE_NEUTRAL,
        TONE_PLAYFUL,
        TONE_TENDER,
        TONE_ELEGANT,
        TONE_INSPIRING,
        TONE_IRONIC,
    }
)
VALID_TEXT_LENGTH = frozenset(
    {LENGTH_SHORT, LENGTH_BALANCED, LENGTH_DETAILED, LENGTH_EXPANDED}
)

DEFAULT_PROFILE_PREFERENCES: dict[str, str] = {
    PREF_FIELD_NAME: "",
    PREF_FIELD_GENDER: "",
    PREF_FIELD_ADDRESS: ADDRESS_INFORMAL,
    PREF_FIELD_TONE: TONE_WARM,
    PREF_FIELD_LENGTH: LENGTH_BALANCED,
}

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from utils.i18n import Lang


@dataclass(frozen=True)
class ProfilePreferences:
    display_name: str
    gender_or_wording: str
    address_style: str
    text_tone: str
    text_length: str

    def to_dict(self) -> dict[str, str]:
        return {
            PREF_FIELD_NAME: self.display_name,
            PREF_FIELD_GENDER: self.gender_or_wording,
            PREF_FIELD_ADDRESS: self.address_style,
            PREF_FIELD_TONE: self.text_tone,
            PREF_FIELD_LENGTH: self.text_length,
        }

    def has_saved_display_name(self) -> bool:
        return bool(self.display_name.strip())


def default_profile_preferences() -> ProfilePreferences:
    return ProfilePreferences(
        display_name=DEFAULT_PROFILE_PREFERENCES[PREF_FIELD_NAME],
        gender_or_wording=DEFAULT_PROFILE_PREFERENCES[PREF_FIELD_GENDER],
        address_style=DEFAULT_PROFILE_PREFERENCES[PREF_FIELD_ADDRESS],
        text_tone=DEFAULT_PROFILE_PREFERENCES[PREF_FIELD_TONE],
        text_length=DEFAULT_PROFILE_PREFERENCES[PREF_FIELD_LENGTH],
    )


def _coerce_field(
    raw: Mapping[str, Any],
    key: str,
    valid: frozenset[str],
    default: str,
) -> str:
    value = raw.get(key, default)
    if not isinstance(value, str):
        return default
    value = value.strip()
    return value if value in valid else default


def _coerce_name(raw: Mapping[str, Any]) -> str:
    value = raw.get(PREF_FIELD_NAME, "")
    if not isinstance(value, str):
        return ""
    name = value.strip()
    if not name:
        return ""
    validated = validate_display_name(name)
    return validated or ""


def _coerce_gender(_raw: Mapping[str, Any]) -> str:
    """Legacy field in stored JSON; not used by MoodMuse."""
    return ""


def normalize_profile_preferences(raw: object | None) -> ProfilePreferences:
    """Parse JSON/dict; invalid or unknown keys fall back to defaults."""
    if not isinstance(raw, Mapping):
        return default_profile_preferences()
    return ProfilePreferences(
        display_name=_coerce_name(raw),
        gender_or_wording=_coerce_gender(raw),
        address_style=_coerce_field(
            raw, PREF_FIELD_ADDRESS, VALID_ADDRESS_STYLE, ADDRESS_INFORMAL
        ),
        text_tone=_coerce_field(raw, PREF_FIELD_TONE, VALID_TEXT_TONE, TONE_WARM),
        text_length=_coerce_field(
            raw, PREF_FIELD_LENGTH, VALID_TEXT_LENGTH, LENGTH_BALANCED
        ),
    )


def merge_profile_preference(
    prefs: ProfilePreferences,
    *,
    display_name: Optional[str] = None,
    address_style: Optional[str] = None,
    text_tone: Optional[str] = None,
    text_length: Optional[str] = None,
) -> ProfilePreferences:
    """Return new prefs with validated updates; invalid values are ignored."""
    data = prefs.to_dict()
    if display_name is not None:
        validated = parse_display_name_input(display_name, "ru")
        if not validated:
            validated = parse_display_name_input(display_name, "en")
        if validated:
            data[PREF_FIELD_NAME] = validated
    if address_style is not None and address_style in VALID_ADDRESS_STYLE:
        data[PREF_FIELD_ADDRESS] = address_style
    if text_tone is not None and text_tone in VALID_TEXT_TONE:
        data[PREF_FIELD_TONE] = text_tone
    if text_length is not None and text_length in VALID_TEXT_LENGTH:
        data[PREF_FIELD_LENGTH] = text_length
    return normalize_profile_preferences(data)


def resolve_display_name(
    prefs: ProfilePreferences,
    telegram_first_name: Optional[str] = None,
) -> str:
    if prefs.display_name:
        return prefs.display_name
    if telegram_first_name and telegram_first_name.strip():
        return telegram_first_name.strip()
    return ""


def profile_preferences_prompt_suffix(
    prefs: ProfilePreferences,
    lang: Lang,
    *,
    include_display_name: bool = False,
    telegram_first_name: Optional[str] = None,
) -> str:
    """Soft instructions appended to the text system prompt (does not override audience/style rules)."""
    name = resolve_display_name(prefs, telegram_first_name) if include_display_name else ""
    if lang == "en":
        parts: list[str] = []
        if name:
            parts.append(f"Preferred name: {name}.")
        address = {
            ADDRESS_INFORMAL: "Prefer casual address.",
            ADDRESS_FORMAL: "Prefer polite formal address.",
        }[prefs.address_style]
        tone = {
            TONE_WARM: "Tone: warm, not overly sweet.",
            TONE_NEUTRAL: "Tone: calm and neutral.",
            TONE_PLAYFUL: "Tone: light, gently playful.",
            TONE_TENDER: "Tone: tender and gentle.",
            TONE_ELEGANT: "Tone: elegant and refined.",
            TONE_INSPIRING: "Tone: uplifting and inspiring.",
            TONE_IRONIC: "Tone: lightly ironic; no harsh sarcasm, mockery, or passive aggression.",
        }[prefs.text_tone]
        length = {
            LENGTH_SHORT: "Keep the caption relatively short.",
            LENGTH_BALANCED: "Medium length is fine.",
            LENGTH_DETAILED: "The caption may be slightly more detailed.",
            LENGTH_EXPANDED: "The caption may be a bit more expanded.",
        }[prefs.text_length]
        parts.extend([address, tone, length])
        body = " ".join(parts)
        return (
            "Optional user preferences (only when consistent with audience and style above): "
            f"{body}"
        )

    parts_ru: list[str] = []
    if name:
        parts_ru.append(f"Предпочитаемое имя: {name}.")
    address_ru = {
        ADDRESS_INFORMAL: "По возможности на ты.",
        ADDRESS_FORMAL: "По возможности на вы.",
    }[prefs.address_style]
    tone_ru = {
        TONE_WARM: "Тон тёплый, без чрезмерной сладости.",
        TONE_NEUTRAL: "Тон спокойный и нейтральный.",
        TONE_PLAYFUL: "Тон лёгкий, с мягкой игривостью.",
        TONE_TENDER: "Тон нежный и бережный.",
        TONE_ELEGANT: "Тон элегантный и сдержанный.",
        TONE_INSPIRING: "Тон вдохновляющий и поддерживающий.",
        TONE_IRONIC: "Тон с лёгкой иронией, без злой насмешки и без колкости.",
    }[prefs.text_tone]
    length_ru = {
        LENGTH_SHORT: "Ответ короче.",
        LENGTH_BALANCED: "Ответ средней длины.",
        LENGTH_DETAILED: "Ответ чуть подробнее.",
        LENGTH_EXPANDED: "Ответ может быть развёрнутее.",
    }[prefs.text_length]
    parts_ru.extend([address_ru, tone_ru, length_ru])
    body_ru = " ".join(parts_ru)
    return (
        "Дополнительные пожелания (только если не противоречат аудитории и стилю выше): "
        f"{body_ru}"
    )


# Callback namespace (Telegram limit: 64 bytes)
CB_PROFILE_MAIN = "profile:main"
CB_PROFILE_HOME = "profile:home"
CB_PROFILE_BACK = "profile:back"
CB_PROFILE_NAME = "profile:name"
CB_PROFILE_NAME_CANCEL = "profile:name:cancel"
CB_PROFILE_LANG = "profile:lang"
CB_PROFILE_ADDRESS = "profile:address"
CB_PROFILE_TONE = "profile:tone"
CB_PROFILE_LENGTH = "profile:length"
CB_PROFILE_DEV_RESET = "profile:dev_reset"

PROFILE_MENU_CALLBACKS = frozenset(
    {
        CB_PROFILE_MAIN,
        CB_PROFILE_HOME,
        CB_PROFILE_BACK,
        CB_PROFILE_NAME,
        CB_PROFILE_NAME_CANCEL,
        CB_PROFILE_LANG,
        CB_PROFILE_ADDRESS,
        CB_PROFILE_TONE,
        CB_PROFILE_LENGTH,
        CB_PROFILE_DEV_RESET,
    }
)


def is_profile_callback(data: str) -> bool:
    return data.startswith("profile:")


def parse_profile_set_callback(data: str) -> Optional[tuple[str, str]]:
    """profile:set:<field>:<value> -> (field, value) or None."""
    if not data.startswith("profile:set:"):
        return None
    rest = data[len("profile:set:") :]
    parts = rest.split(":", 1)
    if len(parts) != 2:
        return None
    return parts[0], parts[1]
