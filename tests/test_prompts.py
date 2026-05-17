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
    assert "fantasy" in fantasy or "fairy" in fantasy
    assert "cyberpunk" in cyber
    assert fantasy != cyber


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
