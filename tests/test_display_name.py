"""Display-name extraction and validation for profile/onboarding."""
from __future__ import annotations

import inspect

from handlers import profile as profile_handlers
from utils.display_name import (
    extract_display_name,
    parse_display_name_input,
    validate_display_name,
)
from utils.i18n import t


def test_extract_plain_name_ru() -> None:
    assert extract_display_name("Лена", "ru") == "Лена"


def test_extract_menya_zovut_ru() -> None:
    assert extract_display_name("Меня зовут Лена", "ru") == "Лена"


def test_extract_mozhesh_obrashchatsya_ru() -> None:
    assert extract_display_name("Можешь обращаться ко мне Лена", "ru") == "Лена"
    assert extract_display_name("Можно обращаться ко мне Лена", "ru") == "Лена"
    assert extract_display_name("Обращайся ко мне Лена", "ru") == "Лена"
    assert extract_display_name("Зови меня Лена", "ru") == "Лена"


def test_extract_two_part_name_ru() -> None:
    assert extract_display_name("Меня зовут Елена Шленскова", "ru") == "Елена Шленскова"


def test_extract_ya_lena_ru() -> None:
    assert extract_display_name("Я Лена", "ru") == "Лена"


def test_extract_en_call_me() -> None:
    assert extract_display_name("Lena", "en") == "Lena"
    assert extract_display_name("My name is Lena", "en") == "Lena"
    assert extract_display_name("Call me Lena", "en") == "Lena"
    assert extract_display_name("You can call me Lena", "en") == "Lena"


def test_parse_uses_extracted_name_in_validation() -> None:
    assert parse_display_name_input("Можешь обращаться ко мне Лена", "ru") == "Лена"


def test_reject_multiline_garbage() -> None:
    assert parse_display_name_input("line\nbreak", "ru") is None


def test_reject_url_and_jsonish() -> None:
    assert parse_display_name_input("https://example.com", "ru") is None
    assert parse_display_name_input('{"name":"Lena"}', "ru") is None


def test_reject_too_many_punctuation() -> None:
    assert validate_display_name("!!!@@@###") is None


def test_confirmation_uses_extracted_name() -> None:
    source = inspect.getsource(profile_handlers._handle_name_input)
    assert "parse_display_name_input" in source
    assert "format_profile_name_confirm_prompt" in inspect.getsource(profile_handlers._offer_name_confirm)


def test_reprompt_uses_short_prompt_not_onboarding_greeting() -> None:
    source = inspect.getsource(profile_handlers._reprompt_name)
    assert 't("profile_ask_name"' in source
    assert 't("onboarding_ask_name"' not in source


def test_onboarding_completion_mentions_profile_fields() -> None:
    ru = t("onboarding_done", "ru")
    en = t("onboarding_done", "en")
    assert "имя" in ru
    assert "язык" in ru
    assert "обращение" in ru
    assert "тон" in ru
    assert "длин" in ru
    assert "открытку" in ru
    assert "name" in en.lower()
    assert "language" in en.lower()
    assert "tone" in en.lower()
    assert "length" in en.lower()
    assert "card" in en.lower()
