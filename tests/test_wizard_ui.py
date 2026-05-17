"""Wizard UI keyboards and callbacks."""
from utils.wizard_ui import (
    IMAGE_IDEA_CALLBACKS,
    IMAGE_IDEA_CUSTOM,
    IMAGE_IDEA_SURPRISE,
    image_idea_keyboard,
)


def test_image_idea_keyboard_has_only_surprise_and_custom() -> None:
    rows = image_idea_keyboard("ru")
    callbacks = {cb for row in rows for _, cb in row}
    assert callbacks == {IMAGE_IDEA_SURPRISE, IMAGE_IDEA_CUSTOM}
    assert callbacks <= IMAGE_IDEA_CALLBACKS
    assert len(rows) == 1
    assert len(rows[0]) == 2


def test_image_idea_keyboard_labels_ru() -> None:
    rows = image_idea_keyboard("ru")
    labels = [label for row in rows for label, _ in row]
    assert any("Придумай" in label for label in labels)
    assert any("Особые" in label for label in labels)
