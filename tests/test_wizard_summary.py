"""Generation summary before card creation."""
from utils.wizard_summary import (
    build_generation_summary,
    image_idea_summary_label,
    is_auto_image_idea,
)


def test_auto_image_idea_detection() -> None:
    assert is_auto_image_idea("придумай сам", "ru")
    assert is_auto_image_idea("surprise me", "en")
    assert not is_auto_image_idea("щенок на снегу", "ru")


def test_image_idea_auto_label() -> None:
    label = image_idea_summary_label("придумай сам", "ru")
    assert "MoodMuse" in label or "придумает" in label
    assert "style_" not in label


def test_summary_hides_rejected_invalid_image_description() -> None:
    label = image_idea_summary_label("pfrf yf gj,tht;m", "ru")
    assert "pfrf" not in label.lower()
    assert "придумает MoodMuse" in label or "MoodMuse" in label


def test_generation_summary_uses_labels_not_callbacks() -> None:
    text = build_generation_summary(
        lang="ru",
        occasion="occasion_colleagues",
        image_description="придумай сам",
        holiday="8 Марта",
        image_style="style_realistic",
        text_style="text_humor",
    )
    assert "occasion_colleagues" not in text
    assert "style_realistic" not in text
    assert "text_humor" not in text
    assert "коллег" in text.lower() or "Colleagues" in text
    assert "Реалистичный" in text or "Realistic" in text
    assert "юмор" in text.lower() or "Humor" in text
    assert "придумает MoodMuse" in text or "MoodMuse" in text
    assert "8 Марта" in text
    assert "Генерирую" in text or "Creating" in text
