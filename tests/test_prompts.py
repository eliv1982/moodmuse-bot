"""Prompt builders."""
from utils.prompts import build_image_prompt, build_text_system_prompt, build_text_user_prompt


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
