"""Image idea step: custom wishes accepts text or voice (no separate voice button)."""
import inspect

from handlers import main
from utils.i18n import t


def test_custom_prompt_invites_text_or_voice() -> None:
    assert "голосов" in t("image_idea_custom_prompt", "ru").lower()
    assert "voice" in t("image_idea_custom_prompt", "en").lower()


def test_image_voice_handler_requires_custom_mode() -> None:
    source = inspect.getsource(main.on_image_description_voice)
    assert 'mode != "custom"' in source
    assert "image_idea_use_buttons" in source


def test_text_handler_unchanged_for_custom_mode() -> None:
    source = inspect.getsource(main.on_image_description)
    assert "validate_image_description" in source
    assert 'mode != "custom"' in source
