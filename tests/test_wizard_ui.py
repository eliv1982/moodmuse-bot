"""Wizard UI keyboards and callbacks."""
from utils.wizard_ui import (
    IMAGE_IDEA_CALLBACKS,
    IMAGE_IDEA_CUSTOM,
    IMAGE_IDEA_SURPRISE,
    IMAGE_IDEA_VOICE,
    image_idea_keyboard,
)


def test_image_idea_keyboard_has_surprise_and_custom() -> None:
    rows = image_idea_keyboard("ru", stt_available=True)
    callbacks = {cb for row in rows for _, cb in row}
    assert IMAGE_IDEA_SURPRISE in callbacks
    assert IMAGE_IDEA_CUSTOM in callbacks
    assert IMAGE_IDEA_VOICE in callbacks
    assert callbacks <= IMAGE_IDEA_CALLBACKS


def test_image_idea_keyboard_hides_voice_without_stt() -> None:
    rows = image_idea_keyboard("ru", stt_available=False)
    callbacks = {cb for row in rows for _, cb in row}
    assert IMAGE_IDEA_VOICE not in callbacks
    assert IMAGE_IDEA_SURPRISE in callbacks
