"""Translate helpers for image prompts."""
from utils.translate import translate_holiday_to_english, translate_prompt_to_english


def test_prompt_ru_to_tokens() -> None:
    out = translate_prompt_to_english("тюльпаны и небо", "ru")
    assert "tulip" in out.lower()
    assert "sky" in out.lower()


def test_prompt_en_passthrough() -> None:
    out = translate_prompt_to_english("Red balloons", "en")
    assert "Red balloons" == out


def test_holiday_ru() -> None:
    assert "March" in (translate_holiday_to_english("8 марта", "ru") or "")


def test_holiday_en() -> None:
    h = translate_holiday_to_english("women's day party", "en")
    assert h and "March" in h
