"""Prompt builders and wizard callback constants."""
from utils.prompts import (
    IMAGE_STYLE_CALLBACKS,
    IMAGE_STYLE_KEYBOARD_ORDER,
    IMAGE_STYLE_LABELS,
    TEXT_STYLE_CALLBACKS,
    TEXT_STYLE_LABELS,
    build_image_prompt,
    build_text_system_prompt,
    build_text_user_prompt,
)


def test_build_image_prompt_user_desc() -> None:
    p = build_image_prompt(
        "occasion_clients",
        "style_watercolor",
        user_description="tulips and sun",
        holiday="March 8",
        surprise_phrases={"придумай сам"},
    )
    assert "tulips" in p.lower() or "Tulips" in p
    assert "watercolor" in p.lower()
    assert "no text on image" in p.lower()


def test_build_image_prompt_surprise() -> None:
    p = build_image_prompt(
        "occasion_loved",
        "style_minimal",
        user_description="придумай сам",
        holiday="New Year",
        surprise_phrases={"придумай сам", "придумай сама"},
    )
    assert "greeting card" in p.lower()
    assert "minimal" in p.lower()


def test_text_prompts_bilingual() -> None:
    s_ru = build_text_system_prompt("occasion_colleagues", "text_warm", "ru")
    assert "коллег" in s_ru.lower()
    s_en = build_text_system_prompt("occasion_colleagues", "text_warm", "en")
    assert "colleagues" in s_en.lower()
    u_en = build_text_user_prompt("Birthday", "en")
    assert "Birthday" in u_en
    u_ru = build_text_user_prompt("День рождения", "ru")
    assert "День" in u_ru or "дн" in u_ru.lower()


def test_text_humor_in_callbacks() -> None:
    assert "text_humor" in TEXT_STYLE_CALLBACKS
    assert TEXT_STYLE_CALLBACKS == frozenset(TEXT_STYLE_LABELS.keys())


def test_image_style_keyboard_order_exactly_eight_visible() -> None:
    assert len(IMAGE_STYLE_KEYBOARD_ORDER) == 8
    assert len(set(IMAGE_STYLE_KEYBOARD_ORDER)) == 8
    for key in IMAGE_STYLE_KEYBOARD_ORDER:
        assert key in IMAGE_STYLE_CALLBACKS
        assert key in IMAGE_STYLE_LABELS


def test_fantasy_and_cyberpunk_are_distinct_styles() -> None:
    from utils.prompts import IMAGE_STYLES

    fantasy = IMAGE_STYLES["style_fantasy"].lower()
    cyber = IMAGE_STYLES["style_cyberpunk"].lower()
    assert "cinematic" in fantasy
    assert "cyberpunk" in cyber
    assert fantasy != cyber


def test_fantasy_style_photorealistic_live_action() -> None:
    from utils.prompts import IMAGE_STYLES

    fantasy = IMAGE_STYLES["style_fantasy"].lower()
    assert "this must look like a real live-action fantasy film frame" in fantasy
    assert "photorealistic" in fantasy
    assert "live-action" in fantasy
    assert "film" in fantasy


def test_fantasy_style_avoids_illustration_and_painting() -> None:
    from utils.prompts import IMAGE_STYLES

    fantasy = IMAGE_STYLES["style_fantasy"].lower()
    for phrase in (
        "not an illustration",
        "not a digital painting",
        "not an oil painting",
        "not watercolor",
        "not concept art",
        "not storybook art",
        "not matte painting",
        "not painterly fantasy poster",
        "not cartoon",
        "not anime",
        "not over-stylized",
        "not soft brush-stroke fantasy art",
    ):
        assert phrase in fantasy


def test_fantasy_style_avoids_default_dragons() -> None:
    from utils.prompts import IMAGE_STYLES

    fantasy = IMAGE_STYLES["style_fantasy"].lower()
    assert "no dragons unless" in fantasy


def test_fantasy_label_cinematic_fantasy() -> None:
    ru, en = IMAGE_STYLE_LABELS["style_fantasy"]
    assert ru.startswith("🎬")
    assert "Кино-фэнтези" in ru
    assert en.startswith("🎬")
    assert "Cinematic fantasy" in en
    assert "🐉" not in ru
    assert "🧝" not in ru


def test_regen_text_not_in_text_style_callbacks() -> None:
    assert "regen_text" not in TEXT_STYLE_CALLBACKS


def test_cyberpunk_style_prompt() -> None:
    p = build_image_prompt("occasion_loved", "style_cyberpunk", user_description="city at night")
    assert "cyberpunk" in p.lower()
    assert "neon" in p.lower()


def test_image_prompt_includes_recipient_context() -> None:
    clients = build_image_prompt("occasion_clients", "style_realistic", user_description="office")
    colleagues = build_image_prompt("occasion_colleagues", "style_realistic", user_description="team")
    loved = build_image_prompt("occasion_loved", "style_realistic", user_description="family")
    assert "professional" in clients.lower() or "clients" in clients.lower()
    assert "workplace" in colleagues.lower() or "colleagues" in colleagues.lower()
    assert "warm" in loved.lower() or "personal" in loved.lower()
