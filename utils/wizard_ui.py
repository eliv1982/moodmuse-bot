"""
Wizard inline keyboards and callback constants (no Telegram imports).
"""
from __future__ import annotations

from utils.i18n import Lang, t

IMAGE_IDEA_SURPRISE = "image_idea_surprise"
IMAGE_IDEA_CUSTOM = "image_idea_custom"

IMAGE_IDEA_CALLBACKS = frozenset(
    {
        IMAGE_IDEA_SURPRISE,
        IMAGE_IDEA_CUSTOM,
    }
)


def image_idea_button_labels(lang: Lang) -> dict[str, str]:
    return {
        IMAGE_IDEA_SURPRISE: t("btn_image_idea_surprise", lang),
        IMAGE_IDEA_CUSTOM: t("btn_image_idea_custom", lang),
    }


def image_idea_keyboard(lang: Lang) -> list[list[tuple[str, str]]]:
    """Rows of (label, callback_data) for tests and keyboard builder."""
    return [
        [
            (t("btn_image_idea_surprise", lang), IMAGE_IDEA_SURPRISE),
            (t("btn_image_idea_custom", lang), IMAGE_IDEA_CUSTOM),
        ],
    ]
