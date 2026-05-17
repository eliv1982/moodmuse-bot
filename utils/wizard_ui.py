"""
Wizard inline keyboards and callback constants (no Telegram imports).
"""
from __future__ import annotations

from utils.i18n import Lang, t

IMAGE_IDEA_SURPRISE = "image_idea_surprise"
IMAGE_IDEA_CUSTOM = "image_idea_custom"
IMAGE_IDEA_VOICE = "image_idea_voice"

IMAGE_IDEA_CALLBACKS = frozenset(
    {
        IMAGE_IDEA_SURPRISE,
        IMAGE_IDEA_CUSTOM,
        IMAGE_IDEA_VOICE,
    }
)


def image_idea_button_labels(lang: Lang) -> dict[str, str]:
    return {
        IMAGE_IDEA_SURPRISE: t("btn_image_idea_surprise", lang),
        IMAGE_IDEA_CUSTOM: t("btn_image_idea_custom", lang),
        IMAGE_IDEA_VOICE: t("btn_image_idea_voice", lang),
    }


def image_idea_keyboard(lang: Lang, *, stt_available: bool) -> list[list[tuple[str, str]]]:
    """Rows of (label, callback_data) for tests and keyboard builder."""
    rows: list[list[tuple[str, str]]] = [
        [
            (t("btn_image_idea_surprise", lang), IMAGE_IDEA_SURPRISE),
            (t("btn_image_idea_custom", lang), IMAGE_IDEA_CUSTOM),
        ],
    ]
    if stt_available:
        rows.append([(t("btn_image_idea_voice", lang), IMAGE_IDEA_VOICE)])
    return rows
