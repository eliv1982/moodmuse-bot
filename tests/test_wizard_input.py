"""Wizard free-text validation and small-talk detection."""
from utils.wizard_input import is_small_talk_text, validate_holiday, validate_image_description


def test_image_desc_valid_russian() -> None:
    assert validate_image_description("щенок на зимней поляне", "ru")
    assert validate_image_description("придумай сам", "ru")


def test_image_desc_surprise_phrase_en() -> None:
    assert validate_image_description("surprise me", "en")


def test_image_desc_rejects_keyboard_gibberish() -> None:
    assert not validate_image_description("pfrf yf", "ru")
    assert not validate_image_description("ghbdtn", "ru")


def test_image_desc_allows_english_terms() -> None:
    assert validate_image_description("cyberpunk", "ru")
    assert validate_image_description("cyberpunk city at night", "ru")
    assert validate_image_description("anime sunset", "ru")


def test_holiday_valid_phrases() -> None:
    assert validate_holiday("просто так", "ru")
    assert validate_holiday("just because", "en")
    assert validate_holiday("8 Марта", "ru")
    assert validate_holiday("день рождения", "ru")


def test_holiday_rejects_gibberish() -> None:
    assert not validate_holiday("pfrf", "ru")
    assert not validate_holiday("", "ru")


def test_small_talk_ru_en() -> None:
    assert is_small_talk_text("привет", "ru")
    assert is_small_talk_text("что ты умеешь", "ru")
    assert is_small_talk_text("помоги", "ru")
    assert is_small_talk_text("как дела", "ru")
    assert is_small_talk_text("ghbdtn", "ru")
    assert is_small_talk_text("hello", "en")
    assert is_small_talk_text("what can you do", "en")
    assert is_small_talk_text("how are you", "en")
    assert is_small_talk_text("help", "en")


def test_wizard_meta_holiday_ru() -> None:
    from utils.wizard_input import FIELD_HOLIDAY, is_wizard_meta_question

    assert is_wizard_meta_question("что предложишь?", FIELD_HOLIDAY, "ru")
    assert not is_wizard_meta_question("8 Марта", FIELD_HOLIDAY, "ru")


def test_gibberish_not_small_talk() -> None:
    assert not is_small_talk_text("pfrf yf", "ru")
    assert not is_small_talk_text("горы", "ru")
    assert not is_small_talk_text("отпуск", "ru")


def test_keyboard_garbage_not_valid_image_description() -> None:
    assert not validate_image_description("bfsslf;s;nlvkn f.smf;v", "ru")
    assert not validate_image_description("pfrf yf gj,tht;m", "ru")
